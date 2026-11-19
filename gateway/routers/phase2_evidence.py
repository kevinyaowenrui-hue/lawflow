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

logger = logging.getLogger("lawflow.phase2")
import uuid
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
except ImportError as imp_err:
    logger.debug(f"pillow_heif not installed: {imp_err}")

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
    build_trial_outline_system_prompt,
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
from gateway.utils.contract_review_parse import (
    MODEL_REVIEW_UNUSABLE,
    coerce_contract_review,
    review_needs_retry,
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
    case_title: str = Field(..., examples=["张三诉北京某科技公司技术服务合同纠纷案"])
    cause_of_action: str = Field(..., examples=["技术服务合同纠纷"])
    plaintiff_claims_and_facts: str = Field(
        ...,
        description="原告起诉请求与事实理由概述",
        examples=["原告主张按期完成系统开发并交付，被告已上线试运行但拒付尾款20万元，请求支付尾款及LPR违约金。"]    )
    defendant_defense: str = Field(
        ...,
        description="被告答辩意见及事实异议",
        examples=["被告抗辩称系统存在严重Bug多次崩溃未达验收标准，原告逾期交付超过30天，被告有权解除合同并主张5万元违约金抵扣。"]    )

LF001_DISCLAIMER = (
    "【免责提示】本审查结果由法律工作台基于合同文本自动生成，依据检索日期时有效的公开法律法规和司法解释"
    "（来源：国家法律法规数据库 flk.npc.gov.cn、最高人民法院网站），仅对所提交的文本作风险提示，"
    "未核实交易背景、当事人资信和履行事实，也不包括合同所附但未提交的文件。风险等级为规则化判断，"
    "可能存在误报或漏报；涉及具体金额、期限阈值的，为产品经验值，并非法定标准。法律法规可能修订，"
    "请以官方最新文本为准。本意见仅供参考，不构成正式法律意见。重大交易或争议请咨询执业律师。"
)

class ContractReviewReq(BaseModel):
    contract_title: str = Field(default="商业采购与技术开发服务合同", examples=["技术开发服务合同"])
    contract_text: str = Field(
        ...,
        description="待审查的合同正文条文",
        examples=["第七条 违约责任：乙方如延期交付超过3日，每日应向甲方支付合同总价款5%的惩罚性违约金；甲方有权随时单方解除合同且无需退还首期款项。发生争议由甲方所在地人民法院管辖。"]
    )
    perspective: Optional[str] = Field(
        default=None,
        description="审查立场视角：买方 / 卖方 / 甲方强势版 / 乙方防御版 / 中立版",
        examples=["买方"]
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
    cause_of_action: str = Field(..., examples=["民间借贷纠纷"])
    plaintiff_name: str = Field(..., examples=["张三"])
    evidence_notes: Optional[str] = Field(
        default="",
        description="杂乱证据材料清单或提取文字",
        examples=["证据一：2023年1月1日张三通过招商银行给李四转账50万的网银回单电子凭证，证明借款交付。证据二：李四手写借条原件，约定年利率15%一年后还本付息。证据三：微信聊天记录导出，李四多次在微信中承认欠款并请求宽限两周。"]
    )
    structured_items: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="直接传入结构化证据项（包含 name, category, source, purpose, pages）"
    )
    file_page_map: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="来自合卷 process-evidence 的物理起止精确页码映射表"
    )


class RedactSensitiveReq(BaseModel):
    pdf_filename: str = Field(..., description="storage/generated 或 uploads 中的 PDF 文件名", examples=["合卷证据包_test.pdf"])
    redact_idcard: bool = Field(default=True, description="是否自动涂黑 18 位身份证号码")
    redact_bankcard: bool = Field(default=True, description="是否自动涂黑 16-19 位银行卡号")
    redact_phone: bool = Field(default=True, description="是否自动涂黑 11 位手机号码")


# ==============================================================================
# 1. 证据合卷与贝茨编码流水线 (POST /api/v1/phase2/process-evidence)
# ==============================================================================
_EVIDENCE_MERGE_EXTS = [
    ".pdf", ".png", ".jpg", ".jpeg", ".heic", ".webp", ".bmp", ".heif", ".tiff", ".tif",
    ".docx", ".doc",
]
_EVIDENCE_IMAGE_EXTS = [".jpg", ".jpeg", ".png", ".webp", ".bmp", ".heic", ".heif", ".tiff", ".tif"]


