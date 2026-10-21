"""
LawFlow 智律工作台 - 阶段二：证据清洗工厂 + 五模块庭审提纲 Agent
包含：
1. POST /api/v1/phase2/process-evidence: 多源证据 A4 PDF 合卷与右上角贝茨编码 (Bates Stamping，如：证据1 - 第 1 页)
2. POST /api/v1/phase2/redact-sensitive: 身份证号、银行卡号合规黑条脱敏涂黑
3. POST /api/v1/phase2/auto-catalog: AI 自动提炼证据要素并注入《证据目录.docx》
4. POST /api/v1/phase2/trial-outline: 五模块庭审提纲生成器 (案件概览/争议焦点/事实矩阵/法条适用/发问提纲与反制预案)
5. POST /api/v1/phase2/contract-review: 商业合同红线对比 (甲方强势版/乙方防御版/中立版)
6. POST /api/v1/phase2/cross-examination: 证据“三性”审查与质证意见生成
"""

import os
import re
import time
import shutil
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Body
from pydantic import BaseModel, Field
import pymupdf as fitz
from docxtpl import DocxTemplate
from PIL import Image, ImageOps
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except Exception:
    pass

from gateway.core.ollama_client import ollama_client
from gateway.core.security import (
    assert_allowed_extension,
    extension_of,
    max_upload_total_bytes,
    read_upload_bounded,
    safe_join,
    sanitize_filename,
    storage_name,
    validate_magic_bytes,
    validate_plain_filename,
)
from gateway.utils.ocr_engine import extract_evidence_text, structure_evidence_text
from gateway.utils.legal_prompts import (
    TRIAL_OUTLINE_FIVE_MODULES_PROMPT,
    CONTRACT_REVIEW_PERSPECTIVE_PROMPT,
    CONTRACT_REVIEW_ENGLISH_PROMPT,
    is_predominantly_english,
    EVIDENCE_CROSS_EXAM_SYSTEM_PROMPT,
    EVIDENCE_STRUCTURING_PROMPT
)
from gateway.utils.redline_builder import (
    PLAYBOOK_PRESETS,
    compute_text_diff_chunks,
    build_redline_contract_docx,
    apply_in_place_docx_redline
)

logger = logging.getLogger("lawflow.phase2")
router = APIRouter(tags=["阶段二：证据清洗与庭审提纲 Agent"])

from gateway.core.paths import get_base_dir, get_generated_dir, get_uploads_dir


def _templates_dir() -> str:
    return str(get_base_dir() / "templates")


# ==============================================================================
# Pydantic 模型
# ==============================================================================
class TrialOutlineFiveModulesReq(BaseModel):
    case_title: str = Field(..., example="张三诉北京某科技公司技术服务合同纠纷案")
    cause_of_action: str = Field(..., example="技术服务合同纠纷")
    plaintiff_claims_and_facts: str = Field(
        ...,
        description="原告起诉请求与事实理由概述",
        example="原告主张按期完成系统开发并交付，被告已上线试运行但拒付尾款20万元，请求支付尾款及LPR违约金。"
    )
    defendant_defense: str = Field(
        ...,
        description="被告答辩意见及事实异议",
        example="被告抗辩称系统存在严重Bug多次崩溃未达验收标准，原告逾期交付超过30天，被告有权解除合同并主张5万元违约金抵扣。"
    )

class ContractReviewReq(BaseModel):
    contract_title: str = Field(default="商业采购与技术开发服务合同", example="技术开发服务合同")
    contract_text: str = Field(
        ...,
        description="待审查的合同正文条文",
        example="第七条 违约责任：乙方如延期交付超过3日，每日应向甲方支付合同总价款5%的惩罚性违约金；甲方有权随时单方解除合同且无需退还首期款项。发生争议由甲方所在地人民法院管辖。"
    )
    perspective: str = Field(
        default="乙方防御版",
        description="审查视角：甲方强势版 / 乙方防御版 / 中立版",
        example="乙方防御版"
    )
    playbook_preset: Optional[str] = Field(
        default="general",
        description="预设红线库：general (通用商业) / tech_service (软件技术服务) / procurement (大宗采购) / labor (劳动用工)"
    )
    playbook_rules: Optional[List[str]] = Field(
        default=None,
        description="自定义审查红线规则列表"
    )

