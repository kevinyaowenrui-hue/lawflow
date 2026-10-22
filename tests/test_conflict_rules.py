# -*- coding: utf-8 -*-
"""批次10 I-14：利冲三类定性与 rule_basis 规范。"""
from __future__ import annotations

import json

import pytest


def test_retainer_opposing_is_waivable_with_consent(client):
    """常年顾问单位作为对方当事人 → WAIVABLE_WITH_CONSENT，须取得同意。"""
    resp = client.post(
        "/api/v1/conflict/check",
        json={
            "client_name": "北京知客云服科技有限公司",
            "opposing_party": "北京宏达商贸有限公司",
            "case_subject": "技术合同尾款争议",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["conflict_level"] == "WAIVABLE_WITH_CONSENT"
    assert data["requires_consent"] is True
    assert "须书面告知" in (data.get("consent_note") or "")
    assert data["has_conflict"] is True


def test_dual_clients_is_prohibited(client):
    """双方当事人均为我所客户 → PROHIBITED（不得代理）。"""
    resp = client.post(
        "/api/v1/conflict/check",
        json={
            "client_name": "李四",
            "opposing_party": "智科云服信息技术（北京）有限公司",
            "case_subject": "合同纠纷",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["conflict_level"] == "PROHIBITED"
    assert data["has_conflict"] is True


def test_rule_basis_no_item_refs_and_todo_unverified(client):
    resp = client.post(
        "/api/v1/conflict/check",
        json={
            "client_name": "北京知客云服科技有限公司",
            "opposing_party": "北京宏达商贸有限公司",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    blob = json.dumps(data, ensure_ascii=False)
    assert "第(三)项" not in blob
    assert "第（三）项" not in blob
    assert "顶格" not in blob

    for item in data.get("conflict_items") or []:
        basis = item.get("rule_basis") or ""
        assert "《律师法》第三十九条" in basis
        if "TODO(律师核实)" in basis:
            assert item.get("rule_verified") is False
        assert "第五十条" not in basis
        assert "第五十一条" not in basis
        assert "第四十九条" not in basis


def test_batch2_locked_db_still_not_clear(client, monkeypatch):
    """批次2：锁库时不得返回 CLEAR —— 回归。"""
    import sqlite3
    import gateway.utils.conflict_checker as cc

    def boom(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(cc, "get_db_connection", boom)
    resp = client.post(
        "/api/v1/conflict/check",
        json={"client_name": "甲公司", "opposing_party": "乙公司"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data.get("verdict") == "UNABLE_TO_CHECK"
    assert data.get("conflict_level") == "UNABLE_TO_CHECK"
    assert "CLEAR" not in resp.text
