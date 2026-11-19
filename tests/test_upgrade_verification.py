# -*- coding: utf-8 -*-
"""
验证五大升级步骤的自动化测试用例
"""
import json
import sqlite3
from pathlib import Path
from gateway.core.paths import get_laws_db_path
from gateway.core.db import connect
from gateway.utils.statute_db import init_statute_database
from gateway.utils.citation_guard import verify_single_citation
from gateway.utils.legal_data import clear_legal_data_cache
from gateway.utils.cn_legal_calc import (
    calculate_private_lending_segmented_interest,
    calculate_statute_of_limitations,
    is_prc_non_working_day,
    calculate_court_fees,
    get_provincial_income_baseline,
    PROVINCIAL_INCOME_BASELINES_2025_2026,
)
from gateway.utils.ics_deadline_exporter import build_lawyer_deadline_ics


def test_seed_articles_no_pending_and_no_placeholders():
    root = Path(__file__).resolve().parents[1]
    seed_path = root / "data" / "legal" / "seed_articles.json"
    bundle = json.loads(seed_path.read_text(encoding="utf-8"))
    
    pending = [a for a in bundle["articles"] if a.get("verification_status") == "PENDING_HUMAN"]
    raw_json = json.dumps(bundle, ensure_ascii=False)
    placeholder_count = raw_json.count("【待律师按官方原文录入】")
    
    assert len(pending) == 0, f"仍存在待核验条目: {len(pending)}"
    assert placeholder_count == 0, f"仍存在占位符: {placeholder_count}"


def test_laws_db_citations_and_verifications():
    clear_legal_data_cache()
    init_statute_database(force_reseed=True)

    with connect(get_laws_db_path(), row_factory=sqlite3.Row) as conn:
        row692 = conn.execute(
            "SELECT content, verification_status FROM articles WHERE law_id = 'civil_code_2021' AND article_no_int = 692"
        ).fetchone()
        assert row692 is not None
        assert row692["verification_status"] == "VERIFIED"
        assert "保证期间是确定保证人承担保证责任的期间" in row692["content"]

        row88 = conn.execute(
            "SELECT content, verification_status FROM articles WHERE law_id = 'company_law_2024' AND article_no_int = 88"
        ).fetchone()
        assert row88 is not None
        assert row88["verification_status"] == "VERIFIED"
        assert "股东转让已认缴出资但未届出资期限的股权的" in row88["content"]

    c1 = verify_single_citation("《民法典》", 692)
    assert c1["is_valid"] is True
    assert c1["audit_status"] == "LOCAL_MATCH"
    assert "保证期间是确定保证人承担保证责任的期间" in c1["article_content"]

    c2 = verify_single_citation("《新公司法》", 88)
    assert c2["is_valid"] is True
    assert c2["audit_status"] == "LOCAL_MATCH"
    assert "股东转让已认缴出资但未届出资期限的股权的" in c2["article_content"]


def test_makeup_workdays_and_holidays():
    assert is_prc_non_working_day("2024-02-04") is False  # 2024春节调休上班（周日）
    assert is_prc_non_working_day("2024-02-10") is True   # 2024春节法定假日
    assert is_prc_non_working_day("2025-01-26") is False  # 2025春节调休上班（周日）
    assert is_prc_non_working_day("2025-01-29") is True   # 2025春节法定假日
    assert is_prc_non_working_day("2026-01-04") is False  # 2026元旦调休上班（周日）
    assert is_prc_non_working_day("2026-01-01") is True   # 2026元旦法定假


def test_private_lending_segmented_calculation():
    # 跨期计算：2019-01-01 至 2021-01-01
    res = calculate_private_lending_segmented_interest(
        principal=100000.0,
        start_date="2019-01-01",
        end_date="2021-01-01",
        agreed_annual_rate=0.20,
        filing_date_lpr_1y=0.0345,
        include_delayed_performance_days=10,
    )
    assert len(res["segments"]) == 2
    assert res["delayed_performance_days"] == 10
    assert res["delayed_performance_interest"] > 0
    assert "【民间借贷分段利息计算明细说明】" in res["calculation_explanation_text"]
    assert res["total_claim_amount"] > 100000


