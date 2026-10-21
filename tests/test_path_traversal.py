# -*- coding: utf-8 -*-
"""S-04 路径穿越 / 上传大小与魔数校验验收。"""
from __future__ import annotations

import io
import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("LAWFLOW_API_TOKEN", "test-token")

from gateway.main import app

AUTH = {"X-LawFlow-Token": os.environ["LAWFLOW_API_TOKEN"]}
BASE_DIR = Path(__file__).resolve().parents[1]
GENERATED = BASE_DIR / "storage" / "generated"


@pytest.fixture
def authed():
    with TestClient(app, headers=AUTH) as c:
        yield c


def test_appeal_export_docx_stays_in_generated(authed):
    before_root = {p.name for p in BASE_DIR.iterdir() if p.name.startswith("PWNED")}
    parent = BASE_DIR.parent
    before_parent = {p.name for p in parent.iterdir() if p.name.startswith("PWNED")} if parent.exists() else set()
    stamp = time.time()

    resp = authed.post(
        "/api/v1/litigation/appeal-export-docx",
        json={"title": "../../PWNED_appeal", "content_text": "x"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    filename = data["filename"]
    assert ".." not in filename
    assert "/" not in filename and "\\" not in filename
    fpath = GENERATED / filename
    assert fpath.is_file(), f"期望生成于 storage/generated: {fpath}"

    after_root = {p.name for p in BASE_DIR.iterdir() if p.name.startswith("PWNED")}
    after_parent = {p.name for p in parent.iterdir() if p.name.startswith("PWNED")} if parent.exists() else set()
    assert after_root == before_root
    assert after_parent == before_parent
    # 清理本测试产物
    try:
        if fpath.exists() and fpath.stat().st_mtime >= stamp - 1:
            fpath.unlink()
    except Exception:
        pass


@pytest.mark.parametrize(
    "pdf_filename",
    ["../../outside.pdf", "/etc/passwd", "..\\..\\x.pdf"],
)
def test_redact_sensitive_rejects_path_traversal(authed, pdf_filename):
    resp = authed.post(
        "/api/v1/phase2/redact-sensitive",
        json={"pdf_filename": pdf_filename, "redact_idcard": True, "redact_bankcard": True},
    )
    assert resp.status_code == 400


def test_export_redline_rejects_server_path(authed):
    resp = authed.post(
        "/api/v1/phase2/contract-review/export-redline",
        json={
            "contract_title": "t",
            "contract_text": "第一条 测试",
            "source_docx_path": "/etc/passwd",
        },
    )
    assert resp.status_code == 400
    assert "路径" in resp.text or "上传" in resp.text or "source" in resp.text.lower()


@pytest.mark.parametrize(
    "path",
    [
        "/api/documents/download/..%5C..%5C.env",
        "/api/documents/download/..%2F..%2F.env",
    ],
)
def test_download_rejects_traversal(authed, path):
    resp = authed.get(path)
    assert resp.status_code in (400, 404)
    # 绝不能把 .env 内容返回
    body = resp.content
    assert b"LAWFLOW" not in body or resp.status_code != 200
    assert resp.status_code != 200


def test_upload_oversize_returns_413(authed, monkeypatch):
    monkeypatch.setenv("LAWFLOW_MAX_UPLOAD_MB", "50")
    # 51MB 伪 PDF
    payload = b"%PDF-1.4\n" + (b"x" * (51 * 1024 * 1024))
    files = {"files": ("big.pdf", io.BytesIO(payload), "application/pdf")}
    resp = authed.post(
        "/api/v1/phase2/process-evidence",
        data={"evidence_label": "证据1"},
        files=files,
    )
    assert resp.status_code == 413


def test_upload_wrong_magic_returns_415(authed):
    fake = b"this is not a pdf file at all"
    files = {"files": ("spoof.pdf", io.BytesIO(fake), "application/pdf")}
    resp = authed.post(
        "/api/v1/phase2/process-evidence",
        data={"evidence_label": "证据1"},
        files=files,
    )
    assert resp.status_code == 415
