"""
LawFlow 智律工作台 - 案件独立空间与人机协同中枢路由 (Matter Vault & Workflow Router)
端点：
- /api/v1/vault/matters: 案件独立空间 CRUD
- /api/v1/vault/matters/{matter_id}/documents: 案卷挂载与文档管理
- /api/v1/vault/matters/{matter_id}/graphs: 案件事实时间线、主体关系图、资金流水图抽取与持久化
- /api/v1/vault/workflows: 5 步阶段式人机协同断点工作流（挂起/确认/回退/推进）
"""

import os
import re
import shutil
import time
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Form
from pydantic import BaseModel, Field

from gateway.utils.ocr_engine import extract_evidence_text
from gateway.core.security import (
    assert_allowed_extension,
    read_upload_bounded,
    safe_join,
    storage_name,
    validate_magic_bytes,
)

from gateway.core.paths import get_uploads_dir
from gateway.utils.matter_vault_db import (
    update_matter_status,
    soft_delete_matter,
    delete_document_from_matter,
    create_matter_deadline,
    list_matter_deadlines,
    list_all_matters,
    get_matter_by_id,
    create_new_matter,
    update_matter_record,
    add_document_to_matter,
    save_matter_graphs_db,
    delete_demo_matters,
)
from gateway.utils.conflict_checker import delete_demo_conflict_cases
from gateway.utils.agent_task_db import delete_demo_agent_tasks
from gateway.utils.review_table_engine import delete_demo_review_tables
from gateway.utils.graph_extractor import extract_case_graphs_from_text
from gateway.utils.workflow_engine import (
    start_litigation_workflow,
    advance_workflow_step,
    rollback_workflow_step,
    get_workflow_by_id
)
from gateway.utils.guarantee_and_cashflow_engine import (
    analyze_guarantee_topology_and_deadlines,
    audit_and_reconcile_cashflow
)

logger = logging.getLogger("lawflow.vault_router")
router = APIRouter(prefix="/api/v1/vault", tags=["案件独立空间与协同工作流"])


# =============================================================================
# Request / Response Models
# =============================================================================

class MatterCreateReq(BaseModel):
    matter_id: Optional[str] = None
    title: str = Field(..., description="案件名称")
    cause_of_action: str = Field(..., description="法定案由")
    court_name: Optional[str] = Field(None, description="管辖法院")
    case_number: Optional[str] = Field(None, description="司法案号")
    client_role: str = Field("原告", description="委托人诉讼地位（原告/被告/第三人）")
    plaintiff_name: Optional[str] = None
    defendant_name: Optional[str] = None
    plaintiff_info: Optional[Dict[str, Any]] = None
    defendant_info: Optional[Dict[str, Any]] = None
    principal_amount: float = Field(0.0, description="诉讼标的金额（元）")
    case_summary: Optional[str] = Field(None, description="案件核心事实梗概")
    summary: Optional[str] = None
    tags: Optional[List[str]] = Field(default_factory=list, description="案件特征标签")
    procedure: Optional[str] = None
    plaintiff_phone: Optional[str] = None
    plaintiff_id: Optional[str] = None
    defendant_phone: Optional[str] = None
    defendant_id: Optional[str] = None
    fee_type: Optional[str] = None
    fee_amount: Optional[float] = None
    fee_received: Optional[float] = None
    fee_note: Optional[str] = None
    hourly_rate: Optional[float] = None
    hours_logged: Optional[float] = None
    fee_receivable: Optional[float] = None
    risk_disclosed: Optional[bool] = None
    is_same_matter: Optional[str] = None
    acknowledge_personnel_conflict: bool = False
    practice: Optional[Dict[str, Any]] = None


class MatterUpdateReq(BaseModel):
    title: Optional[str] = None
    cause_of_action: Optional[str] = None
    court_name: Optional[str] = None
    case_number: Optional[str] = None
    client_role: Optional[str] = None
    plaintiff_info: Optional[Dict[str, Any]] = None
    defendant_info: Optional[Dict[str, Any]] = None
    principal_amount: Optional[float] = None
    case_summary: Optional[str] = None
    status: Optional[str] = None
    tags: Optional[List[str]] = None
    procedure: Optional[str] = None
    fee_type: Optional[str] = None
    fee_amount: Optional[float] = None
    fee_received: Optional[float] = None
    fee_note: Optional[str] = None
    risk_disclosed: Optional[bool] = None
    is_same_matter: Optional[str] = None
    practice: Optional[Dict[str, Any]] = None
    plaintiff_name: Optional[str] = None
    defendant_name: Optional[str] = None


class MatterLedgerReq(BaseModel):
    fee_invoiced: Optional[float] = None
    fee_amount: Optional[float] = None
    fee_received: Optional[float] = None
    seal_records: Optional[List[Dict[str, Any]]] = None
    filing_checklist: Optional[List[Dict[str, Any]]] = None
    local_filing_items: Optional[List[Dict[str, Any]]] = None


class DocumentMountReq(BaseModel):
    doc_type: str = Field("evidence", description="材料类型: evidence / contract / pleading / transcript / precedent")
    title: Optional[str] = None
    doc_title: Optional[str] = None
    file_path: Optional[str] = None
    file_size: Optional[int] = 0
    text_content: Optional[str] = None
    content_text: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)

    def to_doc_dict(self) -> Dict[str, Any]:
        actual_title = self.title or self.doc_title or "未命名案卷材料"
        actual_text = self.text_content or self.content_text or ""
        return {
            "doc_type": self.doc_type,
            "title": actual_title,
            "file_path": self.file_path or "",
            "file_size": self.file_size or len(actual_text),
            "text_content": actual_text,
            "metadata": self.metadata or {}
        }


class GraphExtractReq(BaseModel):
    facts_text: Optional[str] = None
    include_mounted_docs: bool = True


class GuaranteeAnalysisReq(BaseModel):
    principal_due_date: Optional[str] = Field(default=None, examples=["2024-03-15"], description="主债务约定到期日")
    today_date: Optional[str] = Field(default=None, examples=["2024-06-01"], description="审查核验基准日")
    override_nodes: Optional[List[Dict[str, Any]]] = None
    override_edges: Optional[List[Dict[str, Any]]] = None


