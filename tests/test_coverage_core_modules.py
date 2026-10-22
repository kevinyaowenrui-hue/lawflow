# -*- coding: utf-8 -*-
"""
覆盖率补强：cn_legal_calc / citation_guard / guarantee_and_cashflow_engine。

断言仅使用：
- 模块 docstring / 源码已写明的示例输出
- 既有用例已核验的数值与枚举（lawyer_cases / batch5 / p1 / p2 / p3 / citation_guard_logic / full_suite）
- 结构性属性（valid/keys/status/types），不编造法条文本或法律结论金额
"""
from __future__ import annotations

from datetime import date

import pytest

from gateway.utils.citation_guard import (
    audit_case_numbers,
    audit_citations_in_text,
    cn_to_int,
    get_official_max_article,
    int_to_cn_article,
    verify_single_case_number,
)
from gateway.utils.cn_legal_calc import (
    calculate_appeal_deadline,
    calculate_court_fees,
    calculate_preservation_renewal,
    calculate_settlement_npv_and_recovery,
    calculate_statute_of_limitations,
    rmb_to_capital,
    validate_and_parse_idcard,
    validate_and_parse_uscc,
)
from gateway.utils.guarantee_and_cashflow_engine import (
    analyze_guarantee_topology_and_deadlines,
    audit_and_reconcile_cashflow,
)


# ---------------------------------------------------------------------------
# rmb_to_capital（docstring 示例 + 原生兜底）
# ---------------------------------------------------------------------------

def test_rmb_to_capital_docstring_examples():
    assert rmb_to_capital(0) == "人民币零元整"
    assert rmb_to_capital(123000) == "人民币壹拾贰万叁仟元整"
    assert rmb_to_capital("10500.50") == "人民币壹万零伍佰元伍角整"
    assert rmb_to_capital(0.58) == "人民币伍角捌分"


def test_rmb_to_capital_invalid_raises():
    with pytest.raises(ValueError, match="无效的金额"):
        rmb_to_capital("not-a-number")


def test_rmb_to_capital_native_fallback_matches_docstring(monkeypatch):
    import gateway.utils.cn_legal_calc as m

    monkeypatch.setattr(m, "cn2an", None)
    assert m.rmb_to_capital(0) == "人民币零元整"
    assert m.rmb_to_capital(123000) == "人民币壹拾贰万叁仟元整"
    assert m.rmb_to_capital("10500.50") == "人民币壹万零伍佰元伍角整"
    assert m.rmb_to_capital(0.58) == "人民币伍角捌分"
    assert m.rmb_to_capital(-100).startswith("人民币负")
    assert "元" in m.rmb_to_capital(1)


def test_rmb_to_capital_cn2an_exception_falls_back(monkeypatch):
    import gateway.utils.cn_legal_calc as m

    class _Boom:
        @staticmethod
        def an2cn(*_a, **_k):
            raise RuntimeError("force fallback")

    monkeypatch.setattr(m, "cn2an", _Boom)
    assert m.rmb_to_capital(123000) == "人民币壹拾贰万叁仟元整"


# ---------------------------------------------------------------------------
# 身份证 / USCC：仅结构与既有 R24 USCC
# ---------------------------------------------------------------------------

def test_idcard_wrong_length_invalid():
    res = validate_and_parse_idcard("12345")
    assert res["valid"] is False
    assert "18" in res["error_message"]


def test_idcard_unknown_province_invalid():
    res = validate_and_parse_idcard("99110119900101123X")
    assert res["valid"] is False
    assert "行政区划" in res["error_message"]


def test_idcard_bad_birth_date_invalid():
    res = validate_and_parse_idcard("11010119901301123X")
    assert res["valid"] is False
    assert "出生日期" in res["error_message"] or "公历" in res["error_message"]


def test_idcard_non_digit_body_invalid():
    res = validate_and_parse_idcard("11010119900101ABCX")
    assert res["valid"] is False
    assert "数字" in res["error_message"]


def _idcard_with_check(body17: str) -> str:
    """按 GB/ISO 7064 MOD 11-2 生成校验位（技术校验，非法条文本）。"""
    weights = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
    check_codes = "10X98765432"
    s = sum(int(body17[i]) * weights[i] for i in range(17))
    return body17 + check_codes[s % 11]


