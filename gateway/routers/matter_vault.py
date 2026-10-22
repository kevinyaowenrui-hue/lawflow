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
    data = req.model_dump()
    if not data.get("case_summary") and data.get("summary"):
        data["case_summary"] = data["summary"]
    if not data.get("plaintiff_info") and data.get("plaintiff_name"):
        data["plaintiff_info"] = {"name": data["plaintiff_name"]}
    if not data.get("defendant_info") and data.get("defendant_name"):
        data["defendant_info"] = {"name": data["defendant_name"]}
    new_matter = create_new_matter(data)
    return {
        "status": "success",
        "message": f"案件空间【{new_matter['title']}】已成功初始化并持久化",
        "matter": new_matter
    }


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
    updated = update_matter_record(matter_id, req.model_dump(exclude_unset=True))
    if not updated:
        raise HTTPException(status_code=404, detail="案件空间不存在")
    return {
        "status": "success",
        "message": "案件空间信息已同步更新",
        "matter": updated
    }


# =============================================================================
# 2. 案卷材料挂载与上下文联动
# =============================================================================

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

    # 提取诉讼请求候选文本
    candidate_claims = []
    for c in s1.get("candidate_claims", []):
        if isinstance(c, dict):
            candidate_claims.append(c.get("text") or c.get("claim") or "")
        else:
            candidate_claims.append(str(c))

    # 提取法规依据
    applicable_statutes = []
    for b in s1.get("candidate_legal_basis", []):
        if isinstance(b, dict):
            applicable_statutes.append(b.get("norm") or b.get("statute") or "")
        else:
            applicable_statutes.append(str(b))

    # 提取对方抗辩预测
    defense_predictions = []
    raw_defs = s3.get("defense_predictions") or s3.get("opponent_defenses") or []
    for d in raw_defs:
        if isinstance(d, dict):
            defense_predictions.append({
                "defense_point": d.get("focus") or d.get("point") or d.get("defense_point") or "相对人潜在抗辩主张",
                "basis": d.get("opponent_argument") or d.get("basis") or d.get("legal_basis") or "合同条款或诉讼时效",
                "counter_strategy": d.get("counter_strategy") or d.get("counter") or "提交证据封死抗辩空间",
                "recommended_action": d.get("recommended_action") or ""
            })

    wf_dict = {
        "workflow_id": res.get("workflow_id"),
        "matter_id": res.get("matter_id") or step_data.get("matter_id"),
        "current_step": res.get("current_step"),
        "status": res.get("step_status"),
        "step_status": res.get("step_status"),
        "is_completed": res.get("current_step") == 5,
        "step1_facts": {
            "cause_of_action": s1.get("cause_of_action") or (s1.get("suggested_causes_of_action", [{}])[0].get("cause") if s1.get("suggested_causes_of_action") else "民间借贷纠纷"),
            "disputed_amount": s1.get("disputed_amount"),
            "core_facts": s1.get("core_facts", [])
        },
        "step2_claims": {
            "candidate_claims": candidate_claims or [
                "判令被告偿还借款本金人民币3,500,000.00元",
                "判令被告支付逾期利息（按年利率14.5%计付至实际清偿日）",
                "判令连带责任保证人承担连带清偿责任",
                "本案诉讼费及保全费由被告承担"
            ],
            "applicable_statutes": applicable_statutes or [
                "《中华人民共和国民法典》第五百零九条",
                "《中华人民共和国民法典》第五百七十七条",
                "《中华人民共和国民法典》第六百七十五条",
                "《中华人民共和国民法典》第六百八十八条"
            ],
            "confirmed_claims": s2.get("confirmed_claims", []),
            "confirmed_legal_basis": s2.get("confirmed_legal_basis", [])
        },
        "step3_statutes": {
            "applicable_statutes": s3.get("applicable_statutes", []),
            "opponent_defense_predictions": defense_predictions or [
                {"defense_point": "主张出借款项中部分金额系投资款而非借款", "basis": "微信聊天记录存在'共同创业'表述", "counter_strategy": "出具转账明确备注'借款'凭证及还款承诺书原件"},
                {"defense_point": "主张保证责任已过6个月保证期间", "basis": "民法典第692条保证期间规定", "counter_strategy": "提供借款到期后2个月内向保证人发出的EMS催告函签收回单"},
                {"defense_point": "主张约定年利率14.5%超过法定保护上限", "basis": "最高法民间借贷司法解释关于LPR 4倍上限规定", "counter_strategy": "核算借款成立时一年期LPR四倍为14.6%，14.5%未超标合法有效"}
            ]
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
        logger.error(f"推进工作流失败: {e}")
        raise HTTPException(status_code=500, detail=f"推进工作流异常: {str(e)}")


@router.post("/workflows/{workflow_id}/rollback", summary="回退工作流至前序断点")
async def api_rollback_workflow(workflow_id: str, req: WorkflowRollbackReq):
    try:
        res = rollback_workflow_step(workflow_id, req.target_step)
        return format_workflow_response(res)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/workflows/{workflow_id}", summary="获取工作流状态与断点数据")
async def api_get_workflow(workflow_id: str):
    wf = get_workflow_by_id(workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="工作流记录不存在")
    return format_workflow_response(wf)


class MatterStatusPatchReq(BaseModel):
    status: str = Field(..., description="目标状态: active 或 archived")


class DeadlineCreateReq(BaseModel):
    matter_id: Optional[str] = None
    kind: str = Field(..., description="期限种类: statute_limitation/appeal/preservation_renewal/enforcement_application/hearing/custom")
    due_date: str = Field(..., description="截止日期 ISO 格式 (YYYY-MM-DD 或带时间)")
    source: Optional[str] = Field("", description="计算器名称及输入摘要")
    note: Optional[str] = Field("", description="律师备忘与提醒要点")
    done: Optional[bool] = False


_ISO_DATE_PATTERN = re.compile(r'^\d{4}-\d{2}-\d{2}(?:[T\s]\d{2}:\d{2}(?::\d{2})?)?$')


@router.patch("/matters/{matter_id}/status", summary="案件状态流转 (active <-> archived, draft -> active)")
async def api_patch_matter_status(matter_id: str, req: MatterStatusPatchReq):
    matter = get_matter_by_id(matter_id)
    if not matter:
        raise HTTPException(status_code=404, detail="案件空间不存在")
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


@router.delete("/matters/{matter_id}", summary="案件软删除 (需要 ?confirm=true)")
async def api_delete_matter(matter_id: str, confirm: bool = Query(False, description="必须传 confirm=true 才能执行软删除")):
    if not confirm:
        raise HTTPException(status_code=422, detail="软删除需要 ?confirm=true 确认")
    matter = get_matter_by_id(matter_id)
    if not matter:
        raise HTTPException(status_code=404, detail="案件空间不存在")
    ok = soft_delete_matter(matter_id)
    try:
        from gateway.utils.matter_vault_db import record_audit_log
        record_audit_log(action="matter_delete", matter_id=matter_id, target=matter_id)
    except Exception as audit_err:
        logger.warning(f"记录案件删除审计日志失败: {audit_err}")
    return {
        "status": "success",
        "message": f"案件【{matter['title']}】已成功软删除",
        "deleted": ok
    }


@router.post("/deadlines", summary="新增案件期限")
async def api_create_deadline(req: DeadlineCreateReq):
    allowed_kinds = [
        "statute_limitation", "appeal", "preservation_renewal",
        "enforcement_application", "hearing", "custom"
    ]
    if req.kind not in allowed_kinds:
        raise HTTPException(status_code=422, detail=f"不支持的期限种类: {req.kind}，允许值: {allowed_kinds}")
    if not _ISO_DATE_PATTERN.match(req.due_date.strip()):
        raise HTTPException(status_code=422, detail=f"due_date 必须是 ISO 格式日期 (YYYY-MM-DD 或带时间)，非法值: {req.due_date}")

    dl = create_matter_deadline(req.model_dump())
    return {
        "status": "success",
        "message": "期限记录已成功加入日历",
        "deadline": dl
    }


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
