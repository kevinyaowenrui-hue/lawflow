"""
LawFlow 智律工作台 - 集中路径常量
所有 storage / 数据库路径在调用时读取环境变量，便于测试重定向。
"""
from __future__ import annotations

import os
from pathlib import Path


def get_base_dir() -> Path:
    """项目根目录（含 gateway/、frontend/、storage/）。"""
    return Path(__file__).resolve().parent.parent.parent


def get_storage_dir() -> Path:
    """
    数据目录：优先环境变量 LAWFLOW_STORAGE_DIR，否则 <BASE_DIR>/storage。
    每次调用重新读取，保证测试可在导入后重定向。
    """
    override = os.environ.get("LAWFLOW_STORAGE_DIR")
    if override:
        path = Path(override).expanduser().resolve()
    else:
        path = get_base_dir() / "storage"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_generated_dir() -> Path:
    path = get_storage_dir() / "generated"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_uploads_dir() -> Path:
    path = get_storage_dir() / "uploads"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_laws_db_path() -> Path:
    return get_storage_dir() / "cn_laws_kb.db"


def get_vault_db_path() -> Path:
    return get_storage_dir() / "matter_vault.db"


# 兼容旧代码中的模块级别名风格（仍为函数，避免导入时固化路径）
def BASE_DIR() -> str:
    return str(get_base_dir())


def STORAGE_DIR() -> str:
    return str(get_storage_dir())


def GENERATED_DIR() -> str:
    return str(get_generated_dir())


def UPLOADS_DIR() -> str:
    return str(get_uploads_dir())


def LAWS_DB_PATH() -> str:
    return str(get_laws_db_path())


def VAULT_DB_PATH() -> str:
    return str(get_vault_db_path())