class CashflowAuditReq(BaseModel):
    principal_amount: Optional[float] = Field(default=None, examples=[5000000.0], description="借款/合同本金总额")
    annual_interest_rate: Optional[float] = Field(default=None, examples=[0.12], description="约定年化利息率（小数，如0.12）")
    annual_rate: Optional[float] = Field(default=None, examples=[0.12], description="annual_interest_rate 别名")
    start_date: Optional[str] = Field(default=None, examples=["2023-03-16"], description="出借交付起息日")
    contract_date: Optional[str] = Field(default=None, description="合同成立日（默认取起息日）")
    filing_date: Optional[str] = Field(default=None, description="起诉日（2020-08-20前合同核验上限时需要）")
    fees: Optional[float] = Field(default=None, description="实现债权的有关费用")
    agreed_offset_order: Optional[List[str]] = Field(default=None, description="约定抵充顺序")
    override_cashflow: Optional[List[Dict[str, Any]]] = None


class WorkflowStartReq(BaseModel):
    matter_id: str
    case_title: Optional[str] = None
    facts_text: Optional[str] = None
    initial_facts: Optional[str] = None
    cause_of_action: Optional[str] = None
    client_role: str = Field("原告", description="委托人诉讼地位")
    perspective: str = Field("己方主办律师 (Blue Team)", description="分析视角")


class WorkflowAdvanceReq(BaseModel):
    step: Optional[int] = None
    confirmed_data: Optional[Dict[str, Any]] = None
    human_decisions: Optional[Dict[str, Any]] = None


class WorkflowRollbackReq(BaseModel):
    target_step: int = Field(2, description="回退到的目标步骤序号（2 或 4）")


# =============================================================================
# 1. 案件独立空间 (Matter Vault) CRUD 路由
# =============================================================================

@router.delete("/demo-data", summary="清空全部【演示】种子数据")
async def api_delete_demo_data():
    """删除标题含【演示】的案件、利冲底档、任务与阅卷表。"""
    counts = {
        "review_tables": delete_demo_review_tables(),
        "matters": delete_demo_matters(),
        "conflict_cases": delete_demo_conflict_cases(),
        "agent_tasks": delete_demo_agent_tasks(),
    }
    return {
        "status": "success",
        "message": "演示数据已清空",
        "counts": counts,
    }


@router.get("/matters", summary="获取案件独立空间列表")
async def api_list_matters(
    status: Optional[str] = Query(None, description="状态筛选: active / archived / draft"),
    search: Optional[str] = Query(None, description="搜索关键词")
):
    matters = list_all_matters(status=status, search=search)
    return {
        "status": "success",
        "total": len(matters),
        "matters": matters
    }


