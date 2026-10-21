# -*- coding: utf-8 -*-
"""S-01 鉴权 / CORS / TrustedHost / reseed / 首页 token 注入验收。"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("LAWFLOW_API_TOKEN", "test-token")

from gateway.main import app

TOKEN = os.environ["LAWFLOW_API_TOKEN"]
AUTH = {"X-LawFlow-Token": TOKEN}


@pytest.fixture
def authed():
    with TestClient(app, headers=AUTH) as c:
        yield c


@pytest.fixture
def bare():
    with TestClient(app) as c:
        yield c


def test_api_without_token_returns_401(bare):
    for path in ("/api/v1/vault/matters", "/api/v1/settings/llm"):
        resp = bare.get(path)
        assert resp.status_code == 401, path
        body = resp.json()
        assert body.get("error_code") == "AUTH_REQUIRED" or (
            isinstance(body.get("detail"), dict) and body["detail"].get("error_code") == "AUTH_REQUIRED"
        )


def test_api_with_token_returns_200(authed):
    for path in ("/api/v1/vault/matters", "/api/v1/settings/llm"):
        resp = authed.get(path)
        assert resp.status_code == 200, f"{path}: {resp.text}"


def test_cors_preflight_rejects_evil_origin(bare):
    resp = bare.options(
        "/api/v1/vault/matters",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "X-LawFlow-Token",
        },
    )
    acao = resp.headers.get("access-control-allow-origin", "")
    assert acao != "https://evil.example"


def test_cors_get_rejects_evil_origin(authed):
    resp = authed.get(
        "/api/v1/vault/matters",
        headers={"Origin": "https://evil.example"},
    )
    acao = resp.headers.get("access-control-allow-origin", "")
    assert acao != "https://evil.example"


def test_trusted_host_rejects_evil_host(bare):
    resp = bare.get(
        "/api/v1/vault/matters",
        headers={**AUTH, "host": "evil.example"},
    )
    assert resp.status_code == 400


def test_reseed_without_confirm_returns_400(authed):
    resp = authed.post("/api/v1/statutes/reseed", json={})
    assert resp.status_code == 400
    resp2 = authed.post("/api/v1/statutes/reseed", json={"confirm": "NOPE"})
    assert resp2.status_code == 400


def test_index_injects_lawflow_token_meta(bare):
    resp = bare.get("/")
    assert resp.status_code == 200
    html = resp.text
    assert 'name="lawflow-token"' in html
    assert TOKEN in html or f'content="{TOKEN}"' in html