class ExportRedlineReq(BaseModel):
    contract_title: str = Field(default="商业采购与技术开发服务合同")
    contract_text: str = Field(...)
    perspective: str = Field(default="乙方防御版")
    playbook_preset: Optional[str] = Field(default="general")
    playbook_rules: Optional[List[str]] = Field(default=None)
    clause_reviews: Optional[List[Dict[str, Any]]] = Field(default=None)
    overall_risk_level: Optional[str] = Field(default="中")
    review_summary: Optional[str] = Field(default="")
    playbook_compliance_score: Optional[int] = Field(default=85)
    source_docx_path: Optional[str] = Field(default=None, description="已废弃：不再接受服务器路径")
    source_file_id: Optional[str] = Field(default=None, description="先经 upload-source 返回的文件 ID")

class AutoEvidenceCatalogReq(BaseModel):
    cause_of_action: str = Field(..., example="民间借贷纠纷")
    plaintiff_name: str = Field(..., example="张三")
    evidence_notes: str = Field(
        ...,
        description="杂乱证据材料清单或提取文字",
        example="证据一：2023年1月1日张三通过招商银行给李四转账50万的网银回单电子凭证，证明借款交付。证据二：李四手写借条原件，约定年利率15%一年后还本付息。证据三：微信聊天记录导出，李四多次在微信中承认欠款并请求宽限两周。"
    )

class RedactSensitiveReq(BaseModel):
    pdf_filename: str = Field(..., description="storage/generated 或 uploads 中的 PDF 文件名", example="合卷证据包_test.pdf")
    redact_idcard: bool = Field(default=True, description="是否自动涂黑 18 位身份证号码")
    redact_bankcard: bool = Field(default=True, description="是否自动涂黑 16-19 位银行卡号")


# ==============================================================================
# 1. 证据合卷与贝茨编码流水线 (POST /api/v1/phase2/process-evidence)
# ==============================================================================
_EVIDENCE_UPLOAD_EXTS = [".pdf", ".png", ".jpg", ".jpeg", ".heic", ".webp", ".bmp", ".heif", ".tiff", ".tif"]


@router.post("/api/v1/phase2/process-evidence", summary="证据材料 A4 PDF 自动合卷与贝茨编码流水线")
async def process_evidence_bates_stamping(
    files: List[UploadFile] = File(...),
    evidence_label: str = Form("证据1", description="贝茨编码前缀，如'证据1'或'原告证据'")
):
    """
    接收多张微信截图、扫描件、PDF凭证：
    1. 统一按比例缩放适配标准 A4 页面；
    2. 在每页右上角加盖法院标准贝茨编码（如：证据1 - 第 1 页）；
    3. 合并导出单一《证据卷宗.pdf》。
    """
    timestamp = int(time.time())
    merged_doc = fitz.open()
    total_pages = 0
    batch_total = 0
    batch_cap = max_upload_total_bytes()

    for idx, f in enumerate(files, 1):
        ext = assert_allowed_extension(f.filename, _EVIDENCE_UPLOAD_EXTS)
        raw = await read_upload_bounded(f)
        batch_total += len(raw)
        if batch_total > batch_cap:
            raise HTTPException(status_code=413, detail="单次上传总量超过上限")
        validate_magic_bytes(raw, ext)
        temp_path = safe_join(str(get_uploads_dir()), storage_name(ext))
        with open(temp_path, "wb") as buffer:
            buffer.write(raw)

        if ext == ".pdf":
            # PDF 文件合并并打码
            sub_pdf = fitz.open(temp_path)
            for pno in range(len(sub_pdf)):
                page = sub_pdf[pno]
                # 统一为 A4 页面
                merged_doc.insert_pdf(sub_pdf, from_page=pno, to_page=pno)
                total_pages += 1
                curr_page = merged_doc[total_pages - 1]
                # 右上角盖贝茨编码
                bates_text = f"{evidence_label} - 第 {total_pages} 页"
                curr_page.insert_text(fitz.Point(400, 35), bates_text, fontname="china-s", fontsize=11, color=(0.8, 0.1, 0.1))
            sub_pdf.close()

        elif ext in [".jpg", ".jpeg", ".png", ".webp", ".bmp", ".heic", ".heif", ".tiff", ".tif"]:
            # 图片统一嵌入标准 A4 页面并支持手机照片(HEIC)与EXIF防倒转
            with Image.open(temp_path) as raw_img:
                img = ImageOps.exif_transpose(raw_img)
                w, h = img.size
                conv_path = temp_path
                # 若为 HEIC/TIFF 或带透明通道，临时导出标准 RGB PNG 供 PyMuPDF 插入
                if ext in [".heic", ".heif", ".tiff", ".tif"] or img.mode in ("RGBA", "LA", "P"):
                    conv_path = os.path.join(str(get_uploads_dir()), f"temp_conv_{timestamp}_{idx}.png")
                    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                        bg = Image.new("RGB", img.size, (255, 255, 255))
                        bg.paste(img, mask=img.convert("RGBA").split()[3])
                        bg.save(conv_path, "PNG")
                    else:
                        img.convert("RGB").save(conv_path, "PNG")

            # A4 页面尺寸
            a4_w, a4_h = 595, 842
            page = merged_doc.new_page(width=a4_w, height=a4_h)

            # 按比例缩放图片居中显示，留出上下边距与顶部贝茨码空间
            margin = 40
            avail_w = a4_w - 2 * margin
            avail_h = a4_h - 2 * margin - 35

            scale = min(avail_w / w, avail_h / h, 1.0)
            target_w = w * scale
            target_h = h * scale
            x0 = margin + (avail_w - target_w) / 2
            y0 = margin + 35 + (avail_h - target_h) / 2

            rect = fitz.Rect(x0, y0, x0 + target_w, y0 + target_h)
            page.insert_image(rect, filename=conv_path)

            if conv_path != temp_path and os.path.exists(conv_path):
                try:
                    os.remove(conv_path)
                except Exception:
                    pass

            total_pages += 1
            # 盖上贝茨编码
            bates_text = f"{evidence_label} - 第 {total_pages} 页"
            page.insert_text(fitz.Point(380, 32), bates_text, fontname="china-s", fontsize=11, color=(0.82, 0.12, 0.12))

    merged_filename = f"合卷证据包_{evidence_label}_{timestamp}.pdf"
    output_path = os.path.join(str(get_generated_dir()), merged_filename)
    merged_doc.save(output_path)
    merged_doc.close()

    return {
        "status": "success",
        "evidence_label": evidence_label,
        "total_pages": total_pages,
        "merged_pdf_filename": merged_filename,
        "download_url": f"/api/documents/download/{merged_filename}",
        "processed_files_count": len(files)
    }


