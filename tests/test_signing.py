# -*- coding: utf-8 -*-
"""电子签约：正式 DocuSeal 路径、webhook 鉴权、真实哈希、持久化。"""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("LAWFLOW_API_TOKEN", "test-token")
os.environ.setdefault("LAWFLOW_ALLOWED_HOSTS", "127.0.0.1,localhost,testserver")

AUTH = {"X-LawFlow-Token": os.environ["LAWFLOW_API_TOKEN"]}
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
    monkeypatch.delenv("DOCUSEAL_API_TOKEN", raising=False)
    monkeypatch.delenv("DOCUSEAL_API_KEY", raising=False)
    import gateway.routers.phase3_rag_sign as sign_mod

    if hasattr(sign_mod, "SIGNING_STORAGE"):
        sign_mod.SIGNING_STORAGE.clear()
    yield tmp_path


@pytest.fixture
def authed(signing_env):
    from gateway.main import app

    with TestClient(app, headers=AUTH) as c:
        yield c


DOCUSEAL_EMBED = "http://127.0.0.1:3000/s/realSlugFromDocuseal"
_REAL_ASYNC_CLIENT = httpx.AsyncClient


def docuseal_success_body(embed_src: str = DOCUSEAL_EMBED, slug: str = "realSlugFromDocuseal"):
    return {
        "id": 5,
        "name": "委托合同",
        "submitters": [
            {
                "id": 1,
                "submission_id": 5,
                "slug": slug,
                "embed_src": embed_src,
                "role": "委托人",
                "status": "sent",
            }
        ],
    }


class DocuSealApiStub:
    """替身：拦截创建提交，其它请求仍交给真实 httpx 客户端。"""

    status_code = 200
    body = docuseal_success_body()
    calls: list = []
    raise_on_post = None
    bad_json = False

    def __init__(self, *args, **kwargs):
        self._real = _REAL_ASYNC_CLIENT(*args, **kwargs)

    async def __aenter__(self):
        await self._real.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return await self._real.__aexit__(exc_type, exc, tb)

    async def post(self, url, json=None, headers=None, **kwargs):
        if "/api/submissions" not in str(url):
            return await self._real.post(url, json=json, headers=headers, **kwargs)
        type(self).calls.append({"url": url, "json": json, "headers": dict(headers or {})})
        if type(self).raise_on_post is not None:
            raise type(self).raise_on_post

        status = type(self).status_code
        payload = type(self).body
        bad_json = type(self).bad_json

        class _Resp:
            status_code = status
            text = ""

            def json(self):
                if bad_json:
                    raise ValueError("not json")
                return payload

        return _Resp()

    def __getattr__(self, name):
        return getattr(self._real, name)


def reset_docuseal_stub():
    DocuSealApiStub.status_code = 200
    DocuSealApiStub.body = docuseal_success_body()
    DocuSealApiStub.calls = []
    DocuSealApiStub.raise_on_post = None
    DocuSealApiStub.bad_json = False


def install_docuseal_stub(monkeypatch):
    reset_docuseal_stub()

    async def _ok():
        return True

    monkeypatch.setattr(
        "gateway.routers.phase3_rag_sign._probe_docuseal_available",
        _ok,
    )
    monkeypatch.setattr(
        "gateway.routers.phase3_rag_sign._docuseal_http_client",
        lambda **kwargs: DocuSealApiStub(**kwargs),
    )


@pytest.fixture
def configured(authed, monkeypatch):
    """配置齐全且 DocuSeal 探测视为可用，创建提交走替身。"""
    monkeypatch.setenv("DOCUSEAL_URL", "http://127.0.0.1:3000")
    monkeypatch.setenv("DOCUSEAL_WEBHOOK_SECRET", "test-webhook-secret")
    monkeypatch.setenv("DOCUSEAL_API_TOKEN", "test-api-token")
    install_docuseal_stub(monkeypatch)
    return authed


def _webhook_headers(secret: str = "test-webhook-secret", header: str = "X-LawFlow-Webhook-Secret"):
    return {header: secret, "Content-Type": "application/json"}


def test_create_without_config_returns_503(authed):
    resp = authed.post("/api/v1/phase3/create-signing-link", json=CREATE_PAYLOAD)
    assert resp.status_code == 503, resp.text
    assert "DOCUSEAL" in resp.text


