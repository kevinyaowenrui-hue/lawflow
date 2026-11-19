# -*- coding: utf-8 -*-
"""律师日常口径：诉讼费类型、立案预交与结案减半、申请执行期间、诉讼时效公休日顺延。"""
from gateway.utils.cn_legal_calc import (
    calculate_court_fees,
    calculate_enforcement_application_deadline,
    calculate_labor_compensation,
    calculate_lpr_interest,
    calculate_statute_of_limitations,
)


def test_execution_fee_schedule_and_no_amount_flat():
    res = calculate_court_fees(100000, case_type="execution")
    assert res["fee_nature"] == "申请费"
    assert res["standard_fee"] == 1400.0
    flat = calculate_court_fees(0, case_type="execution", execution_flat_fee=80)
    assert flat["standard_fee"] == 80.0


def test_application_fee_is_not_halved_by_summary_procedure():
    res = calculate_court_fees(100000, case_type="execution", is_summary_procedure=True)
    assert res["is_half_fee"] is False
    assert res["actual_fee"] == res["standard_fee"]


def test_personality_payment_order_and_fixed_application_fees():
    base_only = calculate_court_fees(0, case_type="personality", personality_base_fee=200)
    assert base_only["standard_fee"] == 200.0
    with_damages = calculate_court_fees(80000, case_type="personality", personality_base_fee=200)
    assert with_damages["standard_fee"] == 500.0
    payment = calculate_court_fees(500000, case_type="payment_order")
    assert payment["standard_fee"] == 2933.33
    assert calculate_court_fees(0, case_type="public_summons")["standard_fee"] == 100.0
    assert calculate_court_fees(0, case_type="arbitration_revoke")["standard_fee"] == 400.0


def test_mediation_half_is_settlement_not_filing_prepay():
    res = calculate_court_fees(100000, is_mediation_or_withdrawal=True)
    assert res["actual_fee"] == res["standard_fee"] / 2
    assert res["filing_prepay_fee"] == res["standard_fee"]
    assert "立案预交仍按全额" in res["filing_prepay_note"]
    rule = res["statutory_reduction_rule"]
    assert "《诉讼费用交纳办法》第十五条" in rule
    assert "第十六条" not in rule
    assert "退费口径" in rule
    assert "不是立案就预交一半" in rule


def test_summary_procedure_half_cites_article_16_and_prepay_stays_full():
    """未确定适用简易程序时按全额预交。减半只引用第16条，是结案退费，不是立案预交一半。"""
    res = calculate_court_fees(100000, is_summary_procedure=True)
    assert res["actual_fee"] == res["standard_fee"] / 2
    assert res["filing_prepay_fee"] == res["standard_fee"]
    assert res["filing_prepay_fee"] != res["actual_fee"]
    rule = res["statutory_reduction_rule"]
    assert "《诉讼费用交纳办法》第十六条" in rule
    assert "第十五条" not in rule
    assert "立案时即按减半预交" not in (rule or "")
    assert "未确定适用简易程序" in res["filing_prepay_note"]
    assert "退费口径" in res["filing_prepay_note"]
    assert "不是立案就预交一半" in res["filing_prepay_note"]
    joined = calculate_court_fees(
        100000, is_summary_procedure=True, is_mediation_or_withdrawal=True
    )
    assert joined["filing_prepay_fee"] == joined["standard_fee"]
    assert "第十六条" in joined["statutory_reduction_rule"]
    assert "第十五条" in joined["statutory_reduction_rule"]
    assert "立案时即按减半预交" not in joined["statutory_reduction_rule"]


def test_labor_court_fee_is_court_acceptance_not_arbitration():
    res = calculate_court_fees(100000, case_type="labor")
    assert res["actual_fee"] == 10.0
    assert res["standard_fee"] == 10.0
    note = res["labor_court_fee_note"]
    assert note == (
        "向人民法院起诉的劳动争议案件受理费，每件 10 元。劳动仲裁不收费，不要用本项。"
        "依据《诉讼费用交纳办法》第十三条、《劳动争议调解仲裁法》第五十三条。"
    )
    blob = str(res["tier_breakdown"])
    assert "向人民法院起诉的劳动争议案件受理费，每件 10 元。劳动仲裁不收费，不要用本项。" in blob
    assert "劳动人事争议" not in blob
    assert "法定10元" not in blob
    summary = calculate_court_fees(100000, case_type="labor", is_summary_procedure=True)
    assert summary["actual_fee"] == 5.0
    assert summary["filing_prepay_fee"] == 10.0
    assert "第十六条" in summary["statutory_reduction_rule"]
    assert "第十五条" not in summary["statutory_reduction_rule"]


