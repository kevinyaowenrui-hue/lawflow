# -*- coding: utf-8 -*-
"""律师默认检索不返回演示类案。打开开关后才返回，并标明不能当胜诉案例引用。"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOAN_QUERY = "借条丢失 微信聊天记录 借贷合意 职务行为"


def _search(client, **payload):
    resp = client.post("/api/v1/phase3/rag/search", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _assert_labeled_demo(case):
    assert case.get("is_demo") is True
    assert "不是本所" in (case.get("source") or "")
    assert "不能当胜诉案例引用" in (case.get("citation_notice") or "")
    title = case.get("title") or ""
    assert "本所胜诉" not in title
    assert "全额支持" not in title


def test_default_dual_search_hides_demo_and_keeps_local_statute_first(client):
    hidden = _search(client, query=LOAN_QUERY, corpus_type="all", top_k=3)
    shown = _search(
        client,
        query=LOAN_QUERY,
        corpus_type="all",
        top_k=3,
        include_demo=True,
    )

    assert hidden["include_demo"] is False
    assert hidden["winning_cases"] == []
    assert all(not item.get("is_demo") for item in hidden["results"])
    assert "【演示】" not in json.dumps(hidden, ensure_ascii=False)

    top = hidden["statutes"][0]
    assert "民法典" in top["citation"] or "民间借贷" in top["citation"]
    assert "本地法规库" in top["source"]
    assert shown["statutes"][0]["citation"] == top["citation"]
    assert shown["results"][0]["citation"] == top["citation"]
    assert shown["results"][0].get("is_demo") is not True

    assert shown["include_demo"] is True
    assert shown["winning_cases"]
    for case in shown["winning_cases"]:
        _assert_labeled_demo(case)
    blob = json.dumps(shown, ensure_ascii=False)
    assert "不能当胜诉案例引用" in blob
    assert "全额支持" not in blob
    assert "全国各高级法院" not in blob


def test_case_corpus_stays_hidden_when_switch_off(client):
    body = _search(
        client,
        query="二倍工资",
        corpus_type="private_cases",
        top_k=3,
        include_demo=False,
    )
    assert body["include_demo"] is False
    assert body["winning_cases"] == []
    assert body["results"] == []
    assert "【演示】" not in json.dumps(body, ensure_ascii=False)


def test_legacy_private_case_request_remains_labeled(client):
    """未传开关且点名演示案例库时，仍返回已标明的演示项，供既有验收使用。"""
    body = _search(client, query="二倍工资", corpus_type="private_cases", top_k=3)
    assert body["include_demo"] is True
    assert body["winning_cases"]
    for case in body["winning_cases"]:
        _assert_labeled_demo(case)
    blob = json.dumps(body, ensure_ascii=False)
    assert "全额支持" not in blob
    assert "全国各高级法院" not in blob


def test_blank_search_does_not_fill_sample_statutes(client):
    body = _search(
        client,
        query="   ",
        corpus_type="public_statutes",
        top_k=3,
        include_demo=True,
    )
    assert body["matched_statutes_count"] == 0
    assert body["statutes"] == []
    assert body["winning_cases"] == []


def test_consult_uses_the_same_demo_switch(client, monkeypatch):
    prompts = []

    async def fake_generate(**kwargs):
        prompts.append(kwargs.get("prompt") or "")
        return "只依据给出的法条整理请求权基础。"

    monkeypatch.setattr(
        "gateway.routers.phase3_rag_sign.ollama_client.generate",
        fake_generate,
    )

    omitted = client.post(
        "/api/v1/phase3/rag/consult",
        json={"question": "未签合同 二倍工资 仲裁时效"},
    )
    assert omitted.status_code == 200, omitted.text
    omitted_body = omitted.json()
    assert omitted_body["include_demo"] is False
    assert omitted_body["winning_case_references"] == []
    assert "【演示】" not in prompts[-1]

    hidden = client.post(
        "/api/v1/phase3/rag/consult",
        json={"question": "未签合同 二倍工资 仲裁时效", "include_demo": False},
    )
    assert hidden.status_code == 200, hidden.text
    assert hidden.json()["winning_case_references"] == []
    assert "【演示】" not in prompts[-1]

    shown = client.post(
        "/api/v1/phase3/rag/consult",
        json={"question": "未签合同 二倍工资 仲裁时效", "include_demo": True},
    )
    assert shown.status_code == 200, shown.text
    shown_body = shown.json()
    assert shown_body["include_demo"] is True
    assert shown_body["winning_case_references"]
    for case in shown_body["winning_case_references"]:
        _assert_labeled_demo(case)
    assert "不能当胜诉案例引用" in prompts[-1]
    assert "【演示】" in prompts[-1]


def test_search_toggle_defaults_off_in_the_search_form():
    js = (ROOT / "frontend" / "js" / "modules" / "04_appeal_signing.js").read_text(encoding="utf-8")
    assert "显示演示材料" in js
    tag = js.split('id="rag-show-demo"', 1)[1].split(">", 1)[0]
    assert "checked" not in tag
    assert "include_demo: showDemo" in js
    assert "不能当胜诉案例引用" in js
