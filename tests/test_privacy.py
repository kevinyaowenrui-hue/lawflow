# -*- coding: utf-8 -*-
"""I-23 数据出网脱敏、cloud_consent、health llm_mode、入库脱敏。"""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("LAWFLOW_API_TOKEN", "test-token")
AUTH = {"X-LawFlow-Token": os.environ["LAWFLOW_API_TOKEN"]}


@pytest.fixture
def privacy_env(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    settings_file = tmp_path / "llm_settings.json"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("LAWFLOW_SETTINGS_FILE", str(settings_file))
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("LAWFLOW_ALLOW_REMOTE_OLLAMA", "1")

    import gateway.core.ollama_client as oc
    import gateway.routers.settings_router as sr
    import gateway.routers.phase1_litigation as p1
    import gateway.main as main_mod

    prev = {
        "oc": oc.ollama_client,
        "sr": sr.ollama_client,
        "p1": getattr(p1, "ollama_client", None),
        "main": main_mod.ollama_client,
    }

    client = oc.UniversalLLMClient()
    client.settings.update({
        "provider": "cloud",
        "cloud_consent": True,
        "api_key": "sk-test-privacy-key-abcdef",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "pii_shield_enabled": True,
        "ollama_base_url": "http://127.0.0.1:11434",
        "ollama_model": "gemma4:12b",
    })
    # 禁止真实探测拖死用例
    client._ollama_available = False
    client._last_ollama_probe = 1e18
    oc.ollama_client = client
    sr.ollama_client = client
    p1.ollama_client = client
    main_mod.ollama_client = client

    yield {"client": client, "home": home, "settings_file": settings_file, "oc": oc}

    oc.ollama_client = prev["oc"]
    sr.ollama_client = prev["sr"]
    if prev["p1"] is not None:
        p1.ollama_client = prev["p1"]
    main_mod.ollama_client = prev["main"]


@pytest.fixture
def app_client(privacy_env):
    from gateway.main import app

    with TestClient(app, headers=AUTH) as c:
        yield c, privacy_env


def _party_payload():
    return {
        "cause_of_action": "民间借贷纠纷",
        "court_name": "北京市朝阳区人民法院",
        "claim_amount": 100000.0,
        "raw_case_notes": "测试原告甲向被告出借款项，住所在北京市朝阳区测试路1号。",
        "claims": ["判令被告偿还借款本金"],
        "plaintiff": {
            "name": "测试原告甲",
            "address": "北京市朝阳区测试路1号",
            "id_card_or_uscc": "110101199003072375",
            "phone": "13800138000",
            "party_type": "natural",
            "gender": "男",
            "birth": "1990年3月7日",
        },
        "defendant": {
            "name": "测试被告乙",
            "address": "北京市海淀区示例街2号",
            "id_card_or_uscc": "110101199001011234",
            "phone": "13900139000",
            "party_type": "natural",
            "gender": "女",
            "birth": "1990年1月1日",
        },
    }


def test_a_cloud_outbound_masked_and_unmasked_in_response(privacy_env, monkeypatch):
    """外发不含当事人姓名与住所，占位符在返回结果中已还原。"""
    import asyncio

    client = privacy_env["client"]
    captured = []

    class FakeResp:
        status_code = 200

        def json(self):
            body = captured[-1]
            user_content = body["messages"][-1]["content"]
            return {
                "choices": [{
                    "message": {
                        "content": f"已审阅：{user_content}"
                    }
                }]
            }

        @property
        def text(self):
            return "{}"

    class FakeAsyncClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None):
            captured.append(json or {})
            return FakeResp()

        async def get(self, *a, **k):
            raise RuntimeError("unexpected get")

    monkeypatch.setattr("httpx.AsyncClient", FakeAsyncClient)

    from gateway.utils.pii_sanitizer import build_entities_from_parties

    parties = [
        {"name": "测试原告甲", "address": "北京市朝阳区测试路1号", "party_type": "natural"},
        {"name": "测试被告乙", "address": "北京市海淀区示例街2号", "party_type": "natural"},
    ]
    entities = build_entities_from_parties(parties)
    prompt = "当事人测试原告甲住所北京市朝阳区测试路1号，请润色事实与理由。"
    out = asyncio.run(client.generate(prompt=prompt, custom_entities=entities))

    assert captured, "应发起云端请求"
    outbound = json.dumps(captured[0], ensure_ascii=False)
    assert "测试原告甲" not in outbound
    assert "测试路1号" not in outbound
    assert "[" in outbound and "]" in outbound  # 占位符
    assert "测试原告甲" in out
    assert "测试路1号" in out