def test_enforcement_period_two_years_from_performance_last_day():
    res = calculate_enforcement_application_deadline(
        "2024-03-11",
        anchor_type="performance_last_day",
        today_date="2024-03-12",
    )
    assert res["period_start_date"] == "2024-03-11"
    assert res["raw_deadline"] == "2026-03-11"
    assert res["legal_basis"].startswith("《中华人民共和国民事诉讼法》（2023修正）第二百五十条")
    assert "中止、中断" in res["interruption_note"]


def test_enforcement_period_effective_plus_ten_days_and_last_installment():
    plus = calculate_enforcement_application_deadline(
        "2024-03-01",
        anchor_type="effective_plus_days",
        performance_days=10,
        today_date="2024-03-01",
    )
    assert plus["period_start_date"] == "2024-03-11"
    assert plus["raw_deadline"] == "2026-03-11"
    last = calculate_enforcement_application_deadline(
        "2024-01-15",
        anchor_type="last_installment",
        today_date="2024-01-16",
    )
    assert last["raw_deadline"] == "2026-01-15"
    assert "最后一期" in last["installment_note"]


def test_enforcement_deadline_rolls_off_weekend():
    # 2024-06-06 加两年为 2026-06-06（周六），周日 6 月 7 日继续顺延到 6 月 8 日。
    res = calculate_enforcement_application_deadline(
        "2024-06-06",
        today_date="2024-06-07",
        treat_weekend_as_holiday=True,
    )
    assert res["raw_deadline"] == "2026-06-06"
    assert res["deadline"] == "2026-06-08"
    assert res["extended_for_holiday_or_weekend"] is True


def test_limitation_rolls_ordinary_weekend_but_guarantee_period_does_not():
    limitation = calculate_statute_of_limitations(
        "2021-06-01",
        cause_type="general_3y",
        today_date="2024-01-01",
    )
    assert limitation["final_expire_date"] == "2024-06-03"
    guarantee = calculate_statute_of_limitations(
        "2023-01-01",
        cause_type="guarantee_joint_6m",
        today_date="2023-01-02",
    )
    assert guarantee["final_expire_date"] == "2023-07-01"


def test_pre_lpr_benchmark_follows_pboc_steps_not_flat_435():
    res = calculate_lpr_interest(
        100000, "2015-08-01", "2015-11-01", term="1Y", rule_mode="commercial_floating"
    )
    rates = [seg["base_lpr"] for seg in res["segments"]]
    assert rates == [4.85, 4.60, 4.35]
    assert "TODO" not in res["complaint_statement"]


def test_benchmark_before_schedule_is_not_silently_priced_at_435():
    res = calculate_lpr_interest(
        100000, "2012-01-01", "2012-02-01", term="1Y", rule_mode="commercial_floating"
    )
    assert res["total_interest"] == 0
    assert any("2012-07-06" in w for w in res["warnings"])


def test_five_year_benchmark_is_not_the_one_year_rate():
    res = calculate_lpr_interest(
        100000, "2015-10-24", "2015-11-01", term="5Y", rule_mode="commercial_floating"
    )
    assert res["segments"][0]["base_lpr"] == 4.90


def test_cross_2008_labor_pleading_uses_segment_note():
    res = calculate_labor_compensation(
        monthly_salary=10000,
        hire_date="2005-03-01",
        termination_date="2010-03-01",
        termination_reason="expiry_termination",
    )
    assert res["pleading_basis"] == "segment_2008"
    assert "total_segmented_n" in res["pleading_note"]
    assert res["segment_2008"]["total_segmented_n"] != res["tiers"]["N"]["amount"]


def test_sales_overdue_after_lpr_reform_is_fixed_at_breach_date():
    res = calculate_lpr_interest(
        100000,
        "2025-01-01",
        "2026-01-01",
        rule_mode="sales_fixed_lpr_markup",
        markup_ratio=0.5,
    )
    assert len(res["segments"]) == 1
    assert res["segments"][0]["base_kind"] == "lpr"
    assert res["segments"][0]["applied_annual_rate"] == 4.65
    assert "不随后续报价调整" in res["complaint_statement"]
    assert "需律师核实" not in res["complaint_statement"]


def test_sales_overdue_before_lpr_reform_uses_benchmark_not_lpr():
    res = calculate_lpr_interest(
        100000,
        "2018-01-01",
        "2019-01-01",
        rule_mode="sales_fixed_lpr_markup",
        markup_ratio=0.5,
    )
    assert res["segments"][0]["base_kind"] == "pboc"
    assert res["segments"][0]["base_lpr"] == 4.35
    assert res["segments"][0]["applied_annual_rate"] == 6.525
    assert round(res["total_interest"], 2) == 6525.00
    assert "贷款基准利率" in res["complaint_statement"]


