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

from gateway.core.ollama_client import ollama_client, read_secrets
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
    law_name: str = Field(default="中华人民共和国民法典", examples=["中华人民共和国民法典"])

class RAGSearchReq(BaseModel):
    query: str = Field(..., examples=["借条丢失 微信聊天记录 借贷合意"])
    corpus_type: str = Field(default="all", description="检索库范围：all (双库融合) / public_statutes (公共法规库) / private_cases (演示案例库)")
    top_k: int = Field(default=3)
    include_demo: Optional[bool] = Field(
        default=None,
        description="是否返回演示材料。律师界面默认传 false。true 才返回，并标明不是本所案件、不能当胜诉案例引用。",
    )

class RAGConsultReq(BaseModel):
    question: str = Field(..., examples=["当事人只有微信转账记录没有借条，对方微信答应了会还，但现在不认账，应该如何起诉，如何引用法条？"])
    selected_statute_ids: Optional[List[str]] = Field(default=None)
    include_demo: Optional[bool] = Field(
        default=None,
        description="是否把演示材料放进咨询上下文。默认不放。",
    )

class CreateSigningLinkReq(BaseModel):
    client_name: str = Field(..., examples=["张三"])
    client_phone: str = Field(default="", examples=["13800000000"])
    client_email: str = Field(default="")
    lawyer_name: str = Field(default="")
    law_firm: str = Field(default="", description="律师事务所名称。不预填示例律所。")
    service_fee: Optional[float] = Field(default=None, description="未填写时签字页写【待填写】，不写成 0 元已约定")
    agreement_title: str = Field(default="民事委托代理协议及诉讼风险告知书")
    case_summary: str = Field(default="")
    matter_id: str = Field(default="")


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


DEMO_CASE_SOURCE = "演示材料，不是本所已核验案件"
DEMO_CASE_NOTICE = "不是本所案件，不能当胜诉案例引用"


def _demo_cases_allowed(req: RAGSearchReq) -> bool:
    """律师默认检索不返回 is_demo。

    include_demo 为 true 才返回演示项。
    未传该字段时：双库融合与咨询不返回；仅 corpus_type=private_cases 仍返回已标明的演示项，
    以保持既有「仅演示案例库」验收。律师界面总会传 true 或 false。
    """
    if req.include_demo is True:
        return True
    if req.include_demo is False:
        return False
    return req.corpus_type == "private_cases"


