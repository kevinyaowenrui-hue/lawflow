"""
LawFlow 智律工作台 - 阶段三：律所私有知识库检索 + 无纸化电子签约
包含：
1. 中国法律文本结构专用正则切片器 (chinese_law_chunker: 编-章-节-条-款 精准切片，绝不切断法条)
2. 【公共法规库】与【律所私有胜诉案例库】双库隔离检索与上下文增强 (POST /api/v1/phase3/rag/search, /api/v1/phase3/rag/consult)
3. 远程委托电子签约闭环 (POST /api/v1/phase3/create-signing-link, /api/v1/phase3/signing-webhook)
"""

import os
import re
import uuid
import time
import logging
import hmac
import html
import json
import hashlib
import secrets
import sqlite3
from datetime import datetime
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
import httpx
import pymupdf as fitz

from gateway.core.ollama_client import ollama_client
from gateway.core.db import connect
from gateway.core.paths import get_generated_dir, get_vault_db_path
from gateway.utils.cn_legal_calc import rmb_to_capital

logger = logging.getLogger("lawflow.phase3")
router = APIRouter(tags=["阶段三：私有类案检索与电子签约"])

DEMO_SIGNING_NOTICE = "演示模式：未接入真实电子签名服务，签署结果不具有法律效力"
FILE_SHA256_LABEL = "文件 SHA-256 摘要（用于比对文件是否被修改，不等于第三方存证）"
DEFAULT_WEBHOOK_HEADER = "X-LawFlow-Webhook-Secret"


# ==============================================================================
# 1. 中国法律文本结构（编-章-节-条-款）专用正则切片器 (Chinese Law Chunker)
# ==============================================================================
def chinese_law_chunker(raw_text: str, law_name: str = "法律法规") -> List[Dict[str, Any]]:
    """
    专用法律正则切片器：
    解析“编、章、节、条、款”层级，以【条】为最小独立单元，确保绝不将同一法条切断。
    """
    lines = raw_text.splitlines()
    chunks = []

    current_part = "总则"
    current_chapter = ""
    current_section = ""

    article_pattern = re.compile(r"^(第[一二三四五六七八九十百千]+条)\s*(.*)")
    part_pattern = re.compile(r"^(第[一二三四五六七八九十]+编)\s*(.*)")
    chapter_pattern = re.compile(r"^(第[一二三四五六七八九十百]+章)\s*(.*)")
    section_pattern = re.compile(r"^(第[一二三四五六七八九十]+节)\s*(.*)")

    current_article_no = None
    current_article_lines = []

    def flush_article():
        nonlocal current_article_no, current_article_lines
        if current_article_no and current_article_lines:
            content = "\n".join(current_article_lines).strip()
            chunks.append({
                "law_name": law_name,
                "part": current_part,
                "chapter": current_chapter,
                "section": current_section,
                "article_no": current_article_no,
                "citation": f"《{law_name}》{current_article_no}",
                "content": content,
                "token_estimate": len(content)
            })
            current_article_no = None
            current_article_lines = []

    for line in lines:
        line_s = line.strip()
        if not line_s:
            continue

        # 匹配 编
        m_part = part_pattern.match(line_s)
        if m_part:
            flush_article()
            current_part = f"{m_part.group(1)} {m_part.group(2)}".strip()
            continue

        # 匹配 章
        m_chap = chapter_pattern.match(line_s)
        if m_chap:
            flush_article()
            current_chapter = f"{m_chap.group(1)} {m_chap.group(2)}".strip()
            continue

        # 匹配 节
        m_sec = section_pattern.match(line_s)
        if m_sec:
            flush_article()
            current_section = f"{m_sec.group(1)} {m_sec.group(2)}".strip()
            continue

        # 匹配 条
        m_art = article_pattern.match(line_s)
        if m_art:
            flush_article()
            current_article_no = m_art.group(1)
            current_article_lines.append(line_s)
        else:
            if current_article_no:
                current_article_lines.append(line_s)

    flush_article()
    return chunks


