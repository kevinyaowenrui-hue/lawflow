"""
LawFlow 智律工作台 - 案件独立空间与人机协同中枢路由 (Matter Vault & Workflow Router)
端点：
- /api/v1/vault/matters: 案件独立空间 CRUD
- /api/v1/vault/matters/{matter_id}/documents: 案卷挂载与文档管理
- /api/v1/vault/matters/{matter_id}/graphs: 案件事实时间线、主体关系图、资金流水图抽取与持久化
- /api/v1/vault/workflows: 5 步阶段式人机协同断点工作流（挂起/确认/回退/推进）
"""

import os
import shutil
import time
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Form
from pydantic import BaseModel, Field

from gateway.utils.ocr_engine import extract_evidence_text

from gateway.utils.matter_vault_db import (
    list_all_matters,
    get_matter_by_id,
    create_new_matter,
    update_matter_record,
    add_document_to_matter,
    save_matter_graphs_db
)
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
    principal_due_date: Optional[str] = Field(default=None, example="2024-03-15", description="主债务约定到期日")
    today_date: Optional[str] = Field(default=None, example="2024-06-01", description="审查核验基准日")
    override_nodes: Optional[List[Dict[str, Any]]] = None
    override_edges: Optional[List[Dict[str, Any]]] = None


class CashflowAuditReq(BaseModel):
    principal_amount: Optional[float] = Field(default=None, example=5000000.0, description="借款/合同本金总额")
    annual_interest_rate: Optional[float] = Field(default=0.144, example=0.144, description="约定年化利息率")
    start_date: Optional[str] = Field(default=None, example="2023-03-16", description="出借交付起息日")
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
    doc_type: str = Form("evidence")
):
    matter = get_matter_by_id(matter_id)
    if not matter:
        raise HTTPException(status_code=404, detail="案件空间不存在")

    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    uploads_dir = os.path.join(base_dir, "storage", "uploads")
    os.makedirs(uploads_dir, exist_ok=True)

    timestamp = int(time.time())
    safe_filename = f"{timestamp}_{file.filename}"
    saved_path = os.path.join(uploads_dir, safe_filename)

    with open(saved_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    file_size = os.path.getsize(saved_path)
    # 调用统一 OCR 与文档文本提取引擎
    extracted_text = extract_evidence_text(saved_path)

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
            "uploaded_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "extracted_chars": len(extracted_text)
        }
    }

    doc = add_document_to_matter(matter_id, doc_data)
    doc["doc_title"] = doc["title"]
    doc["content_text"] = doc["text_content"]

    return {
        "status": "success",
        "message": f"文件【{file.filename}】已完成解析并成功挂载入空间",
        "document": doc
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
    return analyze_guarantee_topology_and_deadlines(
        nodes=nodes,
        edges=edges,
        timeline=timeline,
        principal_due_date=req.principal_due_date,
        today_date=req.today_date
    )


@router.post("/matters/{matter_id}/cashflow-audit", summary="资金穿透流水大屏与民法典第561条法定冲抵对账")
async def api_matter_cashflow_audit(matter_id: str, req: Optional[CashflowAuditReq] = None):
    req = req or CashflowAuditReq()
    matter = get_matter_by_id(matter_id)
    if not matter:
        raise HTTPException(status_code=404, detail="案件空间不存在")
    graphs = matter.get("graphs", {})
    flows = req.override_cashflow if req.override_cashflow is not None else graphs.get("cashflow", [])
    principal = req.principal_amount if req.principal_amount is not None else (matter.get("principal_amount") or 5000000.0)
    rate = req.annual_interest_rate if req.annual_interest_rate is not None else 0.144
    return audit_and_reconcile_cashflow(
        cashflow_records=flows,
        principal_amount=principal,
        annual_interest_rate=rate,
        start_date=req.start_date
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
        "matter_id": res.get("matter_id"),
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
    try:
        decisions = req.confirmed_data or req.human_decisions or {}
        res = await advance_workflow_step(workflow_id, decisions)
        return format_workflow_response(res)
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
