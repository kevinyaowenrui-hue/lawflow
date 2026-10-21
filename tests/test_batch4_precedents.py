# -*- coding: utf-8 -*-
"""批次4 S-07：演示判例不得默认入库；文书不含未核验案号。"""
from __future__ import annotations

import os
import re
import sqlite3

import pytest

from gateway.core.db import connect
from gateway.core.paths import get_laws_db_path
from gateway.utils.appeal_and_precedent_engine import analyze_first_instance_judgment_and_precedents
from gateway.utils.citation_guard import CASE_NUMBER_PATTERN, LEGACY_CASE_NUMBER_PATTERN, ensure_court_precedents_table
from gateway.utils.legal_data import clear_legal_data_cache
from gateway.utils.statute_db import init_statute_database


def test_fresh_db_without_demo_has_empty_precedents(tmp_path, monkeypatch):
    monkeypatch.setenv("LAWFLOW_STORAGE_DIR", str(tmp_path))
    monkeypatch.delenv("LAWFLOW_SEED_DEMO", raising=False)
    clear_legal_data_cache()
    init_statute_database(force_reseed=True)
    with connect(get_laws_db_path(), row_factory=sqlite3.Row) as conn:
        ensure_court_precedents_table(conn)
        n = conn.execute("SELECT COUNT(*) AS c FROM court_precedents").fetchone()["c"]
    assert n == 0


def test_demo_mode_precedents_are_demo_flagged(tmp_path, monkeypatch):
    monkeypatch.setenv("LAWFLOW_STORAGE_DIR", str(tmp_path))
    monkeypatch.setenv("LAWFLOW_SEED_DEMO", "1")
    clear_legal_data_cache()
    init_statute_database(force_reseed=True)
    with connect(get_laws_db_path(), row_factory=sqlite3.Row) as conn:
        ensure_court_precedents_table(conn)
        rows = conn.execute("SELECT case_number, is_demo, source FROM court_precedents").fetchall()
    assert len(rows) >= 1
    for r in rows:
        assert int(r["is_demo"] or 0) == 1
        assert "演示" in (r["source"] or "")


def test_appeal_docs_contain_no_case_numbers_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("LAWFLOW_STORAGE_DIR", str(tmp_path))
    monkeypatch.delenv("LAWFLOW_SEED_DEMO", raising=False)
    clear_legal_data_cache()
    init_statute_database(force_reseed=True)

    res = analyze_first_instance_judgment_and_precedents()
    blob = (res.get("appellate_memo_report") or "") + "\n" + (res.get("appellate_pleading_text") or "")
    modern = list(CASE_NUMBER_PATTERN.finditer(blob))
    legacy = list(LEGACY_CASE_NUMBER_PATTERN.finditer(blob))
    assert len(modern) + len(legacy) == 0
    assert res.get("total_pro_precedents", 0) == 0
    assert "本地无已核验类案" in blob or "【类案案号待律师核验后填写】" in blob


def test_demo_precedents_not_written_into_pleadings(tmp_path, monkeypatch):
    monkeypatch.setenv("LAWFLOW_STORAGE_DIR", str(tmp_path))
    monkeypatch.setenv("LAWFLOW_SEED_DEMO", "1")
    clear_legal_data_cache()
    init_statute_database(force_reseed=True)
    with connect(get_laws_db_path(), row_factory=sqlite3.Row) as conn:
        ensure_court_precedents_table(conn)

    res = analyze_first_instance_judgment_and_precedents()
    blob = (res.get("appellate_memo_report") or "") + "\n" + (res.get("appellate_pleading_text") or "")
    assert "最高法民终1067" not in blob
    assert "（2020）最高法民终1067号" not in blob