def test_sales_overdue_before_benchmark_schedule_does_not_invent_a_rate():
    res = calculate_lpr_interest(
        100000,
        "2012-01-01",
        "2012-07-01",
        rule_mode="sales_fixed_lpr_markup",
        markup_ratio=0.3,
    )
    assert res["total_interest"] == 0
    assert res["segments"][0]["applied_annual_rate"] is None


def test_private_lending_without_agreed_rate_uses_lpr_not_four_times():
    plain = calculate_lpr_interest(
        100000,
        "2024-01-01",
        "2025-01-01",
        rule_mode="private_lending_cap",
        contract_date="2024-01-01",
    )
    capped = calculate_lpr_interest(
        100000,
        "2024-01-01",
        "2025-01-01",
        fixed_annual_rate=24,
        rule_mode="private_lending_cap",
        contract_date="2024-01-01",
    )
    assert "第二十八条" in plain["complaint_statement"]
    assert plain["total_interest"] < capped["total_interest"]
    assert plain["total_interest"] > 0
    assert "3.85" not in plain["complaint_statement"]


def test_rule_fallback_does_not_invent_performance_or_evidence():
    from gateway.core.ollama_client import ollama_client

    facts = ollama_client._generate_rule_fallback(
        "请润色事实与理由。\n【案件案由】民间借贷纠纷\n【律师案情碎片笔记】\n2024年1月1日借款10万元。",
        None,
    )
    assert "全面恪守" not in facts
    assert "多次以书面" not in facts
    assert "不是四倍" in facts

    empty_catalog = ollama_client._generate_rule_fallback("请梳理提炼为规范的 JSON 数组。证据目录：", None)
    assert empty_catalog.strip() == "[]"

    outline = ollama_client._generate_rule_fallback("请输出五模块结构的出庭提纲", None)
    assert "4倍红线" not in outline
    assert "第85条" not in outline
    assert "第九十三条" in outline
    assert "视为标的物" not in outline


def test_construction_priority_notice_says_corpus_gap():
    res = calculate_statute_of_limitations("2024-01-01", cause_type="construction_priority_18m")
    blob = str(res)
    assert "第四十一条" in blob
    assert "本地库未收录" in blob
    assert "除斥期间" in blob


def test_lawyer_facing_labels_do_not_teach_caps_or_fake_verification(client):
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    calc_js = (root / "frontend/js/modules/01_calc.js").read_text(encoding="utf-8")
    search_js = (root / "frontend/js/modules/06_citation_guard.js").read_text(encoding="utf-8")
    matters_js = (root / "frontend/js/modules/07_matters.js").read_text(encoding="utf-8")
    assert "调减后金额" not in calc_js
    assert "违约金30%上限" not in search_js
    assert "套取贷款转贷无效" not in search_js
    assert "100% 现行有效" not in matters_js
    assert "已达起诉标准" not in (root / "frontend/js/modules/05_enforcement.js").read_text(encoding="utf-8")
    assert "100% 权威现行有效" not in search_js
    assert "100% 权威现行有效" not in (root / "frontend/js/modules/modals.js").read_text(encoding="utf-8")
    assert "SHA-256 存证一致" not in (root / "frontend/js/modules/05_enforcement.js").read_text(encoding="utf-8")
    assert "不能据此起诉" in (root / "frontend/js/modules/05_enforcement.js").read_text(encoding="utf-8")
    matters = (root / "frontend/js/modules/07_matters.js").read_text(encoding="utf-8")
    assert "100% 凭证吻合" not in matters
    assert "打破被告抗辩" not in matters
    assert "洗钱" not in matters
    assert "先费用，再利息，再本金" in matters
    assert "已验真" not in matters
    assert "未核对原件" in matters
    appeal_js = (root / "frontend/js/modules/04_appeal_signing.js").read_text(encoding="utf-8")
    assert "支持派权威判例" not in appeal_js
    assert "二审终稿" not in appeal_js
    assert "不是最高法院代理词" in appeal_js

    loan = client.post("/api/v1/deep-matrix/analyze", json={"case_preset": "case_loan_intermingled"}).json()
    loan_blob = str(loan)
    assert "4倍红线" not in loan_blob

    tech = client.post("/api/v1/deep-matrix/analyze", json={"case_preset": "case_tech_development"}).json()
    tech_blob = str(tech)
    assert "解释》第十条" not in tech_blob
    assert "依法推定" not in tech_blob
    assert "司法惯例" not in tech_blob
    assert "合同第4条" in tech_blob

    found = client.post("/api/v1/statutes/search", json={"query": "合同编通则解释 65"}).json()
    articles = found.get("results") or []
    assert any(item.get("article_no_cn") == "第六十五条" and "过分高于" in item.get("content", "") for item in articles)
