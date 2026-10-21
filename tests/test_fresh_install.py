# -*- coding: utf-8 -*-
"""S-03 / A-11：空目录全新安装自动建库；演示种子默认关闭。"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


AUTH = {"X-LawFlow-Token": "test-token"}


def test_fresh_install_creates_dbs_and_overview(tmp_path, monkeypatch):
    monkeypatch.setenv("LAWFLOW_STORAGE_DIR", str(tmp_path))
    monkeypatch.delenv("LAWFLOW_SEED_DEMO", raising=False)
    monkeypatch.setenv("LAWFLOW_API_TOKEN", "test-token")

    from gateway.main import app

    with TestClient(app, headers=AUTH) as client:
        assert (tmp_path / "cn_laws_kb.db").exists()
        assert (tmp_path / "matter_vault.db").exists()
        resp = client.get("/api/v1/statutes/overview")
        assert resp.status_code == 200


def test_no_demo_seed_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("LAWFLOW_STORAGE_DIR", str(tmp_path))
    monkeypatch.delenv("LAWFLOW_SEED_DEMO", raising=False)
    monkeypatch.setenv("LAWFLOW_API_TOKEN", "test-token")

    from gateway.main import app

    with TestClient(app, headers=AUTH) as client:
        matters = client.get("/api/v1/vault/matters")
        assert matters.status_code == 200
        body = matters.json()
        items = body.get("matters") or body.get("data") or body
        if isinstance(items, dict):
            items = items.get("matters") or items.get("items") or []
        assert items == [] or len(items) == 0

        registry = client.get("/api/v1/conflict/registry")
        assert registry.status_code == 200
        reg = registry.json()
        assert (reg.get("count") or 0) == 0 or (reg.get("registry") or []) == []


def test_demo_seed_and_delete(tmp_path, monkeypatch):
    monkeypatch.setenv("LAWFLOW_STORAGE_DIR", str(tmp_path))
    monkeypatch.setenv("LAWFLOW_SEED_DEMO", "1")
    monkeypatch.setenv("LAWFLOW_API_TOKEN", "test-token")

    from gateway.main import app
    from gateway.seed_demo import seed_all_demo_data

    with TestClient(app, headers=AUTH) as client:
        # 显式灌种（避免同进程内“已种子”标志挡住新 tmp 目录）
        seed_all_demo_data()

        matters = client.get("/api/v1/vault/matters").json()
        items = matters.get("matters") or matters.get("data") or []
        if isinstance(items, dict):
            items = items.get("matters") or []
        assert len(items) >= 1
        assert any("【演示】" in (m.get("title") or "") for m in items)

        registry = client.get("/api/v1/conflict/registry").json()
        regs = registry.get("registry") or []
        assert len(regs) >= 1
        assert any("【演示】" in (r.get("case_title") or "") for r in regs)

        deleted = client.delete("/api/v1/vault/demo-data")
        assert deleted.status_code == 200

        matters2 = client.get("/api/v1/vault/matters").json()
        items2 = matters2.get("matters") or matters2.get("data") or []
        if isinstance(items2, dict):
            items2 = items2.get("matters") or []
        assert all("【演示】" not in (m.get("title") or "") for m in items2)

        registry2 = client.get("/api/v1/conflict/registry").json()
        regs2 = registry2.get("registry") or []
        assert all("【演示】" not in (r.get("case_title") or "") for r in regs2)