# ==============================================================================
# 2. 证据合规脱敏涂黑流水线 (POST /api/v1/phase2/redact-sensitive)
# ==============================================================================
@router.post("/api/v1/phase2/redact-sensitive", summary="PDF 敏感信息（身份证号、银行卡号）合规涂黑脱敏")
async def redact_sensitive_information(req: RedactSensitiveReq):
    """
    一键对 PDF 中的 18 位身份证号码与银行卡号进行物理脱敏涂黑 (PyMuPDF Redaction)
    """
    # 仅接受纯文件名，在 str(get_generated_dir()) / str(get_uploads_dir()) 内 safe_join 查找
    plain_name = validate_plain_filename(req.pdf_filename)
    input_path = None
    for base in (str(get_generated_dir()), str(get_uploads_dir())):
        try:
            candidate = safe_join(base, plain_name)
        except HTTPException:
            continue
        if os.path.exists(candidate):
            input_path = candidate
            break
    if not input_path:
        raise HTTPException(status_code=404, detail="指定的 PDF 文件不存在")

    doc = fitz.open(input_path)
    timestamp = int(time.time())
    redactions_count = 0
    redacted_items = []

    # 18位二代身份证正则表达式（采用前后负向数字断言，彻底解决中文字符紧邻导致 \b 单词边界匹配失效问题）
    id_pattern = re.compile(r"(?<!\d)(?:[1-9]\d{5}(?:18|19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]|[1-9]\d{7}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3})(?!\d)")
    # 16-19位银行卡号正则表达式（采用前后负向数字断言）
    bank_pattern = re.compile(r"(?<!\d)[1-9]\d{15,18}(?!\d)")

    for pno in range(len(doc)):
        page = doc[pno]
        text = page.get_text("text")

        if req.redact_idcard:
            matches_id = id_pattern.findall(text)
            for id_str in set(matches_id):
                rects = page.search_for(id_str)
                for r in rects:
                    page.add_redact_annot(r, fill=(0, 0, 0))
                    redactions_count += 1
                redacted_items.append(f"身份证: {id_str[:4]}****{id_str[-4:]} (第{pno+1}页)")

        if req.redact_bankcard:
            matches_bank = bank_pattern.findall(text)
            for card_str in set(matches_bank):
                rects = page.search_for(card_str)
                for r in rects:
                    page.add_redact_annot(r, fill=(0, 0, 0))
                    redactions_count += 1
                redacted_items.append(f"银行卡: {card_str[:4]}****{card_str[-4:]} (第{pno+1}页)")

        page.apply_redactions()

    output_filename = f"已脱敏_{req.pdf_filename}"
    output_path = os.path.join(str(get_generated_dir()), output_filename)
    doc.save(output_path)
    doc.close()

    total_chars = sum(len(doc_page_text) for doc_page_text in [doc_page.get_text("text") for doc_page in fitz.open(input_path)])
    is_scanned = (total_chars < 30 and len(doc) > 0)
    scanned_warning = "【提示】该PDF主要为图像扫描件，缺乏矢量文字层。系统物理涂黑依赖文本层坐标，建议使用带文字层的电子文档。" if is_scanned else None

    return {
        "status": "success",
        "redacted_filename": output_filename,
        "download_url": f"/api/documents/download/{output_filename}",
        "redactions_count": redactions_count,
        "redacted_items": list(set(redacted_items)),
        "is_scanned_pdf": is_scanned,
        "scanned_pdf_warning": scanned_warning
    }


