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
import shutil
import subprocess
import time
import uuid
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any, Literal, Tuple
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
    calculate_settlement_npv_and_recovery,
    calculate_appeal_deadline,
)
from gateway.utils.text_utils import (
    normalize_court_name,
    normalize_arbitration_committee,
    extract_agreed_annual_rate,
    extract_first_date_iso,
    format_date_cn,
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

PLACEHOLDER = "【待填写】"


def _templates_dir() -> str:
    return str(get_base_dir() / "templates")

STIRLING_PDF_URL = os.getenv("STIRLING_PDF_URL", "http://127.0.0.1:8081").rstrip("/")


def _find_soffice() -> Optional[str]:
    """定位 LibreOffice soffice 可执行文件。"""
    for cand in (
        shutil.which("soffice"),
        shutil.which("libreoffice"),
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        "/usr/bin/soffice",
        "/usr/bin/libreoffice",
    ):
        if cand and os.path.isfile(cand):
            return cand
    return None


def _convert_docx_via_soffice(docx_path: str, pdf_path: str) -> bool:
    soffice = _find_soffice()
    if not soffice:
        return False
    out_dir = os.path.dirname(os.path.abspath(pdf_path)) or "."
    try:
        proc = subprocess.run(
            [
                soffice,
                "--headless",
                "--nologo",
                "--nofirststartwizard",
                "--convert-to",
                "pdf",
                "--outdir",
                out_dir,
                os.path.abspath(docx_path),
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if proc.returncode != 0:
            logger.warning(f"LibreOffice 转换失败: {proc.stderr}")
            return False
        produced = os.path.join(out_dir, os.path.splitext(os.path.basename(docx_path))[0] + ".pdf")
        if os.path.abspath(produced) != os.path.abspath(pdf_path):
            if os.path.isfile(produced):
                shutil.move(produced, pdf_path)
        return os.path.isfile(pdf_path) and os.path.getsize(pdf_path) > 100
    except Exception as e:
        logger.warning(f"LibreOffice 转换异常: {e}")
        return False


def _extract_docx_paragraphs(docx_path: str, text_summary: str = "") -> List[str]:
    import docx as python_docx
    d = python_docx.Document(docx_path)
    lines: List[str] = []
    for p in d.paragraphs:
        if p.text.strip():
            lines.append(p.text)
    for table in d.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                lines.append("  ".join(cells))
    if not lines:
        if text_summary:
            lines = [text_summary]
        else:
            lines = ["司法文书内容"]
    return lines


def _pymupdf_fit_lines(doc: "fitz.Document", text_rect, lines: List[str], fontsize: int = 11) -> int:
    """二分查找能完整写入当前新页的最大行数；写入后返回消耗行数。"""
    if not lines:
        return 0
    page_width, page_height = 595, 842
    lo, hi = 1, len(lines)
    best = 1
    while lo <= hi:
        mid = (lo + hi) // 2
        probe = doc.new_page(width=page_width, height=page_height)
        rc = probe.insert_textbox(
            text_rect, "\n".join(lines[:mid]), fontsize=fontsize, fontname="china-s", align=0
        )
        doc.delete_page(-1)
        if rc >= 0:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    page = doc.new_page(width=page_width, height=page_height)
    page.insert_textbox(
        text_rect, "\n".join(lines[:best]), fontsize=fontsize, fontname="china-s", align=0
    )
    return best


def _pymupdf_paginated_render(paragraphs: List[str], pdf_path: str) -> bool:
    """
    按行分页写入 PDF：检查 insert_textbox 返回值，溢出则新开一页继续，直至写完。
    """
    page_width, page_height = 595, 842
    margin_x, margin_top, margin_bottom = 54, 72, 55
    fontsize = 11
    all_lines: List[str] = []
    for p in paragraphs:
        text = p if p is not None else ""
        if not text:
            all_lines.append("")
            continue
        for i in range(0, len(text), 38):
            all_lines.append(text[i : i + 38])
        all_lines.append("")

    doc = fitz.open()
    text_rect = fitz.Rect(margin_x, margin_top, page_width - margin_x, page_height - margin_bottom)
    remaining = all_lines
    while remaining:
        consumed = _pymupdf_fit_lines(doc, text_rect, remaining, fontsize=fontsize)
        if consumed <= 0:
            # 保底：强制写一行避免死循环
            page = doc.new_page(width=page_width, height=page_height)
            page.insert_textbox(text_rect, remaining[0], fontsize=fontsize, fontname="china-s", align=0)
            consumed = 1
        remaining = remaining[consumed:]

    total_pages = doc.page_count
    for pno in range(total_pages):
        page = doc[pno]
        footer_rect = fitz.Rect(margin_x, page_height - 35, page_width - margin_x, page_height - 15)
        footer_str = f"LawFlow 智律工作台 · 电子文书存证副本 · 第 {pno + 1} 页 / 共 {total_pages} 页"
        page.insert_textbox(footer_rect, footer_str, fontsize=8, fontname="china-s", align=1)

    doc.save(pdf_path)
    doc.close()
    return total_pages > 0 and os.path.isfile(pdf_path)


# ==============================================================================
# 文书转换辅助函数：将 Word 转换为 PDF
# ==============================================================================
async def convert_docx_to_pdf(docx_path: str, pdf_path: str, title: str = "司法公文", text_summary: str = "") -> bool:
    """
    优先 LibreOffice (soffice)；其次 Stirling-PDF；最后 PyMuPDF 按行分页兜底。
    全部失败时返回 False，不得生成缺页/空壳 PDF。
    """
    # 1. LibreOffice
    if _convert_docx_via_soffice(docx_path, pdf_path):
        logger.info(f"LibreOffice 成功将 {docx_path} 转换为 {pdf_path}")
        return True

    # 2. Stirling-PDF
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

    # 3. PyMuPDF 按行分页兜底
    try:
        paragraphs = _extract_docx_paragraphs(docx_path, text_summary=text_summary)
        ok = _pymupdf_paginated_render(paragraphs, pdf_path)
        if ok:
            logger.info(f"PyMuPDF 分页渲染成功: {pdf_path}")
            return True
        logger.error("PyMuPDF 分页渲染失败：未生成有效 PDF")
        return False
    except Exception as e:
        logger.error(f"PDF 转换异常: {e}")
        if os.path.isfile(pdf_path):
            try:
                os.remove(pdf_path)
            except OSError:
                pass
        return False


def _highlight_placeholders_in_docx(docx_path: str) -> None:
    """将文档中【待填写】文字标为黄色高亮。"""
    try:
        import docx as python_docx
        from docx.enum.text import WD_COLOR_INDEX
        d = python_docx.Document(docx_path)
        targets = list(d.paragraphs)
        for table in d.tables:
            for row in table.rows:
                for cell in row.cells:
                    targets.extend(cell.paragraphs)
        for p in targets:
            for run in p.runs:
                if PLACEHOLDER in (run.text or ""):
                    run.font.highlight_color = WD_COLOR_INDEX.YELLOW
        d.save(docx_path)
    except Exception as e:
        logger.warning(f"黄色高亮占位符失败: {e}")


def _or_placeholder(value: Optional[str], missing_fields: List[str], field_name: str) -> str:
    if value is None or str(value).strip() == "":
        missing_fields.append(field_name)
        return PLACEHOLDER
    s = str(value).strip()
    # 禁止字段名充当内容
    if s == field_name or s in ("法定代表人", "主要负责人", "性别", "出生日期"):
        missing_fields.append(field_name)
        return PLACEHOLDER
    return s


def _resolve_party(party: "PartyInfo", role: str, missing_fields: List[str]) -> Dict[str, Any]:
    """按 party_type 解析当事人展示字段。"""
    pid = (party.id_card_or_uscc or "").strip()
    party_type = party.party_type
    id_info = validate_and_parse_idcard(pid) if pid else {"valid": False}
    uscc_info = validate_and_parse_uscc(pid) if pid else {"valid": False}

    if party_type is None:
        if uscc_info.get("valid"):
            party_type = "legal"
        elif id_info.get("valid"):
            party_type = "natural"
        else:
            # 18 位且含字母倾向法人；否则自然人占位
            if len(pid) == 18 and any(c.isalpha() for c in pid):
                party_type = "legal"
            else:
                party_type = "natural"

    result: Dict[str, Any] = {
        "name": _or_placeholder(party.name, missing_fields, f"{role}.name"),
        "address": _or_placeholder(party.address, missing_fields, f"{role}.address"),
        "phone": _or_placeholder(party.phone, missing_fields, f"{role}.phone"),
        "party_type": party_type,
        "ethnicity": party.ethnicity or "汉族",
        "id_card_or_uscc": pid or PLACEHOLDER,
    }
    if not pid:
        missing_fields.append(f"{role}.id_card_or_uscc")

    if party_type == "natural":
        parsed_gender = id_info.get("gender") if id_info.get("valid") else None
        parsed_birth = None
        if id_info.get("valid") and id_info.get("birth_date"):
            # 1990-03-07 → 1990年3月7日
            parsed_birth = format_date_cn(id_info["birth_date"])

        if party.gender and parsed_gender and party.gender != parsed_gender:
            raise _http_422(
                f"{role} 性别填写「{party.gender}」与身份证解析结果「{parsed_gender}」冲突"
            )
        if party.birth and parsed_birth:
            # 宽松比较：去掉 0 填充差异
            def _norm_birth(s: str) -> str:
                return re.sub(r"年0*", "年", re.sub(r"月0*", "月", s.replace("日", "")))
            if _norm_birth(party.birth) != _norm_birth(parsed_birth):
                raise _http_422(
                    f"{role} 出生日期填写「{party.birth}」与身份证解析结果「{parsed_birth}」冲突"
                )

        result["gender"] = party.gender or parsed_gender or PLACEHOLDER
        result["birth"] = party.birth or parsed_birth or PLACEHOLDER
        if result["gender"] == PLACEHOLDER:
            missing_fields.append(f"{role}.gender")
        if result["birth"] == PLACEHOLDER:
            missing_fields.append(f"{role}.birth")
        result["id_label"] = "公民身份号码"
        result["legal_rep"] = ""
        result["rep_position"] = ""
    else:
        result["gender"] = ""
        result["birth"] = ""
        result["id_label"] = "统一社会信用代码"
        result["legal_rep"] = _or_placeholder(party.legal_rep, missing_fields, f"{role}.legal_rep")
        result["rep_position"] = _or_placeholder(party.rep_position, missing_fields, f"{role}.rep_position")

    return result


def _build_claims_for_cause(
    req: "GenerateLitigationPackageReq",
    agreed_rate: Optional[float],
    start_date_iso: str,
    start_date_display: str,
    interest_meta: Dict[str, Any],
) -> List[str]:
    """用户诉请原样写入；利息诉请按约定/上限格式化；不追加暂计金额。"""
    claims: List[str] = []
    for raw in req.claims or []:
        c = str(raw).strip()
        if not c:
            continue
        # 劳动争议用语规范化
        if "劳动" in req.cause_of_action:
            c = c.replace("判令被告", "裁决被申请人").replace("判令", "裁决")
            c = c.replace("原告", "申请人").replace("被告", "被申请人")
        # 利息诉请：有约定利率时改写为规范表述
        if "利息" in c and ("借贷" in req.cause_of_action or agreed_rate is not None):
            rate = interest_meta.get("applied_rate")
            if rate is not None:
                note = ""
                if interest_meta.get("capped"):
                    note = f"（约定年利率{agreed_rate:g}%超过法定上限，按上限年利率{rate:g}%主张）"
                c = (
                    f"判令被告支付利息（以{req.claim_amount:,.2f}元为基数，按年利率{rate:g}%，"
                    f"自{start_date_display}起计算至实际清偿之日止）{note}"
                )
        # 律师费旁注
        if "律师费" in c and "需有合同约定" not in c:
            c = f"{c.rstrip('；;。.')}（需有合同约定或法律依据）"
        claims.append(c)
    return claims



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
    id_card_or_uscc: str = Field(default="", example="110101199003072375")
    gender: Optional[str] = Field(default=None, example="男")
    birth: Optional[str] = Field(default=None, example="1990年3月7日")
    ethnicity: Optional[str] = Field(default="汉族", example="汉族")
    address: str = Field(default="", example="北京市朝阳区建国门外大街1号")
    phone: Optional[str] = Field(default=None, example="13800000000")
    legal_rep: Optional[str] = Field(default=None, example="李某某")
    rep_position: Optional[str] = Field(default=None, example="执行董事")
    party_type: Optional[Literal["natural", "legal"]] = Field(
        default=None,
        description="natural=自然人 / legal=法人或非法人组织；未传时自动判断",
    )

    @model_validator(mode="before")
    @classmethod
    def _alias_id_fields(cls, data):
        if isinstance(data, dict):
            if not data.get("id_card_or_uscc"):
                for alt in ("id_number", "id_card", "id", "uscc"):
                    if data.get(alt):
                        data["id_card_or_uscc"] = data[alt]
                        break
        return data

    @model_validator(mode="after")
    def _auto_party_type(self):
        if self.party_type is not None:
            return self
        pid = (self.id_card_or_uscc or "").strip()
        if len(pid) == 18:
            if validate_and_parse_uscc(pid).get("valid"):
                object.__setattr__(self, "party_type", "legal")
            elif validate_and_parse_idcard(pid).get("valid"):
                object.__setattr__(self, "party_type", "natural")
        return self


class EvidenceItem(BaseModel):
    name: str = Field(..., description="证据名称")
    source: Optional[str] = Field(default="", description="证据来源")
    witness_name: Optional[str] = Field(default="", description="证人姓名")
    witness_address: Optional[str] = Field(default="", description="证人住所")
    category: Optional[str] = Field(default="书证")
    purpose: Optional[str] = Field(default="")
    pages: Optional[str] = Field(default="")
    original_or_copy: Optional[str] = Field(default="复印件")


class GenerateLitigationPackageReq(BaseModel):
    cause_of_action: str = Field(
        default="民间借贷纠纷",
        description="案由：民间借贷纠纷 / 劳动人事争议 / 买卖合同纠纷 / 通用民事纠纷",
        example="民间借贷纠纷"
    )
    plaintiff: PartyInfo
    defendant: PartyInfo
    claims: List[str] = Field(
        default_factory=list,
        description="诉讼请求列表（原样写入文书）",
    )
    claim_amount: float = Field(default=200000.0)
    raw_case_notes: str = Field(
        ...,
        description="律师碎片化案情笔记（AI将自动提炼并引用民法典或劳动合同法法条）",
        example="2022年3月5日，被告李四因公司资金周转，向原告借款20万元，原告当天通过招商银行网银全额转入被告账户。被告出具借条承诺1年内还清，年化利率15%。借款到期后原告多次通过微信及电话催促还款，被告拒不偿还本金和利息。"
    )
    court_name: str = Field(default="北京市朝阳区人民法院", example="北京市朝阳区人民法院")
    arbitration_committee: Optional[str] = Field(
        default=None,
        description="劳动争议致送机关全称；未填时按地区补全为××劳动人事争议仲裁委员会",
    )
    lawyer_name: str = Field(default="王律师", example="王律师")
    law_firm: str = Field(default="北京市京师律师事务所", example="北京市京师律师事务所")
    lawyer_phone: str = Field(default="13900008888", example="13900008888")
    lawyer_license: str = Field(default="11101201510123456", example="11101201510123456")
    auto_generate_sub_docs: bool = Field(default=True, description="是否一并生成授权委托书、送达地址确认书、身份证明或保全申请书")
    evidences: Optional[List[EvidenceItem]] = Field(default=None, description="证据和证据来源，证人姓名和住所")
    copies: Optional[int] = Field(default=None, description="起诉状副本份数，默认等于被告人数")
    agreed_annual_rate: Optional[float] = Field(default=None, description="约定年利率（百分数）")
    contract_date: Optional[str] = Field(default=None, description="合同成立日 YYYY-MM-DD")


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


class AppealDeadlineReq(BaseModel):
    service_date: str = Field(..., example="2026-11-02", description="一审裁判送达日期 YYYY-MM-DD")
    judgment_type: Literal["judgment", "ruling"] = Field(..., description="judgment=判决 / ruling=裁定")
    holidays: Optional[List[str]] = Field(default=None, description="额外法定节假日 YYYY-MM-DD 列表；默认读 data/legal/holidays_cn.json")
    treat_weekend_as_holiday: bool = Field(
        default=True,
        description="周六日是否顺延；口径 TODO(律师核实)，默认 True",
    )


@router.post("/api/v1/phase1/calc/appeal-deadline", summary="上诉期截止日测算（《民事诉讼法》第171条）")
@router.post("/api/calc/appeal-deadline", include_in_schema=False)
async def api_appeal_deadline(req: AppealDeadlineReq):
    try:
        return calculate_appeal_deadline(
            service_date=req.service_date,
            judgment_type=req.judgment_type,
            holidays=req.holidays,
            treat_weekend_as_holiday=req.treat_weekend_as_holiday,
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
    missing_fields: List[str] = []

    # 1. 当事人解析（自然人/法人）
    plaintiff = _resolve_party(req.plaintiff, "plaintiff", missing_fields)
    defendant = _resolve_party(req.defendant, "defendant", missing_fields)

    court_full = normalize_court_name(req.court_name)
    is_labor = "劳动" in req.cause_of_action
    arbitration_full = ""
    if is_labor:
        region_hint = (req.court_name or "").replace("人民法院", "").replace("法院", "").strip()
        arbitration_full = normalize_arbitration_committee(
            req.arbitration_committee or req.court_name, region_hint=region_hint
        )

    # 退休审查（仅自然人身份证）
    p_id_info: Dict[str, Any] = {"is_retired": False}
    if plaintiff["party_type"] == "natural" and len(plaintiff["id_card_or_uscc"]) == 18:
        p_id_info = validate_and_parse_idcard(plaintiff["id_card_or_uscc"])

    # 2. 事实与理由：显式传入案由，禁止兜底猜案由
    prompt = f"""【案件案由】{req.cause_of_action}
【诉讼请求】
{chr(10).join(req.claims or [])}

【律师案情碎片笔记】
{req.raw_case_notes}

【原告】{plaintiff['name']} (住址: {plaintiff['address']})
【被告】{defendant['name']} (住址: {defendant['address']})
【受诉法院】{court_full if not is_labor else arbitration_full}

请将上述材料改写为条理清晰、因果严密、引用具体法律条文（如《民法典》或《劳动合同法》具体法条）的《事实与理由》。"""

    try:
        facts_polished = await ollama_client.generate(
            prompt=prompt,
            system_prompt=FACTS_POLISH_SYSTEM_PROMPT,
            temperature=0.2,
            cause_of_action=req.cause_of_action,
        )
    except Exception as e:
        logger.warning(f"大模型润色异常，降级使用原始笔记: {e}")
        facts_polished = req.raw_case_notes

    from gateway.utils.citation_guard import audit_citations_in_text
    citation_audit = audit_citations_in_text(facts_polished, auto_sanitize=True)
    if citation_audit.get("has_abrogated_laws") and citation_audit.get("sanitized_text"):
        facts_polished = citation_audit["sanitized_text"]

    statute_pattern = re.compile(r"《(?:中华人民共和国)?(?:民法典|劳动合同法|民事诉讼法)[^》]+》[第\d条款、及]+")
    statute_citations = statute_pattern.findall(facts_polished)

    court_fees = calculate_court_fees(req.claim_amount)

    # 利息：约定利率 + private_lending_cap 上限，不再默认 4 倍 LPR
    interest_statement = ""
    start_date_str = extract_first_date_iso(req.raw_case_notes) or req.contract_date or "2023-01-01"
    start_date_display = format_date_cn(start_date_str)
    total_interest_val = 0.0
    agreed_rate = req.agreed_annual_rate
    if agreed_rate is None:
        agreed_rate = extract_agreed_annual_rate(req.raw_case_notes)
    interest_meta: Dict[str, Any] = {"applied_rate": agreed_rate, "capped": False}

    if "借贷" in req.cause_of_action:
        contract_date = req.contract_date or start_date_str
        end_date = datetime.now().strftime("%Y-%m-%d")
        try:
            lpr_calc = calculate_lpr_interest(
                principal=req.claim_amount,
                start_date=start_date_str,
                end_date=end_date,
                fixed_annual_rate=agreed_rate if agreed_rate is not None else None,
                rule_mode="private_lending_cap",
                contract_date=contract_date,
            )
            interest_statement = lpr_calc.get("complaint_statement", "")
            total_interest_val = float(lpr_calc.get("total_interest", 0.0))
            # 从分段取实际执行年利率
            segs = lpr_calc.get("segments") or []
            applied = None
            capped = False
            for seg in segs:
                if seg.get("applied_annual_rate") is not None:
                    applied = float(seg["applied_annual_rate"])
                if seg.get("is_rate_capped"):
                    capped = True
            if applied is None and agreed_rate is not None:
                applied = float(agreed_rate)
            interest_meta = {"applied_rate": applied, "capped": capped, "agreed_rate": agreed_rate}
        except Exception as e:
            logger.warning(f"利息精算失败: {e}")
            interest_meta = {"applied_rate": agreed_rate, "capped": False, "agreed_rate": agreed_rate}

    claims_final = _build_claims_for_cause(req, agreed_rate, start_date_str, start_date_display, interest_meta)
    if not claims_final:
        claims_final = [PLACEHOLDER]
        missing_fields.append("claims")

    evidences = []
    if req.evidences:
        for ev in req.evidences:
            evidences.append(ev.model_dump() if hasattr(ev, "model_dump") else dict(ev))
    copies = req.copies if req.copies is not None else 1

    # 当事人公共模板上下文
    def _party_ctx(prefix: str, info: Dict[str, Any]) -> Dict[str, Any]:
        return {
            f"{prefix}_name": info["name"],
            f"{prefix}_gender": info.get("gender") or "",
            f"{prefix}_birth": info.get("birth") or "",
            f"{prefix}_ethnicity": info.get("ethnicity") or "",
            f"{prefix}_address": info["address"],
            f"{prefix}_id": info["id_card_or_uscc"],
            f"{prefix}_id_label": info.get("id_label") or "",
            f"{prefix}_phone": info.get("phone") or PLACEHOLDER,
            f"{prefix}_legal_rep": info.get("legal_rep") or "",
            f"{prefix}_rep_position": info.get("rep_position") or "",
            f"{prefix}_party_type": info["party_type"],
            f"{prefix}_is_natural": info["party_type"] == "natural",
            f"{prefix}_is_legal": info["party_type"] == "legal",
        }

    generated_docs = []
    common_party = {}
    common_party.update(_party_ctx("plaintiff", plaintiff))
    common_party.update(_party_ctx("defendant", defendant))
    # 劳动仲裁用语别名
    common_party.update(_party_ctx("applicant", plaintiff))
    common_party.update(_party_ctx("respondent", defendant))

    if "借贷" in req.cause_of_action:
        main_tpl = "civil_complaint_loan_template.docx"
        doc_label = "民事起诉状(民间借贷版)"
        context_main = {
            **common_party,
            "claims": claims_final,
            "loan_principal": f"{req.claim_amount:,.2f}",
            "loan_principal_capital": rmb_to_capital(req.claim_amount),
            "interest_start_date": start_date_display,
            "interest_annual_rate": (
                f"{interest_meta['applied_rate']:g}" if interest_meta.get("applied_rate") is not None else PLACEHOLDER
            ),
            "interest_base": f"{req.claim_amount:,.2f}",
            "interest_end_date": filing_date_str,
            "total_interest": f"{total_interest_val:,.2f}" if total_interest_val else PLACEHOLDER,
            "total_interest_capital": rmb_to_capital(total_interest_val) if total_interest_val else PLACEHOLDER,
            "lawyer_fee_note": "需有合同约定或法律依据",
            "facts_and_reasons": facts_polished,
            "interest_calc_statement": interest_statement,
            "court_name": court_full,
            "filing_date": filing_date_str,
            "evidences": evidences,
            "copies": copies,
        }
    elif is_labor:
        main_tpl = "labor_arbitration_template.docx"
        doc_label = "劳动人事争议仲裁申请书"
        context_main = {
            **common_party,
            "respondent_legal_rep": defendant.get("legal_rep") or PLACEHOLDER,
            "arbitration_claims": claims_final,
            "facts_and_reasons": facts_polished,
            "arbitration_committee": arbitration_full,
            "filing_date": filing_date_str,
            "evidences": evidences,
            "arbitration_limitation_note": "仲裁时效一般为1年，具体以律师核实为准",
        }
    elif "买卖" in req.cause_of_action:
        main_tpl = "civil_complaint_sales_template.docx"
        doc_label = "民事起诉状(买卖合同版)"
        context_main = {
            **common_party,
            "claims": claims_final,
            "contract_arrears": f"{req.claim_amount:,.2f}",
            "contract_arrears_capital": rmb_to_capital(req.claim_amount),
            "liquidated_damages": PLACEHOLDER,
            "overdue_rate_desc": "按照全国银行间同业拆借中心公布的一年期贷款市场报价利率（LPR）及合同约定或依法可主张的标准计算",
            "facts_and_reasons": facts_polished,
            "court_name": court_full,
            "filing_date": filing_date_str,
            "evidences": evidences,
            "copies": copies,
        }
    else:
        main_tpl = "civil_complaint_template.docx"
        doc_label = "民事起诉状"
        context_main = {
            **common_party,
            "claims": claims_final,
            "facts_and_reasons": facts_polished,
            "court_name": court_full,
            "filing_date": filing_date_str,
            "evidences": evidences,
            "copies": copies,
        }

    tpl_path = os.path.join(_templates_dir(), main_tpl)
    safe_party_name = sanitize_filename(plaintiff["name"]) or "当事人"
    main_docx_name = f"{doc_label}_{safe_party_name}_{timestamp}.docx"
    main_docx_path = os.path.join(str(get_generated_dir()), main_docx_name)
    main_pdf_name = f"{doc_label}_{safe_party_name}_{timestamp}.pdf"
    main_pdf_path = os.path.join(str(get_generated_dir()), main_pdf_name)

    doc = DocxTemplate(tpl_path)
    doc.render(context_main)
    doc.save(main_docx_path)
    _highlight_placeholders_in_docx(main_docx_path)

    pdf_ok = await convert_docx_to_pdf(main_docx_path, main_pdf_path, title=doc_label, text_summary=facts_polished)
    if not pdf_ok:
        logger.error(f"主文书 PDF 转换失败: {main_docx_path}")

    generated_docs.append({
        "doc_type": doc_label,
        "filename_docx": main_docx_name,
        "path": main_docx_path,
        "docx_url": f"/api/documents/download/{main_docx_name}",
        "filename_pdf": main_pdf_name if pdf_ok else None,
        "pdf_path": main_pdf_path if pdf_ok else None,
        "pdf_url": f"/api/documents/download/{main_pdf_name}" if pdf_ok else None,
    })

    if req.auto_generate_sub_docs:
        poa_tpl = os.path.join(_templates_dir(), "power_of_attorney_template.docx")
        poa_docx_name = f"民事授权委托书_{safe_party_name}_{timestamp}.docx"
        poa_docx_path = os.path.join(str(get_generated_dir()), poa_docx_name)
        poa_pdf_name = f"民事授权委托书_{safe_party_name}_{timestamp}.pdf"
        poa_pdf_path = os.path.join(str(get_generated_dir()), poa_pdf_name)

        doc_poa = DocxTemplate(poa_tpl)
        doc_poa.render({
            "client_name": plaintiff["name"],
            "client_id": plaintiff["id_card_or_uscc"],
            "client_phone": plaintiff.get("phone") or PLACEHOLDER,
            "opponent_name": defendant["name"],
            "cause_of_action": req.cause_of_action,
            "lawyer_name": req.lawyer_name,
            "law_firm": req.law_firm,
            "lawyer_license": req.lawyer_license,
            "lawyer_phone": req.lawyer_phone,
            "court_name": court_full,
            "authorization_scope": "□一般代理  □特别授权（□代为承认、放弃、变更诉讼请求 □进行和解 □提起反诉或上诉）",
            "sign_date": filing_date_str,
        })
        doc_poa.save(poa_docx_path)
        await convert_docx_to_pdf(poa_docx_path, poa_pdf_path, title="民事授权委托书")
        generated_docs.append({
            "doc_type": "民事授权委托书",
            "filename_docx": poa_docx_name,
            "docx_url": f"/api/documents/download/{poa_docx_name}",
            "filename_pdf": poa_pdf_name,
            "pdf_url": f"/api/documents/download/{poa_pdf_name}",
        })

        addr_tpl = os.path.join(_templates_dir(), "service_address_template.docx")
        addr_docx_name = f"送达地址确认书_{safe_party_name}_{timestamp}.docx"
        addr_docx_path = os.path.join(str(get_generated_dir()), addr_docx_name)
        doc_addr = DocxTemplate(addr_tpl)
        doc_addr.render({
            "cause_of_action": req.cause_of_action,
            "recipient_name": plaintiff["name"],
            "recipient_id": plaintiff["id_card_or_uscc"],
            "lawyer_name": req.lawyer_name,
            "law_firm": req.law_firm,
            "lawyer_phone": req.lawyer_phone,
            "mail_address": plaintiff["address"],
            "postal_code": PLACEHOLDER,
            "mobile_phone": plaintiff.get("phone") or PLACEHOLDER,
            "email_address": PLACEHOLDER,
            "electronic_methods": "短信、电子邮件、统一微法院",
            "sign_date": filing_date_str,
        })
        doc_addr.save(addr_docx_path)
        generated_docs.append({
            "doc_type": "送达地址确认书",
            "filename_docx": addr_docx_name,
            "docx_url": f"/api/documents/download/{addr_docx_name}",
        })

        if "买卖" in req.cause_of_action or "借贷" in req.cause_of_action:
            preserv_tpl = os.path.join(_templates_dir(), "property_preservation_template.docx")
            preserv_docx_name = f"财产保全申请书_{safe_party_name}_{timestamp}.docx"
            preserv_docx_path = os.path.join(str(get_generated_dir()), preserv_docx_name)
            doc_preserv = DocxTemplate(preserv_tpl)
            doc_preserv.render({
                "applicant_name": plaintiff["name"],
                "applicant_id": plaintiff["id_card_or_uscc"],
                "applicant_phone": plaintiff.get("phone") or PLACEHOLDER,
                "applicant_address": plaintiff["address"],
                "applicant_legal_rep": plaintiff.get("legal_rep") or PLACEHOLDER,
                "respondent_name": defendant["name"],
                "respondent_id": defendant["id_card_or_uscc"],
                "respondent_address": defendant["address"],
                "preservation_amount": f"{req.claim_amount:,.2f}",
                "preservation_amount_capital": rmb_to_capital(req.claim_amount),
                "cause_of_action": req.cause_of_action,
                "property_clues": f"1. 被申请人名下银行基本存款账户；\n2. 被申请人名下位于 {defendant['address']} 之不动产或经营设备。",
                "guarantee_method": PLACEHOLDER,
                "guarantee_institution": PLACEHOLDER,
                "preservation_type_pre": "□",
                "preservation_type_in": "□",
                "case_number": PLACEHOLDER,
                "court_name": court_full,
                "sign_date": filing_date_str,
            })
            doc_preserv.save(preserv_docx_path)
            generated_docs.append({
                "doc_type": "财产保全申请书",
                "filename_docx": preserv_docx_name,
                "docx_url": f"/api/documents/download/{preserv_docx_name}",
            })

        if is_labor:
            labor_tpl = os.path.join(_templates_dir(), "labor_compensation_calc_template.docx")
            labor_docx_name = f"经济补偿金计算清单_{safe_party_name}_{timestamp}.docx"
            labor_docx_path = os.path.join(str(get_generated_dir()), labor_docx_name)
            labor_calc = calculate_labor_compensation(12000, "2021-03-01", datetime.now().strftime("%Y-%m-%d"))
            doc_labor = DocxTemplate(labor_tpl)
            doc_labor.render({
                "applicant_name": plaintiff["name"],
                "respondent_name": defendant["name"],
                "hire_date": PLACEHOLDER,
                "termination_date": filing_date_str,
                "tenure_str": labor_calc["tenure_str"],
                "monthly_salary": PLACEHOLDER,
                "compensation_months": f"{labor_calc['compensation_months']}",
                "amount_n": f"{labor_calc['tiers']['N']['amount']:,.2f}",
                "amount_plus_1_notice": f"{labor_calc['tiers']['N+1']['notice_pay']:,.2f}",
                "amount_2n": f"{labor_calc['tiers']['2N']['amount']:,.2f}",
                "cap_reason": labor_calc["cap_reason"],
                "filing_date": filing_date_str,
            })
            doc_labor.save(labor_docx_path)
            generated_docs.append({
                "doc_type": "经济补偿金计算清单",
                "filename_docx": labor_docx_name,
                "docx_url": f"/api/documents/download/{labor_docx_name}",
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
        "missing_fields": missing_fields,
        "generated_documents": generated_docs,
        "main_docx_path": main_docx_path,
        "main_pdf_path": main_pdf_path if pdf_ok else None,
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
    claim_amount: Optional[float] = Field(default=None, description="回购或争议标的金额")
    agreed_repurchase_rate: Optional[float] = Field(default=None, description="合同约定年化回购溢价/违约金率")
    first_instance_court: str = Field(..., description="作出一审判决之法院名称（必填，无默认）")
    first_instance_errors: Optional[List[str]] = Field(default=None, description="一审争议与错误倾向")
    use_demo: bool = Field(default=False, description="为 true 时载入 data/demo/appeal_demo.json")
    appellant: Optional[PartyInfo] = Field(default=None, description="上诉人完整身份信息")
    appellee: Optional[PartyInfo] = Field(default=None, description="被上诉人完整身份信息")
    first_instance_case_no: Optional[str] = Field(default=None, description="原审案号")
    cause_of_action: Optional[str] = Field(default=None, description="案由")
    appellate_court: Optional[str] = Field(default=None, description="二审法院；未填则文书写待填写上一级法院")
    judgment_type: Optional[Literal["judgment", "ruling"]] = Field(default=None, description="判决或裁定")
    service_date: Optional[str] = Field(default=None, description="送达日期 YYYY-MM-DD")
    include_preservation_insurance: bool = Field(
        default=False,
        description="用户明确提供时才写入保全责任险保费诉请",
    )


class AppealExportDocxRequest(BaseModel):
    title: str = Field(default="二审上诉文书", description="文档标题")
    content_text: str = Field(..., description="文书正文文本")
    doc_type: str = Field(default="appeal_pleading", description="appeal_pleading 或 appeal_memo")


@router.post("/api/v1/litigation/appeal-audit", summary="二审/再审一审判决漏洞剖析与最高院类案分歧穿透")
@router.post("/api/v1/phase1/appeal-audit", summary="二审/再审一审判决漏洞剖析与最高院类案分歧穿透（别名）")
async def api_appeal_audit(req: AppealAuditRequest):
    try:
        appeal_deadline = None
        if req.service_date and req.judgment_type:
            try:
                appeal_deadline = calculate_appeal_deadline(
                    req.service_date, req.judgment_type
                ).get("deadline")
            except ValueError:
                appeal_deadline = None
        res = analyze_first_instance_judgment_and_precedents(
            judgment_text=req.judgment_text or "",
            case_title=req.case_title,
            claim_amount=req.claim_amount,
            agreed_repurchase_rate=req.agreed_repurchase_rate,
            first_instance_court=req.first_instance_court,
            first_instance_errors=req.first_instance_errors,
            use_demo=req.use_demo,
            appellant=req.appellant.model_dump() if req.appellant else None,
            appellee=req.appellee.model_dump() if req.appellee else None,
            first_instance_case_no=req.first_instance_case_no,
            cause_of_action=req.cause_of_action,
            appellate_court=req.appellate_court,
            judgment_type=req.judgment_type,
            service_date=req.service_date,
            include_preservation_insurance=req.include_preservation_insurance,
            appeal_deadline=appeal_deadline,
        )
        if appeal_deadline:
            res["appeal_deadline"] = appeal_deadline
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

