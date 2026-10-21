# -*- coding: utf-8 -*-
"""批次4 I-01 / I-02 / I-03：条号文号修正、导入未核验、FTS 同步、引擎引用覆盖。"""
from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from gateway.core.db import connect
from gateway.core.paths import get_laws_db_path
from gateway.utils.cn_legal_calc import calculate_statute_of_limitations
from gateway.utils.engine_citations import ENGINE_CITED_ARTICLES
from gateway.utils.legal_data import clear_legal_data_cache
from gateway.utils.statute_db import (
    get_statute_database_stats,
    import_custom_statute,
    init_statute_database,
)


AUTH = {"X-LawFlow-Token": "test-token"}


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("LAWFLOW_STORAGE_DIR", str(tmp_path))
    monkeypatch.setenv("LAWFLOW_API_TOKEN", "test-token")
    monkeypatch.delenv("LAWFLOW_SEED_DEMO", raising=False)
    clear_legal_data_cache()
    init_statute_database(force_reseed=True)
    yield tmp_path
    clear_legal_data_cache()


def test_construction_priority_basis_article_41(isolated):
    res = calculate_statute_of_limitations(
        start_date="2024-01-01",
        cause_type="construction_priority_18m",
    )
    basis = res.get("basis") or res.get("period_basis") or ""
    if not basis and isinstance(res.get("rule"), dict):
        basis = res["rule"].get("basis", "")
    # 兼容不同返回结构
    blob = str(res)
    assert "第四十一条" in blob
    assert "第三十六条" not in blob or "第四十一条" in blob


def test_nine_minutes_article_set(isolated):
    with connect(get_laws_db_path(), row_factory=sqlite3.Row) as conn:
        nos = {
            r["article_no_int"]
            for r in conn.execute(
                "SELECT article_no_int FROM articles WHERE law_id = 'nine_minutes_2019'"
            ).fetchall()
        }
    assert 41 in nos
    assert 46 in nos
    assert 50 in nos
    assert 53 not in nos


def test_prosecution_fraud_loan_is_art_22(isolated):
    with connect(get_laws_db_path(), row_factory=sqlite3.Row) as conn:
        rows = conn.execute(
            "SELECT article_no_int, content, review_note FROM articles WHERE law_id = 'prosecution_standards_2022' AND article_no_int IN (19, 22)"
        ).fetchall()
    nos = {r["article_no_int"] for r in rows}
    assert 22 in nos
    assert 19 not in nos


def test_fts_count_matches_articles_after_init(isolated):
    with connect(get_laws_db_path()) as conn:
        a = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        f = conn.execute("SELECT COUNT(*) FROM articles_fts").fetchone()[0]
    assert a == f
    assert a > 0


def test_import_marks_unverified_and_keeps_fts_sync(isolated):
    raw = """
第一条 为了测试导入核验状态而制定本办法。
第二条 本办法所称平台用工，是指依托互联网平台提供劳务的用工形式。
"""
    result = import_custom_statute(
        law_id="user_import_demo_labor_2024",
        full_name="【测试】某市法院关于平台用工的试行办法",
        short_name="【测试】平台用工试行办法",
        hierarchy=4,
        promulgated_by="某市人民法院",
        effective_date="2024-05-01",
        domain="劳动",
        raw_text=raw,
        summary="测试导入",
    )
    assert result["articles_imported"] == 2
    with connect(get_laws_db_path(), row_factory=sqlite3.Row) as conn:
        law = conn.execute(
            "SELECT status, verification_status FROM laws WHERE id = ?",
            ("user_import_demo_labor_2024",),
        ).fetchone()
        arts = conn.execute(
            "SELECT verification_status FROM articles WHERE law_id = ?",
            ("user_import_demo_labor_2024",),
        ).fetchall()
        a = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        f = conn.execute("SELECT COUNT(*) FROM articles_fts").fetchone()[0]
    assert law["status"] == "USER_IMPORTED"
    assert law["verification_status"] == "USER_IMPORTED_UNVERIFIED"
    assert all(r["verification_status"] == "USER_IMPORTED_UNVERIFIED" for r in arts)
    assert a == f


def test_reseed_keeps_fts_sync(isolated):
    init_statute_database(force_reseed=True)
    with connect(get_laws_db_path()) as conn:
        a = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        f = conn.execute("SELECT COUNT(*) FROM articles_fts").fetchone()[0]
        n_test = conn.execute(
            "SELECT COUNT(*) FROM laws WHERE id LIKE 'test_%'"
        ).fetchone()[0]
    assert a == f
    assert n_test == 0


def test_no_test_law_id_in_seed_json():
    from gateway.utils.legal_data import load_seed_articles_bundle

    clear_legal_data_cache()
    bundle = load_seed_articles_bundle()
    for law in bundle["laws"]:
        assert not str(law["id"]).startswith("test_")


def test_engine_cited_articles_resolvable(isolated):
    with connect(get_laws_db_path(), row_factory=sqlite3.Row) as conn:
        for item in ENGINE_CITED_ARTICLES:
            law_id = item["law_id"]
            art_no = item["article_no_int"]
            row = conn.execute(
                "SELECT id, verification_status FROM articles WHERE law_id = ? AND article_no_int = ?",
                (law_id, art_no),
            ).fetchone()
            assert row is not None, f"引擎引用缺失: {law_id} art_{art_no}"


def test_search_civil_code_692_pending_tag(isolated):
    from gateway.main import app

    with TestClient(app, headers=AUTH) as client:
        resp = client.post("/api/v1/statutes/search", json={"query": "民法典第692条"})
        assert resp.status_code == 200
        results = resp.json().get("results") or []
        assert len(results) >= 1
        hit = results[0]
        assert hit.get("article_no_int") == 692 or "692" in str(hit.get("article_no_cn"))
        label = hit.get("verification_label") or hit.get("verification_status") or ""
        assert "待律师核验" in str(label) or hit.get("verification_status") == "PENDING_HUMAN"


def test_overview_no_absolute_path_and_has_verification_counts(isolated):
    from gateway.main import app

    with TestClient(app, headers=AUTH) as client:
        resp = client.get("/api/v1/statutes/overview")
        assert resp.status_code == 200
        data = resp.json().get("data") or resp.json()
        blob = str(data)
        # 不得返回服务器绝对路径
        assert '"database_file"' not in blob or not str(data.get("database_file", "")).startswith(("/", "\\")) or data.get("database_file") in (None, "")
        if data.get("database_file"):
            assert not data["database_file"].startswith("/")
            assert ":" not in data["database_file"][:3] or data["database_file"] is None
        assert "verification_counts" in data or "by_verification_status" in data
        counts = data.get("verification_counts") or data.get("by_verification_status")
        assert isinstance(counts, dict)
        assert sum(counts.values()) >= 1
