"""
tests/ 子目录 conftest：每个测试使用独立临时 storage（LAWFLOW_STORAGE_DIR → tmp_path），
并在隔离目录内重新初始化核心库（避免「有路径无表」）。
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("LAWFLOW_API_TOKEN", "test-token")
os.environ.setdefault("LAWFLOW_ALLOWED_HOSTS", "127.0.0.1,localhost,testserver")


@pytest.fixture(autouse=True)
def _isolate_lawflow_storage(tmp_path, monkeypatch):
    """验收：每个测试独立临时目录；结束后不得改动仓库内 storage/。"""
    storage = tmp_path / "storage"
    storage.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("LAWFLOW_STORAGE_DIR", str(storage))

    try:
        from gateway.utils.legal_data import clear_legal_data_cache

        clear_legal_data_cache()
    except Exception:
        pass

    # 路径切换后必须重建 schema，否则 API/引擎会落到空库
    from gateway.utils.agent_task_db import init_agent_task_db
    from gateway.utils.conflict_checker import init_conflict_database
    from gateway.utils.matter_vault_db import init_matter_vault_db
    from gateway.utils.review_table_engine import init_review_tables_schema
    from gateway.utils.statute_db import init_statute_database

    init_statute_database(force_reseed=True)
    init_conflict_database()
    init_matter_vault_db()
    init_review_tables_schema()
    init_agent_task_db()

    if os.environ.get("LAWFLOW_SEED_DEMO", "1") == "1":
        try:
            from gateway.seed_demo import seed_all_demo_data

            seed_all_demo_data()
        except Exception:
            pass

    yield

    try:
        from gateway.utils.legal_data import clear_legal_data_cache

        clear_legal_data_cache()
    except Exception:
        pass