def _stamp_bates_on_page(page, evidence_label: str, page_no: int) -> None:
    """在 A4 页面右上角安全出血区绘制纯白衬垫框并打上贝茨码，防止覆盖原始单据金额或时间戳。"""
    bates_text = f"{evidence_label} · 第 {page_no} 页"
    # A4 顶部安全出血区纯白底色衬垫框与细边框 (max(10, width - 165), 6, width - 10, 26)
    box_rect = fitz.Rect(max(10.0, page.rect.width - 165.0), 6.0, page.rect.width - 10.0, 26.0)
    page.draw_rect(box_rect, color=(0.80, 0.80, 0.80), fill=(1.0, 1.0, 1.0), width=0.5)
    page.insert_text(
        fitz.Point(box_rect.x0 + 6.0, 20.0),
        bates_text,
        fontname="china-s",
        fontsize=10.0,
        color=(0.82, 0.12, 0.12),
    )


def split_pdf_by_court_size_limit(pdf_path: str, max_mb: float = 30.0) -> List[str]:
    """
    当合卷后的 PDF 超过全国法院网上立案系统单文件体积限制（默认 30MB）时，
    使用 PyMuPDF 按页自动切分为 _第1卷.pdf、_第2卷.pdf 等分卷文件。
    若未超过上限，直接返回原路径列表 [pdf_path]。
    """
    if not os.path.isfile(pdf_path):
        return []
    file_size_mb = os.path.getsize(pdf_path) / (1024 * 1024)
    if file_size_mb <= max_mb:
        return [pdf_path]

    src_doc = fitz.open(pdf_path)
    total_pages = len(src_doc)
    if total_pages <= 1:
        src_doc.close()
        return [pdf_path]

    base, ext = os.path.splitext(pdf_path)
    volume_paths: List[str] = []
    vol_num = 1
    current_doc = fitz.open()

    for pno in range(total_pages):
        current_doc.insert_pdf(src_doc, from_page=pno, to_page=pno)
        vol_file = f"{base}_第{vol_num}卷{ext}"
        current_doc.save(vol_file, garbage=3, deflate=True)
        cur_size_mb = os.path.getsize(vol_file) / (1024 * 1024)

        if cur_size_mb >= max_mb and len(current_doc) > 1:
            current_doc.delete_page(len(current_doc) - 1)
            current_doc.save(vol_file, garbage=3, deflate=True)
            current_doc.close()
            volume_paths.append(vol_file)

            vol_num += 1
            current_doc = fitz.open()
            current_doc.insert_pdf(src_doc, from_page=pno, to_page=pno)

    if len(current_doc) > 0:
        vol_file = f"{base}_第{vol_num}卷{ext}"
        current_doc.save(vol_file, garbage=3, deflate=True)
        current_doc.close()
        volume_paths.append(vol_file)

    src_doc.close()
    return volume_paths


def _append_pdf_with_bates(merged_doc, pdf_path: str, evidence_label: str, start_page: int) -> int:
    """将 pdf_path 各页并入 merged_doc 并盖贝茨码；返回新增页数。"""
    sub_pdf = fitz.open(pdf_path)
    added = 0
    try:
        for pno in range(len(sub_pdf)):
            merged_doc.insert_pdf(sub_pdf, from_page=pno, to_page=pno)
            added += 1
            curr_page = merged_doc[start_page + added - 1]
            _stamp_bates_on_page(curr_page, evidence_label, start_page + added)
    finally:
        sub_pdf.close()
    return added


