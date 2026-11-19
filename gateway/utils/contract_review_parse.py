# -*- coding: utf-8 -*-
"""把合同审查模型输出收成条款列表。收不回来就保持未审查，不编造条款。"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

MODEL_REVIEW_UNUSABLE = "模型未给出可用的条款审查，请再试一次"
RULE_REVIEW_SUMMARY = (
    "未审查：当前处于规则模式（未连接大模型），系统未对该合同进行审查，未输出审查结论。"
    "买卖合同审查须连接大语言模型。"
)

_CLAUSE_LIST_KEYS = (
    "clause_reviews",
    "clauses",
    "reviews",
    "risk_clauses",
    "clauseReviews",
    "items",
    "条款审查",
    "审查条款",
    "风险条款",
)
_NEST_KEYS = ("review", "data", "result", "output")
_FIELD_MAP = {
    "clause_title": "clause_title",
    "title": "clause_title",
    "条款名称": "clause_title",
    "条款标题": "clause_title",
    "original_clause": "original_clause",
    "original": "original_clause",
    "原文": "original_clause",
    "原条款": "original_clause",
    "合同原文": "original_clause",
    "suggested_clause": "suggested_clause",
    "suggestion": "suggested_clause",
    "建议条款": "suggested_clause",
    "修订建议": "suggested_clause",
    "修改建议": "suggested_clause",
    "risk_analysis": "risk_analysis",
    "risk": "risk_analysis",
    "风险分析": "risk_analysis",
    "风险": "risk_analysis",
    "negotiation_tip": "negotiation_tip",
    "谈判建议": "negotiation_tip",
    "谈判话术": "negotiation_tip",
    "playbook_deviation": "playbook_deviation",
    "偏离度": "playbook_deviation",
    "matched_playbook_rule": "matched_playbook_rule",
    "命中红线": "matched_playbook_rule",
    "deviation_reason": "deviation_reason",
    "偏离原因": "deviation_reason",
}
_USEFUL = ("original_clause", "suggested_clause", "clause_title", "risk_analysis")
_UNCAPTURED = re.compile(
    r'"(?:original_clause|suggested_clause|原文|建议条款|原条款)"\s*:\s*"(?:[^"\\]|\\.){4,}"'
)


def _repair(text: str) -> str:
    cleaned = text.replace("\ufeff", "")
    cleaned = cleaned.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)
    return cleaned


def _loads_one(blob: str) -> Any:
    for candidate in (blob, _repair(blob)):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
        for opener, closer in (("{", "}"), ("[", "]")):
            start = candidate.find(opener)
            end = candidate.rfind(closer)
            if start == -1 or end <= start:
                continue
            sliced = candidate[start:end + 1]
            for piece in (sliced, _repair(sliced)):
                try:
                    return json.loads(piece)
                except json.JSONDecodeError:
                    continue
    return None


def _candidate_texts(raw: str) -> List[str]:
    text = (raw or "").strip()
    if not text:
        return []
    found: List[str] = [text]
    outside = re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.IGNORECASE).strip()
    if outside and outside != text:
        found.append(outside)
    if not outside:
        found.extend(
            piece.strip()
            for piece in re.findall(r"<think>([\s\S]*?)</think>", text, flags=re.IGNORECASE)
            if piece and piece.strip()
        )
    found.extend(
        piece.strip()
        for piece in re.findall(r"```(?:json)?\s*([\s\S]*?)```", text, flags=re.IGNORECASE)
        if piece and piece.strip()
    )
    return found


def _parse_any(raw: str) -> Any:
    for text in _candidate_texts(raw):
        loaded = _loads_one(text)
        if loaded is not None:
            return loaded
        if isinstance(loaded, (dict, list)):
            return loaded
    return None


def _as_score(value: Any) -> Optional[float]:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        stripped = value.strip().rstrip("分")
        try:
            return float(stripped)
        except ValueError:
            return None
    return None


def _normalize_clause(item: Any) -> Optional[Dict[str, str]]:
    if not isinstance(item, dict):
        return None
    out: Dict[str, str] = {}
    for key, value in item.items():
        mapped = _FIELD_MAP.get(str(key).strip())
        if not mapped or value is None:
            continue
        text = str(value).strip()
        if text:
            out[mapped] = text
    if not any(out.get(name) for name in _USEFUL):
        return None
    return out


def _dig_clause_list(obj: Any, depth: int = 0) -> Optional[List[Any]]:
    if depth > 4:
        return None
    if isinstance(obj, list):
        return obj
    if not isinstance(obj, dict):
        return None
    if obj.get("error") == "Failed to parse structured JSON from model response" and not any(
        key in obj for key in _CLAUSE_LIST_KEYS
    ):
        return None
    for key in _CLAUSE_LIST_KEYS:
        if key not in obj:
            continue
        value = obj.get(key)
        if isinstance(value, str):
            inner = _loads_one(value)
            if isinstance(inner, list):
                return inner
        if isinstance(value, list):
            return value
    for key in _NEST_KEYS:
        if key in obj:
            found = _dig_clause_list(obj.get(key), depth + 1)
            if found is not None:
                return found
    return None


def _summary_source(obj: Any) -> Dict[str, Any]:
    if isinstance(obj, dict) and not (
        obj.get("error") == "Failed to parse structured JSON from model response" and "clause_reviews" not in obj
    ):
        return obj
    return {}


def coerce_contract_review(raw_text: str) -> Dict[str, Any]:
    """解析模型正文。条款必须来自正文，解析失败时 clauses 为空。"""
    parsed = _parse_any(raw_text or "")
    valid_json = isinstance(parsed, (dict, list))
    source = _summary_source(parsed)
    raw_list = _dig_clause_list(parsed) if valid_json else None
    clauses: List[Dict[str, str]] = []
    if raw_list:
        for item in raw_list:
            normalized = _normalize_clause(item)
            if normalized:
                clauses.append(normalized)
    score = _as_score(source.get("playbook_compliance_score"))
    summary = str(source.get("review_summary") or "").strip()
    risk = str(source.get("overall_risk_level") or "").strip()
    review = {
        "overall_risk_level": risk or "未标明",
        "review_summary": summary or "已整理模型返回的条款意见，请律师逐条核对。",
        "playbook_compliance_score": score,
        "clause_reviews": clauses,
    }
    return {
        "valid_json": valid_json,
        "clauses": clauses,
        "review": review,
    }


def review_needs_retry(raw_text: str, coerced: Dict[str, Any]) -> bool:
    """第一次不是合法 JSON，或正文里有条款却没解析出来时，才重试一次。"""
    if coerced.get("clauses"):
        return False
    if not coerced.get("valid_json"):
        return True
    return bool(_UNCAPTURED.search(raw_text or ""))
