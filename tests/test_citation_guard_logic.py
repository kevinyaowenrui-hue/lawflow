# -*- coding: utf-8 -*-
"""批次3：Citation Guard 判定逻辑与法律数据单一来源。"""
from __future__ import annotations

import json
import re

import pytest

from gateway.utils.citation_guard import (
    audit_case_numbers,
    audit_citations_in_text,
    normalize_law_name,
)
from gateway.utils.cn_legal_calc import verify_statutory_validity
from gateway.utils.legal_texts import CIVIL_CODE_TIME_EFFECT_ART1_PARA2
from gateway.utils.statute_db import init_statute_database
from gateway.core.paths import get_laws_db_path
from gateway.core.db import connect
import sqlite3


def test_normalize_law_name_strips_prefix_and_marks():
    assert normalize_law_name("《中华人民共和国劳动合同法》") == "劳动合同法"
    assert normalize_law_name("中华人民共和国合同法") == "合同法"


def test_adoption_law_abrogated_blocked():
    res = audit_citations_in_text(raw_text="依据《收养法》第一条", auto_sanitize=False)
    assert res["citations"][0]["status"] == "ABROGATED_BLOCKED"


def test_private_lending_old_rate_yellow_hint():
    res = audit_citations_in_text(
        raw_text="双方约定年利率24%，依据《民间借贷规定》第二十五条。",
        auto_sanitize=False,
    )
    joined = " ".join(res.get("warnings") or [])
    assert "2020年修正前的民间借贷利率口径" in joined
    assert res["overall_status"] in ("PARTIALLY_VERIFIED", "ABROGATED_INTERCEPTED", "LOCAL_MATCH_PASSED")


def test_case_number_structure_only_unverified():
    cases = audit_case_numbers("参照（2025）京0105民初12345号判决")
    assert len(cases) >= 1
    assert cases[0]["status"] == "STRUCTURE_ONLY_UNVERIFIED"


def test_output_json_no_forbidden_phrases():
    res = audit_citations_in_text(
        raw_text="依据《民法典》第五百八十五条，并参照（2025）京0105民初12345号。",
        auto_sanitize=False,
    )
    blob = json.dumps(res, ensure_ascii=False)
    assert "零幻觉" not in blob
    assert "验真通过" not in blob


def test_s18_contract_vs_labor_contract():
    bad = verify_statutory_validity("依据《合同法》第一百一十四条")
    assert bad["is_safe"] is False
    good = verify_statutory_validity("《劳动合同法》第十条与《民法典》第五百八十五条")
    assert good["is_safe"] is True


def test_s19_sanitize_with_incident_date_once():
    text = "依据《合同法》第一百一十四条主张违约金。"
    res = audit_citations_in_text(
        raw_text=text, auto_sanitize=True, incident_date="2022-03-01"
    )
    assert "第五百八十五条" in res["sanitized_text"]
    assert res["sanitized_text"].count("第五百八十五条") == 1
    assert "合同法" not in res["sanitized_text"]


def test_s19_no_replace_labor_contract_114_lookalike():
    # 定点替换：不得因全文 replace 把《劳动合同法》第一百一十四条误换成民法典585
    text = "另依《劳动合同法》第一百一十四条；又依《合同法》第一百一十四条。"
    res = audit_citations_in_text(
        raw_text=text, auto_sanitize=True, incident_date="2022-03-01"
    )
    assert "《合同法》第一百一十四条" not in res["sanitized_text"]
    # 劳动合同法条目不得被映射为民法典第五百八十五条（定点替换）
    assert "《中华人民共和国民法典》第五百八十五条" in res["sanitized_text"]
    assert res["sanitized_text"].count("第五百八十五条") == 1
    labor_cit = [c for c in res["citations"] if c.get("law_name") == "劳动合同法"]
    assert labor_cit
    assert labor_cit[0].get("sanitized_to") != "《中华人民共和国民法典》第五百八十五条"
    assert labor_cit[0].get("status") != "ABROGATED_BLOCKED"


def test_a01_statute_max_versions():
    r307 = audit_citations_in_text(
        raw_text="依据《民事诉讼法》第三百零七条", auto_sanitize=False
    )
    assert r307["citations"][0]["status"] == "HALLUCINATION_EXCEEDED"

    r74 = audit_citations_in_text(
        raw_text="依据《个人信息保护法》第七十四条", auto_sanitize=False
    )
    assert r74["citations"][0]["status"] != "HALLUCINATION_EXCEEDED"

    r41 = audit_citations_in_text(
        raw_text="依据《反不正当竞争法》第四十一条", auto_sanitize=False
    )
    assert r41["citations"][0]["status"] != "HALLUCINATION_EXCEEDED"


def test_a02_case_type_and_legacy():
    modern = audit_case_numbers("（2023）京0105民特12号")
    assert modern[0]["status"] == "STRUCTURE_ONLY_UNVERIFIED"
    legacy = audit_case_numbers("(2012)民提字第11号")
    assert legacy[0]["status"] == "STRUCTURE_ONLY_UNVERIFIED"
    assert "民提" in legacy[0]["standard_case_number"]


def test_a03_time_effect_quote_complete():
    res = verify_statutory_validity(
        "依据《合同法》第一百零七条", incident_date="2019-05-01"
    )
    assert "适用当时的法律、司法解释的规定" in res["time_validity_note"]
    assert CIVIL_CODE_TIME_EFFECT_ART1_PARA2 in res["time_validity_note"]


def test_a12_minfa_zongze_both_paths_abrogated():
    v = verify_statutory_validity("依据《民法总则》第一百八十八条")
    assert v["is_safe"] is False
    assert any("民法总则" in (x.get("keyword") or "") for x in v["detected_abrogated"])

    a = audit_citations_in_text(
        raw_text="依据《民法总则》第一百八十八条", auto_sanitize=False
    )
    assert a["citations"][0]["status"] == "ABROGATED_BLOCKED"


def test_a12_fresh_db_has_nine_abrogated():
    init_statute_database(force_reseed=True)
    with connect(get_laws_db_path(), row_factory=sqlite3.Row) as conn:
        rows = conn.execute("SELECT name FROM abrogated_laws").fetchall()
    names = {r["name"] for r in rows}
    required = {
        "合同法", "物权法", "担保法", "民法通则", "侵权责任法",
        "婚姻法", "继承法", "民法总则", "收养法",
    }
    assert required.issubset(names)


def test_no_substring_false_positive_in_gateway_strings():
    # 验收辅助：时间效力漏字旧文不应再出现
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "gateway"
    bad = "适用当时的法律规定"
    hits = []
    for p in root.rglob("*.py"):
        text = p.read_text(encoding="utf-8")
        if bad in text:
            hits.append(str(p))
    assert hits == []