def test_idcard_checksum_and_structural_fields():
    # 北京 + 1960-01-01 男：走 2025 前已达原退休年龄分支（源码 215-217）
    card = _idcard_with_check("11010119600101123")
    res = validate_and_parse_idcard(card)
    assert res["valid"] is True
    assert res["province"] == "北京市"
    assert res["birth_date"] == "1960-01-01"
    assert res["gender"] == "男"
    assert res["delay_months"] == 0
    assert isinstance(res["is_retired"], bool)
    assert "retirement_note" in res


def test_idcard_cadre_flag_changes_orig_retire_age():
    # 女工人 vs 女干部：仅断言 orig_retire_age 枚举（50/55），不编造退休结论文案
    card = _idcard_with_check("11010119900101122")  # 末位偶数为女
    worker = validate_and_parse_idcard(card, is_cadre=False)
    cadre = validate_and_parse_idcard(card, is_cadre=True)
    assert worker["valid"] is True and cadre["valid"] is True
    assert worker["gender"] == "女"
    assert worker["orig_retire_age"] == 50
    assert cadre["orig_retire_age"] == 55


def test_uscc_r24_known_valid():
    # 与 test_lawyer_cases.test_R24_uscc_valid 同源
    res = validate_and_parse_uscc("914403001922038216")
    assert res["valid"] is True
    assert res["uscc"] == "914403001922038216"
    assert "department" in res


def test_uscc_wrong_length_and_illegal_char():
    short = validate_and_parse_uscc("91440300")
    assert short["valid"] is False
    assert "18" in short["error_message"]

    bad = validate_and_parse_uscc("91440300192203821I")  # I 非法
    assert bad["valid"] is False
    assert "非法字符" in bad["error_message"]


# ---------------------------------------------------------------------------
# 诉讼费：R1 同源 + labor/divorce 结构（法定固定档位写在源码）
# ---------------------------------------------------------------------------

def test_court_fees_r1_regression():
    res = calculate_court_fees(1000000)
    assert res["actual_fee"] == 13800
    assert res["preservation_fee"] == 5000


def test_court_fees_summary_r2():
    res = calculate_court_fees(1000000, is_summary_procedure=True)
    assert res["actual_fee"] == 6900


def test_court_fees_negative_raises():
    with pytest.raises(ValueError, match="不能为负数"):
        calculate_court_fees(-1)


def test_court_fees_labor_fixed_10():
    res = calculate_court_fees(100000, case_type="labor")
    assert res["actual_fee"] == 10.0
    assert res["tier_breakdown"]


def test_court_fees_divorce_tiers_structural():
    low = calculate_court_fees(100000, case_type="divorce")
    assert low["actual_fee"] == 100.0
    high = calculate_court_fees(300000, case_type="离婚")
    assert high["standard_fee"] > 100.0
    assert isinstance(high["rmb_capital"], str)
    assert high["rmb_capital"].startswith("人民币")


def test_court_fees_property_small_tier():
    res = calculate_court_fees(5000)
    assert res["actual_fee"] == 50.0
    assert res["preservation_fee"] == 30.0 + (5000 - 1000) * 0.01


# ---------------------------------------------------------------------------
# 保全续行：允许类型 + 既有 advance_days=7
# ---------------------------------------------------------------------------

def test_preservation_movable_and_equity_advance_7():
    mov = calculate_preservation_renewal(
        "movable_property", "2026-01-01", today_date="2026-10-21"
    )
    assert mov["advance_days_required"] == 7
    assert mov["expire_date"] == "2028-01-01"
    assert mov["renewal_application_deadline"] == "2027-12-25"
    assert mov["status_level"] in ("SAFE", "WARNING", "URGENT", "CRITICAL_BREACH", "EXPIRED")

    eq = calculate_preservation_renewal(
        "real_estate_equity", "2026-01-01", today_date="2026-10-21"
    )
    assert eq["advance_days_required"] == 7
    assert eq["expire_date"] == "2029-01-01"
    assert eq["status_level"] == "SAFE"


