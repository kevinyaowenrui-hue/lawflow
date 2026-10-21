# -*- coding: utf-8 -*-
"""
批次 5 / I-32：计算接口输入校验（不得静默回退）。
"""
from __future__ import annotations

from gateway.utils.cn_legal_calc import calculate_lpr_interest


def test_term_1y_lowercase_same_as_1Y():
    a = calculate_lpr_interest(100000, "2023-01-01", "2023-12-31", term="1y")
    b = calculate_lpr_interest(100000, "2023-01-01", "2023-12-31", term="1Y")
    assert round(a["total_interest"], 2) == 3550.68
    assert round(b["total_interest"], 2) == 3550.68
    assert round(a["total_interest"], 2) == round(b["total_interest"], 2)


def test_term_invalid_raises():
    import pytest

    with pytest.raises(ValueError, match="1Y|5Y"):
        calculate_lpr_interest(100000, "2023-01-01", "2023-12-31", term="2Y")


def test_api_fixed_annual_rate_decimal_422(client):
    resp = client.post(
        "/api/v1/phase1/calc/lpr-interest",
        json={
            "principal": 100000,
            "start_date": "2023-01-01",
            "end_date": "2024-01-01",
            "fixed_annual_rate": 0.24,
        },
    )
    assert resp.status_code == 422
    assert "百分数" in str(resp.json()) or "0.24" in str(resp.json())


def test_api_date_inverted_422(client):
    resp = client.post(
        "/api/v1/phase1/calc/lpr-interest",
        json={
            "principal": 100000,
            "start_date": "2024-01-01",
            "end_date": "2023-01-01",
            "term": "1Y",
        },
    )
    assert resp.status_code == 422


def test_api_claim_amount_negative_422(client):
    resp = client.post(
        "/api/v1/phase1/calc/court-fees",
        json={"claim_amount": -100, "case_type": "property"},
    )
    assert resp.status_code == 422


def test_api_claim_amount_zero_property_422(client):
    resp = client.post(
        "/api/v1/phase1/calc/court-fees",
        json={"claim_amount": 0, "case_type": "property"},
    )
    assert resp.status_code == 422
    assert "大于 0" in str(resp.json()) or "须大于" in str(resp.json())


def test_api_settlement_negative_claim_422(client):
    resp = client.post(
        "/api/v1/phase1/calc/settlement-simulation",
        json={"total_claim_nominal": -5, "plan_type": "hybrid"},
    )
    assert resp.status_code == 422


def test_api_settlement_bad_plan_type_422(client):
    resp = client.post(
        "/api/v1/phase1/calc/settlement-simulation",
        json={"total_claim_nominal": 100000, "plan_type": "xxx"},
    )
    assert resp.status_code == 422


def test_api_preservation_real_estate_422(client):
    resp = client.post(
        "/api/v1/phase1/calc/preservation-renewal",
        json={"preservation_type": "real_estate", "start_date": "2026-01-01"},
    )
    assert resp.status_code == 422
