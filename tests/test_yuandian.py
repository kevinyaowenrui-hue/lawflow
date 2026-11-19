# -*- coding: utf-8 -*-
"""元典客户端：密钥不回传，检索结果能从元典返回里抽出条文。"""
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from gateway.utils.yuandian import YuandianClient, to_items


def test_to_items_reads_article_list():
    payload = {
        "results": {
            "law_article_list": [
                {
                    "regulation_name": "中华人民共和国民法典",
                    "article_number": "第五百八十五条",
                    "content": "当事人可以约定一方违约时应当根据违约情况向对方支付一定数额的违约金。",
                    "article_id": "a1",
                }
            ]
        }
    }
    items = to_items(payload, limit=5)
    assert items[0]["title"] == "中华人民共和国民法典"
    assert items[0]["article"] == "第五百八十五条"
    assert "违约金" in items[0]["snippet"]


def test_save_key_is_masked_and_keeps_llm_secret(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("LAWFLOW_DOTENV_FILE", str(tmp_path / ".env"))
    monkeypatch.delenv("YUANDIAN_API_KEY", raising=False)
    from gateway.core.ollama_client import read_secrets, write_secrets

    write_secrets({"api_key": "sk-llm-should-stay"})
    client = YuandianClient()
    secret = "sk_unit_test_key_12345678"
    status = client.save_api_key(secret)
    dumped = json.dumps(status, ensure_ascii=False)
    assert secret not in dumped
    assert status["configured"] is True
    assert "****" in status["key_masked"] or "*" in status["key_masked"]
    stored = read_secrets()
    assert stored["api_key"] == "sk-llm-should-stay"
    assert stored["yuandian_api_key"] == secret
    assert secret in (tmp_path / ".env").read_text(encoding="utf-8")


def test_search_endpoint_uses_named_tool(monkeypatch):
    monkeypatch.setenv("YUANDIAN_API_KEY", "sk_present_for_route")
    calls = []

    def fake_call(server, tool, arguments=None):
        calls.append((server, tool, arguments))
        return {
            "results": {
                "law_article_list": [
                    {"regulation_name": "证券法", "article_number": "第一条", "content": "为了规范证券发行和交易行为。"}
                ]
            }
        }

    monkeypatch.setattr("gateway.routers.yuandian_router.yuandian.call_tool", fake_call)
    from gateway.main import app

    client = TestClient(app, headers={"X-LawFlow-Token": "test-token"})
    resp = client.post("/api/v1/yuandian/search", json={"kind": "law", "query": "证券发行", "limit": 3})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["items"][0]["title"] == "证券法"
    assert calls[0][0] == "law"
    assert calls[0][1] == "yuandian_semantic_search_legal_articles"
    assert "sk_present_for_route" not in resp.text