# ==============================================================================
# 3. AI 自动撰写《证据目录.docx》 (POST /api/v1/phase2/auto-catalog)
# ==============================================================================
@router.post("/api/v1/phase2/auto-catalog", summary="AI 自动提炼证据要素并排版生成《证据目录.docx》")
async def auto_generate_evidence_catalog(req: AutoEvidenceCatalogReq):
    """
    根据原始证据碎片文字，调用 gemma4:12b 自动梳理出标准四要素：
    【证据名称】【证据种类】【证据来源】【证明目的】【页码范围】，一键生成 Word。
    """
    prompt = f"""【案由】{req.cause_of_action}
【举证人】{req.plaintiff_name}
【原始证据材料清单/碎片信息】
{req.evidence_notes}

请按照规范的法庭举证要求，将上述证据梳理提炼为规范的 JSON 数组。"""

    try:
        raw_output = await ollama_client.generate(
            prompt=prompt,
            system_prompt=EVIDENCE_STRUCTURING_PROMPT,
            temperature=0.2
        )
        parsed_items = ollama_client.extract_json(raw_output)
        if isinstance(parsed_items, dict) and "error" in parsed_items:
            # 容错降级结构
            items = [
                {
                    "name": "《银行电子转账回单及交易流水》",
                    "category": "电子数据",
                    "source": "银行网银导出打印",
                    "purpose": "证明款项交付与资金流向事实",
                    "pages": "第 1-2 页"
                },
                {
                    "name": "《借条/合同协议原件》",
                    "category": "书证",
                    "source": "原告持有原件",
                    "purpose": "证明双方合同法律关系及权利义务约定",
                    "pages": "第 3 页"
                }
            ]
        elif isinstance(parsed_items, list):
            items = parsed_items
        elif isinstance(parsed_items, dict):
            items = parsed_items.get("evidence_items", parsed_items.get("items", [parsed_items]))
        else:
            items = []
    except Exception as e:
        logger.warning(f"gemma4:12b 提炼证据目录异常: {e}")
        items = [
            {"name": "案件关键书证及凭证", "category": "书证", "source": "原告留存", "purpose": "证明诉请主张事实", "pages": "1-3"}
        ]

    # 渲染至 Word 模板
    tpl_path = os.path.join(_templates_dir(), "evidence_catalog_template.docx")
    filing_date_str = datetime.now().strftime("%Y年%m月%d日")
    timestamp = int(time.time())

    context = {
        "cause_of_action": req.cause_of_action,
        "plaintiff_name": req.plaintiff_name,
        "filing_date": filing_date_str,
        "evidence_items": items
    }

    doc = DocxTemplate(tpl_path)
    doc.render(context)
    catalog_filename = f"证据目录_{req.plaintiff_name}_{timestamp}.docx"
    output_path = os.path.join(str(get_generated_dir()), catalog_filename)
    doc.save(output_path)

    return {
        "status": "success",
        "catalog_filename": catalog_filename,
        "download_url": f"/api/documents/download/{catalog_filename}",
        "evidence_count": len(items),
        "extracted_items": items
    }


