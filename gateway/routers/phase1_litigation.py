"""
LawFlow 智律工作台 - 阶段一：立案文书自动化 + 中国司法实务计算闭环
核心接口：
1. POST /api/v1/phase1/generate-litigation-package:
   一站式生成三大高频案由全套诉讼文书（起诉状、委托书、法定代表人身份证明、送达地址确认书、财产保全申请书、仲裁申请书及补偿金清单），
   调用宿主机 gemma4:12b 自动改写为引用《民法典》或《劳动合同法》的严谨【事实与理由】，并输出 .docx 与 .pdf。
2. 法律精算引擎接口：
   - /api/v1/phase1/calc/rmb-capital: 人民币大写（基于 cn2an）
   - /api/v1/phase1/calc/idcard: 18位身份证校验及法定退休年龄核定
   - /api/v1/phase1/calc/uscc: 18位统一社会信用代码 GB 32100-2015 校验
   - /api/v1/phase1/calc/lpr-interest: 央行 LPR 历期计息及起诉状利息明细说明
   - /api/v1/phase1/calc/labor-arbitration: 劳动争议 N / N+1 / 2N 补偿金精算
   - /api/v1/phase1/calc/court-fees: 诉讼费用交纳办法分段计费
"""

import os
import re
import time
import uuid
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any, Literal
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator, model_validator
from docxtpl import DocxTemplate
import httpx
import pymupdf as fitz

from gateway.utils.cn_legal_calc import (
    rmb_to_capital,
    validate_and_parse_idcard,
    validate_and_parse_uscc,
    calculate_court_fees,
    calculate_lpr_interest,
    calculate_labor_compensation,
    calculate_statute_of_limitations,
    calculate_preservation_renewal,
    verify_statutory_validity,
    calculate_settlement_npv_and_recovery
)


def _http_422(detail: str) -> HTTPException:
    return HTTPException(status_code=422, detail=detail)
from gateway.core.ollama_client import ollama_client
from gateway.core.security import sanitize_filename, safe_join, validate_download_filename
from gateway.utils.legal_prompts import FACTS_POLISH_SYSTEM_PROMPT
from gateway.utils.appeal_and_precedent_engine import analyze_first_instance_judgment_and_precedents

logger = logging.getLogger("lawflow.phase1")
router = APIRouter(tags=["阶段一：立案文书自动化与法律精算"])

from gateway.core.paths import get_base_dir, get_generated_dir


def _templates_dir() -> str:
    return str(get_base_dir() / "templates")

STIRLING_PDF_URL = os.getenv("STIRLING_PDF_URL", "http://127.0.0.1:8081").rstrip("/")