def test_preservation_status_critical_and_expired():
    # 续行截止已过、届满未过 → CRITICAL_BREACH（枚举已在源码）
    crit = calculate_preservation_renewal(
        "bank_deposit", "2025-01-01", today_date="2025-12-28"
    )
    assert crit["status_level"] == "CRITICAL_BREACH"

    exp = calculate_preservation_renewal(
        "bank_deposit", "2024-01-01", today_date="2026-10-21"
    )
    assert exp["status_level"] == "EXPIRED"


# ---------------------------------------------------------------------------
# 上诉期：p3 已核验日期 + 中文别名 + 非法类型
# ---------------------------------------------------------------------------

def test_appeal_deadline_p3_values_and_aliases():
    r1 = calculate_appeal_deadline("2026-11-02", "裁定")
    assert r1["deadline"] == "2026-11-12"
    assert r1["period_days"] == 10
    r2 = calculate_appeal_deadline("2026-11-02", "判决")
    assert r2["deadline"] == "2026-11-17"
    assert r2["period_days"] == 15
    r3 = calculate_appeal_deadline(
        "2026-11-02", "ruling", holidays=["2026-11-12"]
    )
    assert r3["deadline"] == "2026-11-13"
    assert r3["extended_for_holiday_or_weekend"] is True


def test_appeal_deadline_invalid_type():
    with pytest.raises(ValueError, match="judgment_type"):
        calculate_appeal_deadline("2026-11-02", "mediation")


# ---------------------------------------------------------------------------
# 时效：full_suite / lawyer_cases / batch4 / batch5 已核验路径
# ---------------------------------------------------------------------------

def test_sol_guarantee_periods_from_full_suite():
    gen = calculate_statute_of_limitations(
        "2023-01-01", cause_type="guarantee_general_6m", today_date="2026-10-21"
    )
    assert gen["is_preclusive"] is True
    assert gen["final_expire_date"] == "2023-07-01"
    assert "起诉主债务人" in (gen.get("special_notice") or "")

    joint = calculate_statute_of_limitations(
        "2023-01-01", cause_type="guarantee_joint_6m", today_date="2026-10-21"
    )
    assert joint["is_preclusive"] is True
    assert joint["final_expire_date"] == "2023-07-01"


def test_sol_construction_priority_article_41_in_basis():
    res = calculate_statute_of_limitations(
        "2024-01-01",
        cause_type="construction_priority_18m",
        today_date="2026-10-21",
    )
    assert "第四十一条" in str(res)
    assert res["is_preclusive"] is True
    assert res["final_expire_date"] == "2025-07-01"


def test_sol_cancel_right_1y_five_year_cap_batch5():
    res = calculate_statute_of_limitations(
        "2026-03-01",
        cause_type="cancel_right_1y",
        act_date="2021-06-01",
        today_date="2026-10-21",
    )
    assert res["final_expire_date"] == "2026-06-01"


def test_sol_r9_r10_and_status_levels():
    expired = calculate_statute_of_limitations(
        "2026-01-01",
        cause_type="cancel_mistake_90d",
        today_date="2026-10-21",
    )
    assert expired["final_expire_date"] == "2026-04-01"
    assert expired["status_level"] == "CRITICAL_EXPIRED"

    interrupted = calculate_statute_of_limitations(
        "2023-01-01",
        interruption_events=[{"date": "2025-06-01", "type": "催告"}],
        today_date="2026-10-21",
    )
    assert interrupted["final_expire_date"] == "2028-06-01"
    assert interrupted["status_level"] == "SAFE_GREEN"

    # 中断事件缺 date → 跳过（结构）
    skip = calculate_statute_of_limitations(
        "2023-01-01",
        interruption_events=[{"type": "催告"}],
        today_date="2026-10-21",
    )
    assert skip["effective_interruptions_count"] == 0

    # 时效已过后的催告 → 记入 timeline 无效行为
    late = calculate_statute_of_limitations(
        "2020-01-01",
        interruption_events=[{"date": "2024-01-01", "type": "催告"}],
        today_date="2026-10-21",
    )
    assert any("无效" in (t.get("event") or "") for t in late["timeline_log"])