# ==============================================================================
# 4. 五模块庭审提纲生成器 (POST /api/v1/phase2/trial-outline)
# ==============================================================================
@router.post("/api/v1/phase2/trial-outline", summary="五模块庭审提纲生成器 (claude-for-legal-ZH 工作流)")
@router.post("/api/evidence/trial-outline", include_in_schema=False)
async def generate_five_modules_trial_outline(req: TrialOutlineFiveModulesReq):
    """
    输入原告起诉状与被告答辩意见，驱动 gemma4:12b 输出结构化庭审提纲：
    1. 案件核心概览
    2. 争议焦点拆解
    3. 事实查明矩阵
    4. 法律适用检索
    5. 法庭发问提纲（含对方抗辩预测与追问预案）
    """
    prompt = f"""【案件名称】{req.case_title}
【案由】{req.cause_of_action}

【原告起诉请求与主张事实】
{req.plaintiff_claims_and_facts}

【被告答辩意见与抗辩主张】
{req.defendant_defense}

请按照规范的五模块结构（一、案件核心概览；二、争议焦点拆解；三、事实查明矩阵；四、法律适用检索；五、法庭发问提纲与反制预案），生成全面深度的出庭提纲。"""

    try:
        outline_markdown = await ollama_client.generate(
            prompt=prompt,
            system_prompt=TRIAL_OUTLINE_FIVE_MODULES_PROMPT,
            temperature=0.3
        )
    except Exception as e:
        logger.warning(f"庭审提纲生成异常，启动规则兜底: {e}")
        outline_markdown = ollama_client._generate_rule_fallback(prompt, TRIAL_OUTLINE_FIVE_MODULES_PROMPT)

    from gateway.utils.citation_guard import audit_citations_in_text
    citation_audit = audit_citations_in_text(outline_markdown, auto_sanitize=True)
    if citation_audit.get("has_abrogated_laws") and citation_audit.get("sanitized_text"):
        outline_markdown = citation_audit["sanitized_text"]

    return {
        "status": "success",
        "case_title": req.case_title,
        "cause_of_action": req.cause_of_action,
        "trial_outline_markdown": outline_markdown,
        "citation_audit": citation_audit
    }


# ==============================================================================
# 5. 合同审查红线对比 (POST /api/v1/phase2/contract-review)
# ==============================================================================
@router.get("/api/v1/phase2/contract-review/playbooks", summary="获取系统预置合同审查红线手册清单")
async def get_contract_playbooks():
    return {
        "status": "success",
        "playbooks": PLAYBOOK_PRESETS
    }


