# -*- coding: utf-8 -*-
"""告知文案、外发留存和风险代理禁令。"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

ADULT_ID = "110101199003072375"
MINOR_ID = "110101201003072375"
ROOT = Path(__file__).resolve().parents[1]


def _base_matter(**extra):
    payload = {
        "title": "风险代理校验案",
        "cause_of_action": "买卖合同纠纷",
        "plaintiff_name": "校验委托人甲",
        "defendant_name": "校验对方乙",
        "client_role": "原告",
        "is_same_matter": "否",
        "principal_amount": 100000,
    }
    payload.update(extra)
    return payload


def test_frontend_copy_matches_real_flow():
    settings = (ROOT / "frontend/js/modules/settings.js").read_text(encoding="utf-8")
    modals = (ROOT / "frontend/js/modules/modals.js").read_text(encoding="utf-8")
    citation = "《律师法》（2017年修正文本）第三十九条；全国律协《律师执业行为规范》利益冲突条款（项次待核对）"
    subtitle = modals.split('id="modal-conflict-check"', 1)[1].split("modal-subtitle\">", 1)[1].split("<", 1)[0]
    assert subtitle == citation
    assert "第四十二条" not in subtitle
    assert "2026" not in subtitle
    assert "第50/51" not in modals
    assert "第50条" not in modals
    assert "第51条" not in modals
    assert 'conflict-registry-count-badge">4' not in modals
    assert "new-matter-risk-ratio" in modals
    assert "勾选「已说明」不能代替书面风险代理合同。" in modals
    assert "案情文本将在脱敏后发送" not in settings
    assert "诉讼归档留底有效" not in settings
    assert "防伪效力" not in settings
    assert "案情、证据摘录、代理意见会发给所填服务商" in settings
    assert "身份证号、手机号、银行卡号等号码也会发送" in settings
    assert "/yuandian/check" in settings
    assert "open.chineselaw.com" in settings
    assert "certificate_no" in settings
    assert "certNo && cert.is_cleared" in settings


def test_withhold_keeps_unidentified_text_and_drops_known_sensitive_segments():
    from gateway.utils.pii_sanitizer import withhold_network_sensitive

    text = (
        f"原告身份证{ADULT_ID}。"
        "这个孩子今年很小，但合同仍有效。"
        "出生日期：1990年3月7日。"
        "原告现年36周岁。"
        f"未成年人身份证{MINOR_ID}。"
        "出生日期：2015年1月1日。"
        "原告现年17周岁。"
        "出院小结：患者右腿骨折内固定。"
    )
    cleaned, report = withhold_network_sensitive(text)
    assert ADULT_ID in cleaned
    assert "这个孩子今年很小" in cleaned
    assert "1990年3月7日" in cleaned
    assert "36周岁" in cleaned
    assert MINOR_ID not in cleaned
    assert "2015年1月1日" not in cleaned
    assert "17周岁" not in cleaned
    assert "出院小结" not in cleaned
    assert "骨折内固定" not in cleaned
    assert report["minor_withheld"] is True
    assert report["medical_withheld"] is True
    assert report["blocked_unidentified"] is False
    assert "没有拦截" in report["note"]
    assert "已经拦住" not in cleaned


def test_id_card_minor_detection_does_not_guess_invalid_dates():
    from gateway.utils.pii_sanitizer import id_card_is_minor

    assert id_card_is_minor(ADULT_ID) is False
    assert id_card_is_minor(MINOR_ID) is True
    assert id_card_is_minor("110101199013402375") is None


def test_cloud_shield_off_sends_adult_id_but_not_minor_or_medical(monkeypatch, tmp_path):
    captured = []

    class FakeResp:
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"content": "已收到"}}]}

        @property
        def text(self):
            return "{}"

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, json=None, headers=None):
            captured.append(json or {})
            return FakeResp()

        async def get(self, *args, **kwargs):
            raise RuntimeError("不应探测")

    monkeypatch.setattr("httpx.AsyncClient", FakeAsyncClient)
    monkeypatch.setenv("LAWFLOW_SETTINGS_FILE", str(tmp_path / "llm.json"))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    from gateway.core.ollama_client import UniversalLLMClient

    client = UniversalLLMClient()
    client.settings.update({
        "provider": "cloud",
        "cloud_consent": True,
        "api_key": "sk-test-disclosure",
        "base_url": "https://api.example.test/v1",
        "model": "demo-model",
        "pii_shield_enabled": False,
    })
    prompt = (
        f"原告身份证{ADULT_ID}。"
        f"未成年人身份证{MINOR_ID}。"
        "出院小结：患者右腿骨折内固定。"
        "这个孩子今年很小。"
    )
    out = asyncio.run(client.generate(prompt=prompt))
    assert out == "已收到"
    assert captured
    outbound = json.dumps(captured[0], ensure_ascii=False)
    assert ADULT_ID in outbound
    assert MINOR_ID not in outbound
    assert "骨折内固定" not in outbound
    assert "这个孩子今年很小" in outbound


def test_loopback_ollama_does_not_pretend_to_block_medical(monkeypatch, tmp_path):
    captured = []

    class FakeResp:
        status_code = 200

        def json(self):
            return {"response": "本地回执"}

        @property
        def text(self):
            return "{}"

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, json=None, headers=None):
            captured.append(json or {})
            return FakeResp()

    monkeypatch.setattr("httpx.AsyncClient", FakeAsyncClient)
    monkeypatch.setenv("LAWFLOW_SETTINGS_FILE", str(tmp_path / "llm.json"))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    from gateway.core.ollama_client import UniversalLLMClient

    client = UniversalLLMClient()
    client.settings.update({
        "provider": "ollama",
        "cloud_consent": False,
        "api_key": "",
        "pii_shield_enabled": False,
        "ollama_base_url": "http://127.0.0.1:11434",
    })
    client._ollama_available = True
    client._last_ollama_probe = 1e18
    client._active_ollama_url = "http://127.0.0.1:11434"
    asyncio.run(client.generate(prompt="出院小结：患者右腿骨折内固定。"))
    body = json.dumps(captured[0], ensure_ascii=False)
    assert "骨折内固定" in body


def test_yuandian_check_text_drops_identified_segments_and_keeps_citation(monkeypatch):
    from gateway.utils.yuandian import YuandianClient, YuandianError

    calls = []

    def fake_call(server, tool, arguments=None):
        calls.append((server, tool, arguments))
        return {"ok": True}

    client = YuandianClient()
    monkeypatch.setattr(client, "call_tool", fake_call)
    result = client.check_text(
        "根据《民法典》第五百八十五条。"
        f"原告身份证{ADULT_ID}。"
        f"未成年人身份证{MINOR_ID}。"
        "出院小结：患者右腿骨折内固定。"
    )
    assert result == {"ok": True}
    assert calls[0][0] == "hallucination"
    sent = calls[0][2]["text"]
    assert "第五百八十五条" in sent
    assert ADULT_ID in sent
    assert MINOR_ID not in sent
    assert "骨折内固定" not in sent
    assert "脱敏" not in json.dumps(calls, ensure_ascii=False)

    with pytest.raises(YuandianError, match="没有剩余核对文本"):
        client.check_text("出院小结：患者右腿骨折内固定。")
    assert len(calls) == 1