# ==============================================================================
# 2. 双库数据：公共法规走 statute_db；私有案例走 data/demo/private_cases_demo.json
# ==============================================================================
def _private_cases_corpus():
    from gateway.utils.legal_data import load_private_cases_demo
    rows = []
    for cs in load_private_cases_demo():
        item = dict(cs)
        item["is_demo"] = True
        rows.append(item)
    return rows


# ==============================================================================
# Pydantic 模型
# ==============================================================================
class ChunkLawReq(BaseModel):
    raw_law_text: str = Field(..., description="法律法规原始文本")
    law_name: str = Field(default="中华人民共和国民法典", example="中华人民共和国民法典")

class RAGSearchReq(BaseModel):
    query: str = Field(..., example="借条丢失 微信聊天记录 借贷合意")
    corpus_type: str = Field(default="all", description="检索库范围：all (双库融合) / public_statutes (公共法规库) / private_cases (律所胜诉案例库)")
    top_k: int = Field(default=3)

class RAGConsultReq(BaseModel):
    question: str = Field(..., example="当事人只有微信转账记录没有借条，对方微信答应了会还，但现在不认账，应该如何起诉，如何引用法条？")
    selected_statute_ids: Optional[List[str]] = Field(default=None)

class CreateSigningLinkReq(BaseModel):
    client_name: str = Field(..., example="张三")
    client_phone: str = Field(..., example="13800000000")
    client_email: str = Field(default="client@example.com", example="client@example.com")
    lawyer_name: str = Field(default="李四律师", example="李四律师")
    law_firm: str = Field(default="北京市京师律师事务所", example="北京市京师律师事务所")
    service_fee: float = Field(default=20000.0, example=20000.0)
    agreement_title: str = Field(default="民事委托代理协议及诉讼风险告知书", example="民事委托代理协议及诉讼风险告知书")
    case_summary: str = Field(default="代理原告张三诉北京某公司技术合同纠纷一审诉讼", example="代理原告张三诉北京某公司技术合同纠纷一审诉讼")
    matter_id: str = Field(default="", example="")


# ==============================================================================
# 3. 法律文本切片接口 (POST /api/v1/phase3/rag/chunk-law)
# ==============================================================================
@router.post("/api/v1/phase3/rag/chunk-law", summary="中国法律文本结构专用正则切片器 (编-章-节-条-款)")
async def api_chunk_law(req: ChunkLawReq):
    chunks = chinese_law_chunker(req.raw_law_text, req.law_name)
    return {
        "status": "success",
        "law_name": req.law_name,
        "total_chunks": len(chunks),
        "chunks": chunks
    }


