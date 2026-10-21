# -*- coding: utf-8 -*-
"""S-02 大模型配置安全：URL 白名单、禁止 Key 回落探测、密钥不落仓库。"""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("LAWFLOW_API_TOKEN", "test-token")

AUTH = {"X-LawFlow-Token": os.environ["LAWFLOW_API_TOKEN"]}


@pytest.fixture
def settings_env(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    settings_file = tmp_path / "llm_settings.json"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("LAWFLOW_SETTINGS_FILE", str(settings_file))
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    # 重新加载客户端单例配置路径
    import gateway.core.ollama_client as oc

    oc.SETTINGS_FILE = str(settings_file)
    oc.SECRETS_FILE = str(home / ".lawflow" / "secrets.json")
    client = oc.UniversalLLMClient()
    oc.ollama_client = client
    # 同步 settings_router 引用
    import gateway.routers.settings_router as sr

    sr.ollama_client = client
    yield {"home": home, "settings_file": settings_file, "client": client, "repo_root": Path(oc.BASE_DIR)}


@pytest.fixture
def authed_app(settings_env):
    from gateway.main import app

    with TestClient(app, headers=AUTH) as c:
        yield c, settings_env


def test_save_rejects_http_evil_base_url(authed_app):
    client, _ = authed_app
    resp = client.post(
        "/api/v1/settings/llm",
        json={
            "provider": "cloud",
            "cloud_preset": "deepseek",
            "api_key": "sk-test-key-abcdef",
            "base_url": "http://evil.example/v1",
            "model": "deepseek-chat",
        },
    )
    assert resp.status_code == 422


def test_save_rejects_remote_ollama(authed_app):
    client, _ = authed_app
    resp = client.post(
        "/api/v1/settings/llm",
        json={
            "provider": "ollama",
            "ollama_base_url": "http://10.0.0.5:11434",
            "ollama_model": "gemma4:12b",
        },
    )
    assert resp.status_code == 422


def test_test_llm_new_base_url_without_key_no_network(authed_app, monkeypatch):
    client, env = authed_app
    # 先保存合法配置
    save = client.post(
        "/api/v1/settings/llm",
        json={
            "provider": "cloud",
            "cloud_preset": "deepseek",
            "api_key": "sk-saved-key-xyz98765",
            "base_url": "https://api.deepseek.com/v1",
            "model": "deepseek-chat",
        },
    )
    assert save.status_code == 200, save.text

    network_calls = []

    async def boom(*args, **kwargs):
        network_calls.append((args, kwargs))
        raise AssertionError("不应发起网络请求")

    monkeypatch.setattr("httpx.AsyncClient.post", boom)
    monkeypatch.setattr("httpx.AsyncClient.get", boom)

    resp = client.post(
        "/api/v1/settings/test-llm",
        json={
            "provider": "cloud",
            "cloud_preset": "deepseek",
            "base_url": "https://api.siliconflow.cn/v1",
            "model": "deepseek-chat",
            "api_key": "",
        },
    )
    assert resp.status_code == 400
    assert "API Key" in resp.text or "api" in resp.text.lower()
    assert network_calls == []


def test_saved_key_not_in_repo_tree(authed_app):
    client, env = authed_app
    # 运行时生成，避免密钥字面量出现在测试源码中导致自检误报
    secret = "sk-leakcheck-" + uuid.uuid4().hex
    resp = client.post(
        "/api/v1/settings/llm",
        json={
            "provider": "cloud",
            "cloud_preset": "deepseek",
            "api_key": secret,
            "base_url": "https://api.deepseek.com/v1",
            "model": "deepseek-chat",
        },
    )
    assert resp.status_code == 200, resp.text

    repo_root = env["repo_root"]
    # 只扫仓库内常见文本，跳过 .venv / __pycache__ / .git
    skip_dirs = {".venv", "__pycache__", ".git", "node_modules", ".pytest_cache"}
    leaked = []
    for root, dirs, files in os.walk(repo_root):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        # 不扫用户 HOME（可能在仓库外）；若 settings 误写入仓库则能抓到
        for fn in files:
            fp = Path(root) / fn
            try:
                if fp.stat().st_size > 2_000_000:
                    continue
                text = fp.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            if secret in text:
                leaked.append(str(fp))
    assert leaked == [], f"密钥出现在仓库文件: {leaked}"


def test_get_llm_returns_masked_key(authed_app):
    client, _ = authed_app
    secret = "sk-maskme-1234567890abcd"
    save = client.post(
        "/api/v1/settings/llm",
        json={
            "provider": "cloud",
            "cloud_preset": "deepseek",
            "api_key": secret,
            "base_url": "https://api.deepseek.com/v1",
            "model": "deepseek-chat",
        },
    )
    assert save.status_code == 200, save.text

    resp = client.get("/api/v1/settings/llm")
    assert resp.status_code == 200
    data = resp.json()
    settings = data.get("settings") or data
    masked = settings.get("api_key_masked") or settings.get("api_key") or ""
    assert secret not in json.dumps(data, ensure_ascii=False)
    assert "****" in masked or "*" in masked