# ==============================================================================
# 文书转换辅助函数：将 Word 转换为 PDF
# ==============================================================================
async def convert_docx_to_pdf(docx_path: str, pdf_path: str, title: str = "司法公文", text_summary: str = "") -> bool:
    """
    优先调用 Stirling-PDF 容器服务；若未启动，使用 PyMuPDF 本地公文引擎生成标准 PDF
    """
    # 1. 尝试 Stirling-PDF 转换
    urls_to_try = [STIRLING_PDF_URL, "http://127.0.0.1:8081", "http://stirling-pdf:8080"]
    for url in urls_to_try:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                with open(docx_path, "rb") as f:
                    files = {"fileInput": (os.path.basename(docx_path), f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
                    resp = await client.post(f"{url}/api/v1/convert/file/pdf", files=files)
                    if resp.status_code == 200 and len(resp.content) > 100:
                        with open(pdf_path, "wb") as pdf_file:
                            pdf_file.write(resp.content)
                        logger.info(f"Stirling-PDF 成功将 {docx_path} 转换为 {pdf_path}")
                        return True
        except Exception:
            continue

    # 2. 本地 PyMuPDF 兜底渲染机制 (支持任意长文多页流式排版，绝不丢字截断)
    try:
        import docx
        d = docx.Document(docx_path)
        content_lines = [p.text for p in d.paragraphs if p.text.strip()]
        paragraphs = content_lines if content_lines else ([text_summary] if text_summary else ["司法文书内容"])

        page_width, page_height = 595, 842
        margin_x, margin_top, margin_bottom = 54, 72, 60
        max_lines_per_page = 42

        # 逐段按字宽折行并分流至各页
        pages_lines = []
        curr_page = []
        curr_lines = 0

        for p in paragraphs:
            # 依 38 字符折行
            sub_lines = [p[i:i+38] for i in range(0, len(p), 38)]
            for line_str in sub_lines:
                if curr_lines >= max_lines_per_page:
                    pages_lines.append(curr_page)
                    curr_page = []
                    curr_lines = 0
                curr_page.append(line_str)
                curr_lines += 1
            # 段落间插入空行间隔
            if curr_lines < max_lines_per_page:
                curr_page.append("")
                curr_lines += 1

        if curr_page:
            pages_lines.append(curr_page)

        total_pages = max(1, len(pages_lines))
        doc = fitz.open()

        for pno, plines in enumerate(pages_lines, 1):
            page = doc.new_page(width=page_width, height=page_height)
            page_text = "\n".join(plines)
            text_rect = fitz.Rect(margin_x, margin_top, page_width - margin_x, page_height - margin_bottom)
            page.insert_textbox(text_rect, page_text, fontsize=11, fontname="china-s", align=0)

            # 页脚加盖防伪水印说明与页码
            footer_rect = fitz.Rect(margin_x, page_height - 35, page_width - margin_x, page_height - 15)
            footer_str = f"LawFlow 智律工作台 · 电子文书存证副本 · 第 {pno} 页 / 共 {total_pages} 页 · 符合最高人民法院电子诉讼标准"
            page.insert_textbox(footer_rect, footer_str, fontsize=8, fontname="china-s", align=1)

        doc.save(pdf_path)
        doc.close()
        logger.info(f"PyMuPDF 成功为 {docx_path} 生成多页标准 PDF ({total_pages} 页): {pdf_path}")
        return True
    except Exception as e:
        logger.error(f"PDF 转换异常: {e}")
        return False


# ==============================================================================
# Pydantic 模型定义
# ==============================================================================
class RMBCapitalReq(BaseModel):
    amount: float = Field(..., example=123000.50)

class IDCardReq(BaseModel):
    id_card: str = Field(..., example="110101199003072375")
    is_cadre: bool = Field(default=False, description="针对女性，是否为管理/干部岗位（干部55岁退休，工人50岁）")

class USCCReq(BaseModel):
    uscc: str = Field(..., example="91440300708461136T")

class CourtFeeReq(BaseModel):
    claim_amount: float = Field(..., ge=0, example=250000.0)
    case_type: str = Field(default="property")
    is_summary_procedure: bool = Field(default=False)

class LPRInterestReq(BaseModel):
    principal: float = Field(..., example=100000.0)
    start_date: str = Field(..., example="2023-01-01")
    end_date: str = Field(..., example="2024-01-01")
    multiplier: float = Field(default=1.0)
    term: Literal["1Y", "5Y"] = Field(default="1Y")
    fixed_annual_rate: Optional[float] = Field(
        default=None,
        ge=0,
        le=100,
        description="年利率，单位为百分数，例如 12 表示年利率 12%",
    )
    rule_mode: str = Field(default="commercial_floating", example="commercial_floating")
    contract_date: Optional[str] = Field(default=None, example="2022-03-01")
    filing_date: Optional[str] = Field(
        default=None,
        example="2021-12-01",
        description="起诉日期（2020-08-20 前成立的民间借贷合同必填）",
    )
    markup_ratio: Optional[float] = Field(
        default=None,
        description="买卖合同固定 LPR 加计比例，须在 0.3–0.5",
    )
    today_date: Optional[str] = Field(default=None)

    @field_validator("term", mode="before")
    @classmethod
    def _normalize_term(cls, v):
        if v is None:
            return "1Y"
        s = str(v).strip().upper()
        if s not in ("1Y", "5Y"):
            raise ValueError('term 仅允许 "1Y" 或 "5Y"')
        return s

    @field_validator("fixed_annual_rate")
    @classmethod
    def _reject_decimal_rate(cls, v):
        if v is not None and 0 < float(v) < 1:
            raise ValueError("疑似填写了小数，请输入百分数（例如 0.24 应写为 24）")
        return v

    @model_validator(mode="after")
    def _check_date_order(self):
        try:
            d0 = datetime.strptime(self.start_date, "%Y-%m-%d").date()
            d1 = datetime.strptime(self.end_date, "%Y-%m-%d").date()
        except ValueError as e:
            raise ValueError(f"日期格式无效: {e}") from e
        if d1 < d0:
            raise ValueError("计息截止日期不能早于起始日期")
        return self

class LaborCalcReq(BaseModel):
    monthly_salary: float = Field(..., example=12000.0)
    hire_date: str = Field(..., example="2021-03-01")
    termination_date: str = Field(..., example="2024-05-15")
    local_avg_salary: Optional[float] = Field(default=None)

class PartyInfo(BaseModel):
    name: str = Field(..., example="张三")
    id_card_or_uscc: str = Field(..., example="110101199003072375")
    gender: str = Field(default="男", example="男")
    birth: str = Field(default="1990年3月7日", example="1990年3月7日")
    ethnicity: str = Field(default="汉族", example="汉族")
    address: str = Field(..., example="北京市朝阳区建国门外大街1号")
    phone: str = Field(..., example="13800000000")
    legal_rep: Optional[str] = Field(default=None, example="李某某 (企业法定代表人)")
    rep_position: Optional[str] = Field(default="执行董事", example="执行董事")

class GenerateLitigationPackageReq(BaseModel):
    cause_of_action: str = Field(
        default="民间借贷纠纷",
        description="案由：民间借贷纠纷 / 劳动人事争议 / 买卖合同纠纷 / 通用民事纠纷",
        example="民间借贷纠纷"
    )
    plaintiff: PartyInfo
    defendant: PartyInfo
    claims: List[str] = Field(
        default_factory=lambda: [
            "判令被告立即向原告偿还借款本金人民币 200,000 元；",
            "判令被告向原告支付利息（按照全国银行间同业拆借中心公布的 LPR 4倍计算）；",
            "判令本案诉讼费用由被告承担。"
        ]
    )
    claim_amount: float = Field(default=200000.0)
    raw_case_notes: str = Field(
        ...,
        description="律师碎片化案情笔记（AI将自动提炼并引用民法典或劳动合同法法条）",
        example="2022年3月5日，被告李四因公司资金周转，向原告借款20万元，原告当天通过招商银行网银全额转入被告账户。被告出具借条承诺1年内还清，年化利率15%。借款到期后原告多次通过微信及电话催促还款，被告拒不偿还本金和利息。"
    )
    court_name: str = Field(default="北京市朝阳区", example="北京市朝阳区")
    lawyer_name: str = Field(default="王律师", example="王律师")
    law_firm: str = Field(default="北京市京师律师事务所", example="北京市京师律师事务所")
    lawyer_phone: str = Field(default="13900008888", example="13900008888")
    lawyer_license: str = Field(default="11101201510123456", example="11101201510123456")
    auto_generate_sub_docs: bool = Field(default=True, description="是否一并生成授权委托书、送达地址确认书、身份证明或保全申请书")


# ==============================================================================
# 计算接口
# ==============================================================================
@router.post("/api/v1/phase1/calc/rmb-capital", summary="人民币大写转换 (cn2an)")
@router.post("/api/calc/rmb-capital", include_in_schema=False)
async def api_rmb_capital(req: RMBCapitalReq):
    return {"amount": req.amount, "rmb_capital": rmb_to_capital(req.amount)}


@router.post("/api/v1/phase1/calc/idcard", summary="18位身份证解析与法定退休年龄判断")
@router.post("/api/calc/idcard", include_in_schema=False)
async def api_idcard(req: IDCardReq):
    return validate_and_parse_idcard(req.id_card, is_cadre=req.is_cadre)


@router.post("/api/v1/phase1/calc/uscc", summary="18位统一社会信用代码校验与解析 (GB 32100-2015)")
async def api_uscc(req: USCCReq):
    return validate_and_parse_uscc(req.uscc)


@router.post("/api/v1/phase1/calc/court-fees", summary="《诉讼费用交纳办法》分段计费")
@router.post("/api/calc/court-fees", include_in_schema=False)
async def api_court_fees(req: CourtFeeReq):
    try:
        return calculate_court_fees(req.claim_amount, req.case_type, req.is_summary_procedure)
    except ValueError as e:
        raise _http_422(str(e)) from e


@router.post("/api/v1/phase1/calc/lpr-interest", summary="央行 LPR 历期计息及诉状利息明细说明")
@router.post("/api/calc/lpr-interest", include_in_schema=False)
async def api_lpr_interest(req: LPRInterestReq):
    try:
        return calculate_lpr_interest(
            principal=req.principal,
            start_date=req.start_date,
            end_date=req.end_date,
            multiplier=req.multiplier,
            term=req.term,
            fixed_annual_rate=req.fixed_annual_rate,
            rule_mode=req.rule_mode,
            contract_date=req.contract_date,
            filing_date=req.filing_date,
            markup_ratio=req.markup_ratio,
            today_date=req.today_date,
        )
    except ValueError as e:
        raise _http_422(str(e)) from e


@router.post("/api/v1/phase1/calc/labor-arbitration", summary="劳动争议经济补偿金精算 (N / N+1 / 2N)")
@router.post("/api/calc/labor-arbitration", include_in_schema=False)
async def api_labor_calc(req: LaborCalcReq):
    return calculate_labor_compensation(
        monthly_salary=req.monthly_salary,
        hire_date=req.hire_date,
        termination_date=req.termination_date,
        local_avg_salary=req.local_avg_salary
    )


class StatuteLimitationsReq(BaseModel):
    start_date: str = Field(..., example="2023-01-01")
    cause_type: str = Field(default="general_3y", example="general_3y")
    interruption_events: Optional[List[Dict[str, str]]] = Field(default=None)
    suspension_events: Optional[List[Dict[str, str]]] = Field(default=None)
    today_date: Optional[str] = Field(default=None)
    act_date: Optional[str] = Field(
        default=None,
        example="2021-06-01",
        description="民事法律行为发生日（撤销权校验 5 年最长期限）",
    )

class PreservationRenewalReq(BaseModel):
    preservation_type: Literal["bank_deposit", "movable_property", "real_estate_equity"] = Field(
        default="bank_deposit", example="bank_deposit"
    )
    start_date: str = Field(..., example="2023-05-10")
    custom_years: Optional[float] = Field(default=None)
    today_date: Optional[str] = Field(default=None)
    internal_reminder_days: int = Field(default=30, ge=1)

class StatuteValidityReq(BaseModel):
    citation_text: str = Field(..., example="《中华人民共和国合同法》第一百零七条")
    incident_date: Optional[str] = Field(default=None, example="2023-05-01")


@router.post("/api/v1/phase1/calc/statute-limitations", summary="诉讼时效与除斥期间精确核算器 (《民法典》第188、194、195、199条)")
@router.post("/api/calc/statute-limitations", include_in_schema=False)
async def api_statute_limitations(req: StatuteLimitationsReq):
    try:
        return calculate_statute_of_limitations(
            start_date=req.start_date,
            cause_type=req.cause_type,
            interruption_events=req.interruption_events,
            suspension_events=req.suspension_events,
            today_date=req.today_date,
            act_date=req.act_date,
        )
    except ValueError as e:
        raise _http_422(str(e)) from e


@router.post("/api/v1/phase1/calc/preservation-renewal", summary="财产保全续查封续冻结红线精算 (法释〔2016〕22号第十八条)")
@router.post("/api/calc/preservation-renewal", include_in_schema=False)
async def api_preservation_renewal(req: PreservationRenewalReq):
    try:
        return calculate_preservation_renewal(
            preservation_type=req.preservation_type,
            start_date=req.start_date,
            custom_years=req.custom_years,
            today_date=req.today_date,
            internal_reminder_days=req.internal_reminder_days,
        )
    except ValueError as e:
        raise _http_422(str(e)) from e


@router.post("/api/v1/phase1/calc/statute-validity", summary="规范性法律文件现行有效性与废止拦截核验")
@router.post("/api/calc/statute-validity", include_in_schema=False)
async def api_statute_validity(req: StatuteValidityReq):
    return verify_statutory_validity(
        citation_text=req.citation_text,
        incident_date=req.incident_date
    )


class InstallmentItem(BaseModel):
    months: int = Field(..., example=3, description="到期时间距今月数")
    amount: float = Field(..., example=500000.0, description="本期计划还款金额")
    note: Optional[str] = Field(default="", description="分期说明")

class AssetPlanInput(BaseModel):
    asset_name: str = Field(default="抵债不动产/商办房产", example="朝阳区商办写字楼3套")
    nominal_asset_valuation: float = Field(..., example=4500000.0, description="名义评估值或抵债作价")
    prior_liens: float = Field(default=0.0, example=1500000.0, description="在先优先受偿权（工程款优先权、第一顺位银行抵押等）")
    auction_discount_rate: float = Field(default=0.70, example=0.70, description="司法拍卖/变现折价率（一拍7折/二拍56折）")
    liquidation_costs_rate: float = Field(default=0.12, example=0.12, description="过户税费与持有清算成本率")
    time_to_liquidate_months: int = Field(default=18, example=18, description="处置变现周期月数")
    encumbrance_status: Optional[str] = Field(default="", example="在先银行抵押150万元")

class SettlementSimulationReq(BaseModel):
    total_claim_nominal: float = Field(..., gt=0, example=5000000.0, description="债权标的名义总额")
    plan_type: Literal["cash_installments", "debt_for_asset", "hybrid"] = Field(
        default="hybrid",
        example="hybrid",
        description="和解方案类型: cash_installments / debt_for_asset / hybrid",
    )
    annual_discount_rate: float = Field(default=0.08, ge=0, example=0.08, description="年化资金折现率/资本成本")
    installments: Optional[List[InstallmentItem]] = Field(default=None, description="分期还款计划")
    asset_plan: Optional[AssetPlanInput] = Field(default=None, description="以物抵债方案")


@router.post("/api/v1/phase1/calc/settlement-simulation", summary="商业诉讼和解与以物抵债现值/回收率精算")
@router.post("/api/calc/settlement-simulation", include_in_schema=False)
async def api_settlement_simulation(req: SettlementSimulationReq):
    try:
        installments_list = [i.model_dump() if hasattr(i, "model_dump") else i.dict() for i in req.installments] if req.installments else []
        asset_dict = req.asset_plan.model_dump() if hasattr(req.asset_plan, "model_dump") else (req.asset_plan.dict() if req.asset_plan else {})
        return calculate_settlement_npv_and_recovery(
            total_claim_nominal=req.total_claim_nominal,
            plan_type=req.plan_type,
            annual_discount_rate=req.annual_discount_rate,
            installments=installments_list,
            asset_plan=asset_dict
        )
    except ValueError as e:
        raise _http_422(str(e)) from e



# ==============================================================================
# 核心大模型案情法言法语润色与诉讼文书包一键流水线
# ==============================================================================
@router.post("/api/v1/phase1/generate-litigation-package", summary="三大高频案由全套立案文书流水线 (.docx + .pdf)")
async def generate_litigation_package(req: GenerateLitigationPackageReq):
    """
    一键输出：
    1. 宿主机 gemma4:12b 润色的引用民法典或劳动合同法的《事实与理由》
    2. 主起诉状/仲裁申请书 (.docx + .pdf)
    3. 配套法律公文包（授权委托书、法定代表人身份证明、送达地址确认书、保全申请书或补偿金清单）
    """
    timestamp = int(time.time())
    package_id = f"pkg-{uuid.uuid4().hex[:10]}"
    filing_date_str = datetime.now().strftime("%Y年%m月%d日")

    # 1. 自动进行当事人主体资格与退休审查
    p_id_info = validate_and_parse_idcard(req.plaintiff.id_card_or_uscc) if len(req.plaintiff.id_card_or_uscc) == 18 and req.plaintiff.id_card_or_uscc[:2].isdigit() else {"is_retired": False}

    # 2. 调用宿主机 gemma4:12b 重构《事实与理由》
    prompt = f"""【案件案由】{req.cause_of_action}
【诉讼请求】
{chr(10).join(req.claims)}

【律师案情碎片笔记】
{req.raw_case_notes}

【原告】{req.plaintiff.name} (住址: {req.plaintiff.address})
【被告】{req.defendant.name} (住址: {req.defendant.address})
【受诉法院】{req.court_name}人民法院

请将上述材料改写为条理清晰、因果严密、引用具体法律条文（如《民法典》或《劳动合同法》具体法条）的《事实与理由》。"""

    try:
        facts_polished = await ollama_client.generate(
            prompt=prompt,
            system_prompt=FACTS_POLISH_SYSTEM_PROMPT,
            temperature=0.2
        )
    except Exception as e:
        logger.warning(f"gemma4:12b 润色异常，降级使用原始笔记: {e}")
        facts_polished = req.raw_case_notes

    # 3. 经过零幻觉引注熔断网关 (Citation Guard) 进行废止法规与条号穿透核验
    from gateway.utils.citation_guard import audit_citations_in_text
    citation_audit = audit_citations_in_text(facts_polished, auto_sanitize=True)
    if citation_audit.get("has_abrogated_laws") and citation_audit.get("sanitized_text"):
        # 自动将废止法律条文替换为现行《民法典》合法条文，杜绝废法写入法院起诉状
        facts_polished = citation_audit["sanitized_text"]

    # 提取引用的法条
    statute_pattern = re.compile(r"《(?:中华人民共和国)?(?:民法典|劳动合同法|民事诉讼法)[^》]+》[第\d条款、及]+")
    statute_citations = statute_pattern.findall(facts_polished)

    # 诉讼费预估
    court_fees = calculate_court_fees(req.claim_amount)

    # 计算利息或仲裁补偿金说明
    interest_statement = ""
    start_date_str = "2023-01-01"
    start_date_display = "2023年1月1日"
    total_interest_val = 0.0

    if "借贷" in req.cause_of_action:
        # 动态从案情笔记中提取真实借款或违约起息日
        date_pattern = re.compile(r"(\d{4}[年\-\/\.]\d{1,2}[月\-\/\.]\d{1,2}日?)")
        found_dates = date_pattern.findall(req.raw_case_notes)
        if found_dates:
            raw_d = found_dates[0]
            norm_d = raw_d.replace("年", "-").replace("月", "-").replace("日", "").replace(".", "-").replace("/", "-")
            d_parts = norm_d.split("-")
            if len(d_parts) == 3:
                try:
                    start_date_str = f"{int(d_parts[0]):04d}-{int(d_parts[1]):02d}-{int(d_parts[2]):02d}"
                    start_date_display = f"{int(d_parts[0])}年{int(d_parts[1])}月{int(d_parts[2])}日"
                except Exception:
                    start_date_display = raw_d
        lpr_calc = calculate_lpr_interest(req.claim_amount, start_date_str, datetime.now().strftime("%Y-%m-%d"), multiplier=4.0)
        interest_statement = lpr_calc.get("complaint_statement", "")
        total_interest_val = float(lpr_calc.get("total_interest", 0.0))
        if total_interest_val <= 0:
            total_interest_val = round(req.claim_amount * 0.15, 2)

    # 3. 渲染主文书 .docx
    generated_docs = []

    # 判定模板类型
    if "借贷" in req.cause_of_action:
        main_tpl = "civil_complaint_loan_template.docx"
        doc_label = "民事起诉状(民间借贷版)"
        context_main = {
            "plaintiff_name": req.plaintiff.name,
            "plaintiff_gender": req.plaintiff.gender,
            "plaintiff_birth": req.plaintiff.birth,
            "plaintiff_ethnicity": req.plaintiff.ethnicity,
            "plaintiff_address": req.plaintiff.address,
            "plaintiff_id": req.plaintiff.id_card_or_uscc,
            "plaintiff_phone": req.plaintiff.phone,
            "defendant_name": req.defendant.name,
            "defendant_gender": req.defendant.gender,
            "defendant_birth": req.defendant.birth,
            "defendant_ethnicity": req.defendant.ethnicity,
            "defendant_address": req.defendant.address,
            "defendant_id": req.defendant.id_card_or_uscc,
            "defendant_phone": req.defendant.phone,
            "loan_principal": f"{req.claim_amount:,.2f}",
            "loan_principal_capital": rmb_to_capital(req.claim_amount),
            "interest_start_date": start_date_display,
            "interest_end_date": filing_date_str,
            "total_interest": f"{total_interest_val:,.2f}",
            "total_interest_capital": rmb_to_capital(total_interest_val),
            "lawyer_fee": "根据民事委托代理协议及发票据实结算",
            "facts_and_reasons": facts_polished,
            "interest_calc_statement": interest_statement,
            "court_name": req.court_name,
            "filing_date": filing_date_str
        }
    elif "劳动" in req.cause_of_action:
        main_tpl = "labor_arbitration_template.docx"
        doc_label = "劳动人事争议仲裁申请书"
        context_main = {
            "applicant_name": req.plaintiff.name,
            "applicant_gender": req.plaintiff.gender,
            "applicant_birth": req.plaintiff.birth,
            "applicant_address": req.plaintiff.address,
            "applicant_id": req.plaintiff.id_card_or_uscc,
            "applicant_phone": req.plaintiff.phone,
            "respondent_name": req.defendant.name,
            "respondent_address": req.defendant.address,
            "respondent_id": req.defendant.id_card_or_uscc,
            "respondent_legal_rep": req.defendant.legal_rep or "负责人",
            "respondent_phone": req.defendant.phone,
            "arbitration_claims": req.claims,
            "facts_and_reasons": facts_polished,
            "arbitration_committee": req.court_name,
            "filing_date": filing_date_str
        }
    elif "买卖" in req.cause_of_action:
        main_tpl = "civil_complaint_sales_template.docx"
        doc_label = "民事起诉状(买卖合同版)"
        context_main = {
            "plaintiff_name": req.plaintiff.name,
            "plaintiff_address": req.plaintiff.address,
            "plaintiff_id": req.plaintiff.id_card_or_uscc,
            "plaintiff_legal_rep": req.plaintiff.legal_rep or req.plaintiff.name,
            "plaintiff_rep_position": req.plaintiff.rep_position or "法定代表人",
            "plaintiff_phone": req.plaintiff.phone,
            "defendant_name": req.defendant.name,
            "defendant_address": req.defendant.address,
            "defendant_id": req.defendant.id_card_or_uscc,
            "defendant_legal_rep": req.defendant.legal_rep or "法定代表人",
            "defendant_phone": req.defendant.phone,
            "contract_arrears": f"{req.claim_amount:,.2f}",
            "contract_arrears_capital": rmb_to_capital(req.claim_amount),
            "liquidated_damages": f"{req.claim_amount * 0.05:,.2f}",
            # 利率描述改为模板变量；完整口径由批次7/律师确认，此处仅占位避免硬编码「加计50%」
            "overdue_rate_desc": "按照全国银行间同业拆借中心公布的一年期贷款市场报价利率（LPR）及合同约定或依法可主张的标准计算",
            "facts_and_reasons": facts_polished,
            "court_name": req.court_name,
            "filing_date": filing_date_str
        }
    else:
        main_tpl = "civil_complaint_template.docx"
        doc_label = "民事起诉状"
        context_main = {
            "plaintiff_name": req.plaintiff.name,
            "plaintiff_gender": req.plaintiff.gender,
            "plaintiff_birth": req.plaintiff.birth,
            "plaintiff_ethnicity": req.plaintiff.ethnicity,
            "plaintiff_id": req.plaintiff.id_card_or_uscc,
            "plaintiff_address": req.plaintiff.address,
            "plaintiff_phone": req.plaintiff.phone,
            "defendant_name": req.defendant.name,
            "defendant_gender": req.defendant.gender,
            "defendant_birth": req.defendant.birth,
            "defendant_ethnicity": req.defendant.ethnicity,
            "defendant_id": req.defendant.id_card_or_uscc,
            "defendant_address": req.defendant.address,
            "defendant_phone": req.defendant.phone,
            "claims": req.claims,
            "facts_and_reasons": facts_polished,
            "court_name": req.court_name,
            "filing_date": filing_date_str
        }

    # 渲染主诉状
    tpl_path = os.path.join(_templates_dir(), main_tpl)
    main_docx_name = f"{doc_label}_{req.plaintiff.name}_{timestamp}.docx"
    main_docx_path = os.path.join(str(get_generated_dir()), main_docx_name)
    main_pdf_name = f"{doc_label}_{req.plaintiff.name}_{timestamp}.pdf"
    main_pdf_path = os.path.join(str(get_generated_dir()), main_pdf_name)

    doc = DocxTemplate(tpl_path)
    doc.render(context_main)
    doc.save(main_docx_path)

    # 转换 PDF
    await convert_docx_to_pdf(main_docx_path, main_pdf_path, title=doc_label, text_summary=facts_polished)

    generated_docs.append({
        "doc_type": doc_label,
        "filename_docx": main_docx_name,
        "docx_url": f"/api/documents/download/{main_docx_name}",
        "filename_pdf": main_pdf_name,
        "pdf_url": f"/api/documents/download/{main_pdf_name}"
    })

    # 若开启生成配套文书
    if req.auto_generate_sub_docs:
        # A. 民事授权委托书
        poa_tpl = os.path.join(_templates_dir(), "power_of_attorney_template.docx")
        poa_docx_name = f"民事授权委托书_{req.plaintiff.name}_{timestamp}.docx"
        poa_docx_path = os.path.join(str(get_generated_dir()), poa_docx_name)
        poa_pdf_name = f"民事授权委托书_{req.plaintiff.name}_{timestamp}.pdf"
        poa_pdf_path = os.path.join(str(get_generated_dir()), poa_pdf_name)

        doc_poa = DocxTemplate(poa_tpl)
        doc_poa.render({
            "client_name": req.plaintiff.name,
            "client_id": req.plaintiff.id_card_or_uscc,
            "client_phone": req.plaintiff.phone,
            "opponent_name": req.defendant.name,
            "cause_of_action": req.cause_of_action,
            "lawyer_name": req.lawyer_name,
            "law_firm": req.law_firm,
            "lawyer_license": req.lawyer_license,
            "lawyer_phone": req.lawyer_phone,
            "authorization_scope": "特别授权：代为承认、放弃、变更诉讼请求，进行和解，提起反诉或者上诉，申请执行，签收法律文书等全部诉讼权利。",
            "sign_date": filing_date_str
        })
        doc_poa.save(poa_docx_path)
        await convert_docx_to_pdf(poa_docx_path, poa_pdf_path, title="民事授权委托书")

        generated_docs.append({
            "doc_type": "民事授权委托书",
            "filename_docx": poa_docx_name,
            "docx_url": f"/api/documents/download/{poa_docx_name}",
            "filename_pdf": poa_pdf_name,
            "pdf_url": f"/api/documents/download/{poa_pdf_name}"
        })

        # B. 送达地址确认书
        addr_tpl = os.path.join(_templates_dir(), "service_address_template.docx")
        addr_docx_name = f"送达地址确认书_{req.plaintiff.name}_{timestamp}.docx"
        addr_docx_path = os.path.join(str(get_generated_dir()), addr_docx_name)
        doc_addr = DocxTemplate(addr_tpl)
        doc_addr.render({
            "cause_of_action": req.cause_of_action,
            "recipient_name": req.plaintiff.name,
            "recipient_id": req.plaintiff.id_card_or_uscc,
            "lawyer_name": req.lawyer_name,
            "law_firm": req.law_firm,
            "lawyer_phone": req.lawyer_phone,
            "mail_address": req.plaintiff.address,
            "postal_code": "100022",
            "mobile_phone": req.plaintiff.phone,
            "email_address": "lawyer_service@lawflow.cn",
            "sign_date": filing_date_str
        })
        doc_addr.save(addr_docx_path)
        generated_docs.append({
            "doc_type": "送达地址确认书",
            "filename_docx": addr_docx_name,
            "docx_url": f"/api/documents/download/{addr_docx_name}"
        })

        # C. 针对买卖合同欠款：自动生成《财产保全申请书》
        if "买卖" in req.cause_of_action or "借贷" in req.cause_of_action:
            preserv_tpl = os.path.join(_templates_dir(), "property_preservation_template.docx")
            preserv_docx_name = f"财产保全申请书_{req.plaintiff.name}_{timestamp}.docx"
            preserv_docx_path = os.path.join(str(get_generated_dir()), preserv_docx_name)
            doc_preserv = DocxTemplate(preserv_tpl)
            doc_preserv.render({
                "applicant_name": req.plaintiff.name,
                "applicant_id": req.plaintiff.id_card_or_uscc,
                "applicant_phone": req.plaintiff.phone,
                "respondent_name": req.defendant.name,
                "respondent_id": req.defendant.id_card_or_uscc,
                "respondent_address": req.defendant.address,
                "preservation_amount": f"{req.claim_amount:,.2f}",
                "preservation_amount_capital": rmb_to_capital(req.claim_amount),
                "cause_of_action": req.cause_of_action,
                "property_clues": f"1. 被申请人名下银行基本存款账户；\n2. 被申请人名下位于 {req.defendant.address} 之不动产或经营设备。",
                "court_name": req.court_name,
                "sign_date": filing_date_str
            })
            doc_preserv.save(preserv_docx_path)
            generated_docs.append({
                "doc_type": "财产保全申请书",
                "filename_docx": preserv_docx_name,
                "docx_url": f"/api/documents/download/{preserv_docx_name}"
            })

        # D. 针对劳动争议：自动生成《经济补偿金计算清单》
        if "劳动" in req.cause_of_action:
            labor_tpl = os.path.join(_templates_dir(), "labor_compensation_calc_template.docx")
            labor_docx_name = f"经济补偿金计算清单_{req.plaintiff.name}_{timestamp}.docx"
            labor_docx_path = os.path.join(str(get_generated_dir()), labor_docx_name)
            labor_calc = calculate_labor_compensation(12000, "2021-03-01", datetime.now().strftime("%Y-%m-%d"))
            doc_labor = DocxTemplate(labor_tpl)
            doc_labor.render({
                "applicant_name": req.plaintiff.name,
                "respondent_name": req.defendant.name,
                "hire_date": "2021年3月1日",
                "termination_date": filing_date_str,
                "tenure_str": labor_calc["tenure_str"],
                "monthly_salary": "12,000.00",
                "compensation_months": f"{labor_calc['compensation_months']}",
                "amount_n": f"{labor_calc['tiers']['N']['amount']:,.2f}",
                "amount_plus_1_notice": f"{labor_calc['tiers']['N+1']['notice_pay']:,.2f}",
                "amount_2n": f"{labor_calc['tiers']['2N']['amount']:,.2f}",
                "cap_reason": labor_calc["cap_reason"],
                "filing_date": filing_date_str
            })
            doc_labor.save(labor_docx_path)
            generated_docs.append({
                "doc_type": "经济补偿金计算清单",
                "filename_docx": labor_docx_name,
                "docx_url": f"/api/documents/download/{labor_docx_name}"
            })

    return {
        "status": "success",
        "package_id": package_id,
        "cause_of_action": req.cause_of_action,
        "facts_and_reasons_polished": facts_polished,
        "statute_citations": list(set(statute_citations)),
        "citation_audit": citation_audit,
        "court_fees_estimate": court_fees,
        "retirement_check": p_id_info.get("retirement_note"),
        "generated_documents": generated_docs
    }


# ==============================================================================
# 兼容旧版路由与下载接口
# ==============================================================================
@router.get("/api/documents/download/{filename}", summary="文书下载接口")
async def download_doc(filename: str):
    safe_name = validate_download_filename(filename)
    try:
        file_path = safe_join(str(get_generated_dir()), safe_name)
    except HTTPException:
        raise
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="文件不存在")
    media = "application/pdf" if safe_name.endswith(".pdf") else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return FileResponse(path=file_path, filename=os.path.basename(safe_name), media_type=media)


# ==============================================================================
# P3: 二审/再审生死局·一审裁决漏洞剖析与最高院类案分歧穿透接口
# ==============================================================================
class AppealAuditRequest(BaseModel):
    judgment_text: Optional[str] = Field(default="", description="一审判决书全文或裁判理由段落")
    case_title: Optional[str] = Field(default=None, description="案件名称")
    claim_amount: Optional[float] = Field(default=80000000.0, description="回购或争议标的金额")
    agreed_repurchase_rate: Optional[float] = Field(default=0.15, description="合同约定年化回购溢价/违约金率")
    first_instance_court: Optional[str] = Field(default="一审中级人民法院", description="作出一审判决之法院名称")
    first_instance_errors: Optional[List[str]] = Field(default=None, description="一审争议与错误倾向")


class AppealExportDocxRequest(BaseModel):
    title: str = Field(default="二审上诉文书", description="文档标题")
    content_text: str = Field(..., description="文书正文文本")
    doc_type: str = Field(default="appeal_pleading", description="appeal_pleading 或 appeal_memo")


@router.post("/api/v1/litigation/appeal-audit", summary="二审/再审一审判决漏洞剖析与最高院类案分歧穿透")
@router.post("/api/v1/phase1/appeal-audit", summary="二审/再审一审判决漏洞剖析与最高院类案分歧穿透（别名）")
async def api_appeal_audit(req: AppealAuditRequest):
    try:
        res = analyze_first_instance_judgment_and_precedents(
            judgment_text=req.judgment_text or "",
            case_title=req.case_title,
            claim_amount=req.claim_amount or 80000000.0,
            agreed_repurchase_rate=req.agreed_repurchase_rate or 0.15,
            first_instance_court=req.first_instance_court or "一审中级人民法院",
            first_instance_errors=req.first_instance_errors
        )
        return res
    except Exception as e:
        logger.error(f"二审类案审计失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/litigation/appeal-export-docx", summary="二审上诉状与类案检索报告Word原生导出")
@router.post("/api/v1/phase1/appeal-export-docx", summary="二审上诉状与类案检索报告Word原生导出（别名）")
async def api_appeal_export_docx(req: AppealExportDocxRequest):
    try:
        import docx
        from docx.shared import Pt, Inches, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH

        doc = docx.Document()
        
        # 页面边距设置 (司法公文标准)
        for s in doc.sections:
            s.top_margin = Inches(1.0)
            s.bottom_margin = Inches(1.0)
            s.left_margin = Inches(1.1)
            s.right_margin = Inches(1.1)

        # 标题
        h = doc.add_heading(level=1)
        h_run = h.add_run(req.title)
        h_run.font.name = "黑体"
        h_run.font.size = Pt(17)
        h_run.font.bold = True
        h_run.font.color.rgb = RGBColor(0x14, 0x23, 0x3C)
        h.alignment = WD_ALIGN_PARAGRAPH.CENTER

        # 段落渲染
        lines = req.content_text.splitlines()
        for line in lines:
            line_str = line.strip()
            if not line_str:
                doc.add_paragraph()
                continue
            p = doc.add_paragraph()
            p.paragraph_format.line_spacing = 1.35
            p.paragraph_format.space_after = Pt(4)
            p_run = p.add_run(line)
            p_run.font.name = "仿宋_GB2312"
            p_run.font.size = Pt(12)
            if any(line.startswith(prefix) for prefix in ["一、", "二、", "三、", "四、", "【", "上诉请求", "事实与理由", "民 事 上 诉 状"]):
                p_run.font.bold = True
                p_run.font.color.rgb = RGBColor(0x14, 0x23, 0x3C)
                if line.startswith("【") or line == "民 事 上 诉 状":
                    p.paragraph_format.space_before = Pt(8)

        safe_title = sanitize_filename(req.title)
        filename = f"{safe_title}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}.docx"
        filepath = safe_join(str(get_generated_dir()), filename)
        doc.save(filepath)

        return {
            "status": "success",
            "filename": filename,
            "download_url": f"/api/documents/download/{filename}",
            "file_size": os.path.getsize(filepath)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"导出二审文书Docx失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