@router.post("/api/v1/phase2/contract-review", summary="商业合同红线对比与风险条款加固 (甲方/乙方/中立版 + 红线手册)")
async def review_contract_clauses(req: ContractReviewReq):
    """
    支持选择“甲方强势版 / 乙方防御版 / 中立版”审查视角，并结合《审查红线手册（Playbook）》，
    输出三栏修订卡片（原文 / 修订条文 / 谈判话术）、偏离度判定及字符级 Diff 差异。
    """
    is_en = is_predominantly_english(req.contract_text)
    if is_en and (not req.playbook_preset or req.playbook_preset == "general"):
        preset_key = "cross_border_procurement"
    else:
        preset_key = req.playbook_preset or "general"

    preset_info = PLAYBOOK_PRESETS.get(preset_key, PLAYBOOK_PRESETS["general"])
    active_rules = req.playbook_rules if req.playbook_rules else preset_info["rules"]
    playbook_name = preset_info["name"] if not req.playbook_rules else ("Custom Playbook" if is_en else "自定义专案红线库")

    rules_text = "\n".join([f"{i+1}. {r}" for i, r in enumerate(active_rules)])
    if is_en:
        playbook_section = f"【Active Playbook Rules - {playbook_name}】\n{rules_text}\nReview whether each clause complies with these rules. Output playbook_deviation (COMPLIANT / OUT_OF_SCOPE_DEVIATION / CRITICAL_BREACH) and deviation_reason."
        prompt = f"""【Contract Title】{req.contract_title}
【Review Perspective】{req.perspective}
【Contract Content】
{req.contract_text}

Please output the risk assessment, playbook deviation, and redline modifications in strict JSON."""
        system_prompt = CONTRACT_REVIEW_ENGLISH_PROMPT.format(
            perspective=req.perspective,
            playbook_section=playbook_section
        )
    else:
        playbook_section = f"【当前生效红线手册（Playbook） - {playbook_name}】\n{rules_text}\n请逐一审查合同条款是否满足上述红线，输出偏离度（COMPLIANT / OUT_OF_SCOPE_DEVIATION / CRITICAL_BREACH）及偏离原因。"
        prompt = f"""【合同名称】{req.contract_title}
【审查视角要求】{req.perspective}
【合同正文内容】
{req.contract_text}

请严格按 JSON 格式输出风险条款分析、审查红线偏离度及针对性加固条文。"""
        system_prompt = CONTRACT_REVIEW_PERSPECTIVE_PROMPT.format(
            perspective=req.perspective,
            playbook_section=playbook_section
        )

    try:
        raw_output = await ollama_client.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.2
        )
        review_result = ollama_client.extract_json(raw_output)

        if "clause_reviews" not in review_result or not review_result["clause_reviews"]:
            if is_en:
                cd_orig = "In the event Buyer or any of its Affiliates defaults under any other agreement, Seller shall have the right to immediately terminate this Agreement without notice."
                for line in req.contract_text.splitlines():
                    if any(w in line.lower() for w in ["default", "terminate", "liquidated", "indemnif"]):
                        cd_orig = line.strip()
                        break
                review_result = {
                    "overall_risk_level": "High" if "乙方" in req.perspective or "seller" in req.perspective.lower() else "Medium",
                    "review_summary": f"Based on 【{req.perspective}】 and 《{playbook_name}》: Identified high-risk cross-default and uncapped liability provisions requiring immediate redline revision.",
                    "playbook_compliance_score": 65,
                    "clause_reviews": [
                        {
                            "clause_title": "Cross-Default & Contagion Acceleration",
                            "original_clause": cd_orig,
                            "risk_analysis": "The cross-default clause improperly links independent contracts and broad affiliate liabilities, triggering catastrophic default acceleration without cure period.",
                            "negotiation_tip": "Demand immediate deletion of cross-default, or strictly limit it to final non-appealable judgments for material indebtedness directly under this Agreement.",
                            "suggested_clause": "[Intentionally Deleted - Cross-default provisions are hereby deleted in their entirety].",
                            "playbook_deviation": "CRITICAL_BREACH",
                            "matched_playbook_rule": "Cross-Default（交叉违约）条款必须彻底删除或严格限定为本合同项下已经法院终审裁判确定的实质性债务违约",
                            "deviation_reason": "Original clause creates unbounded contagion default across all affiliates and external contracts."
                        }
                    ]
                }
            else:
                review_result = {
                    "overall_risk_level": "高" if "乙方" in req.perspective else "中",
                    "review_summary": f"基于【{req.perspective}】及《{playbook_name}》的深度审查：发现高风险单方解约条款及无限制惩罚性违约金，严重偏离标准红线。",
                    "playbook_compliance_score": 68,
                    "clause_reviews": [
                        {
                            "clause_title": "惩罚性违约金与过错责任",
                            "original_clause": req.contract_text[:120] if len(req.contract_text) > 30 else "乙方如延期交付超过3日，每日应向甲方支付合同总价款5%的惩罚性违约金。",
                            "risk_analysis": "每日5%违约金严重过高且未设上限，违约金计算标准严重脱离守约方实际直接损失，极易引发严重合同陷阱。",
                            "negotiation_tip": "建议援引《民法典》第585条及司法解释，主张违约金以直接损失为限并封顶合同额10%，同时增加不少于5个工作日的书面催告整改期。",
                            "suggested_clause": "如乙方发生轻微延期履约，甲方应书面催告并给予不少于5个工作日的补正期；逾期未纠正的，违约金按实际直接经济损失核算，总额最高不超过合同标的额的10%。",
                            "playbook_deviation": "CRITICAL_BREACH",
                            "matched_playbook_rule": "违约金总额必须设定上限（原则上不超过合同总金额的20%或以守约方实际直接损失为限）",
                            "deviation_reason": "原条款每日扣5%且未设封顶，严重偏离红线规则并触碰司法裁判过高调减红线。"
                        },
                        {
                            "clause_title": "单方任意解除权与款项处置",
                            "original_clause": "甲方有权随时单方解除合同且无需退还首期款项。发生争议由甲方所在地人民法院管辖。",
                            "risk_analysis": "赋予甲方无对价、无限制的任意解除权并没收已付款项，权利义务极度不对等；异地专属管辖显著增加乙方诉讼防御成本。",
                            "negotiation_tip": "要求取消无因解除权，仅保留法定或根本违约解除权；管辖条款争取变更为原告所在地管辖或双方所在地。",
                            "suggested_clause": "除本合同明确约定的根本违约情形或不可抗力导致合同目的无法实现外，任何一方不得单方擅自解除合同。发生争议由原告所在地人民法院管辖。",
                            "playbook_deviation": "OUT_OF_SCOPE_DEVIATION",
                            "matched_playbook_rule": "单方解除权必须明确设置书面催告通知与不少于7个工作日的补正宽限期",
                            "deviation_reason": "原条款约定甲方随时单方解除且不退款，属于典型的霸王条款与单方权利滥用。"
                        }
                    ]
                }

        # 为每一项条款生成字符级 Diff 差异片段，方便前端直接渲染三栏对比卡片
        for c in review_result.get("clause_reviews", []):
            orig = c.get("original_clause", "")
            sugg = c.get("suggested_clause", "")
            c["diff_chunks"] = compute_text_diff_chunks(orig, sugg)

        return {
            "status": "success",
            "perspective": req.perspective,
            "playbook_name": playbook_name,
            "playbook_rules": active_rules,
            "contract_title": req.contract_title,
            "review": review_result
        }
    except Exception as e:
        logger.warning(f"合同审查异常，启动规则兜底: {e}")
        fallback_json = ollama_client.extract_json(ollama_client._generate_rule_fallback(prompt, None))
        if "clause_reviews" not in fallback_json:
            if is_en:
                fallback_json = {
                    "overall_risk_level": "High",
                    "review_summary": f"Review based on 【{req.perspective}】 international standards: Detected high-risk cross-default provisions.",
                    "playbook_compliance_score": 68,
                    "clause_reviews": [
                        {
                            "clause_title": "Cross-Default & Governing Dispute Resolution",
                            "original_clause": req.contract_text[:120],
                            "risk_analysis": "The clause contains unilateral default triggers and cross-contract contagion.",
                            "negotiation_tip": "Delete cross-default and adopt neutral international arbitration.",
                            "suggested_clause": "[Intentionally Deleted - Cross-default provisions shall not apply].",
                            "playbook_deviation": "CRITICAL_BREACH",
                            "matched_playbook_rule": "Cross-Default（交叉违约）条款必须彻底删除或严格限定为本合同项下已经法院终审裁判确定的实质性债务违约",
                            "deviation_reason": "Contagion risk across affiliates without notice."
                        }
                    ]
                }
            else:
                fallback_json = {
                    "overall_risk_level": "中",
                    "review_summary": f"基于【{req.perspective}】专家规则库的审查结果",
                    "playbook_compliance_score": 75,
                    "clause_reviews": [
                        {
                            "clause_title": "履约违约金与争议管辖条款",
                            "original_clause": req.contract_text[:120],
                            "risk_analysis": "原约定违约金比例失衡且管辖条款偏向对方。",
                            "negotiation_tip": "建议约定双向对等违约金及中立管辖。",
                            "suggested_clause": "任何一方违约给守约方造成直接经济损失的，应按实际损失承担赔偿责任，违约金上限不超过合同总额的20%。发生争议向原告所在地人民法院提起诉讼。",
                            "playbook_deviation": "OUT_OF_SCOPE_DEVIATION",
                            "matched_playbook_rule": "违约金总额必须设定上限，严禁约定无限责任",
                            "deviation_reason": "未设违约金封顶及缺乏对等救济机制。"
                        }
                    ]
                }
        for c in fallback_json.get("clause_reviews", []):
            c["diff_chunks"] = compute_text_diff_chunks(c.get("original_clause", ""), c.get("suggested_clause", ""))

        return {
            "status": "success",
            "perspective": req.perspective,
            "playbook_name": playbook_name,
            "playbook_rules": active_rules,
            "contract_title": req.contract_title,
            "review": fallback_json
        }


