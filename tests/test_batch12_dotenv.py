# -*- coding: utf-8 -*-
"""I-18：.env 存在时 load_dotenv 可读 LOG_LEVEL；不覆盖已有环境变量。"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_load_dotenv_reads_log_level(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("LOG_LEVEL=DEBUG\n", encoding="utf-8")
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    # 防止仓库根 .env 被二次发现
    monkeypatch.setenv("LAWFLOW_DOTENV_FILE", str(env_file))

    from gateway.main import bootstrap_env_and_logging

    level = bootstrap_env_and_logging(env_file=env_file)
    assert os.environ.get("LOG_LEVEL", "").upper() == "DEBUG"
    assert level == logging.DEBUG


def test_load_dotenv_does_not_override_existing(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("LOG_LEVEL=DEBUG\n", encoding="utf-8")
    monkeypatch.setenv("LOG_LEVEL", "WARNING")

    from gateway.main import bootstrap_env_and_logging

    level = bootstrap_env_and_logging(env_file=env_file)
    assert os.environ.get("LOG_LEVEL") == "WARNING"
    assert level == logging.WARNING


def test_license_file_exists_and_is_mit():
    license_path = ROOT / "LICENSE"
    assert license_path.is_file(), "LICENSE 文件必须存在"
    text = license_path.read_text(encoding="utf-8")
    assert "MIT License" in text
    assert "Copyright (c) 2026 TODO(业主填写版权人)" in text


def test_no_hardcoded_weak_secret_in_tracked_sources():
    """验收：业务源码与配置中不得出现历史弱口令占位。"""
    needle = "lawflow_secret_key_" + "2026"
    skip_dirs = {
        ".git", ".venv", ".cursor-batches", "__pycache__", "htmlcov",
        ".pytest_cache", "venv-clean",
    }
    skip_names = {".env"}  # 本地私有；由 .gitignore 排除
    # 本测试文件会拼出 needle，排除自身
    skip_files = {Path(__file__).resolve()}
    hits = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if path.resolve() in skip_files:
            continue
        if path.name in skip_names:
            continue
        if any(part in skip_dirs for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if needle in text:
            hits.append(str(path.relative_to(ROOT)))
    assert hits == [], f"发现弱口令占位: {hits}"


def test_import_gateway_main_subprocess_with_dotenv(tmp_path):
    """子进程导入：临时 .env 的 LOG_LEVEL 可被读取。"""
    # 将 .env 放在项目根由 bootstrap 读取；用环境变量注入路径更稳妥
    env_file = tmp_path / ".env"
    env_file.write_text("LOG_LEVEL=DEBUG\n", encoding="utf-8")
    env = os.environ.copy()
    env.pop("LOG_LEVEL", None)
    env["LAWFLOW_DOTENV_FILE"] = str(env_file)
    env["LAWFLOW_API_TOKEN"] = "test-token"
    home = ROOT / ".cursor-batches" / "home"
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    env["LAWFLOW_SETTINGS_FILE"] = str(home / ".lawflow" / "llm_settings.json")
    code = (
        "import os, logging\n"
        "from gateway.main import logger\n"
        "assert os.environ.get('LOG_LEVEL','').upper()=='DEBUG'\n"
        "assert logging.getLogger().level <= logging.DEBUG or "
        "logger.isEnabledFor(logging.DEBUG)\n"
        "print('ok')\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "ok" in proc.stdout
