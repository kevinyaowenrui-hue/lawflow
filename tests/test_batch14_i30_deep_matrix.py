# -*- coding: utf-8 -*-
"""批次14 I-30：自定义案情推演案由识别、标的额、第三人栏。"""
from __future__ import annotations


SALES_FACTS = "原告向被告供应货物，被告以质量问题为由拒付货款 30 万元"
PLACEHOLDER_THIRD = "以案情实际涉及为准"


def test_sales_case_auto_cause_and_amount(client):
    resp = client.post(
        "/api/v1/deep-matrix/analyze-custom",
        json={"custom_raw_text": SALES_FACTS},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data.get("status") == "success"
    assert data["cause_of_action"] == "买卖合同纠纷"
    assert data["claim_amount"] == 300000
    assert PLACEHOLDER_THIRD not in str(data)
    third = (data.get("parties") or {}).get("third_party")
    assert third in (None, "", "无") or "third_party" not in (data.get("parties") or {})


def test_explicit_cause_of_action_overrides_keywords(client):
    resp = client.post(
        "/api/v1/deep-matrix/analyze-custom",
        json={
            "custom_raw_text": SALES_FACTS,
            "cause_of_action": "民间借贷纠纷",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["cause_of_action"] == "民间借贷纠纷"
    assert data.get("status") == "success"


def test_ambiguous_facts_need_input(client):
    resp = client.post(
        "/api/v1/deep-matrix/analyze-custom",
        json={"custom_raw_text": "双方因某事发生争议，请求法院依法处理。"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data.get("status") == "NEED_INPUT"
    assert isinstance(data.get("candidates"), list) and len(data["candidates"]) >= 1
    assert "请选择案由" in (data.get("message") or data.get("hint") or "")
    assert data.get("cause_of_action") != "民间借贷纠纷" or data.get("status") == "NEED_INPUT"
