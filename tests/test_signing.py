# -*- coding: utf-8 -*-
"""S-13 电子签约：演示标识、webhook 鉴权、真实哈希、持久化、XSS。"""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("LAWFLOW_API_TOKEN", "test-token")
os.environ.setdefault("LAWFLOW_ALLOWED_HOSTS", "127.0.0.1,localhost,testserver")

AUTH = {"X-LawFlow-Token": os.environ["LAWFLOW_API_TOKEN"]}
DEMO_NOTICE = "演示模式：未接入真实电子签名服务，签署结果不具有法律效力"
CREATE_PAYLOAD = {
    "agreement_title": "民事委托代理协议及诉讼风险告知书",
    "client_name": "测试委托人",
    "client_phone": "13800138000",
    "lawyer_name": "测试律师",
    "law_firm": "测试律师事务所",
    "service_fee": 10000.0,
    "case_summary": "测试事由",
}


@pytest.fixture
def signing_env(tmp_path, monkeypatch):
    """独立临时 storage；默认无 DocuSeal、无 webhook secret。"""
    monkeypatch.setenv("LAWFLOW_STORAGE_DIR", str(tmp_path))
    monkeypatch.setenv("LAWFLOW_PUBLIC_BASE_URL", "http://127.0.0.1:5221")
    monkeypatch.setenv("DOCUSEAL_URL", "")
    monkeypatch.delenv("DOCUSEAL_WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("DOCUSEAL_WEBHOOK_HEADER", raising=False)
    # 确保模块级缓存不会干扰
    import gateway.routers.phase3_rag_sign as sign_mod

    if hasattr(sign_mod, "SIGNING_STORAGE"):
        sign_mod.SIGNING_STORAGE.clear()
    yield tmp_path


@pytest.fixture
def authed(signing_env):
    from gateway.main import app

    with TestClient(app, headers=AUTH) as c:
        yield c


@pytest.fixture
def bare(signing_env):
    from gateway.main import app

    with TestClient(app) as c:
        yield c


def _webhook_headers(secret: str = "test-webhook-secret", header: str = "X-LawFlow-Webhook-Secret"):
    return {header: secret, "Content-Type": "application/json"}


def test_a_webhook_without_secret_returns_503(authed):
    resp = authed.post(
        "/api/v1/phase3/signing-webhook",
        json={"envelope_id": "ds-nonexistent"},
    )
    assert resp.status_code == 503, resp.text
    assert "webhook 未启用" in resp.text


def test_b_webhook_auth_and_missing_envelope(authed, monkeypatch):
    monkeypatch.setenv("DOCUSEAL_WEBHOOK_SECRET", "test-webhook-secret")

    created = authed.post("/api/v1/phase3/create-signing-link", json=CREATE_PAYLOAD)
    assert created.status_code == 200, created.text
    envelope_id = created.json()["envelope_id"]
    assert created.json()["envelope"]["status"] == "pending_signature"

    # 无头 → 401
    r1 = authed.post(
        "/api/v1/phase3/signing-webhook",
        json={"envelope_id": envelope_id},
    )
    assert r1.status_code == 401, r1.text

    # 错误头 → 401
    r2 = authed.post(
        "/api/v1/phase3/signing-webhook",
        headers=_webhook_headers("wrong-secret"),
        json={"envelope_id": envelope_id},
    )
    assert r2.status_code == 401, r2.text

    # 正确头 + 非法 JSON → 400
    r3 = authed.post(
        "/api/v1/phase3/signing-webhook",
        headers=_webhook_headers(),
        content=b"not json",
    )
    assert r3.status_code == 400, r3.text

    # 正确头 + 不存在的 envelope_id → 404，已有信封状态不变
    r4 = authed.post(
        "/api/v1/phase3/signing-webhook",
        headers=_webhook_headers(),
        json={"envelope_id": "ds-does-not-exist"},
    )
    assert r4.status_code == 404, r4.text

    from gateway.routers.phase3_rag_sign import get_signing_envelope

    row = get_signing_envelope(envelope_id)
    assert row is not None
    assert row["status"] == "pending_signature"


def test_c_webhook_completes_with_real_file_sha256(authed, monkeypatch):
    monkeypatch.setenv("DOCUSEAL_WEBHOOK_SECRET", "test-webhook-secret")

    created = authed.post("/api/v1/phase3/create-signing-link", json=CREATE_PAYLOAD)
    assert created.status_code == 200, created.text
    envelope_id = created.json()["envelope_id"]

    resp = authed.post(
        "/api/v1/phase3/signing-webhook",
        headers=_webhook_headers(),
        json={"envelope_id": envelope_id},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data.get("status") in ("success", "completed") or data.get("envelope_status") == "completed"
    file_sha256 = data["file_sha256"]
    assert file_sha256 and not file_sha256.startswith("SHA256:")
    assert "uuid" not in file_sha256.lower()

    from gateway.routers.phase3_rag_sign import get_signing_envelope

    row = get_signing_envelope(envelope_id)
    assert row["status"] == "completed"
    assert row["file_path"]
    assert Path(row["file_path"]).is_file()
    expected = hashlib.sha256(Path(row["file_path"]).read_bytes()).hexdigest()
    assert file_sha256 == expected
    assert row["file_sha256"] == expected


def test_d_signing_url_uses_public_base_not_8000(authed, monkeypatch):
    monkeypatch.setenv("LAWFLOW_PUBLIC_BASE_URL", "http://127.0.0.1:5221")
    resp = authed.post("/api/v1/phase3/create-signing-link", json=CREATE_PAYLOAD)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    url = data["signing_url"]
    assert url.startswith("http://127.0.0.1:5221")
    assert ":8000" not in url
    assert data.get("is_demo") is True
    assert data.get("mode") == "demo"
    assert DEMO_NOTICE in (data.get("demo_notice") or data.get("message") or "") or DEMO_NOTICE in str(data)


def test_e_sign_view_xss_and_view_token(authed, bare):
    payload = dict(CREATE_PAYLOAD)
    payload["client_name"] = "<script>alert(1)</script>"
    created = authed.post("/api/v1/phase3/create-signing-link", json=payload)
    assert created.status_code == 200, created.text
    data = created.json()
    envelope_id = data["envelope_id"]
    signing_url = data["signing_url"]
    parsed = urlparse(signing_url)
    qs = parse_qs(parsed.query)
    view_token = (qs.get("view_token") or [None])[0]
    assert view_token

    ok = bare.get(f"/api/v1/phase3/sign-view/{envelope_id}?view_token={view_token}")
    assert ok.status_code == 200, ok.text
    html = ok.text
    assert "<script>alert(1)" not in html
    assert "&lt;script&gt;" in html
    assert DEMO_NOTICE in html
    csp = ok.headers.get("content-security-policy", "")
    assert "default-src" in csp

    bad = bare.get(f"/api/v1/phase3/sign-view/{envelope_id}?view_token=wrong-token")
    assert bad.status_code == 404

    missing = bare.get(f"/api/v1/phase3/sign-view/{envelope_id}")
    assert missing.status_code == 404


def test_f_persists_across_app_restart(signing_env, monkeypatch):
    monkeypatch.setenv("DOCUSEAL_WEBHOOK_SECRET", "test-webhook-secret")
    from gateway.main import app
    import gateway.routers.phase3_rag_sign as sign_mod

    with TestClient(app, headers=AUTH) as c1:
        created = c1.post("/api/v1/phase3/create-signing-link", json=CREATE_PAYLOAD)
        assert created.status_code == 200, created.text
        envelope_id = created.json()["envelope_id"]

    # 模拟进程内存丢失
    if hasattr(sign_mod, "SIGNING_STORAGE"):
        sign_mod.SIGNING_STORAGE.clear()

    with TestClient(app, headers=AUTH) as c2:
        # 通过 DB 辅助查询（或 status 接口）确认仍在
        row = sign_mod.get_signing_envelope(envelope_id)
        assert row is not None, "重启后应按 envelope_id 查到签约记录"
        assert row["envelope_id"] == envelope_id
        assert row["client_name"] == CREATE_PAYLOAD["client_name"]
        assert row["status"] == "pending_signature"
        # sign-view 仍可用
        token = row["view_token"]
        r = c2.get(f"/api/v1/phase3/sign-view/{envelope_id}?view_token={token}")
        assert r.status_code == 200


def test_g_no_false_claims_and_demo_flag(authed):
    resp = authed.post("/api/v1/phase3/create-signing-link", json=CREATE_PAYLOAD)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data.get("is_demo") is True
    assert data.get("mode") == "demo"

    root = Path(__file__).resolve().parents[1]
    pattern = re.compile(r"政务短信|电子合同专用章|防篡改时间戳|防伪电子证书")
    hits = []
    for rel in ("gateway", "frontend", "README.md"):
        path = root / rel
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
            if pattern.search(text):
                hits.append(str(rel))
        elif path.is_dir():
            for f in path.rglob("*"):
                if f.suffix.lower() in {".py", ".html", ".md", ".js", ".ts", ".tsx"}:
                    text = f.read_text(encoding="utf-8", errors="replace")
                    if pattern.search(text):
                        hits.append(str(f.relative_to(root)))
    assert hits == [], f"仍含虚假表述: {hits}"