# ==============================================================================
# 4. 双库隔离检索接口 (POST /api/v1/phase3/rag/search)
# ==============================================================================
@router.post("/api/v1/phase3/rag/search", summary="【公共法规库】与【律所私有胜诉案例库】双库隔离检索")
@router.post("/api/rag/search-precedents", include_in_schema=False)
async def api_rag_search(req: RAGSearchReq):
    """
    双库隔离特征加权匹配：
    - public_statutes: 确保精确法条引用
    - private_cases: 提取过往胜诉代理词与裁判思维
    """
    query_lower = req.query.lower()
    query_terms = [t.strip() for t in query_lower.split() if t.strip()]
    cleaned = re.sub(r"[^\w\u4e00-\u9fa5]+", " ", query_lower)
    sub_tokens = [w for w in cleaned.split() if w]
    for w in sub_tokens:
        if len(w) >= 2:
            query_terms.append(w)
            for i in range(len(w) - 1):
                query_terms.append(w[i:i+2])
                if i + 3 <= len(w):
                    query_terms.append(w[i:i+3])
    query_terms = list(set(query_terms))

    statute_results = []
    case_results = []

    # 1. 穿透本地权威法律数据库 (SQLite FTS5 + 子母法图谱三路混合检索)
    if req.corpus_type in ["all", "public_statutes"]:
        seen_citations = set()
        try:
            from gateway.utils.statute_db import search_statutes_hybrid

            # 整句检索 + 分词补召（替代原 PUBLIC_STATUTES_CORPUS 关键词表）
            probe_queries = [req.query]
            for t in query_terms:
                if len(t) >= 2 and t not in probe_queries:
                    probe_queries.append(t)
            # 常见请求权锚点：保证借贷/违约类查询仍能命中法典库
            for anchor in ("借款合同", "违约金", "借贷", "劳动合同", "经济补偿"):
                if anchor in query_lower or any(anchor in t for t in query_terms):
                    probe_queries.append(anchor)

            for pq in probe_queries:
                for art in search_statutes_hybrid(pq, limit=req.top_k * 2):
                    cite_str = f"《{art['full_name']}》{art['article_no_cn']}"
                    if cite_str in seen_citations:
                        continue
                    seen_citations.add(cite_str)
                    statute_results.append({
                        "score": 10,
                        "item": {
                            "citation": cite_str,
                            "content": art["content"],
                            "keywords": [art.get("short_name", ""), art.get("claim_basis_type", "")],
                            "source": "国家权威法典库(FTS5)",
                        },
                    })
        except Exception as e_db:
            logger.debug(f"statute_db 混合检索略过: {e_db}")

        statute_results.sort(key=lambda x: x["score"], reverse=True)

    # 2. 检索律所私有胜诉案例库
    if req.corpus_type in ["all", "private_cases"]:
        for cs in _private_cases_corpus():
            score = 0
            for kw in cs["keywords"]:
                kw_low = kw.lower()
                if kw_low in query_lower:
                    score += 6
                elif any(t in kw_low for t in query_terms if len(t) >= 2):
                    score += 3
            for t in query_terms:
                if len(t) >= 2:
                    if t in cs["title"]:
                        score += 3
                    if t in cs["win_strategy"]:
                        score += 2
            if score > 0:
                case_results.append({"score": score, "item": {**cs, "source": "律所胜诉案例库(演示)", "is_demo": True}})
        case_results.sort(key=lambda x: x["score"], reverse=True)

    final_statutes = [s["item"] for s in statute_results[:req.top_k]]
    final_cases = [c["item"] for c in case_results[:req.top_k]]
    combined_results = final_statutes + final_cases

    return {
        "status": "success",
        "query": req.query,
        "corpus_type": req.corpus_type,
        "matched_statutes_count": len(final_statutes),
        "matched_cases_count": len(final_cases),
        "statutes": final_statutes,
        "winning_cases": final_cases,
        "results": combined_results
    }


# ==============================================================================
# 5. 上下文增强法律咨询 (POST /api/v1/phase3/rag/consult)
# ==============================================================================
@router.post("/api/v1/phase3/rag/consult", summary="法条与胜诉代理词精准注入的办案问答 (杜绝法条幻觉)")
@router.post("/api/rag/qa", include_in_schema=False)
async def api_rag_consult(req: RAGConsultReq):
    # 双库检索
    search_res = await api_rag_search(RAGSearchReq(query=req.question, corpus_type="all", top_k=2))
    statutes = search_res["statutes"]
    cases = search_res["winning_cases"]

    context_str = "【必须遵循的现行法条依据（严禁捏造不存在的法条）】\n"
    for st in statutes:
        context_str += f"- {st['citation']}:\n  {st['content']}\n"

    context_str += "\n【律所历史胜诉代理词与裁判思路借鉴】\n"
    for cs in cases:
        context_str += f"- 案例: {cs['title']}\n  胜诉要点: {cs['win_strategy']}\n  代理词示范: {cs['winning_brief_quote']}\n"

    system_prompt = """你是一名中华全国律师协会顶级出庭诉讼大律师与最高法院审判研究专家。
请根据提供的【现行法条依据】与【律所胜诉代理词】，回答律师的办案策略与起诉指引。
要求：
1. 严禁出现法条幻觉，必须严格援引提供给你的法条条文；
2. 借鉴律所胜诉案件中的证明思路与代理词要点；
3. 输出包含：诉讼请求权基础明确、举证链补强指引、法庭辩论说理词示范。"""

    user_prompt = f"【律师咨询问题】\n{req.question}\n\n{context_str}\n\n请出具专业律师办案策略指导意见。"

    from gateway.utils.pii_sanitizer import build_entities_from_matter

    _rag_entities = build_entities_from_matter(getattr(req, "matter_id", "") or "")
    try:
        ans = await ollama_client.generate(
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.2,
            custom_entities=_rag_entities or None,
        )
        return {
            "status": "success",
            "question": req.question,
            "statute_references": statutes,
            "winning_case_references": cases,
            "legal_strategy": ans,
            "llm_mode": getattr(ollama_client, "last_llm_mode", "rule_fallback"),
        }
    except Exception as e:
        logger.warning(f"RAG 咨询异常，启动规则兜底: {e}")
        fallback_ans = ollama_client._generate_rule_fallback(user_prompt, system_prompt)
        return {
            "status": "success",
            "question": req.question,
            "statute_references": statutes,
            "winning_case_references": cases,
            "legal_strategy": fallback_ans
        }