@router.post("/matters", summary="新建案件独立空间")
async def api_create_matter(req: MatterCreateReq):
    from gateway.utils.matter_intake import FILING_NOTICE, conflict_parties, default_filing_checklist, normalize_matter_intake
    from gateway.utils.matter_vault_db import save_matter_practice

    try:
        data = normalize_matter_intake(req.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    conflict = _screen_intake_conflict(data)
    from gateway.utils.firm_roster import screen_personnel

    parties = conflict_parties(data)
    personnel = screen_personnel(
        parties.get("opposing_name") or "",
        parties.get("opposing_id") or "",
        party_ids=[parties.get("client_id") or "", parties.get("opposing_id") or ""],
    )
    practice = dict(data.get("practice") or {})
    practice["conflict"] = {
        "conflict_level": conflict.get("conflict_level"),
        "status_label": conflict.get("status_label"),
        "summary": conflict.get("summary"),
        "recommendation": conflict.get("recommendation"),
    }
    practice["personnel_status"] = personnel.get("status") or ""
    needs_personnel_ack = personnel.get("status") in {"HIT", "SIMILAR"}
    if needs_personnel_ack and data.get("acknowledge_personnel_conflict"):
        practice["personnel_check"] = personnel.get("ack_message") or personnel.get("personnel_and_relatives_check") or ""
    else:
        practice["personnel_check"] = personnel.get("personnel_and_relatives_check") or ""
    if conflict.get("conflict_level") == "PROHIBITED":
        raise HTTPException(
            status_code=409,
            detail={
                "message": "利益冲突排查结果为禁止代理，不能建立本案承办空间。",
                "conflict_level": "PROHIBITED",
                "status_label": conflict.get("status_label") or "",
                "recommendation": conflict.get("recommendation") or "",
            },
        )
    if needs_personnel_ack and not data.get("acknowledge_personnel_conflict"):
        raise HTTPException(
            status_code=409,
            detail=personnel.get("block_message") or "对方与本所律师或近亲属同名，未确认前不能建案。",
        )
    if needs_personnel_ack:
        personnel_sentence = personnel.get("ack_message") or ""
    else:
        personnel_sentence = personnel.get("personnel_and_relatives_check") or ""
    practice.setdefault("filing_checklist", default_filing_checklist())
    practice.setdefault("seal_records", [])
    practice["filing_notice"] = FILING_NOTICE
    from gateway.utils.practice_workflow import default_arbitration_materials, seed_claim
    if not practice.get("claims"):
        practice["claims"] = [seed_claim(data.get("cause_of_action") or "", data.get("court_name") or "")]
    if practice.get("procedure") == "arbitration" or "劳动" in (data.get("cause_of_action") or ""):
        practice.setdefault("local_filing_items", default_arbitration_materials())
        practice["filing_route"] = "arbitration"
    else:
        practice.setdefault("local_filing_items", [])
        practice["filing_route"] = "court"
    data["practice"] = practice
    new_matter = create_new_matter(data)
    save_matter_practice(new_matter["matter_id"], practice)
    new_matter = get_matter_by_id(new_matter["matter_id"])
    conflict = _write_parties_and_recheck(new_matter)
    save_matter_practice(new_matter["matter_id"], {"conflict": _conflict_snapshot(conflict)})
    new_matter = get_matter_by_id(new_matter["matter_id"])
    message = f"案件空间【{new_matter['title']}】已保存"
    level = conflict.get("conflict_level")
    if level == "MANUAL_REVIEW":
        message += "。利冲结果为需人工判断，确认前不要接案。"
    elif level == "WAIVABLE_WITH_CONSENT":
        message += "。存在须书面同意后才能代理的冲突，同意完成前不要接案。"
    elif level == "CLEAR":
        label = (conflict.get("status_label") or "").strip()
        message += f"。{label}" if label else "。底档未发现冲突。"
    elif level == "UNABLE_TO_CHECK":
        message += "。利冲底档无法检查，不能当作未发现冲突。"
    elif not data.get("plaintiff_name") or not data.get("defendant_name"):
        message += "。当事人尚未填齐，本次未做利冲比对。"
    if personnel_sentence:
        message += personnel_sentence if personnel_sentence.startswith("。") else f"。{personnel_sentence}"
    return {
        "status": "success",
        "message": message,
        "conflict": _conflict_snapshot(conflict),
        "personnel": personnel,
        "matter": new_matter
    }


def _conflict_snapshot(result: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "conflict_level": result.get("conflict_level"),
        "status_label": result.get("status_label"),
        "summary": result.get("summary"),
        "recommendation": result.get("recommendation"),
        "not_checked_note": result.get("not_checked_note") or "",
        "registered_record_count": result.get("registered_record_count"),
    }


def _screen_intake_conflict(data: Dict[str, Any], exclude_case_id: str = "") -> Dict[str, Any]:
    from gateway.utils.conflict_checker import (
        _NOT_CHECKED_ITEMS,
        _NOT_CHECKED_NOTE,
        check_conflict_of_interest,
    )
    from gateway.utils.matter_intake import conflict_parties

    parties = conflict_parties(data)
    if not parties["client_name"] or not parties["opposing_name"]:
        return {
            "conflict_level": "UNABLE_TO_CHECK",
            "status_label": "当事人未齐，未做利冲比对",
            "summary": "当事人未齐，未做利冲比对",
            "recommendation": "补齐委托人和对方名称后再排查。",
            "not_checked": list(_NOT_CHECKED_ITEMS),
            "not_checked_note": _NOT_CHECKED_NOTE,
            "registered_record_count": 0,
        }
    same = (data.get("practice") or {}).get("is_same_matter")
    return check_conflict_of_interest(
        client_name=parties["client_name"],
        opposing_party=parties["opposing_name"],
        client_id_or_code=parties["client_id"],
        opposing_id_or_code=parties["opposing_id"],
        cause_of_action=data.get("cause_of_action") or "",
        is_same_matter=same,
        exclude_case_id=exclude_case_id or None,
    )


def _write_parties_and_recheck(matter: Dict[str, Any]) -> Dict[str, Any]:
    """把本案当事人写入利冲底档，再按现有规则重查（不把本案自己算成冲突）。"""
    from gateway.utils.conflict_checker import upsert_matter_conflict_registry

    upsert_matter_conflict_registry(matter)
    return _screen_intake_conflict(matter, exclude_case_id=str(matter.get("matter_id") or ""))


@router.get("/matters/{matter_id}", summary="获取单案件完整空间详情（含案卷、核心图谱与工作流）")
async def api_get_matter(matter_id: str):
    matter = get_matter_by_id(matter_id)
    if not matter:
        raise HTTPException(status_code=404, detail="案件空间不存在")
    return {
        "status": "success",
        "matter": matter
    }


@router.put("/matters/{matter_id}", summary="更新案件空间信息")
async def api_update_matter(matter_id: str, req: MatterUpdateReq):
    from gateway.utils.matter_intake import normalize_matter_intake
    from gateway.utils.matter_vault_db import save_matter_practice

    existing = get_matter_by_id(matter_id)
    if not existing:
        raise HTTPException(status_code=404, detail="案件空间不存在")
    payload = req.model_dump(exclude_unset=True)
    merged = {
        "title": payload.get("title", existing.get("title")),
        "cause_of_action": payload.get("cause_of_action", existing.get("cause_of_action")),
        "client_role": payload.get("client_role", existing.get("client_role")),
        "plaintiff_info": payload.get("plaintiff_info", existing.get("plaintiff_info")),
        "defendant_info": payload.get("defendant_info", existing.get("defendant_info")),
        "plaintiff_name": payload.get("plaintiff_name", existing.get("plaintiff_name")),
        "defendant_name": payload.get("defendant_name", existing.get("defendant_name")),
        "principal_amount": payload.get("principal_amount", existing.get("principal_amount")),
        "case_summary": payload.get("case_summary", existing.get("case_summary")),
        "practice": payload.get("practice", existing.get("practice") or {}),
        "procedure": payload.get("procedure"),
        "fee_type": payload.get("fee_type"),
        "fee_amount": payload.get("fee_amount"),
        "fee_received": payload.get("fee_received"),
        "fee_note": payload.get("fee_note"),
        "risk_disclosed": payload.get("risk_disclosed"),
        "is_same_matter": payload.get("is_same_matter"),
    }
    if "plaintiff_name" in payload:
        plaintiff_info = dict(merged.get("plaintiff_info") or {})
        plaintiff_info["name"] = payload.get("plaintiff_name") or ""
        merged["plaintiff_info"] = plaintiff_info
    if "defendant_name" in payload:
        defendant_info = dict(merged.get("defendant_info") or {})
        defendant_info["name"] = payload.get("defendant_name") or ""
        merged["defendant_info"] = defendant_info
    try:
        normalized = normalize_matter_intake(merged)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    preview = dict(existing)
    preview.update(normalized)
    preview["matter_id"] = matter_id
    screened = _screen_intake_conflict(preview, exclude_case_id=matter_id)
    if screened.get("conflict_level") == "PROHIBITED":
        raise HTTPException(
            status_code=409,
            detail={
                "message": "利益冲突排查结果为禁止代理，不能把当事人改成这一组。",
                "conflict_level": "PROHIBITED",
                "status_label": screened.get("status_label") or "",
                "recommendation": screened.get("recommendation") or "",
            },
        )
    updated = update_matter_record(matter_id, normalized)
    if not updated:
        raise HTTPException(status_code=404, detail="案件空间不存在")
    save_matter_practice(matter_id, normalized.get("practice") or {})
    updated = get_matter_by_id(matter_id)
    conflict = _write_parties_and_recheck(updated)
    save_matter_practice(matter_id, {"conflict": _conflict_snapshot(conflict)})
    updated = get_matter_by_id(matter_id)
    label = (conflict.get("status_label") or "").strip()
    message = "案件空间信息已同步更新"
    if label:
        message += f"。利冲重查：{label}"
    return {
        "status": "success",
        "message": message,
        "conflict": _conflict_snapshot(conflict),
        "matter": updated
    }


# =============================================================================
# 2. 案卷材料挂载与上下文联动
# =============================================================================

@router.patch("/matters/{matter_id}/ledger", summary="保存立案材料清单、已开票金额和用印登记")
async def api_update_matter_ledger(matter_id: str, req: MatterLedgerReq):
    """律师自己登记。不推测法院已受理，也不做开票或用印审批。"""
    from gateway.utils.matter_intake import (
        FILING_NOTICE,
        _money,
        assert_invoice_within_receivable,
        normalize_filing_checklist,
        normalize_seal_records,
        receivable_of,
    )
    from gateway.utils.matter_vault_db import save_matter_practice

    existing = get_matter_by_id(matter_id)
    if not existing:
        raise HTTPException(status_code=404, detail="案件空间不存在")
    practice = dict(existing.get("practice") or {})
    updates: Dict[str, Any] = {"filing_notice": FILING_NOTICE}
    try:
        if "fee_invoiced" in req.model_fields_set:
            invoiced = _money(req.fee_invoiced, "已开票金额")
            assert_invoice_within_receivable(invoiced, receivable_of(practice))
            updates["fee_invoiced"] = invoiced
        if "seal_records" in req.model_fields_set:
            updates["seal_records"] = normalize_seal_records(req.seal_records)
        if "filing_checklist" in req.model_fields_set:
            updates["filing_checklist"] = normalize_filing_checklist(
                req.filing_checklist,
                practice.get("filing_checklist"),
            )
            if any(item.get("status") == "已线下提交" for item in updates["filing_checklist"]):
                from gateway.utils.practice_workflow import drafting_block_reason
                blocked = drafting_block_reason(practice)
                if blocked:
                    raise ValueError(blocked)
        if "local_filing_items" in req.model_fields_set:
            from gateway.utils.practice_workflow import normalize_local_filing_items
            updates["local_filing_items"] = normalize_local_filing_items(req.local_filing_items)
        if "fee_amount" in req.model_fields_set or "fee_received" in req.model_fields_set:
            from gateway.utils.matter_intake import _fee_position
            fee_amount = practice.get("fee_amount") if "fee_amount" not in req.model_fields_set else _money(req.fee_amount, "约定律师费")
            fee_received = practice.get("fee_received") if "fee_received" not in req.model_fields_set else _money(req.fee_received, "已到账律师费")
            updates["fee_amount"] = fee_amount
            updates["fee_received"] = fee_received
            updates.update(_fee_position(
                fee_amount,
                fee_received,
                practice.get("fee_hourly_rate"),
                practice.get("fee_hours"),
                practice.get("fee_receivable") if "fee_amount" not in req.model_fields_set else fee_amount,
            ))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    save_matter_practice(matter_id, updates)
    updated = get_matter_by_id(matter_id)
    return {
        "status": "success",
        "message": "立案清单、开票和用印已保存。状态由律师录入，不代表法院已经受理。",
        "filing_notice": FILING_NOTICE,
        "court_accepted": False,
        "matter": updated,
    }


@router.post("/matters/{matter_id}/documents", summary="挂载案卷材料至空间")
async def api_mount_document(matter_id: str, req: DocumentMountReq):
    matter = get_matter_by_id(matter_id)
    if not matter:
        raise HTTPException(status_code=404, detail="案件空间不存在")

    doc = add_document_to_matter(matter_id, req.to_doc_dict())
    doc["doc_title"] = doc["title"]
    doc["content_text"] = doc["text_content"]
    return {
        "status": "success",
        "message": f"案卷材料【{doc['title']}】已成功挂载入空间",
        "document": doc
    }


@router.post("/matters/{matter_id}/upload-document", summary="直接上传案卷原始文件(PDF/Word/Excel/图片)并自动OCR/文本提取挂载")
async def api_upload_mount_document(
    matter_id: str,
    file: UploadFile = File(...),
    doc_type: str = Form("evidence"),
    redact_on_ingest: bool = Form(True),
):
    matter = get_matter_by_id(matter_id)
    if not matter:
        raise HTTPException(status_code=404, detail="案件空间不存在")

    uploads_dir = str(get_uploads_dir())

    allowed = [".pdf", ".docx", ".png", ".jpg", ".jpeg", ".heic", ".csv", ".xlsx", ".txt"]
    ext = assert_allowed_extension(file.filename, allowed)
    raw = await read_upload_bounded(file)
    validate_magic_bytes(raw, ext)
    stored = storage_name(ext)
    saved_path = safe_join(uploads_dir, stored)

    with open(saved_path, "wb") as buffer:
        buffer.write(raw)

    file_size = os.path.getsize(saved_path)
    is_image = ext in [".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif", ".heic"]
    from gateway.utils.ocr_engine import get_easyocr_reader
    reader = get_easyocr_reader()
    if is_image and reader is None:
        doc_data = {
            "doc_type": doc_type,
            "title": file.filename,
            "doc_title": file.filename,
            "file_path": saved_path,
            "file_size": file_size,
            "text_content": "",
            "content_text": "",
            "metadata": {
                "original_filename": file.filename,
                "stored_name": stored,
                "uploaded_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "extracted_chars": 0,
                "ocr_status": "ocr_unavailable",
                "redact_on_ingest": bool(redact_on_ingest),
                "redacted_count": 0,
            }
        }
        doc = add_document_to_matter(matter_id, doc_data)
        doc["doc_title"] = doc["title"]
        doc["content_text"] = doc["text_content"]
        return {
            "status": "ocr_unavailable",
            "message": "未安装 OCR 组件（easyocr），图片未识别文字，请安装 requirements-optional.txt 或手工录入",
            "extracted_text": "",
            "document": doc,
            "redacted_count": 0,
        }

    # 调用统一 OCR 与文档文本提取引擎（原文件按原样保存在存储目录）
    extracted_text = extract_evidence_text(saved_path)

    redacted_count = 0
    if redact_on_ingest and extracted_text:
        from gateway.utils.pii_sanitizer import pii_sanitizer

        # 入库文字仅掩码身份证号与银行卡号；原文件不变供律师查看
        masked_text, _mapping, stats = pii_sanitizer.mask(
            extracted_text,
            custom_entities=None,
            mask_phones=False,
            mask_id_cards=True,
            mask_bank_cards=True,
            mask_emails=False,
            mask_uscc=False,
            mask_addresses=False,
            mask_role_names=False,
        )
        cats = stats.get("categories") or {}
        redacted_count = int(cats.get("id_card", 0)) + int(cats.get("bank_card", 0))
        extracted_text = masked_text

    doc_data = {
        "doc_type": doc_type,
        "title": file.filename,
        "doc_title": file.filename,
        "file_path": saved_path,
        "file_size": file_size,
        "text_content": extracted_text,
        "content_text": extracted_text,
        "metadata": {
            "original_filename": file.filename,
            "stored_name": stored,
            "uploaded_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "extracted_chars": len(extracted_text),
            "redact_on_ingest": bool(redact_on_ingest),
            "redacted_count": redacted_count,
        }
    }

    doc = add_document_to_matter(matter_id, doc_data)
    doc["doc_title"] = doc["title"]
    doc["content_text"] = doc["text_content"]

    return {
        "status": "success",
        "message": f"文件【{file.filename}】已完成解析并成功挂载入空间",
        "document": doc,
        "redacted_count": redacted_count,
    }



@router.get("/matters/{matter_id}/documents", summary="获取空间案卷材料清单")
async def api_get_matter_documents(matter_id: str):
    matter = get_matter_by_id(matter_id)
    if not matter:
        raise HTTPException(status_code=404, detail="案件空间不存在")
    docs = matter.get("documents", [])
    for d in docs:
        if "doc_title" not in d:
            d["doc_title"] = d.get("title", "")
        if "content_text" not in d:
            d["content_text"] = d.get("text_content", "")
    return {
        "status": "success",
        "matter_id": matter_id,
        "documents": docs
    }


# =============================================================================
# 3. 案件三大核心图谱抽取与持久化 (Timeline / Entity-Graph / Cashflow)
# =============================================================================

@router.post("/matters/{matter_id}/graphs/extract", summary="自动抽取案件核心图谱")
async def api_extract_matter_graphs(matter_id: str, req: Optional[GraphExtractReq] = None):
    req = req or GraphExtractReq()
    matter = get_matter_by_id(matter_id)
    if not matter:
        raise HTTPException(status_code=404, detail="案件空间不存在")

    # 优先采用请求携带的事实，否则读取案件主陈述，并融合当事人主体信息
    p_info = matter.get("plaintiff_info") or {}
    d_info = matter.get("defendant_info") or {}
    p_name = matter.get("plaintiff_name") or (p_info.get("name") if isinstance(p_info, dict) else "")
    d_name = matter.get("defendant_name") or (d_info.get("name") if isinstance(d_info, dict) else "")
    party_prefix = f"【涉案当事人】原告：{p_name}；被告：{d_name}。\n" if (p_name or d_name) else ""
    facts_text = party_prefix + (req.facts_text or matter.get("case_summary", ""))

    # 若开启挂载案卷联动，抓取空间所有文档文本
    doc_text_parts = []
    if req.include_mounted_docs:
        for doc in matter.get("documents", []):
            if doc.get("text_content"):
                doc_text_parts.append(f"《{doc.get('title')}》:\n{doc.get('text_content')}")
    combined_docs_text = "\n\n".join(doc_text_parts)

    graphs = await extract_case_graphs_from_text(facts_text, combined_docs_text)

    # 持久化入库
    save_matter_graphs_db(
        matter_id=matter_id,
        timeline=graphs.get("timeline", []),
        entity_graph=graphs.get("entity_graph", {"nodes": [], "edges": []}),
        cashflow=graphs.get("cashflow", [])
    )

    return {
        "status": "success",
        "matter_id": matter_id,
        "message": "案件三大核心图谱已完成智能抽取与持久化",
        "graphs": graphs
    }


@router.get("/matters/{matter_id}/graphs", summary="获取已保存的案件核心图谱")
async def api_get_matter_graphs(matter_id: str):
    matter = get_matter_by_id(matter_id)
    if not matter:
        raise HTTPException(status_code=404, detail="案件空间不存在")

    return {
        "status": "success",
        "matter_id": matter_id,
        "graphs": matter.get("graphs", {
            "timeline": [],
            "entity_graph": {"nodes": [], "edges": []},
            "cashflow": []
        })
    }


@router.post("/matters/{matter_id}/guarantee-analysis", summary="多方交叉担保拓扑与保证期间灭失/物保顺位深度分析")
async def api_matter_guarantee_analysis(matter_id: str, req: Optional[GuaranteeAnalysisReq] = None):
    req = req or GuaranteeAnalysisReq()
    matter = get_matter_by_id(matter_id)
    if not matter:
        raise HTTPException(status_code=404, detail="案件空间不存在")
    graphs = matter.get("graphs", {})
    entity_g = graphs.get("entity_graph", {"nodes": [], "edges": []})
    nodes = req.override_nodes if req.override_nodes is not None else entity_g.get("nodes", [])
    edges = req.override_edges if req.override_edges is not None else entity_g.get("edges", [])
    timeline = graphs.get("timeline", [])
    # 接口返回 200 + insufficient_data 结构（缺少主债务到期日时由引擎判定）
    return analyze_guarantee_topology_and_deadlines(
        nodes=nodes,
        edges=edges,
        timeline=timeline,
        principal_due_date=req.principal_due_date,
        today_date=req.today_date
    )


def _extract_start_date_from_graphs(graphs: Dict[str, Any], flows: List[Dict[str, Any]]) -> Optional[str]:
    """从图谱时间线放款/起息事件或出借流水提取起息日。"""
    for ev in graphs.get("timeline", []) or []:
        text = str(ev.get("event", "") or "")
        tag = str(ev.get("legal_tag", "") or "")
        blob = text + " " + tag
        if any(k in blob for k in ("放款", "起息", "出借", "交付", "电汇本金", "借款实际交付")):
            d = str(ev.get("date", "") or "")[:10]
            if d:
                return d
    for f in flows or []:
        purpose = str(f.get("purpose", "") or "")
        if any(k in purpose for k in ("借款", "出借", "放款", "本金出借", "交付")):
            d = str(f.get("date", "") or "")[:10]
            if d:
                return d
    return None


@router.post("/matters/{matter_id}/cashflow-audit", summary="资金穿透流水大屏与民法典第561条法定冲抵对账")
async def api_matter_cashflow_audit(matter_id: str, req: Optional[CashflowAuditReq] = None):
    req = req or CashflowAuditReq()
    matter = get_matter_by_id(matter_id)
    if not matter:
        raise HTTPException(status_code=404, detail="案件空间不存在")
    graphs = matter.get("graphs", {})
    flows = req.override_cashflow if req.override_cashflow is not None else graphs.get("cashflow", [])

    principal = req.principal_amount if req.principal_amount is not None else matter.get("principal_amount")
    rate = req.annual_interest_rate if req.annual_interest_rate is not None else req.annual_rate
    if principal is None:
        raise HTTPException(status_code=422, detail="缺少 principal_amount（请求体或案件本金）")
    if rate is None:
        raise HTTPException(status_code=422, detail="缺少 annual_interest_rate / annual_rate")

    start_date = req.start_date or _extract_start_date_from_graphs(graphs, flows)
    if not start_date:
        return {
            "status": "insufficient_data",
            "missing_fields": ["start_date"],
            "message": "缺少起息日/放款日，无法进行流水对账",
            "reconciliation_ledger": [],
            "unclassified_records": [],
        }

    return audit_and_reconcile_cashflow(
        cashflow_records=flows,
        principal_amount=principal,
        annual_interest_rate=rate,
        start_date=start_date,
        contract_date=req.contract_date,
        filing_date=req.filing_date,
        fees=req.fees or 0.0,
        agreed_offset_order=req.agreed_offset_order,
    )



# =============================================================================
# 4. 人机协同断点工作流 (Human-in-the-Loop State Machine)
# =============================================================================

def format_workflow_response(res: Dict[str, Any]) -> Dict[str, Any]:
    step_data = res.get("step_data") or {}
    s1 = step_data.get("step1") or {}
    s2 = step_data.get("step2") or {}
    s3 = step_data.get("step3") or {}
    s4 = step_data.get("step4") or {}
    s5 = step_data.get("step5") or {}

    # 提取诉讼请求候选文本。抽不出就保持空列表，不用别的案子补。
    candidate_claims = []
    for c in s1.get("candidate_claims", []) or []:
        if isinstance(c, dict):
            text = c.get("text") or c.get("claim") or ""
        else:
            text = str(c or "")
        text = str(text).strip()
        if text:
            candidate_claims.append(text)

    # 提取法规依据
    applicable_statutes = []
    for b in s1.get("candidate_legal_basis", []) or []:
        if isinstance(b, dict):
            text = b.get("norm") or b.get("statute") or ""
        else:
            text = str(b or "")
        text = str(text).strip()
        if text:
            applicable_statutes.append(text)

    # 提取对方抗辩预测。没有写出抗辩点的条目丢掉，不补微信或催告情节。
    defense_predictions = []
    raw_defs = s3.get("defense_predictions") or s3.get("opponent_defenses") or []
    for d in raw_defs:
        if isinstance(d, dict):
            point = str(d.get("focus") or d.get("point") or d.get("defense_point") or "").strip()
            if not point:
                continue
            defense_predictions.append({
                "defense_point": point,
                "basis": d.get("opponent_argument") or d.get("basis") or d.get("legal_basis") or "",
                "counter_strategy": d.get("counter_strategy") or d.get("counter") or "",
                "recommended_action": d.get("recommended_action") or ""
            })
        else:
            point = str(d or "").strip()
            if point:
                defense_predictions.append({
                    "defense_point": point,
                    "basis": "",
                    "counter_strategy": "",
                    "recommended_action": ""
                })

    wf_dict = {
        "workflow_id": res.get("workflow_id"),
        "matter_id": res.get("matter_id") or step_data.get("matter_id"),
        "current_step": res.get("current_step"),
        "status": res.get("step_status"),
        "step_status": res.get("step_status"),
        "is_completed": res.get("current_step") == 5,
        "step1_facts": {
            "cause_of_action": s1.get("cause_of_action") or (s1.get("suggested_causes_of_action", [{}])[0].get("cause") if s1.get("suggested_causes_of_action") else "案由待律师选择"),
            "disputed_amount": s1.get("disputed_amount"),
            "core_facts": s1.get("core_facts", [])
        },
        "step2_claims": {
            "candidate_claims": candidate_claims,
            "applicable_statutes": applicable_statutes,
            "confirmed_claims": s2.get("confirmed_claims", []),
            "confirmed_legal_basis": s2.get("confirmed_legal_basis", [])
        },
        "step3_statutes": {
            "applicable_statutes": s3.get("applicable_statutes", []),
            "opponent_defense_predictions": defense_predictions
        },
        "step4_defenses": s4,
        "step5_final_draft": {
            "final_pleading_text": s5.get("pleading_text", ""),
            "statute_citations": s5.get("citation_audit", {}).get("citations", []),
            "citation_audit": s5.get("citation_audit", {})
        },
        "step_data": step_data
    }
    return {
        "status": "success",
        "message": f"工作流处于第 {res.get('current_step')} 步: {res.get('step_name', '')}",
        "workflow": wf_dict,
        **res
    }


@router.post("/workflows/start", summary="启动人机协同断点工作流")
async def api_start_workflow(req: WorkflowStartReq):
    matter = get_matter_by_id(req.matter_id)
    if matter:
        from gateway.utils.practice_workflow import drafting_block_reason
        blocked = drafting_block_reason(matter.get("practice") or {})
        if blocked:
            raise HTTPException(status_code=409, detail=blocked)
    case_title = req.case_title or (matter.get("title") if matter else "未命名诉讼案件")
    facts_text = req.facts_text or req.initial_facts or (matter.get("case_summary") if matter else "")

    res = await start_litigation_workflow(
        matter_id=req.matter_id,
        case_title=case_title,
        facts_text=facts_text,
        client_role=req.client_role,
        perspective=req.perspective
    )
    return format_workflow_response(res)


@router.post("/workflows/{workflow_id}/advance", summary="核准断点数据并推进工作流")
async def api_advance_workflow(workflow_id: str, req: WorkflowAdvanceReq):
    from gateway.utils.workflow_engine import WorkflowValidationError
    try:
        decisions = req.confirmed_data or req.human_decisions or {}
        res = await advance_workflow_step(workflow_id, decisions)
        return format_workflow_response(res)
    except WorkflowValidationError as e:
        raise HTTPException(
            status_code=422,
            detail={"message": str(e), "missing_fields": e.missing_fields},
        )
    except Exception as e:
        logger.error(f"推进工作流失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="推进办案工作流异常，请稍后重试")


@router.post("/workflows/{workflow_id}/rollback", summary="回退工作流至前序断点")
async def api_rollback_workflow(workflow_id: str, req: WorkflowRollbackReq):
    try:
        res = rollback_workflow_step(workflow_id, req.target_step)
        return format_workflow_response(res)
    except Exception as e:
        logger.error(f"回退工作流失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="回退办案工作流异常，请检查目标步骤是否存在")


@router.get("/workflows/{workflow_id}", summary="获取工作流状态与断点数据")
async def api_get_workflow(workflow_id: str):
    wf = get_workflow_by_id(workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="工作流记录不存在")
    return format_workflow_response(wf)


class MatterStatusPatchReq(BaseModel):
    status: str = Field(..., description="目标状态: active 或 archived")
    closeout: Optional[Dict[str, Any]] = None


class DeadlineCreateReq(BaseModel):
    matter_id: Optional[str] = None
    kind: str = Field(..., description="期限种类: statute_limitation/appeal/defense_answer/evidence_production/preservation_renewal/enforcement_application/hearing/service_received/custom")
    due_date: str = Field(..., description="截止日期 ISO 格式 (YYYY-MM-DD 或带时间)")
    source: Optional[str] = Field("", description="计算器名称及输入摘要")
    note: Optional[str] = Field("", description="律师备忘与提醒要点")
    origin: Optional[str] = Field("lawyer_note", description="court_notice 法院通知 / statutory_calc 法定推算 / lawyer_note 律师备忘")
    done: Optional[bool] = False


_ISO_DATE_PATTERN = re.compile(r'^\d{4}-\d{2}-\d{2}(?:[T\s]\d{2}:\d{2}(?::\d{2})?)?$')


@router.patch("/matters/{matter_id}/status", summary="案件状态流转 (active <-> archived, draft -> active)")
async def api_patch_matter_status(matter_id: str, req: MatterStatusPatchReq):
    matter = get_matter_by_id(matter_id)
    if not matter:
        raise HTTPException(status_code=404, detail="案件空间不存在")
    if req.status == "archived":
        from gateway.utils.practice_workflow import closeout_blockers, normalize_closeout, open_procedural_deadlines
        from gateway.utils.matter_vault_db import list_matter_deadlines, save_matter_practice
        practice = dict(matter.get("practice") or {})
        if req.closeout is not None:
            try:
                practice["closeout"] = normalize_closeout(req.closeout)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            save_matter_practice(matter_id, {"closeout": practice["closeout"]})
        deadlines = list_matter_deadlines(matter_id=matter_id)
        blockers = closeout_blockers(practice, deadlines)
        if blockers:
            raise HTTPException(status_code=422, detail={
                "message": "结案事项还没确认，不能归档。" + "；".join(blockers),
                "blockers": blockers,
                "open_deadlines": [
                    {"kind": item.get("kind"), "due_date": item.get("due_date"), "note": item.get("note") or ""}
                    for item in open_procedural_deadlines(deadlines)
                ],
            })
    try:
        updated = update_matter_status(matter_id, req.status)
        if not updated:
            raise HTTPException(status_code=404, detail="案件空间不存在")
        return {
            "status": "success",
            "message": f"案件状态已成功更新为 {req.status}",
            "matter": updated
        }
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.delete("/matters/{matter_id}", summary="删除案件（原件删除，索引和证件号默认保留）")
async def api_delete_matter(
    matter_id: str,
    confirm: bool = Query(False, description="必须传 confirm=true 才能执行删除"),
    scrub_identifiers: bool = Query(False, description="连同证件号从案件行抹去"),
):
    if not confirm:
        raise HTTPException(status_code=422, detail="删除需要 ?confirm=true 确认")
    matter = get_matter_by_id(matter_id)
    if not matter:
        raise HTTPException(status_code=404, detail="案件空间不存在")
    ok = soft_delete_matter(matter_id)
    registry_note = ""
    if scrub_identifiers:
        from gateway.utils.matter_vault_db import scrub_matter_direct_identifiers
        scrubbed = scrub_matter_direct_identifiers(matter_id)
        registry_note = scrubbed.get("registry_note") or ""
        message = f"案件【{matter['title']}】原件已删，已连同证件号从案件行抹去。{registry_note}"
    else:
        message = f"案件【{matter['title']}】原件已删，案件索引和证件号仍保留"
    try:
        from gateway.utils.matter_vault_db import record_audit_log
        record_audit_log(
            action="matter_delete_scrub_identifiers" if scrub_identifiers else "matter_delete",
            matter_id=matter_id,
            target=matter_id,
        )
    except Exception as audit_err:
        logger.warning(f"记录案件删除审计日志失败: {audit_err}")
    return {
        "status": "success",
        "message": message,
        "deleted": ok,
        "identifiers_retained": not scrub_identifiers,
        "scrubbed_identifiers": scrub_identifiers,
        "conflict_registry_note": registry_note,
    }


@router.delete("/matters/{matter_id}/documents/{doc_id}", summary="删除案件名下单份案卷材料原件及记录")
async def api_delete_matter_document(matter_id: str, doc_id: str):
    matter = get_matter_by_id(matter_id)
    if not matter:
        raise HTTPException(status_code=404, detail="案件空间不存在")
    ok = delete_document_from_matter(matter_id, doc_id)
    if not ok:
        raise HTTPException(status_code=404, detail="案卷材料不存在或已被删除")
    try:
        from gateway.utils.matter_vault_db import record_audit_log
        record_audit_log(action="document_delete", matter_id=matter_id, target=doc_id)
    except Exception as audit_err:
        logger.warning(f"记录材料删除审计日志失败: {audit_err}")
    return {
        "status": "success",
        "message": f"案卷材料【{doc_id}】原件已从存储目录删除",
        "deleted": True
    }


@router.post("/deadlines", summary="新增案件期限")
async def api_create_deadline(req: DeadlineCreateReq):
    allowed_kinds = [
        "statute_limitation", "appeal", "preservation_renewal",
        "enforcement_application", "hearing", "defense_answer",
        "evidence_production", "service_received", "custom",
        "labor_arbitration", "labor_award_sue", "labor_award_revoke",
        "arbitration_set_aside",
    ]
    allowed_origins = {"court_notice", "statutory_calc", "lawyer_note"}
    if req.kind not in allowed_kinds:
        raise HTTPException(status_code=422, detail=f"不支持的期限种类: {req.kind}，允许值: {allowed_kinds}")
    if (req.origin or "lawyer_note") not in allowed_origins:
        raise HTTPException(status_code=422, detail="期限来源只接受法院通知、法定推算或律师备忘")
    if not _ISO_DATE_PATTERN.match(req.due_date.strip()):
        raise HTTPException(status_code=422, detail=f"due_date 必须是 ISO 格式日期 (YYYY-MM-DD 或带时间)，非法值: {req.due_date}")

    dl = create_matter_deadline(req.model_dump())
    return {
        "status": "success",
        "message": "期限记录已成功加入日历",
        "deadline": dl
    }


@router.get("/matters/{matter_id}/deadlines", summary="查询单个案件已录期限")
async def api_get_matter_deadlines(
    matter_id: str,
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
):
    """与 GET /deadlines?matter_id= 同一份清单，含法院通知来源。"""
    matter = get_matter_by_id(matter_id)
    if not matter:
        raise HTTPException(status_code=404, detail="案件空间不存在")
    deadlines = list_matter_deadlines(from_date=from_date, to_date=to_date, matter_id=matter_id)
    return {
        "status": "success",
        "count": len(deadlines),
        "deadlines": deadlines,
        "matter_id": matter_id,
    }


class PracticeDeskReq(BaseModel):
    claims: Optional[List[Dict[str, Any]]] = None
    extra_parties: Optional[List[Dict[str, Any]]] = None
    conflict_conclusion: Optional[Dict[str, Any]] = None
    defendant_posture: Optional[Dict[str, Any]] = None
    local_filing_items: Optional[List[Dict[str, Any]]] = None
    jurisdiction_facts: Optional[str] = None
    jurisdiction_confirm: Optional[Dict[str, Any]] = None


@router.get("/cause-catalog", summary="民事案由目录")
async def api_cause_catalog():
    from gateway.utils.practice_workflow import CAUSE_CATALOG, DOCUMENT_PRESETS
    return {
        "status": "success",
        "catalog": CAUSE_CATALOG,
        "document_presets": list(DOCUMENT_PRESETS),
        "note": "目录来自民事案件案由规定中的常用案由。不在目录里的案由可以手写，但必须另选文书模板，不会默认成民间借贷。",
    }


@router.get("/deadlines/board", summary="打开工作台即看的期限清单")
async def api_deadline_board():
    from gateway.utils.practice_workflow import build_deadline_board
    deadlines = list_matter_deadlines()
    return {"status": "success", **build_deadline_board(deadlines)}


@router.post("/matters/{matter_id}/practice-desk", summary="保存并列请求、管辖、当事人、利冲结论和被告侧事项")
async def api_save_practice_desk(matter_id: str, req: PracticeDeskReq):
    from gateway.utils.practice_workflow import (
        normalize_claims,
        normalize_conflict_conclusion,
        normalize_defendant_posture,
        normalize_extra_parties,
        normalize_local_filing_items,
        recommend_jurisdiction,
    )
    from gateway.utils.matter_vault_db import save_matter_practice

    existing = get_matter_by_id(matter_id)
    if not existing:
        raise HTTPException(status_code=404, detail="案件空间不存在")
    practice = dict(existing.get("practice") or {})
    updates: Dict[str, Any] = {}
    try:
        if req.claims is not None:
            updates["claims"] = normalize_claims(req.claims, existing.get("cause_of_action") or "")
        if req.extra_parties is not None:
            updates["extra_parties"] = normalize_extra_parties(req.extra_parties)
        if req.conflict_conclusion is not None:
            updates["conflict_conclusion"] = normalize_conflict_conclusion(req.conflict_conclusion)
        if req.defendant_posture is not None:
            updates["defendant_posture"] = normalize_defendant_posture(req.defendant_posture)
        if req.local_filing_items is not None:
            updates["local_filing_items"] = normalize_local_filing_items(req.local_filing_items)
        if req.jurisdiction_facts is not None:
            jurisdiction = recommend_jurisdiction(
                req.jurisdiction_facts,
                existing.get("cause_of_action") or "",
                (practice.get("procedure") or ""),
            )
            jurisdiction["facts"] = req.jurisdiction_facts
            updates["jurisdiction"] = jurisdiction
        if req.jurisdiction_confirm is not None:
            current = dict(updates.get("jurisdiction") or practice.get("jurisdiction") or {})
            if not current.get("tracks") and req.jurisdiction_facts is None:
                raise ValueError("先根据案情判断管辖路径，再确认受理机关。")
            forum = str((req.jurisdiction_confirm or {}).get("confirmed_forum") or "").strip()
            if not forum:
                raise ValueError("请写明确认的仲裁委员会或法院。")
            current["confirmed_forum"] = forum
            current["override_reason"] = str((req.jurisdiction_confirm or {}).get("override_reason") or "").strip()
            updates["jurisdiction"] = current
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if updates:
        save_matter_practice(matter_id, updates)
    updated = get_matter_by_id(matter_id)
    return {"status": "success", "matter": updated}


@router.get("/deadlines", summary="查询案件期限日历")
async def api_get_deadlines(
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
    matter_id: Optional[str] = None
):
    deadlines = list_matter_deadlines(from_date=from_date, to_date=to_date, matter_id=matter_id)
    return {
        "status": "success",
        "count": len(deadlines),
        "deadlines": deadlines
    }


@router.get("/audit-log", summary="案件空间审计日志查询（分页）")
async def api_vault_get_audit_log(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    action: Optional[str] = Query(None),
    matter_id: Optional[str] = Query(None)
):
    from gateway.utils.matter_vault_db import get_audit_logs
    data = get_audit_logs(page=page, page_size=page_size, action=action, matter_id=matter_id)
    return {
        "status": "success",
        "data": data
    }


class FirmRosterLawyerReq(BaseModel):
    lawyer_name: str
    license_no: str = ""
    id_no: str = ""
    law_firm: str = ""
    phone: str = ""
    relatives: Optional[List[Dict[str, Any]]] = None
    is_default: bool = False


class PersonnelScreenReq(BaseModel):
    client_role: str = "原告"
    plaintiff_name: str = ""
    defendant_name: str = ""
    plaintiff_id: str = ""
    defendant_id: str = ""
    opposing_name: str = ""
    opposing_id: str = ""


@router.post("/personnel-screen", summary="接案前查看本所人员及近亲属比对")
async def api_screen_personnel(req: PersonnelScreenReq):
    from gateway.utils.firm_roster import screen_personnel
    from gateway.utils.matter_intake import conflict_parties

    has_parties = any(
        str(value or "").strip()
        for value in (req.plaintiff_name, req.defendant_name, req.plaintiff_id, req.defendant_id)
    )
    if has_parties:
        parties = conflict_parties({
            "client_role": req.client_role or "原告",
            "plaintiff_name": req.plaintiff_name,
            "defendant_name": req.defendant_name,
            "plaintiff_info": {"name": req.plaintiff_name, "id_no": req.plaintiff_id},
            "defendant_info": {"name": req.defendant_name, "id_no": req.defendant_id},
        })
        opposing_name = parties["opposing_name"]
        opposing_id = parties["opposing_id"]
        party_ids = [parties["client_id"], parties["opposing_id"]]
    else:
        opposing_name = req.opposing_name
        opposing_id = req.opposing_id
        party_ids = [req.opposing_id]
    personnel = screen_personnel(opposing_name, opposing_id, party_ids=party_ids)
    return {"status": "success", "personnel": personnel}


@router.get("/firm-roster", summary="本所律师名册")
async def api_list_firm_roster():
    from gateway.utils.firm_roster import NOT_RECORDED_TEXT, list_lawyers

    lawyers = list_lawyers()
    return {
        "status": "success",
        "lawyers": lawyers,
        "empty_notice": "" if lawyers else NOT_RECORDED_TEXT,
    }


@router.get("/firm-roster/default", summary="文书默认承办律师")
async def api_default_firm_counsel():
    from gateway.utils.firm_roster import default_counsel

    return {"status": "success", "lawyer": default_counsel()}


@router.post("/firm-roster", summary="保存本所律师")
async def api_save_firm_lawyer(req: FirmRosterLawyerReq):
    from gateway.utils.firm_roster import save_lawyer

    try:
        lawyer = save_lawyer(req.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"status": "success", "lawyer": lawyer}


@router.delete("/firm-roster/{lawyer_id}", summary="删除本所律师")
async def api_delete_firm_lawyer(lawyer_id: int):
    from gateway.utils.firm_roster import delete_lawyer

    delete_lawyer(lawyer_id)
    return {"status": "success"}
