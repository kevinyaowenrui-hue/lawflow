"""
全局 pytest 配置：在导入 gateway 之前固定测试用 API Token 与临时 storage，
并为 TestClient 提供统一鉴权头。
"""
from __future__ import annotations

import os
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

# 必须在任何 gateway 导入之前设置
os.environ.setdefault("LAWFLOW_API_TOKEN", "test-token")
os.environ.setdefault("LAWFLOW_ALLOWED_HOSTS", "127.0.0.1,localhost,testserver")
# 依赖演示案件的既有测试默认开启；A-11 全新安装用例会在自身 monkeypatch 中关闭
os.environ.setdefault("LAWFLOW_SEED_DEMO", "1")
# 跳过 lifespan 中 Stirling/Ollama 预热，避免每例 TestClient 启动时探测超时拖慢全量测试
os.environ.setdefault("LAWFLOW_SKIP_SERVICE_PROBE_WARMUP", "1")

# 会话级临时 storage，避免污染仓库内 storage/
_TEST_STORAGE = Path(tempfile.mkdtemp(prefix="lawflow_pytest_storage_"))
os.environ["LAWFLOW_STORAGE_DIR"] = str(_TEST_STORAGE)

import pytest
from fastapi.testclient import TestClient


AUTH_HEADERS = {"X-LawFlow-Token": os.environ["LAWFLOW_API_TOKEN"]}


def _ollama_available(timeout: float = 1.5) -> bool:
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=timeout) as resp:
            return getattr(resp, "status", 200) == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _soffice_available() -> bool:
    try:
        from gateway.routers.phase1_litigation import _find_soffice

        return _find_soffice() is not None
    except Exception:
        return False


def pytest_configure(config):
    config.addinivalue_line("markers", "requires_ollama: needs local Ollama at 127.0.0.1:11434")
    config.addinivalue_line("markers", "requires_soffice: needs LibreOffice soffice on PATH or install dir")
    config.addinivalue_line("markers", "slow: long-running coverage gate / integration checks")


def pytest_runtest_setup(item):
    if item.get_closest_marker("requires_ollama") and not _ollama_available():
        pytest.skip("Ollama unavailable at http://127.0.0.1:11434")
    if item.get_closest_marker("requires_soffice") and not _soffice_available():
        pytest.skip("LibreOffice soffice unavailable")


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


@pytest.fixture
def seed_demo(monkeypatch):
    """依赖演示数据的测试使用此 fixture。"""
    monkeypatch.setenv("LAWFLOW_SEED_DEMO", "1")
    from gateway.seed_demo import seed_all_demo_data
    seed_all_demo_data()
    return True