@router.post("/api/v1/phase2/process-evidence", summary="证据材料 A4 PDF 自动合卷与贝茨编码流水线")
async def process_evidence_bates_stamping(
    files: List[UploadFile] = File(...),
    evidence_label: str = Form("证据1", description="贝茨编码前缀，如'证据1'或'原告证据'")
):
    """
    接收多张微信截图、扫描件、PDF/Word 凭证：
    1. docx/doc 先转临时 PDF 再并入；不支持的格式记入 skipped_files；
    2. 统一按比例缩放适配标准 A4 页面；
    3. 在每页右上角加盖法院标准贝茨编码；
    4. 合并导出单一《证据卷宗.pdf》。
    """
    from gateway.routers.phase1_litigation import convert_docx_to_pdf

    merged_doc = fitz.open()
    total_pages = 0
    batch_total = 0
    batch_cap = max_upload_total_bytes()
    merged_files: List[str] = []
    file_page_map: List[Dict[str, Any]] = []
    skipped_files: List[Dict[str, str]] = []
    temp_cleanup: List[str] = []

    try:
        for idx, f in enumerate(files, 1):
            original_name = f.filename or f"upload_{idx}"
            ext = extension_of(original_name)
            raw = await read_upload_bounded(f)
            batch_total += len(raw)
            if batch_total > batch_cap:
                raise HTTPException(status_code=413, detail="单次上传总量超过上限")

            if ext not in _EVIDENCE_MERGE_EXTS:
                skipped_files.append({
                    "filename": original_name,
                    "reason": f"不支持的文件格式: {ext or '(无扩展名)'}",
                })
                continue

            # 魔数不符仍返回 415（安全校验，不静默跳过）
            validate_magic_bytes(raw, ext)

            temp_path = safe_join(str(get_uploads_dir()), storage_name(ext))
            with open(temp_path, "wb") as buffer:
                buffer.write(raw)
            temp_cleanup.append(temp_path)

            try:
                if ext == ".pdf":
                    start_page = total_pages + 1
                    added = _append_pdf_with_bates(merged_doc, temp_path, evidence_label, total_pages)
                    end_page = total_pages + added
                    page_range = f"第{start_page}-{end_page}页" if start_page != end_page else f"第{start_page}页"
                    file_page_map.append({
                        "filename": original_name,
                        "start_page": start_page,
                        "end_page": end_page,
                        "page_count": added,
                        "page_range": page_range,
                        "evidence_label": evidence_label
                    })
                    total_pages += added
                    merged_files.append(original_name)

                elif ext in _EVIDENCE_IMAGE_EXTS:
                    with Image.open(temp_path) as raw_img:
                        img = ImageOps.exif_transpose(raw_img)
                        w, h = img.size
                        conv_path = temp_path
                        if ext in [".heic", ".heif", ".tiff", ".tif"] or img.mode in ("RGBA", "LA", "P"):
                            conv_path = os.path.join(
                                str(get_uploads_dir()),
                                f"temp_conv_{uuid.uuid4().hex[:8]}_{idx}.png",
                            )
                            temp_cleanup.append(conv_path)
                            if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                                bg = Image.new("RGB", img.size, (255, 255, 255))
                                bg.paste(img, mask=img.convert("RGBA").split()[3])
                                bg.save(conv_path, "PNG")
                            else:
                                img.convert("RGB").save(conv_path, "PNG")

                    a4_w, a4_h = 595, 842
                    page = merged_doc.new_page(width=a4_w, height=a4_h)
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
                    total_pages += 1
                    _stamp_bates_on_page(page, evidence_label, total_pages)
                    file_page_map.append({
                        "filename": original_name,
                        "start_page": total_pages,
                        "end_page": total_pages,
                        "page_count": 1,
                        "page_range": f"第{total_pages}页",
                        "evidence_label": evidence_label
                    })
                    merged_files.append(original_name)

                elif ext in (".docx", ".doc"):
                    tmp_pdf = os.path.join(
                        str(get_uploads_dir()),
                        f"temp_docx_{uuid.uuid4().hex[:8]}.pdf",
                    )
                    temp_cleanup.append(tmp_pdf)
                    ok = await convert_docx_to_pdf(
                        temp_path,
                        tmp_pdf,
                        title=os.path.splitext(original_name)[0],
                    )
                    if not ok or not os.path.isfile(tmp_pdf):
                        skipped_files.append({
                            "filename": original_name,
                            "reason": "Word 转 PDF 失败",
                        })
                        continue
                    start_page = total_pages + 1
                    added = _append_pdf_with_bates(merged_doc, tmp_pdf, evidence_label, total_pages)
                    end_page = total_pages + added
                    page_range = f"第{start_page}-{end_page}页" if start_page != end_page else f"第{start_page}页"
                    file_page_map.append({
                        "filename": original_name,
                        "start_page": start_page,
                        "end_page": end_page,
                        "page_count": added,
                        "page_range": page_range,
                        "evidence_label": evidence_label
                    })
                    total_pages += added
                    merged_files.append(original_name)
                else:
                    skipped_files.append({
                        "filename": original_name,
                        "reason": f"不支持的文件格式: {ext}",
                    })
            except Exception as e:
                logger.warning("合卷处理文件 %s 失败: %s", original_name, e)
                skipped_files.append({
                    "filename": original_name,
                    "reason": f"处理失败: {e}",
                })

        if total_pages == 0:
            merged_doc.close()
            raise HTTPException(status_code=400, detail="没有可并入的证据文件")

        label_safe = sanitize_filename(evidence_label) or "证据"
        merged_filename = f"合卷证据包_{label_safe}_{uuid.uuid4().hex[:8]}.pdf"
        output_path = os.path.join(str(get_generated_dir()), merged_filename)
        merged_doc.save(output_path, garbage=3, deflate=True)
        merged_doc.close()

        # 30MB 网上立案系统限制分卷检测与自动分卷
        volumes = split_pdf_by_court_size_limit(output_path, max_mb=30.0)
        split_volume_names = [os.path.basename(v) for v in volumes]
        is_split = len(split_volume_names) > 1

        status = "partial" if skipped_files else "success"
        return {
            "status": status,
            "evidence_label": evidence_label,
            "total_pages": total_pages,
            "merged_pdf_filename": merged_filename,
            "download_url": f"/api/documents/download/{merged_filename}",
            "processed_files_count": len(merged_files),
            "merged_files": merged_files,
            "file_page_map": file_page_map,
            "skipped_files": skipped_files,
            "court_size_limit_mb": 30.0,
            "is_split": is_split,
            "split_volumes": split_volume_names,
            "split_volume_urls": [f"/api/documents/download/{vn}" for vn in split_volume_names] if is_split else [],
        }
    finally:
        for p in temp_cleanup:
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                except OSError as rem_err:
                    logger.debug(f"清理临时文件失败: {rem_err}")