def test_a_webhook_without_secret_returns_503(authed):
    resp = authed.post(
        "/api/v1/phase3/signing-webhook",
        json={"envelope_id": "ds-nonexistent"},
    )
    assert resp.status_code == 503, resp.text
    assert "webhook 未启用" in resp.text


def test_b_webhook_auth_and_missing_envelope(configured):
    created = configured.post("/api/v1/phase3/create-signing-link", json=CREATE_PAYLOAD)
    assert created.status_code == 200, created.text
    envelope_id = created.json()["envelope_id"]
    assert created.json()["envelope"]["status"] == "pending_signature"
    assert created.json().get("is_demo") is False
    assert created.json().get("mode") == "docuseal"

    r1 = configured.post(
        "/api/v1/phase3/signing-webhook",
        json={"envelope_id": envelope_id},
    )
    assert r1.status_code == 401, r1.text

    r2 = configured.post(
        "/api/v1/phase3/signing-webhook",
        headers=_webhook_headers("wrong-secret"),
        json={"envelope_id": envelope_id},
    )
    assert r2.status_code == 401, r2.text

    r3 = configured.post(
        "/api/v1/phase3/signing-webhook",
        headers=_webhook_headers(),
        content=b"not json",
    )
    assert r3.status_code == 400, r3.text

    r4 = configured.post(
        "/api/v1/phase3/signing-webhook",
        headers=_webhook_headers(),
        json={"envelope_id": "ds-does-not-exist"},
    )
    assert r4.status_code == 404, r4.text

    from gateway.routers.phase3_rag_sign import get_signing_envelope

    row = get_signing_envelope(envelope_id)
    assert row is not None
    assert row["status"] == "pending_signature"


