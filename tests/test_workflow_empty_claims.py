# -*- coding: utf-8 -*-
"""诉请或抗辩抽空时，不得回填另一起借款案的金额和微信情节。"""
from __future__ import annotations

import json

import pytest

FORBIDDEN = ("3,500,000", "3500000", "14.5%", "共同创业", "EMS催告")


def _assert_no_foreign_case(blob: str) -> None:
    for marker in FORBIDDEN:
        assert marker not in blob, marker


def test_format_workflow_keeps_empty_claims_and_defenses():
    from gateway.routers.matter_vault import format_workflow_response

    res = format_workflow_response({
        "workflow_id": "WF-EMPTY",
        "matter_id": "M-EMPTY",
        "current_step": 2,
        "step_status": "WAITING_HUMAN_CONFIRMATION",
        "step_data": {
            "step1": {
                "candidate_claims": ["  ", {"text": ""}],
                "candidate_legal_basis": [],
            },
            "step2": {},
            "step3": {"defense_predictions": []},
            "step4": {},
            "step5": {},
        },
    })
    workflow = res["workflow"]
    assert workflow["step2_claims"]["candidate_claims"] == []
    assert workflow["step2_claims"]["applicable_statutes"] == []
    assert workflow["step3_statutes"]["opponent_defense_predictions"] == []
    _assert_no_foreign_case(json.dumps(res, ensure_ascii=False))


@pytest.fixture
def offline_model(monkeypatch):
    async def _generate(prompt="", **kwargs):
        text = prompt or ""
        if "defense_predictions" in text:
            return '{"defense_predictions": []}'
        return '{"candidate_claims": [], "candidate_legal_basis": []}'

    monkeypatch.setattr("gateway.utils.workflow_engine.ollama_client.generate", _generate)


def _start(client, facts: str, cause: str):
    matter = client.post("/api/v1/vault/matters", json={
        "title": "空诉请测试案",
        "cause_of_action": cause,
        "court_name": "某区人民法院",
        "plaintiff_name": "测试原告",
        "defendant_name": "测试被告",
        "summary": facts,
    })
    assert matter.status_code == 200, matter.text
    matter_id = matter.json()["matter"]["matter_id"]
    started = client.post("/api/v1/vault/workflows/start", json={
        "matter_id": matter_id,
        "initial_facts": facts,
        "cause_of_action": cause,
    })
    assert started.status_code == 200, started.text
    return started.json()["workflow"]


def test_vague_facts_stay_empty_when_model_returns_no_claims(client, offline_model):
    wf = _start(client, "双方发生争议，具体请求还没有写。", "民事纠纷")
    claims = wf["step2_claims"]["candidate_claims"]
    assert claims == []
    _assert_no_foreign_case(json.dumps(wf, ensure_ascii=False))


def test_empty_claim_list_still_completes_from_loan_words_without_fake_amounts(client, offline_model):
    wf = _start(client, "原告出借了一笔钱，被告未还。金额还没核对。", "民间借贷纠纷")
    claims = wf["step2_claims"]["candidate_claims"]
    assert claims
    assert any("借款" in text for text in claims)
    blob = json.dumps(wf, ensure_ascii=False)
    _assert_no_foreign_case(blob)
    assert "3,500,000.00" not in blob


def test_empty_defense_list_is_completed_without_wechat_story(client, offline_model):
    wf = _start(client, "原告出借了一笔钱，被告未还。金额还没核对。", "民间借贷纠纷")
    advanced = client.post(
        f"/api/v1/vault/workflows/{wf['workflow_id']}/advance",
        json={
            "human_decisions": {
                "confirmed_claims": ["请求返还录入文字中的借款。"],
                "confirmed_statutes": [],
                "cause_of_action": "民间借贷纠纷",
            }
        },
    )
    assert advanced.status_code == 200, advanced.text
    done = advanced.json()["workflow"]
    predictions = done["step3_statutes"]["opponent_defense_predictions"]
    assert predictions
    blob = json.dumps(predictions, ensure_ascii=False)
    _assert_no_foreign_case(blob)
    assert "微信" not in blob