def test_sol_suspension_art194_from_full_suite():
    res = calculate_statute_of_limitations(
        "2020-01-01",
        cause_type="general_3y",
        suspension_events=[
            {
                "date": "2022-09-01",
                "description": "严重疫情封控导致当事人丧失起诉行为能力",
                "resume_date": "2022-11-01",
            }
        ],
        today_date="2026-10-21",
    )
    assert res["final_expire_date"] == "2023-05-01"


def test_sol_urgent_and_amber_status_enums():
    # 仅断言源码已有 status_level 枚举名，不编造法律结论
    urgent = calculate_statute_of_limitations(
        "2023-11-01",
        cause_type="general_3y",
        today_date="2026-10-21",
    )
    assert urgent["status_level"] in ("URGENT_RED", "WARNING_AMBER", "SAFE_GREEN", "CRITICAL_EXPIRED")
    assert "final_expire_date" in urgent


# ---------------------------------------------------------------------------
# 和解 NPV：p1 / batch5 已核验路径 + 输入校验
# ---------------------------------------------------------------------------

def test_settlement_cash_installments_p1_structural():
    res = calculate_settlement_npv_and_recovery(
        total_claim_nominal=1000000.0,
        plan_type="cash_installments",
        annual_discount_rate=0.08,
        installments=[
            {"months": 3, "amount": 300000.0, "note": "首期付款"},
            {"months": 6, "amount": 300000.0, "note": "第二期付款"},
            {"months": 12, "amount": 400000.0, "note": "结清尾款"},
        ],
    )
    assert res["status"] == "success"
    m = res["metrics"]
    assert m["total_nominal_settlement"] == 1000000.0
    assert m["nominal_recovery_rate"] == 100.0
    assert m["illusion_gap"] > 0.0


def test_settlement_debt_for_asset_batch5_memo():
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


def test_settlement_invalid_inputs():
    with pytest.raises(ValueError):
        calculate_settlement_npv_and_recovery(total_claim_nominal=0, plan_type="hybrid")
    with pytest.raises(ValueError, match="plan_type"):
        calculate_settlement_npv_and_recovery(
            total_claim_nominal=100000, plan_type="xxx"
        )
    with pytest.raises(ValueError, match="无效的债权"):
        calculate_settlement_npv_and_recovery(
            total_claim_nominal="bad", plan_type="hybrid"
        )


# ---------------------------------------------------------------------------
# citation_guard helpers
# ---------------------------------------------------------------------------

def test_cn_to_int_and_int_to_cn_article_roundtrip():
    # 条号均已在既有 citation / top5 用例中出现
    for n in (47, 74, 98, 114, 188, 307, 585, 1064, 1260):
        cn = int_to_cn_article(n)
        assert cn.startswith("第") and cn.endswith("条")
        assert cn_to_int(cn) == n
    assert cn_to_int("") is None
    assert cn_to_int("585") == 585
    assert cn_to_int("第abc条") is None
    assert int_to_cn_article(0) == "第0条"
    assert int_to_cn_article(10) == "第十条"
    assert int_to_cn_article(5) == "第五条"


def test_get_official_max_article_top5():
    assert get_official_max_article("中华人民共和国民法典") == 1260
    assert get_official_max_article("民诉法") == 306
    assert get_official_max_article("劳动合同法") == 98


def test_audit_case_numbers_formats_from_a02():
    assert audit_case_numbers("") == []
    modern = audit_case_numbers("（2023）京0105民特12号")
    assert modern[0]["status"] == "STRUCTURE_ONLY_UNVERIFIED"
    legacy = audit_case_numbers("(2012)民提字第11号")
    assert legacy[0]["status"] == "STRUCTURE_ONLY_UNVERIFIED"
    assert "民提" in legacy[0]["standard_case_number"]


def test_verify_single_case_number_invalid_format():
    res = verify_single_case_number("不是案号")
    assert res["status"] == "INVALID_FORMAT"
    assert res["is_hallucination"] is True