def test_court_fees_reductions():
    res_summary = calculate_court_fees(100000, is_summary_procedure=True)
    assert res_summary["is_half_fee"] is True
    assert res_summary["actual_fee"] == res_summary["standard_fee"] / 2

    res_med = calculate_court_fees(100000, is_mediation_or_withdrawal=True)
    assert res_med["is_half_fee"] is True
    assert res_med["actual_fee"] == res_med["standard_fee"] / 2

    res_counter = calculate_court_fees(100000, is_counterclaim=True)
    assert res_counter["is_half_fee"] is True
    assert res_counter["actual_fee"] == res_counter["standard_fee"] / 2


def test_provincial_baselines():
    bj = get_provincial_income_baseline("北京市")
    assert bj is not None
    assert bj["monthly_three_times_cap"] == 33894.0
    assert bj["cap_allowed"] is False
    assert bj["verified"] is False

    sh = get_provincial_income_baseline("上海")
    assert sh is not None
    assert sh["monthly_three_times_cap"] == 36921.0


def test_ics_exporter():
    events = [
        {
            "title": "【上诉期届满提醒】(2026)京01民初123号",
            "deadline": "2026-05-15",
            "description": "判决书上诉期届满，请递交上诉状",
            "location": "北京市第一中级人民法院",
        }
    ]
    ics = build_lawyer_deadline_ics(events, calendar_name="智律办案测试")
    assert "BEGIN:VCALENDAR" in ics
    assert "VERSION:2.0" in ics
    assert "TRIGGER:-PT24H" in ics
    assert "PT9H" in ics
    assert "END:VCALENDAR" in ics

def test_spc_element_complaint_endpoint():
    from fastapi.testclient import TestClient
    from gateway.main import app

    client = TestClient(app, headers={"X-LawFlow-Token": "test-token"})
    resp = client.post("/api/v1/phase1/generate-spc-element-complaint")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "success"
    assert "最高法要素式起诉状_民间借贷示范文本" in data["filename"]
    assert data["download_url"].startswith("/api/documents/download/")
    assert data["file_size"] > 1000
    assert "法〔2024〕46号" in data["standard_basis"]


def test_private_lending_after_pivot_uses_contract_lpr_not_default_three_percent():
    res = calculate_private_lending_segmented_interest(
        principal=100000.0,
        start_date="2024-01-01",
        end_date="2025-01-01",
        agreed_annual_rate=0.24,
    )
    assert abs(res["four_times_lpr"] - 0.12) > 0.001
    text = res["calculation_explanation_text"]
    assert "合同成立时" in text
    assert "起诉时" not in text


def test_private_lending_before_pivot_does_not_default_to_three_percent():
    try:
        calculate_private_lending_segmented_interest(
            principal=100000.0,
            start_date="2019-01-01",
            end_date="2021-01-01",
            agreed_annual_rate=0.20,
        )
    except ValueError as exc:
        assert "不能默认按3%" in str(exc)
    else:
        raise AssertionError("缺起诉日利率时不应按3%算出结果")


def test_expired_limitation_does_not_say_right_to_win_is_lost():
    ordinary = calculate_statute_of_limitations(
        "2020-01-01", "general_3y", today_date="2026-01-01"
    )
    assert "胜诉权" not in ordinary["risk_alert"]
    assert "债权本身不消灭" in ordinary["risk_alert"]

    preclusive = calculate_statute_of_limitations(
        "2026-01-01", "guarantee_general_6m", today_date="2026-10-01"
    )
    assert "胜诉权" not in preclusive["risk_alert"]
    assert "除斥期间" in preclusive["risk_alert"]
    assert "催告都不能" in preclusive["risk_alert"] or "都不能让这个期间重新计算" in preclusive["risk_alert"]
