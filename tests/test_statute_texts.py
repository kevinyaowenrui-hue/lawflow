# -*- coding: utf-8 -*-
"""批次4 S-06：法条核验状态、占位正文与 Citation Guard 黄标。"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from gateway.core.db import connect
from gateway.core.paths import get_laws_db_path
from gateway.utils.citation_guard import audit_citations_in_text
from gateway.utils.legal_data import clear_legal_data_cache, load_seed_articles_bundle
from gateway.utils.statute_db import init_statute_database


PLACEHOLDER = "【待律师按官方原文录入】"

PENDING_KEYS = [
    ("contract_interp_2023", 64),
    ("contract_interp_2023", 65),
    ("contract_interp_2023", 66),
    ("guarantee_interp_2021", 25),
    ("guarantee_interp_2021", 26),
    ("guarantee_interp_2021", 32),
    ("private_lending_2020", 25),
    ("private_lending_2020", 28),
    ("private_lending_2020", 29),
    ("civil_code_2021", 694),
]


@pytest.fixture
def isolated_laws_db(tmp_path, monkeypatch):
    monkeypatch.setenv("LAWFLOW_STORAGE_DIR", str(tmp_path))
    clear_legal_data_cache()
    init_statute_database(force_reseed=True)
    yield tmp_path
    clear_legal_data_cache()


def test_verified_articles_have_verified_at_and_by(isolated_laws_db):
    with connect(get_laws_db_path(), row_factory=sqlite3.Row) as conn:
        rows = conn.execute(
            "SELECT id, verification_status, verified_at, verified_by FROM articles WHERE verification_status = 'VERIFIED'"
        ).fetchall()
    assert rows, "应存在 VERIFIED 条目"
    for r in rows:
        assert r["verified_at"], f"{r['id']} 缺少 verified_at"
        assert r["verified_by"], f"{r['id']} 缺少 verified_by"


def test_critical_articles_are_pending_with_placeholder(isolated_laws_db):
    with connect(get_laws_db_path(), row_factory=sqlite3.Row) as conn:
        for law_id, art_no in PENDING_KEYS:
            row = conn.execute(
                "SELECT content, verification_status FROM articles WHERE law_id = ? AND article_no_int = ?",
                (law_id, art_no),
            ).fetchone()
            assert row is not None, f"缺少 {law_id} 第{art_no}条"
            assert row["verification_status"] == "PENDING_HUMAN"
            assert PLACEHOLDER in (row["content"] or "")


def test_contract_interp_66_not_deposit_choice(isolated_laws_db):
    with connect(get_laws_db_path(), row_factory=sqlite3.Row) as conn:
        row = conn.execute(
            "SELECT content FROM articles WHERE law_id = 'contract_interp_2023' AND article_no_int = 66"
        ).fetchone()
    assert row is not None
    assert "违约金与定金择一" not in (row["content"] or "")
    assert "定金" not in (row["content"] or "") or PLACEHOLDER in row["content"]


def test_audit_contract_interp_66_pending_verification(isolated_laws_db):
    res = audit_citations_in_text(
        raw_text="依据《合同编通则解释》第六十六条",
        auto_sanitize=False,
    )
    assert res["citations"], "应解析到引用"
    cit = res["citations"][0]
    assert cit["status"] == "PENDING_VERIFICATION"
    assert cit.get("risk_level") != "SAFE"
    # 徽章不得为绿
    badge = res.get("badge_label") or res.get("overall_badge") or ""
    overall = res.get("overall_status") or ""
    assert "绿" not in badge
    assert overall != "LOCAL_MATCH_PASSED" or cit["status"] == "PENDING_VERIFICATION"


def test_seed_json_has_verification_fields():
    clear_legal_data_cache()
    bundle = load_seed_articles_bundle()
    assert "version_note" in bundle["laws"][0] or any("version_note" in l for l in bundle["laws"])
    art = bundle["articles"][0]
    for key in ("verification_status", "source_url", "verified_at", "verified_by", "review_note"):
        assert key in art, f"seed article 缺少字段 {key}"
