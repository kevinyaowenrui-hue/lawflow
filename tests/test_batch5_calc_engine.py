# -*- coding: utf-8 -*-
"""
批次 5：计算引擎口径修正与输入校验相关用例。
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from docx import Document
from fastapi.testclient import TestClient

from gateway.utils.cn_legal_calc import (
    calculate_lpr_interest,
    calculate_preservation_renewal,
    calculate_settlement_npv_and_recovery,
    calculate_statute_of_limitations,
)
from gateway.utils.legal_data import clear_legal_data_cache, load_lpr_history_meta

ROOT = Path(__file__).resolve().parents[1]
AUTH = {"X-LawFlow-Token": "test-token"}


# ---------------------------------------------------------------------------
# S-15 LPR 表
# ---------------------------------------------------------------------------

def test_s15_no_fictional_2026_01_20_in_gateway_or_data():
    hits = []
    for base in (ROOT / "gateway", ROOT / "data"):
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() in {".pyc", ".db", ".png", ".jpg", ".docx", ".pdf"}:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if "2026-01-20" in text:
                hits.append(str(path.relative_to(ROOT)))
    assert hits == [], f"仍含虚构 LPR 日期 2026-01-20: {hits}"


def test_s15_lpr_stale_warning_when_today_far_past_data_as_of():
    clear_legal_data_cache()
    res = calculate_lpr_interest(
        100000, "2026-01-01", "2026-10-21", term="1Y", today_date="2026-12-15"
    )
    assert any("LPR 数据可能已过期" in w for w in res.get("warnings", []))


def test_s15_lpr_end_after_data_as_of_warning():
    clear_legal_data_cache()
    meta = load_lpr_history_meta()
    res = calculate_lpr_interest(
        100000, "2026-10-01", "2026-11-30", term="1Y", today_date="2026-10-21"
    )
    assert any("计息止日超出 LPR 数据截止日" in w for w in res.get("warnings", []))
    assert meta["data_as_of"] == "2026-10-20"


def test_s15_r3_regression_full_year():
    res = calculate_lpr_interest(100000, "2025-01-01", "2026-01-01", term="1Y")
    assert round(res["total_interest"], 2) == 3038.08


# ---------------------------------------------------------------------------
# S-16 民间借贷上限
# ---------------------------------------------------------------------------

def test_s16_pre_2020_contract_requires_filing_date():
    with pytest.raises(ValueError, match="filing_date"):
        calculate_lpr_interest(
            100000,
            "2019-12-01",
            "2021-12-01",
            fixed_annual_rate=20,
            rule_mode="private_lending_cap",
            contract_date="2019-12-01",
        )


def test_s16_post_2020_contract_cap_138_percent():
    """合同成立于 2020-08-20 后：上限=成立时一年期 LPR×4。"""
    res = calculate_lpr_interest(
        100000,
        "2024-01-01",
        "2025-01-01",
        fixed_annual_rate=24,
        rule_mode="private_lending_cap",
        contract_date="2023-12-01",
    )
    assert round(res["total_interest"], 2) == 13837.81
    post_segs = [s for s in res["segments"] if s.get("statutory_cap_rate") == 13.8]
    assert post_segs
    assert post_segs[0].get("cap_basis") == "合同成立时LPR×4"


def test_s16_api_missing_filing_date_returns_422(client):
    resp = client.post(
        "/api/v1/phase1/calc/lpr-interest",
        json={
            "principal": 100000,
            "start_date": "2019-12-01",
            "end_date": "2021-12-01",
            "fixed_annual_rate": 20,
            "rule_mode": "private_lending_cap",
            "contract_date": "2019-12-01",
        },
    )
    assert resp.status_code == 422


def test_s16_r5_post_segment_cap_154():
    res = calculate_lpr_interest(
        100000,
        "2019-12-01",
        "2021-12-01",
        fixed_annual_rate=20,
        rule_mode="private_lending_cap",
        contract_date="2019-12-01",
        filing_date="2021-12-01",
    )
    assert round(res["total_interest"], 2) == 34156.71
    post = [s for s in res["segments"] if s.get("cap_basis") == "起诉时LPR×4"]
    assert post
    assert post[0]["statutory_cap_rate"] == 15.4
    assert post[0].get("segment_start") == "2020-08-20"


# ---------------------------------------------------------------------------
# I-04 保全续行
# ---------------------------------------------------------------------------

def test_i04_preservation_advance_7_days():
    res = calculate_preservation_renewal(
        "bank_deposit", "2026-01-01", today_date="2026-10-21"
    )
    assert res["advance_days_required"] == 7
    assert res["renewal_application_deadline"] == "2026-12-25"
    assert "内部提醒日" in (res.get("internal_reminder_note") or "")
    assert res.get("internal_reminder_date")


def test_i04_invalid_preservation_type_raises():
    with pytest.raises(ValueError, match="bank_deposit|movable_property|real_estate_equity"):
        calculate_preservation_renewal("real_estate", "2026-01-01")


def test_i04_api_real_estate_returns_422(client):
    resp = client.post(
        "/api/v1/phase1/calc/preservation-renewal",
        json={"preservation_type": "real_estate", "start_date": "2026-01-01"},
    )
    assert resp.status_code == 422
    detail = str(resp.json())
    assert "bank_deposit" in detail or "允许" in detail


# ---------------------------------------------------------------------------
# I-05 重大误解撤销权
# ---------------------------------------------------------------------------

def test_i05_cancel_right_1y_five_year_cap():
    res = calculate_statute_of_limitations(
        "2026-03-01",
        cause_type="cancel_right_1y",
        act_date="2021-06-01",
        today_date="2026-10-21",
    )
    assert res["final_expire_date"] == "2026-06-01"
    assert "重大误解" not in res["rule_name"]


def test_i05_cancel_mistake_missing_act_date_warning():
    res = calculate_statute_of_limitations(
        "2026-01-01",
        cause_type="cancel_mistake_90d",
        today_date="2026-10-21",
    )
    assert res["final_expire_date"] == "2026-04-01"
    assert any("未提供行为发生日" in w for w in res.get("warnings", []))


# ---------------------------------------------------------------------------
# I-07 违约金/逾期利息
# ---------------------------------------------------------------------------

def test_i07_commercial_pre_lpr_reform_uses_435_pct():
    """
    商事浮动模式：2019-08-20 前期间按央行同期同类贷款基准利率 1 年期 4.35%。
    预期 2753.01 元为推算衍生值，待律师确认（TODO lawyer-verify）。
    """
    # TODO(律师核实): 2753.01 元为按 4.35%×231/365 推算，非律师原始用例，若律师另有意见以律师为准。
    res = calculate_lpr_interest(
        100000, "2019-01-01", "2019-08-20", term="1Y", rule_mode="commercial_floating"
    )
    assert round(res["total_interest"], 2) == 2753.01
    assert any("4.35" in str(s.get("base_lpr", s.get("rate_basis", ""))) or "基准利率" in str(s) for s in res["segments"]) or \
        "4.35" in res.get("complaint_statement", "") or \
        any("4.35" in str(w) for w in res.get("warnings", [])) or \
        any(s.get("applied_annual_rate") == 4.35 for s in res["segments"])


def test_i07_sales_fixed_lpr_markup_4650():
    """
    买卖合同固定 LPR 加计：基数为起算日一年期 LPR，整段不浮动。
    预期 4650.00 元为推算衍生值，待律师确认（TODO lawyer-verify）。
    """
    # TODO(律师核实): 4650.00 元按 2025-01-01 时一年期 LPR 3.10%×(1+0.5) 推算，待律师确认。
    res = calculate_lpr_interest(
        100000,
        "2025-01-01",
        "2026-01-01",
        rule_mode="sales_fixed_lpr_markup",
        markup_ratio=0.5,
    )
    assert round(res["total_interest"], 2) == 4650.00
    assert len(res["segments"]) == 1
    assert res["segments"][0]["applied_annual_rate"] == 4.65


def test_i07_sales_markup_ratio_out_of_range():
    with pytest.raises(ValueError):
        calculate_lpr_interest(
            100000,
            "2025-01-01",
            "2026-01-01",
            rule_mode="sales_fixed_lpr_markup",
            markup_ratio=0.2,
        )


def test_i07_sales_complaint_template_no_hardcoded_50pct():
    tpl = ROOT / "templates" / "civil_complaint_sales_template.docx"
    assert tpl.is_file()
    doc = Document(str(tpl))
    full = "\n".join(p.text for p in doc.paragraphs)
    assert "加计50%" not in full.replace(" ", "")
    assert "加计 50%" not in full
    assert "{{ overdue_rate_desc }}" in full or "overdue_rate_desc" in full


# ---------------------------------------------------------------------------
# I-17 以物抵债表述
# ---------------------------------------------------------------------------

def test_i17_no_absolute_invalid_phrase_in_gateway():
    hits = []
    for path in (ROOT / "gateway").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "绝对无效" in text:
            hits.append(str(path.relative_to(ROOT)))
    assert hits == []


def test_i17_debt_for_asset_memo_contains_partial_invalidity():
    res = calculate_settlement_npv_and_recovery(
        total_claim_nominal=1000000,
        plan_type="debt_for_asset",
        asset_plan={
            "asset_name": "测试房产",
            "nominal_asset_valuation": 800000,
            "prior_liens": 100000,
            "auction_discount_rate": 0.7,
            "liquidation_costs_rate": 0.12,
            "time_to_liquidate_months": 12,
        },
    )
    memo = res["partner_tactical_memo"]
    assert "不影响合同其他部分的效力" in memo
    assert "绝对无效" not in memo
    assert "让与担保" not in memo
