# -*- coding: utf-8 -*-
"""I-24：CSP 响应头 + innerHTML 扫描纳入 CI；案件名 XSS 不污染列表渲染路径。"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("LAWFLOW_API_TOKEN", "test-token")
AUTH = {"X-LawFlow-Token": os.environ["LAWFLOW_API_TOKEN"]}
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def client():
    from gateway.main import app

    with TestClient(app, headers=AUTH) as c:
        yield c


def test_index_has_csp_header(client):
    resp = client.get("/")
    assert resp.status_code == 200
    csp = resp.headers.get("content-security-policy") or resp.headers.get("Content-Security-Policy")
    assert csp, "GET / 应返回 Content-Security-Policy"
    assert "default-src 'self'" in csp
    assert "object-src 'none'" in csp
    assert "base-uri 'self'" in csp
    assert "frame-ancestors 'none'" in csp


def test_check_innerhtml_script_exits_zero():
    script = ROOT / "scripts" / "check_innerhtml.py"
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr


def test_matter_list_keeps_raw_title_api_uses_escapeHtml_in_grid(client):
    """案件名称含 XSS 载荷时，列表接口仍返回原值；前端 renderMattersGrid 使用 escapeHtml。"""
    xss_title = '<img src=x onerror=alert(1)>'
    create = client.post(
        "/api/v1/vault/matters",
        json={
            "title": xss_title,
            "cause_of_action": "民间借贷纠纷",
            "plaintiff_name": "甲",
            "defendant_name": "乙",
        },
    )
    assert create.status_code == 200, create.text
    matter = create.json().get("matter") or create.json()
    assert xss_title in (matter.get("title") or "")

    listing = client.get("/api/v1/vault/matters")
    assert listing.status_code == 200
    titles = [m.get("title") for m in listing.json().get("matters", [])]
    assert xss_title in titles

    matters_file = ROOT / "frontend" / "js" / "modules" / "07_matters.js"
    source = matters_file.read_text(encoding="utf-8") if matters_file.exists() else (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    needle = "function renderMattersGrid"
    idx = source.find(needle)
    assert idx >= 0
    line_no = source[:idx].count("\n") + 1
    grid_fn = source[idx : idx + 2500]
    assert "escapeHtml(m.title)" in grid_fn
    # 供汇报引用
    print(f"renderMattersGrid starts at line {line_no} of {matters_file.name}; uses escapeHtml(m.title)")


def test_check_fetch_script_exits_zero():
    """批次 17 A-09：除 api.js 外不得直接出现 fetch(。"""
    script = ROOT / "scripts" / "check_fetch.py"
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr


def test_check_a11y_script_exits_zero():
    """批次 17 A-10：无障碍静态扫描通过。"""
    script = ROOT / "scripts" / "check_a11y.py"
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr


def test_frontend_index_line_count_and_csp(client):
    """批次 17 A-09 验收：index.html 行数 < 1,500，且 CSP script-src 不含 'unsafe-inline'。"""
    index_html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    line_count = len(index_html.splitlines())
    assert line_count < 1500, f"frontend/index.html 行数必须 < 1,500，当前为 {line_count}"

    resp = client.get("/")
    assert resp.status_code == 200
    csp = resp.headers.get("content-security-policy") or resp.headers.get("Content-Security-Policy") or ""
    assert "script-src 'self'" in csp
    assert "script-src 'self' 'unsafe-inline'" not in csp
