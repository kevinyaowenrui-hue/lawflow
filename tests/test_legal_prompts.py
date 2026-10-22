# -*- coding: utf-8 -*-
"""批次10 I-15：提示词不得诱导强制引用、编造案例、一律否认证据。"""
from __future__ import annotations

import gateway.utils.legal_prompts as lp


BANNED_PHRASES = (
    "必须引用",
    "最高人民法院同类指导性案例",
    "无法达到其证明目的",
)


def test_prompt_constants_no_inducement():
    for name in dir(lp):
        if name.startswith("_"):
            continue
        val = getattr(lp, name)
        if not isinstance(val, str):
            continue
        for bad in BANNED_PHRASES:
            assert bad not in val, f"{name} 含禁用诱导语「{bad}」"


def test_every_system_prompt_has_anti_fabrication():
    attrs = [
        n
        for n in dir(lp)
        if n.endswith("_SYSTEM_PROMPT") and isinstance(getattr(lp, n), str)
    ]
    # 亦覆盖具名系统提示常量（非 SYSTEM_PROMPT 后缀但实际作 system prompt）
    for extra in (
        "TRIAL_OUTLINE_FIVE_MODULES_PROMPT",
        "CONTRACT_REVIEW_PERSPECTIVE_PROMPT",
        "CONTRACT_REVIEW_ENGLISH_PROMPT",
        "EVIDENCE_STRUCTURING_PROMPT",
    ):
        if extra not in attrs and hasattr(lp, extra):
            attrs.append(extra)
    assert attrs
    for name in attrs:
        text = getattr(lp, name)
        assert "不得编造" in text or "Do not fabricate" in text, f"{name} 缺少防编造约束"


def test_trial_outline_injects_wu_when_no_verified_cases(client, monkeypatch):
    """无已核验判例时，发给 Ollama 的 system prompt 类案块为「无」。"""
    from gateway.core import ollama_client as oc_mod

    captured = {}

    async def fake_generate(prompt, system_prompt="", temperature=0.3, **kwargs):
        captured["system_prompt"] = system_prompt
        captured["prompt"] = prompt
        return "### 一、案件核心概览\n测试提纲"

    monkeypatch.setattr(oc_mod.ollama_client, "generate", fake_generate)

    resp = client.post(
        "/api/v1/phase2/trial-outline",
        json={
            "case_title": "测试案",
            "cause_of_action": "民间借贷纠纷",
            "plaintiff_claims_and_facts": "原告主张借款未还。",
            "defendant_defense": "被告否认借款关系。",
        },
    )
    assert resp.status_code == 200, resp.text
    sp = captured.get("system_prompt") or ""
    assert "【已核验类案】" in sp
    # 类案块为「无」
    assert "【已核验类案】\n无" in sp or "【已核验类案】\r\n无" in sp
    assert "不得编造" in sp


def test_role_is_writing_assistant():
    assert "辅助执业律师起草文书的写作助手" in lp.FACTS_POLISH_SYSTEM_PROMPT
    assert "最高人民法院优秀法官" not in lp.FACTS_POLISH_SYSTEM_PROMPT