# ==============================================================================
# 4. 双库隔离检索接口 (POST /api/v1/phase3/rag/search)
# ==============================================================================
@router.post("/api/v1/phase3/rag/search", summary="【公共法规库】与【演示案例】双库隔离检索")
@router.post("/api/rag/search-precedents", include_in_schema=False)
async def api_rag_search(req: RAGSearchReq):
    """
    双库隔离特征加权匹配：
    - public_statutes: 本地法规库法条，引用前核对效力
    - private_cases: 演示材料。默认不返回；打开开关后才返回，并标明不能当胜诉案例引用
    """
    query_lower = (req.query or "").lower()
    user_terms: List[str] = []
    for raw in re.sub(r"[^\w\u4e00-\u9fa5]+", " ", query_lower).split():
        term = raw.strip()
        if len(term) >= 2 and term not in user_terms:
            user_terms.append(term)

    # 只在整句和词都没命中时，才用字窗补召。字窗不能跟词、锚点抢前三名。
    windows: List[str] = []
    for word in user_terms:
        if len(word) < 4:
            continue
        for i in range(len(word) - 1):
            pair = word[i:i + 2]
            if pair not in user_terms and pair not in windows:
                windows.append(pair)
            if i + 3 <= len(word):
                tri = word[i:i + 3]
                if tri not in user_terms and tri not in windows:
                    windows.append(tri)

    anchors: List[str] = []
    for anchor in ("借款合同", "违约金", "借贷", "劳动合同", "经济补偿"):
        if anchor in user_terms:
            continue
        if anchor in query_lower or any(anchor in term for term in user_terms):
            anchors.append(anchor)

    statute_results = []
    case_results = []

    # 1. 穿透本地权威法律数据库 (SQLite FTS5 + 子母法图谱三路混合检索)
    if req.corpus_type in ["all", "public_statutes"]:
        try:
            from gateway.utils.statute_db import search_statutes_hybrid

            probes: List[tuple] = []
            seen_probes = set()

            def add_probe(text: str, weight: int) -> None:
                text = (text or "").strip()
                if len(text) < 2 or text in seen_probes:
                    return
                seen_probes.add(text)
                probes.append((text, weight))

            add_probe(req.query, 300)
            for term in user_terms:
                add_probe(term, 120 + min(len(term), 40))
            for anchor in anchors:
                add_probe(anchor, 220)

            best: Dict[str, Dict[str, Any]] = {}

            def absorb(probe: str, weight: int) -> None:
                for art in search_statutes_hybrid(probe, limit=max(req.top_k * 2, 4)):
                    cite_str = f"《{art['full_name']}》{art['article_no_cn']}"
                    score = weight + float(art.get("rank_score") or 0)
                    prev = best.get(cite_str)
                    if prev is not None and prev["score"] >= score:
                        continue
                    item = {
                        "citation": cite_str,
                        "content": art["content"],
                        "keywords": [art.get("short_name", ""), art.get("claim_basis_type", "")],
                        "source": "本地法规库。引用前核对效力",
                    }
                    notice = (art.get("cpl_citation_display_note") or "").strip()
                    if notice:
                        item["citation_notice"] = notice
                        item["copyable_as_current_authority"] = False
                    best[cite_str] = {
                        "score": score,
                        "item": item,
                    }

            for probe, weight in probes:
                absorb(probe, weight)
            # 空查询不加示例法条。词和锚点都不够时，才用字窗补足。
            if req.query.strip() and len(best) < req.top_k:
                for probe in windows:
                    absorb(probe, 8 + min(len(probe), 6))
                    if len(best) >= req.top_k:
                        break
            statute_results = sorted(best.values(), key=lambda row: row["score"], reverse=True)
        except Exception as e_db:
            logger.debug(f"statute_db 混合检索略过: {e_db}")

    # 2. 检索演示案例。默认不进入律师结果；打开开关后才附上，并标明不能当胜诉案例引用。
    if req.corpus_type in ["all", "private_cases"]:
        for cs in _private_cases_corpus():
            score = 0
            for kw in cs["keywords"]:
                kw_low = kw.lower()
                if kw_low in query_lower:
                    score += 6
                elif any(t in kw_low for t in user_terms):
                    score += 3
            for t in user_terms:
                if len(t) >= 2:
                    if t in cs["title"]:
                        score += 3
                    if t in cs["win_strategy"]:
                        score += 2
            if score > 0:
                case_results.append({
                    "score": score,
                    "item": {
                        **cs,
                        "source": DEMO_CASE_SOURCE,
                        "is_demo": True,
                        "citation_notice": DEMO_CASE_NOTICE,
                    },
                })
        case_results.sort(key=lambda x: x["score"], reverse=True)

    demo_allowed = _demo_cases_allowed(req)
    if not demo_allowed:
        case_results = [row for row in case_results if not row["item"].get("is_demo")]

    final_statutes = [s["item"] for s in statute_results[:req.top_k]]
    final_cases = [c["item"] for c in case_results[:req.top_k]]
    combined_results = final_statutes + final_cases

    return {
        "status": "success",
        "query": req.query,
        "corpus_type": req.corpus_type,
        "include_demo": demo_allowed,
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
    # 咨询与双列检索共用同一开关：默认不把演示材料放进上下文
    search_res = await api_rag_search(RAGSearchReq(
        query=req.question,
        corpus_type="all",
        top_k=2,
        include_demo=req.include_demo,
    ))
    statutes = search_res["statutes"]
    cases = search_res["winning_cases"]

    context_str = "【必须遵循的现行法条依据（严禁捏造不存在的法条）】\n"
    for st in statutes:
        context_str += f"- {st['citation']}:\n  {st['content']}\n"
        if st.get("citation_notice"):
            context_str += (
                f"  条号对照：{st['citation_notice']}\n"
                "  对不上的《民事诉讼法》条号不能写入代理词作为现行依据。\n"
            )

    if cases:
        context_str += "\n【演示材料，不是裁判要旨，也不是本所胜诉案件。不能当胜诉案例引用】\n"
        for cs in cases:
            notice = cs.get("citation_notice") or DEMO_CASE_NOTICE
            context_str += (
                f"- 演示: {cs['title']}\n"
                f"  标明: {notice}\n"
                f"  仅供对照的写法: {cs['win_strategy']}\n"
                f"  不能当代理词引用: {cs['winning_brief_quote']}\n"
            )

    system_prompt = """你是办案辅助。只能依据下面给出的法条原文。
演示材料不是裁判文书，不能写成本所胜诉案件，也不能把演示里的结论说成法院已经支持。
要求：
1. 只援引提供的法条，不要编造条号；
2. 演示材料如果和法条不一致，以法条为准，并说明演示不能当依据；
3. 分开写请求权基础、还缺什么证据、可以怎么说理。不要写胜诉把握。"""

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
            "include_demo": bool(search_res.get("include_demo")),
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
            "include_demo": bool(search_res.get("include_demo")),
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


def _docuseal_http_client(**kwargs):
    return httpx.AsyncClient(**kwargs)


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


def _docuseal_api_token() -> str:
    """环境变量优先，否则读用户目录 secrets.json，不把令牌写入仓库。"""
    for key in ("DOCUSEAL_API_TOKEN", "DOCUSEAL_API_KEY"):
        value = (os.getenv(key) or "").strip()
        if value:
            return value
    try:
        data = read_secrets()
    except Exception as exc:
        logger.warning("读取 DocuSeal API 令牌失败: %s", exc)
        return ""
    if not isinstance(data, dict):
        return ""
    return str(data.get("docuseal_api_token") or data.get("DOCUSEAL_API_TOKEN") or "").strip()


def _stringify_id(value: Any) -> str:
    if value is None or isinstance(value, bool):
        return ""
    if isinstance(value, float):
        if not value.is_integer():
            return ""
        return str(int(value))
    if isinstance(value, int):
        return str(value)
    return str(value).strip()


def _push_id(keys: List[str], value: Any) -> None:
    text = _stringify_id(value)
    if text and text not in keys:
        keys.append(text)


_COMPLETION_WEBHOOK_EVENTS = frozenset({
    "form.completed",
    "submission.completed",
    "envelope.completed",
})
_STORED_DOCUSEAL_ID_FIELDS = (
    "docuseal_submission_id",
    "docuseal_submitter_id",
    "external_id",
    "docuseal_slug",
)


def _webhook_candidate_ids(body: Dict[str, Any]) -> List[str]:
    """兼容本系统 envelope_id，以及 DocuSeal form/submission 回调里的真实编号。"""
    keys: List[str] = []
    _push_id(keys, body.get("envelope_id"))
    data = body.get("data") if isinstance(body.get("data"), dict) else {}
    _push_id(keys, data.get("external_id"))
    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    _push_id(keys, metadata.get("envelope_id"))
    submission = data.get("submission") if isinstance(data.get("submission"), dict) else {}
    _push_id(keys, submission.get("external_id"))
    submission_meta = submission.get("metadata") if isinstance(submission.get("metadata"), dict) else {}
    _push_id(keys, submission_meta.get("envelope_id"))
    for item in data.get("submitters") or []:
        if not isinstance(item, dict):
            continue
        _push_id(keys, item.get("external_id"))
        item_meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        _push_id(keys, item_meta.get("envelope_id"))
    _push_id(keys, data.get("submission_id"))
    _push_id(keys, submission.get("id"))
    _push_id(keys, data.get("id"))
    for item in data.get("submitters") or []:
        if not isinstance(item, dict):
            continue
        _push_id(keys, item.get("submission_id"))
        _push_id(keys, item.get("id"))
    _push_id(keys, body.get("submission_id"))
    _push_id(keys, body.get("id"))
    return keys


def find_signing_envelope_for_webhook(body: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    candidates = _webhook_candidate_ids(body)
    for key in candidates:
        record = get_signing_envelope(key)
        if record:
            return record
    if not candidates:
        return None
    wanted = set(candidates)
    ensure_signing_envelopes_table()
    with connect(get_vault_db_path(), row_factory=sqlite3.Row) as conn:
        rows = conn.execute(
            "SELECT envelope_id, payload_json FROM signing_envelopes"
        ).fetchall()
    for row in rows:
        try:
            payload = json.loads(row["payload_json"] or "{}")
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        stored = {_stringify_id(payload.get(field)) for field in _STORED_DOCUSEAL_ID_FIELDS}
        stored.discard("")
        if stored & wanted:
            return get_signing_envelope(row["envelope_id"])
    return None


def _retainer_html(req: CreateSigningLinkReq) -> str:
    phone = html.escape((req.client_phone or "").strip() or "【待填写】")
    email = (req.client_email or "").strip()
    email_html = f"<p>电子邮箱：{html.escape(email)}</p>" if email else ""
    return (
        "<!DOCTYPE html><html><body>"
        f"<h1>{html.escape(req.agreement_title)}</h1>"
        f"<p>委托人（甲方）：{html.escape((req.client_name or '').strip())}</p>"
        f"<p>联系电话：{phone}</p>"
        f"{email_html}"
        f"<p>承办律师：{html.escape((req.lawyer_name or '').strip())}</p>"
        f"<p>律师事务所：{html.escape((req.law_firm or '').strip())}</p>"
        f"<p>委托事由：{html.escape((req.case_summary or '').strip())}</p>"
        f"<p>代理费：{html.escape(_fee_line(req.service_fee))}</p>"
        "<p>委托人已知悉诉讼固有风险。委托事项、代理权限和代理费以本页记载为准。"
        "未填写的项目，签署前应当补全。</p>"
        "<p>委托人签字："
        '<signature-field name="委托人签字" role="委托人" required="true" '
        'style="width: 180px; height: 48px; display: inline-block;"></signature-field>'
        "</p></body></html>"
    )


def _submitter_payload(req: CreateSigningLinkReq, envelope_id: str) -> Dict[str, Any]:
    submitter: Dict[str, Any] = {
        "name": req.client_name.strip(),
        "role": "委托人",
        "send_email": False,
        "external_id": envelope_id,
        "metadata": {"envelope_id": envelope_id},
    }
    email = (req.client_email or "").strip()
    if email:
        submitter["email"] = email
    phone = (req.client_phone or "").strip()
    if phone.startswith("+"):
        submitter["phone"] = phone
    return submitter


def _iter_submitters(payload: Any) -> tuple:
    if isinstance(payload, list):
        submitters = [item for item in payload if isinstance(item, dict)]
        submission_id = ""
        for item in submitters:
            submission_id = _stringify_id(item.get("submission_id"))
            if submission_id:
                break
        return submitters, submission_id
    if not isinstance(payload, dict):
        return [], ""
    submission_id = _stringify_id(payload.get("submission_id") or payload.get("id"))
    raw = payload.get("submitters")
    if isinstance(raw, list):
        submitters = [item for item in raw if isinstance(item, dict)]
        for item in submitters:
            nested = _stringify_id(item.get("submission_id"))
            if nested:
                submission_id = nested
                break
        return submitters, submission_id
    if payload.get("embed_src") or payload.get("slug"):
        return [payload], submission_id
    return [], submission_id


def _official_signing_url(base: str, submitter: Dict[str, Any]) -> str:
    embed = str(submitter.get("embed_src") or "").strip()
    slug = str(submitter.get("slug") or "").strip()
    if embed.startswith("http://") or embed.startswith("https://"):
        return embed
    if embed.startswith("/") and not embed.startswith("//"):
        return f"{base}{embed}"
    token = slug
    if not token and embed and "://" not in embed and "/" not in embed and " " not in embed:
        token = embed
    if not token:
        return ""
    return f"{base}/s/{token}"


def _signing_link_from_submission(base: str, payload: Any, envelope_id: str) -> Dict[str, str]:
    submitters, submission_id = _iter_submitters(payload)
    chosen = None
    for item in submitters:
        if str(item.get("role") or "") == "委托人" and _official_signing_url(base, item):
            chosen = item
            break
    if chosen is None:
        for item in submitters:
            if _official_signing_url(base, item):
                chosen = item
                break
    if chosen is None:
        return {}
    signing_url = _official_signing_url(base, chosen)
    if not signing_url:
        return {}
    if envelope_id and signing_url.rstrip("/").endswith("/s/" + envelope_id):
        return {}
    sub_id = _stringify_id(chosen.get("submission_id")) or submission_id
    if sub_id == envelope_id:
        sub_id = ""
    return {
        "signing_url": signing_url,
        "docuseal_submission_id": sub_id,
        "docuseal_submitter_id": _stringify_id(chosen.get("id")),
        "docuseal_slug": str(chosen.get("slug") or "").strip(),
    }


def _docuseal_error_hint(resp: httpx.Response) -> str:
    try:
        data = resp.json()
    except Exception:
        return ""
    if not isinstance(data, dict):
        return ""
    for key in ("error", "message", "detail"):
        value = data.get(key)
        if not isinstance(value, str):
            continue
        text = " ".join(value.split())
        lowered = text.lower()
        if (
            not text
            or "<" in text
            or "traceback" in lowered
            or "x-auth-token" in lowered
            or len(text) > 160
        ):
            continue
        return text
    return ""


def _raise_docuseal_create_error(resp: httpx.Response) -> None:
    if resp.status_code in (401, 403):
        detail = (
            "DocuSeal 拒绝了 API 令牌。请核对 DOCUSEAL_API_TOKEN，"
            "或用户目录 secrets.json 里的 docuseal_api_token。本次没有发起签署。"
        )
    elif resp.status_code == 404:
        detail = (
            "DocuSeal 没有从委托合同创建提交的接口（HTTP 404）。"
            "请确认 DOCUSEAL_URL 指向的服务支持 POST /api/submissions/html。"
            "本次没有发起签署。"
        )
    else:
        detail = f"DocuSeal 创建签署提交失败（HTTP {resp.status_code}）。本次没有发起签署。"
        hint = _docuseal_error_hint(resp)
        if hint:
            detail = f"{detail} {hint}"
    raise HTTPException(status_code=502, detail=detail)


async def _request_docuseal_submission(
    req: CreateSigningLinkReq,
    envelope_id: str,
    token: str,
) -> Dict[str, str]:
    base = _docuseal_base_url()
    url = f"{base}/api/submissions/html"
    body = {
        "name": req.agreement_title,
        "send_email": False,
        "documents": [
            {
                "name": req.agreement_title or "委托合同",
                "html": _retainer_html(req),
                "size": "A4",
            }
        ],
        "submitters": [_submitter_payload(req, envelope_id)],
    }
    try:
        async with _docuseal_http_client(timeout=20.0) as client:
            resp = await client.post(
                url,
                headers={"X-Auth-Token": token, "Accept": "application/json"},
                json=body,
            )
    except httpx.RequestError as exc:
        logger.warning("DocuSeal 创建提交连接失败: %s", exc.__class__.__name__)
        raise HTTPException(
            status_code=503,
            detail="DocuSeal 服务不可达，创建签署提交时连不上，请检查 DOCUSEAL_URL。本次没有发起签署。",
        )
    if resp.status_code >= 400:
        logger.warning("DocuSeal 创建提交被拒绝 status=%s", resp.status_code)
        _raise_docuseal_create_error(resp)
    try:
        payload = resp.json()
    except Exception:
        raise HTTPException(
            status_code=502,
            detail="DocuSeal 创建签署提交失败：返回的不是合法 JSON。本次没有发起签署。",
        )
    link = _signing_link_from_submission(base, payload, envelope_id)
    if not link.get("signing_url"):
        raise HTTPException(
            status_code=502,
            detail=(
                "DocuSeal 创建提交已返回，但响应里没有签署链接"
                "（需要 submitters 里的 embed_src 或 slug）。本次没有发起签署。"
            ),
        )
    logger.info(
        "DocuSeal 签署提交已创建 submission_id=%s",
        link.get("docuseal_submission_id") or "",
    )
    return link


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


OFFLINE_SIGN_NOTICE = "未配置电子签，请线下签字"


def _signing_identity_error(req: CreateSigningLinkReq) -> Optional[str]:
    missing = []
    if not (req.client_name or "").strip():
        missing.append("委托人")
    if not (req.lawyer_name or "").strip():
        missing.append("承办律师")
    if not (req.law_firm or "").strip():
        missing.append("律师事务所")
    if not (req.case_summary or "").strip():
        missing.append("委托事由")
    if not missing:
        return None
    return "请填写" + "、".join(missing) + "。缺这些内容时不生成签字页，避免空白页看起来像已经签好的委托。"


def _fee_line(amount: Optional[float]) -> str:
    if amount is None or amount <= 0:
        return "【待填写】"
    return f"人民币 {float(amount):,.2f} 元（{rmb_to_capital(float(amount))}）"


@router.get("/api/v1/phase3/signing-mode", summary="电子签是否已配置")
async def signing_mode():
    url_ok = bool(_docuseal_base_url())
    secret_ok = bool(_webhook_secret())
    token_ok = bool(_docuseal_api_token())
    if url_ok and secret_ok and token_ok:
        return {
            "status": "success",
            "electronic_signing": True,
            "notice": "已配置电子签。未完成签署前，仍可下载委托签字页线下签字。",
        }
    if url_ok and secret_ok and not token_ok:
        return {
            "status": "success",
            "electronic_signing": True,
            "notice": (
                "DocuSeal 地址和回调密钥已填写，还缺 API 令牌。"
                "请配置 DOCUSEAL_API_TOKEN，或在用户目录 secrets.json 写入 docuseal_api_token。"
                "没有令牌时不能发起电子签署。"
            ),
        }
    return {
        "status": "success",
        "electronic_signing": False,
        "notice": OFFLINE_SIGN_NOTICE,
    }


@router.post("/api/v1/phase3/offline-signature-page", summary="生成线下委托签字页")
async def offline_signature_page(req: CreateSigningLinkReq):
    """没有 DocuSeal 时给律师一份可打印的签字页，不伪造签署链接。"""
    identity_error = _signing_identity_error(req)
    if identity_error:
        raise HTTPException(status_code=422, detail=identity_error)
    if req.service_fee is not None and req.service_fee < 0:
        raise HTTPException(status_code=422, detail="代理费不能为负数。")

    now_str = datetime.now().strftime("%Y年%m月%d日")
    safe_client = re.sub(r'[\\/:*?"<>|\s]+', "_", req.client_name.strip())[:40] or "委托人"
    filename = f"委托签字页_{safe_client}_{int(time.time())}.pdf"
    path = os.path.join(str(get_generated_dir()), filename)
    phone = (req.client_phone or "").strip() or "【待填写】"
    email = (req.client_email or "").strip()
    email_line = f"电子邮箱：{email}\n" if email else ""
    text = (
        "委托签字页\n\n"
        f"{OFFLINE_SIGN_NOTICE}\n"
        "本页只供当面或邮寄签字，不是电子签署，也不是法院立案回执。\n\n"
        f"文件名称：{req.agreement_title}\n"
        f"委托人：{req.client_name.strip()}\n"
        f"联系电话：{phone}\n"
        f"{email_line}"
        f"承办律师：{req.lawyer_name.strip()}\n"
        f"律师事务所：{req.law_firm.strip()}\n"
        f"委托事由：{req.case_summary.strip()}\n"
        f"代理费：{_fee_line(req.service_fee)}\n\n"
        "委托人确认：委托事项、代理权限和代理费以双方另行签署的委托合同为准。"
        "本页未填写的项目，签字前应当手写补全。\n\n"
        "委托人签字：____________________    日期：__________\n\n"
        "承办律师签字：____________________    日期：__________\n\n"
        f"打印日期：{now_str}\n"
    )
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_textbox(fitz.Rect(54, 64, 541, 780), text, fontsize=12, fontname="china-s")
    doc.save(path)
    doc.close()
    return {
        "status": "success",
        "mode": "offline",
        "electronic_signing": False,
        "notice": OFFLINE_SIGN_NOTICE,
        "signing_url": None,
        "filename": filename,
        "download_url": f"/api/documents/download/{filename}",
    }


def _require_docuseal_config() -> None:
    if not _docuseal_base_url() or not _webhook_secret():
        raise HTTPException(
            status_code=503,
            detail="未配置 DOCUSEAL_URL 与 DOCUSEAL_WEBHOOK_SECRET，无法发起正式电子签署",
        )


@router.post("/api/v1/phase3/create-signing-link", summary="将委托合同与风险告知书推至 DocuSeal 发起电子签署")
@router.post("/api/sign/create-envelope", include_in_schema=False)
async def create_signing_link(req: CreateSigningLinkReq):
    """把委托合同提交到 DocuSeal。健康检查通过还不够，签署链接必须来自创建提交的响应。"""
    _require_docuseal_config()
    identity_error = _signing_identity_error(req)
    if identity_error:
        raise HTTPException(status_code=422, detail=identity_error)
    token = _docuseal_api_token()
    if not token:
        raise HTTPException(
            status_code=503,
            detail=(
                "未配置 DocuSeal API 令牌。请设置环境变量 DOCUSEAL_API_TOKEN，"
                "或在用户目录 secrets.json 写入 docuseal_api_token。"
                "没有令牌就不能在 DocuSeal 创建签署提交，本次没有发起签署。"
            ),
        )
    if not await _probe_docuseal_available():
        raise HTTPException(
            status_code=503,
            detail="DocuSeal 服务不可达，请检查 DOCUSEAL_URL。本次没有发起签署。",
        )

    envelope_id = f"ds-{uuid.uuid4().hex[:12]}"
    view_token = secrets.token_urlsafe(32)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    link = await _request_docuseal_submission(req, envelope_id, token)
    signing_url = link["signing_url"]

    envelope_record: Dict[str, Any] = {
        "envelope_id": envelope_id,
        "matter_id": req.matter_id or "",
        "agreement_title": req.agreement_title,
        "client_name": req.client_name,
        "client_phone": req.client_phone,
        "client_email": req.client_email,
        "lawyer_name": req.lawyer_name,
        "law_firm": req.law_firm,
        "service_fee": float(req.service_fee or 0),
        "service_fee_capital": rmb_to_capital(float(req.service_fee or 0)),
        "case_summary": req.case_summary,
        "created_at": now_str,
        "completed_at": None,
        "status": "pending_signature",
        "signing_url": signing_url,
        "view_token": view_token,
        "file_path": None,
        "file_sha256": None,
        "docuseal_integrated": True,
        "docuseal_submission_id": link.get("docuseal_submission_id") or "",
        "docuseal_submitter_id": link.get("docuseal_submitter_id") or "",
        "docuseal_slug": link.get("docuseal_slug") or "",
        "external_id": envelope_id,
        "is_demo": False,
        "mode": "docuseal",
        "audit_logs": [
            {"time": now_str, "action": "签署任务创建", "operator": req.lawyer_name},
            {
                "time": now_str,
                "action": "已把委托合同提交到 DocuSeal",
                "target": req.client_phone,
            },
        ],
    }
    _save_signing_envelope(envelope_record)

    return {
        "status": "success",
        "envelope_id": envelope_id,
        "signing_url": signing_url,
        "docuseal_integrated": True,
        "docuseal_submission_id": link.get("docuseal_submission_id") or "",
        "envelope": envelope_record,
        **_demo_meta(False),
    }


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

    event_type = str(body.get("event_type") or "").strip()
    if event_type and event_type not in _COMPLETION_WEBHOOK_EVENTS:
        return {
            "status": "ignored",
            "event_type": event_type,
            "message": "已收到 DocuSeal 回调。这不是签署完成，未归档。",
        }

    record = find_signing_envelope_for_webhook(body)
    if not record:
        raise HTTPException(status_code=404, detail="envelope 不存在")

    if not bool(record.get("docuseal_integrated")) or bool(record.get("is_demo")):
        raise HTTPException(
            status_code=400,
            detail="该签署任务不是正式 DocuSeal 任务，已停用演示签署完成路径",
        )
    return _finalize_signing_record(record, is_demo=False)


@router.get("/api/v1/phase3/sign-view/{envelope_id}", summary="本地演示签署页已停用")
async def sign_view_h5(envelope_id: str, view_token: Optional[str] = None):
    """历史演示签署页已停用；正式签署请使用 DocuSeal 返回的 signing_url。"""
    _ = envelope_id, view_token
    return HTMLResponse(
        "<h2>本地演示签署页已停用</h2>"
        "<p>请配置 DocuSeal 后从工作台重新发起正式电子签署。</p>",
        status_code=410,
    )