def _ocr_redact_hits(page, patterns: list):
    """扫描页没有文字层时，用 OCR 字块定位号码。OCR 不可用时返回空列表。"""
    from gateway.utils.ocr_engine import (
        easyocr_items,
        get_easyocr_reader,
        sensitive_rects_from_ocr_items,
    )

    reader = get_easyocr_reader()
    if reader is None:
        return [], False
    temp = os.path.join(str(get_generated_dir()), f"_ocr_{uuid.uuid4().hex}.png")
    try:
        pix = page.get_pixmap(dpi=150)
        pix.save(temp)
        results = reader.readtext(temp, detail=1)
        rects = sensitive_rects_from_ocr_items(
            easyocr_items(results),
            patterns,
            page.rect.width,
            page.rect.height,
            pix.width,
            pix.height,
        )
        return rects, True
    except Exception:
        logger.warning("扫描页 OCR 涂黑失败", exc_info=True)
        return [], False
    finally:
        if os.path.exists(temp):
            try:
                os.remove(temp)
            except OSError:
                logger.debug("清理 OCR 临时图失败")


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
    redactions_count = 0
    redacted_items = []
    total_chars = 0
    ocr_pages = 0

    # 18位二代身份证。用前后负向数字断言，避免汉字紧贴号码时 \b 匹配失败。
    id_pattern = re.compile(r"(?<!\d)(?:[1-9]\d{5}(?:18|19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]|[1-9]\d{7}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3})(?!\d)")
    # 16-19位银行卡号
    bank_pattern = re.compile(r"(?<!\d)[1-9]\d{15,18}(?!\d)")
    # 11位中国大陆手机号码
    phone_pattern = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
    active_patterns = []
    if req.redact_idcard:
        active_patterns.append(("身份证", id_pattern))
    if req.redact_bankcard:
        active_patterns.append(("银行卡", bank_pattern))
    if getattr(req, "redact_phone", True):
        active_patterns.append(("手机号", phone_pattern))

    def _mask(label: str, value: str, page_no: int) -> str:
        return f"{label}: {value[:4]}****{value[-4:]} (第{page_no}页)"

    def _paint_pattern_hits(page, text: str, page_no: int, search):
        nonlocal redactions_count
        for label, pattern in active_patterns:
            for value in set(pattern.findall(text or "")):
                rects = search(value)
                if not rects:
                    continue
                for rect in rects:
                    page.add_redact_annot(rect, fill=(0, 0, 0))
                    redactions_count += 1
                redacted_items.append(_mask(label, value, page_no))

    for pno in range(len(doc)):
        page = doc[pno]
        text = page.get_text("text") or ""
        total_chars += len(text.strip())
        _paint_pattern_hits(page, text, pno + 1, page.search_for)
        if len(text.strip()) < 20 and active_patterns:
            ocr_hits, used = _ocr_redact_hits(page, [pat for _, pat in active_patterns])
            if used:
                ocr_pages += 1
            for hit in ocr_hits:
                page.add_redact_annot(fitz.Rect(*hit["rect"]), fill=(0, 0, 0))
                redactions_count += 1
                label = next((name for name, pat in active_patterns if pat.fullmatch(hit["text"])), "敏感信息")
                redacted_items.append(_mask(label, hit["text"], pno + 1))
        page.apply_redactions()

    page_count = len(doc)
    output_filename = f"已脱敏_{req.pdf_filename}"
    output_path = os.path.join(str(get_generated_dir()), output_filename)
    doc.save(output_path)
    doc.close()

    is_scanned = total_chars < 30 and page_count > 0
    if is_scanned and ocr_pages and redactions_count:
        scanned_warning = "该 PDF 没有文字层，已按扫描识别结果涂黑。模糊或断行的号码可能漏涂，下载前请逐页核对。"
        status = "success"
    elif is_scanned and ocr_pages:
        scanned_warning = "已识别扫描件文字，未发现身份证号、银行卡号或手机号。若原件上有号码，请提高清晰度后重试。"
        status = "partial"
    elif is_scanned:
        scanned_warning = "该 PDF 没有文字层，且本机 OCR 不可用，未能涂黑。请安装 OCR 依赖，或改用带文字层的电子文档。"
        status = "partial"
    else:
        scanned_warning = None
        status = "success"

    return {
        "status": status,
        "redacted_filename": output_filename,
        "download_url": f"/api/documents/download/{output_filename}",
        "redactions_count": redactions_count,
        "redacted_items": list(set(redacted_items)),
        "is_scanned_pdf": is_scanned,
        "ocr_pages": ocr_pages,
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

    from gateway.utils.pii_sanitizer import build_entities_from_parties

    def _parse_raw_evidence_items(notes: str) -> list:
        raw_lines = [l.strip() for l in (notes or "").splitlines() if l.strip()]
        if not raw_lines and (notes or "").strip():
            raw_lines = [x.strip() for x in re.split(r'[,，;；\n、]', notes.strip()) if x.strip()]
        extracted = []
        for line in raw_lines:
            body = re.sub(
                r'^\s*(?:证据\s*)?(?:\d+[\.、\-\)]\s*|\([0-9一二三四五六七八九十]+\)\s*|（[0-9一二三四五六七八九十]+）\s*|[一二三四五六七八九十]+[、\.\s]\s*|[-*•]\s*)',
                '',
                line,
            ).strip()
            parts = [p.strip() for p in re.split(r'[|｜]', body) if p.strip()]
            clean_name = parts[0] if parts else body
            clean_name = os.path.splitext(clean_name)[0].strip() or line.strip()
            purpose = parts[1] if len(parts) > 1 else ""
            pages = parts[2] if len(parts) > 2 else ""
            form = parts[3] if len(parts) > 3 else ""
            issue = parts[4] if len(parts) > 4 else ""
            if len(parts) <= 1 and "证明" in clean_name:
                split_purpose = re.split(r'(?:[：:，,]\s*证明|。证明)', clean_name, maxsplit=1)
                if len(split_purpose) == 2:
                    clean_name = split_purpose[0].strip(" ，。")
                    purpose = "证明" + split_purpose[1].strip()
            if not form:
                if "原件" in line and "复印件" not in line:
                    form = "原件"
                elif "复印件" in line:
                    form = "复印件"
            if issue:
                purpose = (purpose or "【待填写】") + f"（关联争点：{issue}）"
            if not clean_name:
                continue
            cat = "书证"
            if any(k in line for k in ["微信", "短信", "聊天", "录音", "视频", "电子", "流水", "回单", "凭单", "网银", "邮件"]):
                cat = "电子数据"
            extracted.append({
                "name": clean_name,
                "category": cat,
                "source": "当事人提交" if form else "【待填写】",
                "purpose": purpose or "【待填写】",
                "pages": pages or "【待填写】",
                "original_or_copy": form or "【待填写】",
                "issue": issue or "【待填写】",
            })
        return extracted

    _catalog_entities = build_entities_from_parties([{"name": getattr(req, "plaintiff_name", None)}])
    parsed_explicit = _parse_raw_evidence_items(req.evidence_notes or "")
    lawyer_typed_columns = any(("|" in line or "｜" in line) for line in (req.evidence_notes or "").splitlines())
    if req.structured_items and len(req.structured_items) > 0:
        items = [dict(it) for it in req.structured_items]
    elif lawyer_typed_columns and parsed_explicit:
        items = parsed_explicit
    else:
        try:
            raw_output = await ollama_client.generate(
                prompt=prompt,
                system_prompt=EVIDENCE_STRUCTURING_PROMPT,
                temperature=0.2,
                custom_entities=_catalog_entities or None,
            )
            parsed_items = ollama_client.extract_json(raw_output)
            if isinstance(parsed_items, dict) and "error" in parsed_items:
                items = _parse_raw_evidence_items(req.evidence_notes)
            elif isinstance(parsed_items, list):
                items = parsed_items
            elif isinstance(parsed_items, dict):
                items = parsed_items.get("evidence_items", parsed_items.get("items", [parsed_items]))
            else:
                items = []
            if not items:
                items = _parse_raw_evidence_items(req.evidence_notes)
        except Exception as e:
            logger.warning(f"gemma4:12b 提炼证据目录异常: {e}")
            items = _parse_raw_evidence_items(req.evidence_notes)

    # 若提供了合卷精确页码映射表 file_page_map，自动注入各证据项页码
    if req.file_page_map and len(req.file_page_map) > 0:
        for idx, item in enumerate(items):
            if idx < len(req.file_page_map):
                pm = req.file_page_map[idx]
                if pm.get("page_range"):
                    item["pages"] = pm["page_range"]

    if not items:
        raise HTTPException(
            status_code=400,
            detail="还没有证据名称。请先写入证据目录再生成，不会自动补合同、流水或聊天记录。",
        )

    # 保留用户原始名称与字段空栏【待填写】补全
    raw_parsed = parsed_explicit
    if len(raw_parsed) == len(items):
        for idx, item in enumerate(items):
            raw = raw_parsed[idx]
            item["name"] = raw["name"]
            for key in ("purpose", "pages", "original_or_copy", "issue", "source", "category"):
                raw_val = (raw.get(key) or "").strip()
                if raw_val and raw_val != "【待填写】":
                    item[key] = raw_val
    for item in items:
        if not item.get("source"):
            item["source"] = "【待填写】"
        if not item.get("purpose"):
            item["purpose"] = "【待填写】"
        if not item.get("pages"):
            item["pages"] = "【待填写】"
        if not item.get("original_or_copy"):
            item["original_or_copy"] = "【待填写】"
        if item.get("issue") and item["issue"] != "【待填写】" and "关联争点" not in (item.get("purpose") or ""):
            item["purpose"] = f"{item.get('purpose') or '【待填写】'}（关联争点：{item['issue']}）" 

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

    try:
        from gateway.utils.matter_vault_db import record_audit_log
        record_audit_log(
            action="document_generate",
            target=catalog_filename,
            result="success"
        )
    except Exception as audit_err:
        logger.warning(f"记录证据目录生成审计日志失败: {audit_err}")

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

    # 无已核验判例时注入「无」，不得诱导模型自行列举案号
    trial_system_prompt = build_trial_outline_system_prompt("无")
    try:
        outline_markdown = await ollama_client.generate(
            prompt=prompt,
            system_prompt=trial_system_prompt,
            temperature=0.3
        )
    except Exception as e:
        logger.warning(f"庭审提纲生成异常，启动规则兜底: {e}")
        outline_markdown = ollama_client._generate_rule_fallback(prompt, trial_system_prompt)

    rule_outline = getattr(ollama_client, "last_llm_mode", "rule_fallback") == "rule_fallback"
    if rule_outline:
        if "规则模式" not in outline_markdown[:150]:
            outline_markdown = "> **【提示】当前为规则模式（未连接模型），以下为通用提纲，需结合案情修改。不能直接当出庭稿。**\n\n" + outline_markdown

    from gateway.utils.citation_guard import audit_citations_in_text
    citation_audit = audit_citations_in_text(outline_markdown, auto_sanitize=True)
    if citation_audit.get("has_abrogated_laws") and citation_audit.get("sanitized_text"):
        outline_markdown = citation_audit["sanitized_text"]

    return {
        "status": "template" if rule_outline else "success",
        "case_title": req.case_title,
        "cause_of_action": req.cause_of_action,
        "trial_outline_markdown": outline_markdown,
        "citation_audit": citation_audit,
        "outline_note": "未连接模型，这是通用提纲，必须按本案改写。" if rule_outline else "",
    }


_CLAUSE_SPLIT = re.compile(r"[。；;\n]+")
_PENALTY_RATE = re.compile(r"(?:百分之|千分之|万分之|\d+(?:\.\d+)?\s*[%％])")
_AUTO_RENEW = re.compile(r"自动续|自动延长|自动延续")
_UNILATERAL_END = re.compile(r"单方解除|任意解除|随时解除|有权解除|一方解除")


def _contract_snippets(text: str) -> List[str]:
    parts = [piece.strip() for piece in _CLAUSE_SPLIT.split(text or "") if piece and piece.strip()]
    if parts:
        return parts
    stripped = (text or "").strip()
    return [stripped] if stripped else []


def _quote_matching_snippets(parts: List[str], matched) -> str:
    hits: List[str] = []
    seen = set()
    for part in parts:
        if not matched(part):
            continue
        key = re.sub(r"\s+", "", part)
        if key in seen:
            continue
        seen.add(key)
        snippet = part if len(part) <= 180 else part[:180] + "…"
        hits.append(f"「{snippet}」")
    return "；".join(hits) if hits else "正文中未找到"


def _is_forum_clause(part: str) -> bool:
    if "仲裁" in part:
        return True
    if "人民法院" in part:
        return True
    return "法院" in part and ("管辖" in part or "起诉" in part)


def describe_unreviewed_contract_marks(contract_text: str) -> str:
    """没连上模型时，只引用正文里真实出现的四类表述，不写修改稿。"""
    parts = _contract_snippets(contract_text)
    forum = _quote_matching_snippets(parts, _is_forum_clause)
    penalty = _quote_matching_snippets(
        parts, lambda part: "违约金" in part and _PENALTY_RATE.search(part) is not None
    )
    renew = _quote_matching_snippets(parts, lambda part: _AUTO_RENEW.search(part) is not None)
    ending = _quote_matching_snippets(parts, lambda part: _UNILATERAL_END.search(part) is not None)
    return (
        "未连接大模型，未生成修改稿。以下只标出律师粘贴的正文里实际写到的内容。\n"
        f"仲裁或法院条款：{forum}\n"
        f"违约金比例：{penalty}\n"
        f"自动续期：{renew}\n"
        f"单方解除：{ending}"
    )


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
    商业合同红线审查（LF-001 规范）：
    1. 审查前必须选择立场（买方 / 卖方），未选不得出审查结论。
    2. 未连上模型时不编造修改稿，只标出正文里实际出现的仲裁或法院条款、违约金比例、自动续期、单方解除；找不到写「正文中未找到」。状态仍为未审查。
    3. 结果附带 LF-001 第 11 节必带免责提示。
    """
    if not req.perspective or not str(req.perspective).strip():
        raise HTTPException(
            status_code=422,
            detail="审查前必须选择立场（买方 / 卖方），未选择立场不得出具审查结论。"
        )
    if not (req.contract_text or "").strip():
        raise HTTPException(
            status_code=422,
            detail="请粘贴合同正文。空文本不能出具审查结论。"
        )

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

    def _unreviewed(summary: str) -> Dict[str, Any]:
        return {
            "status": "unreviewed",
            "perspective": req.perspective,
            "playbook_name": playbook_name,
            "playbook_rules": active_rules,
            "contract_title": req.contract_title,
            "disclaimer": LF001_DISCLAIMER,
            "review": {
                "overall_risk_level": "未审查",
                "playbook_compliance_score": 0,
                "review_summary": summary,
                "clause_reviews": [],
            }
        }

    async def _call_model() -> tuple:
        raw_output = await ollama_client.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.2
        )
        mode = getattr(ollama_client, "last_llm_mode", "rule_fallback")
        return raw_output, mode

    try:
        raw_output, mode = await _call_model()
        # 规则模式会带回预置条款。那不是对本合同的审查，不能标成已审查。
        if mode == "rule_fallback":
            return _unreviewed(describe_unreviewed_contract_marks(req.contract_text))

        coerced = coerce_contract_review(raw_output)
        if not coerced["clauses"] and review_needs_retry(raw_output, coerced):
            try:
                raw_retry, mode_retry = await _call_model()
            except Exception as retry_err:
                logger.warning(f"合同审查重试失败: {retry_err}")
                raw_retry, mode_retry = "", mode
            if mode_retry == "rule_fallback":
                return _unreviewed(describe_unreviewed_contract_marks(req.contract_text))
            retry_coerced = coerce_contract_review(raw_retry)
            if retry_coerced["clauses"] or retry_coerced["valid_json"]:
                coerced = retry_coerced

        if not coerced["clauses"]:
            return _unreviewed(MODEL_REVIEW_UNUSABLE)

        review_result = coerced["review"]
        for clause in review_result.get("clause_reviews", []):
            orig = clause.get("original_clause", "")
            sugg = clause.get("suggested_clause", "")
            clause["diff_chunks"] = compute_text_diff_chunks(orig, sugg)

        return {
            "status": "success",
            "perspective": req.perspective,
            "playbook_name": playbook_name,
            "playbook_rules": active_rules,
            "contract_title": req.contract_title,
            "disclaimer": LF001_DISCLAIMER,
            "review": review_result
        }
    except Exception as e:
        logger.warning(f"合同审查模型调用异常，返回未审查状态: {e}")
        return _unreviewed(describe_unreviewed_contract_marks(req.contract_text))


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

    # 没有条款审查时不能导出一份看起来已经审过的修订稿
    if not clause_reviews:
        review_resp = await review_contract_clauses(ContractReviewReq(
            contract_title=req.contract_title,
            contract_text=req.contract_text,
            perspective=req.perspective,
            playbook_preset=req.playbook_preset,
            playbook_rules=req.playbook_rules
        ))
        if review_resp.get("status") != "success":
            summary = ((review_resp.get("review") or {}).get("review_summary")) or MODEL_REVIEW_UNUSABLE
            raise HTTPException(status_code=422, detail=summary)
        clause_reviews = review_resp["review"].get("clause_reviews") or []
        overall_risk = review_resp["review"].get("overall_risk_level") or "未标明"
        review_summary = review_resp["review"].get("review_summary") or ""
        model_score = review_resp["review"].get("playbook_compliance_score")
        compliance_score = model_score if isinstance(model_score, (int, float)) else 0
    if not clause_reviews:
        raise HTTPException(status_code=422, detail=MODEL_REVIEW_UNUSABLE)

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
        stats = getattr(redline_res, "stats", {})
        revisions_count = stats.get("revisions_count", stats.get("injected_clauses", 0))
        unmatched_clauses = stats.get("unmatched_clauses", [])
        return {
            "status": "success",
            "message": f"已在原文中插入 {revisions_count} 处修订，{len(unmatched_clauses)} 条未定位",
            "filename": filename,
            "download_url": f"/api/documents/download/{filename}",
            "clause_count": len(clause_reviews),
            "revisions_count": revisions_count,
            "unmatched_clauses": unmatched_clauses,
            "perspective": req.perspective,
            "playbook_name": playbook_name,
            "has_native_track_changes": True,
            "in_place_mode": True,
            "stats": stats
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
    evidence_name: str = Field(..., examples=["被告提交的手写收据复印件"])
    evidence_category: str = Field(default="书证", examples=["书证"])
    opponent_purpose: str = Field(..., examples=["证明原告已收取10万元货款并结清"])
    client_facts: str = Field(..., examples=["原告从未收到该款项，收据签名不是原告字迹，被告拒不出示原件"])
    cause_of_action: str = Field(default="", description="案由。含劳动时改列用人单位举证责任")
    track: str = Field(default="", description="labor 时使用劳动争议举证规则")

@router.post("/api/v1/phase2/cross-examination", summary="AI 证据三性审查与反驳意见生成")
@router.post("/api/evidence/cross-examination", include_in_schema=False)
async def api_cross_examination(req: CrossExamReq):
    prompt = f"""【待质证证据】{req.evidence_name}（{req.evidence_category}）
【对方证明目的】{req.opponent_purpose}
【我方当事人真实情况】{req.client_facts}

请输出真实性、合法性、关联性及证明力反驳意见严格 JSON。"""
    from gateway.utils.practice_workflow import evidence_burden
    burden = evidence_burden(req.track, req.cause_of_action)
    if burden["mode"] == "labor_employer":
        prompt += "\n这是劳动争议质证。不要只写民事诉讼三性。必须列出用人单位对解除合法性、工资支付凭证和考勤记录的举证责任。"

    try:
        raw_output = await ollama_client.generate(
            prompt=prompt,
            system_prompt=EVIDENCE_CROSS_EXAM_SYSTEM_PROMPT,
            temperature=0.2
        )
        parsed = ollama_client.extract_json(raw_output)
        if getattr(ollama_client, "last_llm_mode", "rule_fallback") == "rule_fallback":
            if isinstance(parsed, dict) and "disclaimer" not in parsed:
                parsed["disclaimer"] = "当前为规则模式（未连接模型），以下为通用提纲，需结合案情修改。"
        return {
            "status": "success",
            "cross_examination": parsed,
            "burden": burden,
            "raw_output": raw_output
        }
    except Exception as e:
        logger.warning(f"质证意见生成异常，启动规则兜底: {e}")
        fallback_json = ollama_client.extract_json(ollama_client._generate_rule_fallback(prompt, None))
        return {
            "status": "success",
            "cross_examination": fallback_json,
            "burden": burden,
            "raw_output": json.dumps(fallback_json, ensure_ascii=False)
        }