def test_b_remote_ollama_forced_mask(privacy_env, monkeypatch):
    """远程 Ollama 请求体同样脱敏。"""
    import asyncio

    client = privacy_env["client"]
    client.settings["provider"] = "ollama"
    client.settings["cloud_consent"] = False
    client.settings["pii_shield_enabled"] = False  # 关闭盾牌仍强制
    client.settings["ollama_base_url"] = "http://10.0.0.5:11434"
    client._active_ollama_url = "http://10.0.0.5:11434"
    client._ollama_available = True
    client._last_ollama_probe = 1e18

    captured = []

    class FakeResp:
        status_code = 200

        def json(self):
            return {"response": captured[-1].get("prompt", "")}

        @property
        def text(self):
            return "{}"

    class FakeAsyncClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None):
            captured.append(json or {})
            return FakeResp()

        async def get(self, *a, **k):
            m = MagicMock()
            m.status_code = 200
            m.json = lambda: {"models": [{"name": "gemma4:12b"}]}
            return m

    monkeypatch.setattr("httpx.AsyncClient", FakeAsyncClient)

    from gateway.utils.pii_sanitizer import build_entities_from_parties

    entities = build_entities_from_parties([
        {"name": "测试原告甲", "address": "北京市朝阳区测试路1号"},
    ])
    asyncio.run(
        client.generate(
            prompt="测试原告甲住北京市朝阳区测试路1号",
            custom_entities=entities,
        )
    )
    assert captured
    body = json.dumps(captured[0], ensure_ascii=False)
    assert "测试原告甲" not in body
    assert "测试路1号" not in body


def test_c_auto_no_consent_skips_cloud(app_client, monkeypatch):
    """provider=auto、有 Key、cloud_consent=False → 不发起云端请求。"""
    http, env = app_client
    client = env["client"]
    client.settings["provider"] = "auto"
    client.settings["api_key"] = "sk-present-but-no-consent"
    client.settings["cloud_consent"] = False
    client.settings["ollama_base_url"] = "http://127.0.0.1:11434"
    client._ollama_available = False
    client._last_ollama_probe = 1e18

    cloud_posts = []

    class FakeAsyncClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None):
            cloud_posts.append(str(url))
            raise AssertionError(f"不应发起云端请求: {url}")

        async def get(self, url, *a, **k):
            # ollama probe fail
            raise ConnectionError("offline")

    monkeypatch.setattr("httpx.AsyncClient", FakeAsyncClient)

    resp = http.post("/api/v1/phase1/generate-litigation-package", json=_party_payload())
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data.get("llm_mode") in ("ollama", "rule_fallback")
    assert not any("deepseek" in u or "chat/completions" in u for u in cloud_posts)


def test_d_health_rule_fallback(app_client, monkeypatch):
    """无模型时 GET /health → model_ready is False 且 llm_mode == rule_fallback。"""
    http, env = app_client
    client = env["client"]
    client.settings["provider"] = "ollama"
    client.settings["api_key"] = ""
    client.settings["cloud_consent"] = False
    client._ollama_available = False
    client._last_ollama_probe = 1e18

    class FakeAsyncClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **k):
            raise ConnectionError("no model")

        async def post(self, *a, **k):
            raise ConnectionError("no model")

    monkeypatch.setattr("httpx.AsyncClient", FakeAsyncClient)

    resp = http.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("llm_mode") == "rule_fallback"
    assert body.get("model_ready") is False


def test_e_upload_redacts_id_and_bank(app_client):
    """上传含身份证与银行卡的 txt → 案件库文字不含明文，redacted_count ≥ 2。"""
    http, env = app_client

    # 创建案件
    create = http.post(
        "/api/v1/vault/matters",
        json={
            "title": "隐私入库测试案",
            "cause_of_action": "民间借贷纠纷",
            "plaintiff_name": "甲",
            "defendant_name": "乙",
        },
    )
    assert create.status_code == 200, create.text
    matter_id = create.json()["matter"]["matter_id"]

    id_no = "110101199003072340"
    # 可通过银行卡前缀规则的测试号（无需 Luhn；若实现 Luhn 请换有效号）
    card_no = "6222020200112233445"
    content = f"当事人身份证 {id_no}，银行卡 {card_no}。"
    files = {"file": ("pii_sample.txt", io.BytesIO(content.encode("utf-8")), "text/plain")}
    data = {"doc_type": "evidence", "redact_on_ingest": "true"}

    up = http.post(
        f"/api/v1/vault/matters/{matter_id}/upload-document",
        files=files,
        data=data,
    )
    assert up.status_code == 200, up.text
    body = up.json()
    assert body.get("redacted_count", 0) >= 2

    stored = body.get("document", {}).get("text_content") or body.get("document", {}).get("content_text") or ""
    assert id_no not in stored
    assert card_no not in stored

    # 再读案件库文档清单核对
    docs = http.get(f"/api/v1/vault/matters/{matter_id}/documents")
    assert docs.status_code == 200
    texts = " ".join(
        (d.get("text_content") or d.get("content_text") or "")
        for d in docs.json().get("documents", [])
    )
    assert id_no not in texts
    assert card_no not in texts


def test_build_entities_from_parties_types():
    from gateway.utils.pii_sanitizer import build_entities_from_parties, pii_sanitizer

    ents = build_entities_from_parties([
        {
            "name": "张三",
            "address": "北京市朝阳区测试路1号",
            "legal_rep": "李四",
            "agent": "王五",
            "party_type": "natural",
        },
        {"name": "某某科技有限公司", "party_type": "legal"},
    ])
    values = {e["value"] for e in ents}
    assert "张三" in values
    assert "北京市朝阳区测试路1号" in values
    assert "李四" in values
    assert "王五" in values
    assert "某某科技有限公司" in values

    masked, mapping, _ = pii_sanitizer.mask(
        "原告张三住北京市朝阳区测试路1号",
        custom_entities=ents,
    )
    assert "张三" not in masked
    assert "测试路1号" not in masked
    assert mapping