def test_audit_citations_hallucination_and_abrogated_paths():
    # a01 / R15 / R16 同源状态枚举
    r307 = audit_citations_in_text(
        raw_text="依据《民事诉讼法》第三百零七条", auto_sanitize=False
    )
    assert r307["citations"][0]["status"] == "HALLUCINATION_EXCEEDED"

    ab = audit_citations_in_text(
        raw_text="依据《收养法》第一条", auto_sanitize=False
    )
    assert ab["citations"][0]["status"] == "ABROGATED_BLOCKED"

    unk = audit_citations_in_text(
        raw_text="依据《中华人民共和国智能合约促进法》第3条", auto_sanitize=False
    )
    assert unk["citations"][0]["status"] == "UNRECOGNIZED_LAW"


def test_case_number_year_hallucination_from_batch1():
    # test_batch1_e2e 同源：未来年份
    fake = verify_single_case_number("（2099）最高法知民终9999号")
    assert fake["status"] == "CASE_NUMBER_HALLUCINATION_YEAR"
    assert fake["is_hallucination"] is True


def test_private_lending_yellow_and_contract_sanitize_paths():
    # citation_guard_logic / lawyer R19 同源
    yellow = audit_citations_in_text(
        raw_text="双方约定年利率24%，依据《民间借贷规定》第二十五条。",
        auto_sanitize=False,
    )
    joined = " ".join(yellow.get("warnings") or [])
    assert "2020年修正前的民间借贷利率口径" in joined

    no_date = audit_citations_in_text(
        raw_text="2019年签订合同，依据《合同法》第一百一十四条主张违约金。",
        auto_sanitize=True,
    )
    assert "《合同法》第一百一十四条" in no_date["sanitized_text"]

    with_date = audit_citations_in_text(
        raw_text="依据《合同法》第一百一十四条主张违约金。",
        auto_sanitize=True,
        incident_date="2022-03-01",
    )
    assert "第五百八十五条" in with_date["sanitized_text"]
    assert with_date["sanitized_text"].count("第五百八十五条") == 1


def test_load_verified_precedents_and_ensure_table():
    from gateway.core.db import connect
    from gateway.core.paths import get_laws_db_path
    from gateway.utils.citation_guard import (
        ensure_court_precedents_table,
        load_verified_precedents_from_db,
    )

    rows = load_verified_precedents_from_db()
    assert isinstance(rows, list)
    with connect(get_laws_db_path()) as conn:
        ensure_court_precedents_table(conn)
        again = load_verified_precedents_from_db(conn)
        assert isinstance(again, list)


# ---------------------------------------------------------------------------
# guarantee / cashflow：既有 R12/R20 / p2 路径扩展（结构 + 已核验日期）
# ---------------------------------------------------------------------------

def test_guarantee_due_date_from_cn_timeline_text():
    nodes = [
        {"id": "e1", "name": "债权人A", "role": "原告/债权人", "type": "person"},
        {"id": "e2", "name": "债务人B", "role": "主债务人/被告", "type": "person"},
        {"id": "e3", "name": "保证人", "role": "保证人", "type": "person"},
    ]
    edges = [
        {
            "source": "e3",
            "target": "e1",
            "relation": "保证",
            "detail": "连带保证",
            "guarantee_mode": "joint",
        }
    ]
    timeline = [
        {
            "date": "2023-07-01",
            "event": "借款到期届满日为2023年7月1日",
            "legal_tag": "主债务到期",
        }
    ]
    res = analyze_guarantee_topology_and_deadlines(
        nodes, edges, timeline, today_date="2024-05-01"
    )
    assert res["status"] == "success"
    assert res["principal_due_date"] == "2023-07-01"
    assert res["statutory_guarantee_expiry"] == "2024-01-01"


def test_cashflow_r20_regression_and_empty_records():
    res = audit_and_reconcile_cashflow(
        [{"date": "2025-07-01", "amount": 5000, "purpose": "还款"}],
        principal_amount=100000,
        annual_rate=0.12,
        start_date="2025-01-01",
    )
    row = res["reconciliation_ledger"][0]
    assert row["days_accrued"] == 181
    assert row["offset_to_interest"] == 5000
    assert row["offset_to_principal"] == 0

    empty = audit_and_reconcile_cashflow(
        [],
        principal_amount=100000,
        annual_rate=0.12,
        start_date="2025-01-01",
    )
    assert empty["status"] in ("success", "insufficient_data") or "reconciliation_ledger" in empty
    assert isinstance(empty.get("reconciliation_ledger", []), list)