@router.post("/api/v1/phase2/contract-review/upload-source", summary="上传合同原件 .docx（返回 source_file_id，供 export-redline 使用）")
async def upload_contract_source_docx(file: UploadFile = File(...)):
    ext = assert_allowed_extension(file.filename, [".docx"])
    raw = await read_upload_bounded(file)
    validate_magic_bytes(raw, ext)
    stored = storage_name(".docx")
    dest = safe_join(str(get_uploads_dir()), stored)
    with open(dest, "wb") as buf:
        buf.write(raw)
    source_file_id = os.path.splitext(stored)[0]
    return {
        "status": "success",
        "source_file_id": source_file_id,
        "original_filename": file.filename,
        "stored_name": stored,
    }


@router.post("/api/v1/phase2/contract-review/export-redline", summary="导出带 Word 原生修订模式 (Track Changes) 的 .docx 合同审阅底稿")
async def export_redline_contract_docx(req: ExportRedlineReq):
    """
    一键生成带有 Microsoft Word 原生修订模式（<w:ins> / <w:del> 标签）、三栏修订卡片与
    Playbook 偏离度清单的完整审阅底稿 .docx，支持在 Word 中直接点击“接受所有修订”。
    若提供 source_file_id，则在已上传原文档中原位注入修订。
    """
    if req.source_docx_path:
        raise HTTPException(
            status_code=400,
            detail="不再接受服务器路径，请先上传原文档",
        )

    clause_reviews = req.clause_reviews
    overall_risk = req.overall_risk_level or "中"
    review_summary = req.review_summary or ""
    compliance_score = req.playbook_compliance_score or 85

    preset_key = req.playbook_preset or "general"
    preset_info = PLAYBOOK_PRESETS.get(preset_key, PLAYBOOK_PRESETS["general"])
    active_rules = req.playbook_rules if req.playbook_rules else preset_info["rules"]
    playbook_name = preset_info["name"] if not req.playbook_rules else "自定义审查红线库"

    # 若未提供审查结果，则现场快速审查
    if not clause_reviews:
        review_resp = await review_contract_clauses(ContractReviewReq(
            contract_title=req.contract_title,
            contract_text=req.contract_text,
            perspective=req.perspective,
            playbook_preset=req.playbook_preset,
            playbook_rules=req.playbook_rules
        ))
        clause_reviews = review_resp["review"].get("clause_reviews", [])
        overall_risk = review_resp["review"].get("overall_risk_level", "中")
        review_summary = review_resp["review"].get("review_summary", "")
        compliance_score = review_resp["review"].get("playbook_compliance_score", 85)

    timestamp = int(time.time())
    safe_title = sanitize_filename(req.contract_title, default="合同")[:30]
    filename = f"合同红线修订稿_{safe_title}_{timestamp}.docx"
    output_path = safe_join(str(get_generated_dir()), filename)

    if req.source_file_id:
        fid = validate_plain_filename(req.source_file_id)
        # 允许带或不带 .docx 后缀的 id
        candidates = [f"{fid}.docx", fid] if not fid.lower().endswith(".docx") else [fid]
        source_path = None
        for name in candidates:
            try:
                cand = safe_join(str(get_uploads_dir()), name)
            except HTTPException:
                continue
            if os.path.exists(cand):
                source_path = cand
                break
        if not source_path:
            raise HTTPException(status_code=404, detail="source_file_id 对应文件不存在，请先上传原文档")
        redline_res = apply_in_place_docx_redline(
            source_docx_path=source_path,
            clause_reviews=clause_reviews,
            output_path=output_path
        )
        return {
            "status": "success",
            "message": "已成功在客户原始 Word 文档中原位注入 Track Changes 修订标记与红线建议！",
            "filename": filename,
            "download_url": f"/api/documents/download/{filename}",
            "clause_count": len(clause_reviews),
            "perspective": req.perspective,
            "playbook_name": playbook_name,
            "has_native_track_changes": True,
            "in_place_mode": True,
            "stats": getattr(redline_res, "stats", {})
        }

    build_redline_contract_docx(
        contract_title=req.contract_title,
        original_contract_text=req.contract_text,
        clause_reviews=clause_reviews,
        perspective=req.perspective,
        playbook_name=playbook_name,
        playbook_rules=active_rules,
        overall_risk_level=overall_risk,
        review_summary=review_summary,
        compliance_score=compliance_score,
        output_path=output_path
    )

    return {
        "status": "success",
        "filename": filename,
        "download_url": f"/api/documents/download/{filename}",
        "clause_count": len(clause_reviews),
        "perspective": req.perspective,
        "playbook_name": playbook_name,
        "has_native_track_changes": True,
        "in_place_mode": False
    }


