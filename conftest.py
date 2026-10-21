"""
全局 pytest 配置：在导入 gateway 之前固定测试用 API Token，
并为 TestClient 提供统一鉴权头。
"""
from __future__ import annotations

import os

# 必须在任何 gateway 导入之前设置
os.environ.setdefault("LAWFLOW_API_TOKEN", "test-token")
# 测试默认不启动远程 Ollama / 不写用户家目录敏感配置时可被各用例覆盖
os.environ.setdefault("LAWFLOW_ALLOWED_HOSTS", "127.0.0.1,localhost,testserver")

import pytest
from fastapi.testclient import TestClient


AUTH_HEADERS = {"X-LawFlow-Token": os.environ["LAWFLOW_API_TOKEN"]}


@pytest.fixture
def auth_headers():
    return dict(AUTH_HEADERS)


@pytest.fixture
def client():
    from gateway.main import app

    with TestClient(app, headers=AUTH_HEADERS) as c:
        yield c


@pytest.fixture
def client_no_auth():
    from gateway.main import app

    with TestClient(app) as c:
        yield c