# ==============================================================================
# 6. 远程委托电子签约闭环 (POST /api/v1/phase3/create-signing-link)
# ==============================================================================
# 兼容旧测试：进程内字典已废弃，持久化在 SQLite signing_envelopes
SIGNING_STORAGE: Dict[str, Dict[str, Any]] = {}


def _docuseal_base_url() -> str:
    return (os.getenv("DOCUSEAL_URL") or "").strip().rstrip("/")


def _public_base_url() -> str:
    return (os.getenv("LAWFLOW_PUBLIC_BASE_URL") or "http://127.0.0.1:5221").rstrip("/")


def _webhook_secret() -> str:
    return (os.getenv("DOCUSEAL_WEBHOOK_SECRET") or "").strip()


def _webhook_header_name() -> str:
    return (os.getenv("DOCUSEAL_WEBHOOK_HEADER") or DEFAULT_WEBHOOK_HEADER).strip() or DEFAULT_WEBHOOK_HEADER


def ensure_signing_envelopes_table() -> None:
    with connect(get_vault_db_path(), row_factory=sqlite3.Row) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS signing_envelopes (
                envelope_id TEXT PRIMARY KEY,
                matter_id TEXT,
                client_name TEXT,
                status TEXT NOT NULL,
                file_path TEXT,
                file_sha256 TEXT,
                view_token TEXT NOT NULL,
                created_at TEXT NOT NULL,
                completed_at TEXT,
                payload_json TEXT NOT NULL DEFAULT '{}'
            )
            """
        )


def get_signing_envelope(envelope_id: str) -> Optional[Dict[str, Any]]:
    """按 envelope_id 读取签约记录（含 payload 展开字段）。"""
    ensure_signing_envelopes_table()
    with connect(get_vault_db_path(), row_factory=sqlite3.Row) as conn:
        row = conn.execute(
            "SELECT * FROM signing_envelopes WHERE envelope_id = ?",
            (envelope_id,),
        ).fetchone()
    if not row:
        return None
    data = dict(row)
    try:
        payload = json.loads(data.get("payload_json") or "{}")
    except Exception:
        payload = {}
    merged = {**payload, **{k: data[k] for k in data if k != "payload_json"}}
    return merged


def _save_signing_envelope(record: Dict[str, Any]) -> None:
    ensure_signing_envelopes_table()
    core_keys = {
        "envelope_id",
        "matter_id",
        "client_name",
        "status",
        "file_path",
        "file_sha256",
        "view_token",
        "created_at",
        "completed_at",
    }
    payload = {k: v for k, v in record.items() if k not in core_keys}
    with connect(get_vault_db_path(), row_factory=sqlite3.Row) as conn:
        conn.execute(
            """
            INSERT INTO signing_envelopes (
                envelope_id, matter_id, client_name, status, file_path,
                file_sha256, view_token, created_at, completed_at, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(envelope_id) DO UPDATE SET
                matter_id = excluded.matter_id,
                client_name = excluded.client_name,
                status = excluded.status,
                file_path = excluded.file_path,
                file_sha256 = excluded.file_sha256,
                view_token = excluded.view_token,
                created_at = excluded.created_at,
                completed_at = excluded.completed_at,
                payload_json = excluded.payload_json
            """,
            (
                record["envelope_id"],
                record.get("matter_id") or "",
                record.get("client_name") or "",
                record.get("status") or "pending_signature",
                record.get("file_path"),
                record.get("file_sha256"),
                record["view_token"],
                record["created_at"],
                record.get("completed_at"),
                json.dumps(payload, ensure_ascii=False),
            ),
        )


async def _probe_docuseal_available() -> bool:
    base = _docuseal_base_url()
    if not base:
        return False
    try:
        async with httpx.AsyncClient(timeout=1.5) as client:
            resp = await client.get(f"{base}/api/health")
            return resp.status_code == 200
    except Exception:
        return False


def _demo_meta(is_demo: bool) -> Dict[str, Any]:
    if is_demo:
        return {
            "mode": "demo",
            "is_demo": True,
            "demo_notice": DEMO_SIGNING_NOTICE,
        }
    return {"mode": "docuseal", "is_demo": False}


def _finalize_signing_record(record: Dict[str, Any], is_demo: bool) -> Dict[str, Any]:
    """生成归档 PDF，计算真实 file_sha256，更新 SQLite。"""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    safe_title = re.sub(r'[\\/:*?"<>|]', "_", str(record.get("agreement_title") or "协议"))
    safe_client = re.sub(r'[\\/:*?"<>|]', "_", str(record.get("client_name") or "client"))
    archived_pdf_name = f"已签署_{safe_title}_{safe_client}_{int(time.time())}.pdf"
    archived_pdf_path = os.path.join(str(get_generated_dir()), archived_pdf_name)

    demo_banner = "【演示·非真实签署】\n\n" if is_demo else ""
    text_content = (
        f"{demo_banner}"
        f"{record.get('agreement_title', '')}\n\n"
        f"委托人（甲方）：{record.get('client_name', '')} (联系电话: {record.get('client_phone', '')})\n"
        f"受托人（乙方）：{record.get('law_firm', '')} (主办律师: {record.get('lawyer_name', '')})\n\n"
        f"一、委托事项：甲方因【{record.get('case_summary', '')}】一案，特委托乙方担任诉讼代理人。\n"
        f"二、代理费用：本案代理服务费为人民币 {float(record.get('service_fee') or 0):,.2f} 元"
        f"（{record.get('service_fee_capital', '')}）。\n"
        f"三、诉讼风险告知：甲方已知悉诉讼固有风险，并承诺据实陈述事实与提供真实证据。\n\n"
        f"【签署记录】\n"
        f"甲方签字标记：[{record.get('client_name', '')}]\n"
        f"乙方签章标记：[{record.get('law_firm', '')}]\n"
        f"签署时间：{now_str}\n"
        f"{FILE_SHA256_LABEL}：见归档后计算值\n"
    )
    if is_demo:
        text_content += f"\n{DEMO_SIGNING_NOTICE}\n"

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    rect = fitz.Rect(54, 72, 541, 780)
    page.insert_textbox(rect, text_content, fontsize=12, fontname="china-s")
    doc.save(archived_pdf_path)
    doc.close()

    with open(archived_pdf_path, "rb") as f:
        file_sha256 = hashlib.sha256(f.read()).hexdigest()

    # 将摘要写回 PDF 文本不便二次改写；摘要以字段与响应为准
    audit_logs = list(record.get("audit_logs") or [])
    audit_logs.append({
        "time": now_str,
        "action": "签署完成并归档 PDF（演示或回调）",
        "file_sha256": file_sha256,
        "signer": record.get("client_name"),
    })

    record["status"] = "completed"
    record["completed_at"] = now_str
    record["signed_at"] = now_str
    record["file_path"] = archived_pdf_path
    record["file_sha256"] = file_sha256
    record["archived_pdf_url"] = f"/api/documents/download/{archived_pdf_name}"
    record["audit_logs"] = audit_logs
    record["file_sha256_label"] = FILE_SHA256_LABEL
    _save_signing_envelope(record)

    result = {
        "status": "success",
        "envelope_id": record["envelope_id"],
        "envelope_status": "completed",
        "message": "签署已完成并归档 PDF。" + (f" {DEMO_SIGNING_NOTICE}" if is_demo else ""),
        "archived_pdf_url": record["archived_pdf_url"],
        "file_sha256": file_sha256,
        "file_sha256_label": FILE_SHA256_LABEL,
    }
    result.update(_demo_meta(is_demo))
    return result


@router.post("/api/v1/phase3/create-signing-link", summary="将委托合同与风险告知书推至 DocuSeal 发起微信端电子签署")
@router.post("/api/sign/create-envelope", include_in_schema=False)
async def create_signing_link(req: CreateSigningLinkReq):
    """
    将《民事委托代理协议》与《诉讼风险告知书》推送至本地 DocuSeal（若已配置且可用）；
    否则返回工作台内置演示签署页链接（不具法律效力）。
    """
    envelope_id = f"ds-{uuid.uuid4().hex[:12]}"
    view_token = secrets.token_urlsafe(32)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    docuseal_available = await _probe_docuseal_available()
    is_demo = not docuseal_available
    base = _public_base_url()

    if docuseal_available:
        signing_url = f"{_docuseal_base_url()}/s/{envelope_id}"
    else:
        signing_url = (
            f"{base}/api/v1/phase3/sign-view/{envelope_id}"
            f"?view_token={view_token}"
        )

    envelope_record: Dict[str, Any] = {
        "envelope_id": envelope_id,
        "matter_id": req.matter_id or "",
        "agreement_title": req.agreement_title,
        "client_name": req.client_name,
        "client_phone": req.client_phone,
        "client_email": req.client_email,
        "lawyer_name": req.lawyer_name,
        "law_firm": req.law_firm,
        "service_fee": req.service_fee,
        "service_fee_capital": rmb_to_capital(req.service_fee),
        "case_summary": req.case_summary,
        "created_at": now_str,
        "completed_at": None,
        "status": "pending_signature",
        "signing_url": signing_url,
        "view_token": view_token,
        "file_path": None,
        "file_sha256": None,
        "docuseal_integrated": docuseal_available,
        "is_demo": is_demo,
        "mode": "demo" if is_demo else "docuseal",
        "audit_logs": [
            {"time": now_str, "action": "签署任务创建", "operator": req.lawyer_name},
            {
                "time": now_str,
                "action": "生成签署链接（演示页或 DocuSeal）",
                "target": req.client_phone,
            },
        ],
    }
    _save_signing_envelope(envelope_record)

    resp = {
        "status": "success",
        "envelope_id": envelope_id,
        "signing_url": signing_url,
        "docuseal_integrated": docuseal_available,
        "envelope": envelope_record,
        **_demo_meta(is_demo),
    }
    if is_demo:
        resp["message"] = DEMO_SIGNING_NOTICE
    return resp


@router.post("/api/v1/phase3/signing-webhook", summary="DocuSeal 电子签约完成回调与文书自动归档")
async def signing_webhook(request: Request):
    """
    DocuSeal 或受控回调：校验 DOCUSEAL_WEBHOOK_SECRET 后归档 PDF，
    并以归档文件字节计算 file_sha256（不等于第三方存证）。
    """
    secret = _webhook_secret()
    if not secret:
        raise HTTPException(status_code=503, detail="webhook 未启用")

    header_name = _webhook_header_name()
    provided = request.headers.get(header_name) or request.headers.get(header_name.lower())
    provided_s = str(provided or "")
    if (
        not provided_s
        or len(provided_s) != len(secret)
        or not hmac.compare_digest(provided_s, secret)
    ):
        raise HTTPException(status_code=401, detail="webhook 鉴权失败")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="请求体不是合法 JSON")

    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="请求体不是合法 JSON")

    envelope_id = body.get("envelope_id") or body.get("id")
    if not envelope_id:
        raise HTTPException(status_code=404, detail="envelope 不存在")

    record = get_signing_envelope(str(envelope_id))
    if not record:
        raise HTTPException(status_code=404, detail="envelope 不存在")

    is_demo = not bool(record.get("docuseal_integrated"))
    return _finalize_signing_record(record, is_demo=is_demo)


@router.get("/api/v1/phase3/sign-view/{envelope_id}", summary="当事人手机端签署页（演示）")
async def sign_view_h5(envelope_id: str, view_token: Optional[str] = None):
    record = get_signing_envelope(envelope_id)
    if not record:
        return HTMLResponse("<h2>签署任务不存在或已失效</h2>", status_code=404)

    expected = str(record.get("view_token") or "")
    provided_tok = str(view_token or "")
    if (
        not provided_tok
        or not expected
        or len(provided_tok) != len(expected)
        or not hmac.compare_digest(provided_tok, expected)
    ):
        return HTMLResponse("<h2>签署任务不存在或已失效</h2>", status_code=404)

    is_demo = bool(record.get("is_demo", True)) or not bool(record.get("docuseal_integrated"))
    title = html.escape(str(record.get("agreement_title") or ""))
    client_name = html.escape(str(record.get("client_name") or ""))
    client_phone = html.escape(str(record.get("client_phone") or ""))
    law_firm = html.escape(str(record.get("law_firm") or ""))
    lawyer_name = html.escape(str(record.get("lawyer_name") or ""))
    case_summary = html.escape(str(record.get("case_summary") or ""))
    fee = float(record.get("service_fee") or 0)
    notice = html.escape(DEMO_SIGNING_NOTICE)
    eid_js = html.escape(envelope_id, quote=True)

    demo_banner = ""
    if is_demo:
        demo_banner = (
            f'<div style="background:#7f1d1d;color:#fecaca;padding:12px 16px;'
            f'border-radius:8px;margin-bottom:16px;font-size:13px;font-weight:700;">'
            f"⚠ {notice}</div>"
        )

    page = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>在线委托合同电子签署</title>
  <style>
    body {{ font-family: -apple-system, sans-serif; background: #0f172a; color: #f8fafc; padding: 20px; }}
    .card {{ background: #1e293b; padding: 20px; border-radius: 12px; max-width: 500px; margin: 0 auto; }}
    h2 {{ color: #38bdf8; margin-bottom: 12px; }}
    p {{ font-size: 14px; line-height: 1.6; color: #cbd5e1; }}
    .btn {{ background: #0284c7; color: #fff; border: none; padding: 12px 20px; border-radius: 8px; width: 100%; font-size: 16px; font-weight: bold; cursor: pointer; margin-top: 16px; }}
    .btn:hover {{ background: #0369a1; }}
    .cert-box {{ background: #090e1a; padding: 12px; border-radius: 6px; font-size: 12px; margin-top: 14px; color: #34d399; }}
  </style>
</head>
<body>
  <div class="card">
    {demo_banner}
    <h2>{title}</h2>
    <p><strong>委托人：</strong>{client_name} ({client_phone})</p>
    <p><strong>受托机构：</strong>{law_firm} ({lawyer_name})</p>
    <p><strong>委托代理事由：</strong>{case_summary}</p>
    <p><strong>约定代理费用：</strong>￥{fee:,.2f} 元</p>
    <hr style="border-color: rgba(255,255,255,0.1); margin: 16px 0;" />
    <p style="font-size: 12px; color: #94a3b8;">
      提示：本页为工作台签署预览。完成签署需由已配置 webhook 密钥的回调触发；演示环境下请由律师在工作台模拟完成。
    </p>
    <button class="btn" onclick="submitSign()">确认无误并提交签署请求</button>
    <div id="result" class="cert-box" style="display:none;"></div>
  </div>
  <script>
    async function submitSign() {{
      const box = document.getElementById('result');
      box.style.display = 'block';
      box.textContent = '演示页无法直接完成具有法律效力的签署。请返回律师工作台操作，或配置 DOCUSEAL_WEBHOOK_SECRET 后由受控回调完成。';
    }}
  </script>
</body>
</html>"""
    # eid_js 保留供后续扩展；当前演示页不调用未鉴权 webhook
    _ = eid_js

    headers = {
        "Content-Security-Policy": (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:;"
        )
    }
    return HTMLResponse(page, headers=headers)
