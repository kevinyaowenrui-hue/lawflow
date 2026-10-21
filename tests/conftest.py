"""
tests/ 子目录 conftest：与根目录 conftest 配合。
根 conftest 已在收集前设置 LAWFLOW_STORAGE_DIR 与 Token；
此处 fixtures 由根目录自动继承，无需重复定义。
"""
from __future__ import annotations

import os

os.environ.setdefault("LAWFLOW_API_TOKEN", "test-token")
os.environ.setdefault("LAWFLOW_ALLOWED_HOSTS", "127.0.0.1,localhost,testserver")