def test_c_webhook_completes_with_real_file_sha256(configured):
    created = configured.post("/api/v1/phase3/create-signing-link", json=CREATE_PAYLOAD)
    assert created.status_code == 200, created.text
    envelope_id = created.json()["envelope_id"]

    resp = configured.post(
        "/api/v1/phase3/signing-webhook",
        headers=_webhook_headers(),
        json={"envelope_id": envelope_id},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data.get("status") in ("success", "completed") or data.get("envelope_status") == "completed"
    assert data.get("is_demo") is False
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


def test_d_signing_url_uses_docuseal_base(configured):
    resp = configured.post("/api/v1/phase3/create-signing-link", json=CREATE_PAYLOAD)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    url = data["signing_url"]
    assert url.startswith("http://127.0.0.1:3000/")
    assert ":8000" not in url
    assert data.get("is_demo") is False
    assert data.get("mode") == "docuseal"


def test_e_sign_view_retired(configured, signing_env):
    from gateway.main import app

    created = configured.post("/api/v1/phase3/create-signing-link", json=CREATE_PAYLOAD)
    assert created.status_code == 200, created.text
    envelope_id = created.json()["envelope_id"]
    from gateway.routers.phase3_rag_sign import get_signing_envelope

    token = get_signing_envelope(envelope_id)["view_token"]
    with TestClient(app) as bare:
        resp = bare.get(f"/api/v1/phase3/sign-view/{envelope_id}?view_token={token}")
    assert resp.status_code == 410
    assert "已停用" in resp.text


def test_f_persists_across_app_restart(signing_env, monkeypatch):
    monkeypatch.setenv("DOCUSEAL_URL", "http://127.0.0.1:3000")
    monkeypatch.setenv("DOCUSEAL_WEBHOOK_SECRET", "test-webhook-secret")
    monkeypatch.setenv("DOCUSEAL_API_TOKEN", "test-api-token")
    install_docuseal_stub(monkeypatch)
    from gateway.main import app
    import gateway.routers.phase3_rag_sign as sign_mod

    with TestClient(app, headers=AUTH) as c1:
        created = c1.post("/api/v1/phase3/create-signing-link", json=CREATE_PAYLOAD)
        assert created.status_code == 200, created.text
        envelope_id = created.json()["envelope_id"]

    if hasattr(sign_mod, "SIGNING_STORAGE"):
        sign_mod.SIGNING_STORAGE.clear()

    with TestClient(app, headers=AUTH) as c2:
        row = sign_mod.get_signing_envelope(envelope_id)
        assert row is not None, "重启后应按 envelope_id 查到签约记录"
        assert row["envelope_id"] == envelope_id
        assert row["client_name"] == CREATE_PAYLOAD["client_name"]
        assert row["status"] == "pending_signature"
        assert row.get("is_demo") is False
        r = c2.get(f"/api/v1/phase3/sign-view/{envelope_id}?view_token={row['view_token']}")
        assert r.status_code == 410


def test_g_no_false_claims(configured):
    resp = configured.post("/api/v1/phase3/create-signing-link", json=CREATE_PAYLOAD)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data.get("is_demo") is False
    assert data.get("mode") == "docuseal"

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


def _assert_not_integrated_success(resp):
    assert resp.status_code != 200, resp.text
    body = resp.json()
    assert body.get("docuseal_integrated") is not True
    assert body.get("status") != "success"
    assert not body.get("signing_url")


def test_h_signing_url_is_docuseal_embed_src(configured):
    resp = configured.post("/api/v1/phase3/create-signing-link", json=CREATE_PAYLOAD)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert DocuSealApiStub.calls, "应调用 DocuSeal 创建提交"
    posted = DocuSealApiStub.calls[0]
    assert posted["url"] == "http://127.0.0.1:3000/api/submissions/html"
    assert posted["headers"].get("X-Auth-Token") == "test-api-token"
    html_doc = posted["json"]["documents"][0]["html"]
    assert CREATE_PAYLOAD["client_name"] in html_doc
    assert CREATE_PAYLOAD["case_summary"] in html_doc
    assert posted["json"]["send_email"] is False
    assert posted["json"]["submitters"][0]["external_id"] == data["envelope_id"]
    assert posted["json"]["submitters"][0]["metadata"]["envelope_id"] == data["envelope_id"]
    assert data["signing_url"] == DOCUSEAL_EMBED
    assert data["docuseal_integrated"] is True
    assert data["envelope_id"] not in data["signing_url"]
    assert "/s/ds-" not in data["signing_url"]
    assert "test-api-token" not in resp.text

    from gateway.routers.phase3_rag_sign import get_signing_envelope

    row = get_signing_envelope(data["envelope_id"])
    assert str(row.get("docuseal_submission_id")) == "5"
    assert str(row.get("docuseal_submitter_id")) == "1"


def test_h_slug_only_uses_official_slug(configured):
    DocuSealApiStub.body = {
        "id": 9,
        "submitters": [
            {
                "id": 3,
                "submission_id": 9,
                "slug": "officialSlug",
                "role": "委托人",
            }
        ],
    }
    resp = configured.post("/api/v1/phase3/create-signing-link", json=CREATE_PAYLOAD)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["signing_url"] == "http://127.0.0.1:3000/s/officialSlug"
    assert data["envelope_id"] not in data["signing_url"]
    assert data["docuseal_integrated"] is True


def test_i_missing_token_is_not_success(authed, monkeypatch):
    monkeypatch.setenv("DOCUSEAL_URL", "http://127.0.0.1:3000")
    monkeypatch.setenv("DOCUSEAL_WEBHOOK_SECRET", "test-webhook-secret")
    monkeypatch.delenv("DOCUSEAL_API_TOKEN", raising=False)
    monkeypatch.delenv("DOCUSEAL_API_KEY", raising=False)
    import gateway.routers.phase3_rag_sign as sign_mod

    monkeypatch.setattr(sign_mod, "read_secrets", lambda: {}, raising=False)

    async def _ok():
        return True

    monkeypatch.setattr(sign_mod, "_probe_docuseal_available", _ok)
    reset_docuseal_stub()
    DocuSealApiStub.raise_on_post = AssertionError("缺令牌时不应请求 DocuSeal")
    monkeypatch.setattr(
        sign_mod,
        "_docuseal_http_client",
        lambda **kwargs: DocuSealApiStub(**kwargs),
    )

    resp = authed.post("/api/v1/phase3/create-signing-link", json=CREATE_PAYLOAD)
    _assert_not_integrated_success(resp)
    assert "令牌" in resp.text
    assert DocuSealApiStub.calls == []


def test_i_token_from_secrets_json(authed, monkeypatch):
    monkeypatch.setenv("DOCUSEAL_URL", "http://127.0.0.1:3000")
    monkeypatch.setenv("DOCUSEAL_WEBHOOK_SECRET", "test-webhook-secret")
    monkeypatch.delenv("DOCUSEAL_API_TOKEN", raising=False)
    monkeypatch.delenv("DOCUSEAL_API_KEY", raising=False)
    import gateway.routers.phase3_rag_sign as sign_mod

    monkeypatch.setattr(sign_mod, "read_secrets", lambda: {"docuseal_api_token": "secret-file-token"}, raising=False)
    install_docuseal_stub(monkeypatch)

    resp = authed.post("/api/v1/phase3/create-signing-link", json=CREATE_PAYLOAD)
    assert resp.status_code == 200, resp.text
    assert resp.json()["signing_url"] == DOCUSEAL_EMBED
    assert DocuSealApiStub.calls[0]["headers"].get("X-Auth-Token") == "secret-file-token"


def test_j_create_failure_is_not_success(configured):
    DocuSealApiStub.status_code = 500
    DocuSealApiStub.body = {"error": "template exploded"}
    resp = configured.post("/api/v1/phase3/create-signing-link", json=CREATE_PAYLOAD)
    _assert_not_integrated_success(resp)
    assert "创建签署提交失败" in resp.text

    DocuSealApiStub.calls = []
    DocuSealApiStub.status_code = 401
    DocuSealApiStub.body = {"error": "Not authenticated"}
    denied = configured.post("/api/v1/phase3/create-signing-link", json=CREATE_PAYLOAD)
    _assert_not_integrated_success(denied)
    assert "令牌" in denied.text

    import httpx

    DocuSealApiStub.calls = []
    DocuSealApiStub.raise_on_post = httpx.ConnectError("refused")
    down = configured.post("/api/v1/phase3/create-signing-link", json=CREATE_PAYLOAD)
    _assert_not_integrated_success(down)
    assert "不可达" in down.text or "连不上" in down.text


def test_k_response_without_signing_link_is_not_success(configured):
    DocuSealApiStub.body = {"id": 5, "submitters": [{"id": 1, "role": "委托人"}]}
    resp = configured.post("/api/v1/phase3/create-signing-link", json=CREATE_PAYLOAD)
    _assert_not_integrated_success(resp)
    assert "签署链接" in resp.text

    DocuSealApiStub.bad_json = True
    DocuSealApiStub.body = None
    bad = configured.post("/api/v1/phase3/create-signing-link", json=CREATE_PAYLOAD)
    _assert_not_integrated_success(bad)


def test_l_source_does_not_fake_integrated_link():
    root = Path(__file__).resolve().parents[1]
    hits = []
    for path in (root / "gateway").rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="replace")
        if "/s/{envelope_id}" in text or re.search(r"/s/\{[^}\n]*envelope_id[^}\n]*\}", text):
            hits.append(str(path.relative_to(root)))
    assert hits == [], f"仍用本地 envelope 编号拼接 /s/ : {hits}"


def test_m_webhook_matches_real_submission_and_ignores_view(configured):
    created = configured.post("/api/v1/phase3/create-signing-link", json=CREATE_PAYLOAD)
    assert created.status_code == 200, created.text
    envelope_id = created.json()["envelope_id"]

    viewed = configured.post(
        "/api/v1/phase3/signing-webhook",
        headers=_webhook_headers(),
        json={
            "event_type": "form.viewed",
            "data": {
                "id": 1,
                "external_id": envelope_id,
                "metadata": {"envelope_id": envelope_id},
                "submission": {"id": 5, "status": "pending"},
            },
        },
    )
    assert viewed.status_code == 200, viewed.text
    assert viewed.json().get("status") == "ignored"

    from gateway.routers.phase3_rag_sign import get_signing_envelope

    assert get_signing_envelope(envelope_id)["status"] == "pending_signature"

    completed = configured.post(
        "/api/v1/phase3/signing-webhook",
        headers=_webhook_headers(),
        json={
            "event_type": "submission.completed",
            "data": {
                "id": 5,
                "status": "completed",
            },
        },
    )
    assert completed.status_code == 200, completed.text
    assert completed.json().get("envelope_status") == "completed"
    assert get_signing_envelope(envelope_id)["status"] == "completed"
