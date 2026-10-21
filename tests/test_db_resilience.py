# -*- coding: utf-8 -*-
"""S-14：写库异常不锁库；利冲异常不得返回 CLEAR。"""
from __future__ import annotations

import sqlite3
import time

import pytest


def test_statutes_link_missing_ids_not_500_and_no_lock(client):
    resp = client.post(
        "/api/v1/statutes/link",
        json={
            "parent_article_id": "nope",
            "child_article_id": "nope2",
            "relation_type": "x",
        },
    )
    assert resp.status_code in (404, 422), resp.text

    t0 = time.perf_counter()
    guard = client.post(
        "/api/v1/guard/verify-case-number",
        json={"case_number": "（2023）最高法民终123号"},
    )
    elapsed = time.perf_counter() - t0
    assert guard.status_code == 200, guard.text
    assert elapsed < 1.0, f"可能仍锁库，耗时 {elapsed:.2f}s"


def test_conflict_check_unable_when_db_locked(client, monkeypatch):
    import gateway.utils.conflict_checker as cc

    def boom(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(cc, "get_db_connection", boom)

    resp = client.post(
        "/api/v1/conflict/check",
        json={
            "client_name": "甲公司",
            "opposing_party": "乙公司",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    text = resp.text
    assert data.get("verdict") == "UNABLE_TO_CHECK"
    assert "CLEAR" not in text
    assert "clearance_certificate" not in data or data.get("clearance_certificate") in (None, {})
    assert "certificate" not in text.lower() or "无法" in (data.get("message") or "")


def test_conflict_register_returns_503_when_db_locked(client, monkeypatch):
    import gateway.utils.conflict_checker as cc

    def boom(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(cc, "get_db_connection", boom)

    resp = client.post(
        "/api/v1/conflict/register-case",
        json={
            "case_name": "测试案",
            "case_no": "TEST-LOCK-001",
            "client_name": "甲",
            "opposing_party": "乙",
        },
    )
    assert resp.status_code == 503, resp.text