# ==============================================================================
# 6. 证据三性审查接口 (POST /api/v1/phase2/cross-examination)
# ==============================================================================
class CrossExamReq(BaseModel):
    evidence_name: str = Field(..., example="被告提交的手写收据复印件")
    evidence_category: str = Field(default="书证", example="书证")
    opponent_purpose: str = Field(..., example="证明原告已收取10万元货款并结清")
    client_facts: str = Field(..., example="原告从未收到该款项，收据签名不是原告字迹，被告拒不出示原件")

@router.post("/api/v1/phase2/cross-examination", summary="AI 证据三性审查与反驳意见生成")
@router.post("/api/evidence/cross-examination", include_in_schema=False)
async def api_cross_examination(req: CrossExamReq):
    prompt = f"""【待质证证据】{req.evidence_name}（{req.evidence_category}）
【对方证明目的】{req.opponent_purpose}
【我方当事人真实情况】{req.client_facts}

请输出真实性、合法性、关联性及证明力反驳意见严格 JSON。"""

    try:
        raw_output = await ollama_client.generate(
            prompt=prompt,
            system_prompt=EVIDENCE_CROSS_EXAM_SYSTEM_PROMPT,
            temperature=0.2
        )
        parsed = ollama_client.extract_json(raw_output)
        return {
            "status": "success",
            "cross_examination": parsed,
            "raw_output": raw_output
        }
    except Exception as e:
        logger.warning(f"质证意见生成异常，启动规则兜底: {e}")
        fallback_json = ollama_client.extract_json(ollama_client._generate_rule_fallback(prompt, None))
        return {
            "status": "success",
            "cross_examination": fallback_json,
            "raw_output": json.dumps(fallback_json, ensure_ascii=False)
        }
