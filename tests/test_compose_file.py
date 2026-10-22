# -*- coding: utf-8 -*-
"""I-22：docker-compose.yml 供应链与凭据约束。"""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "docker-compose.yml"


def test_compose_no_version_no_latest_official_docassemble():
    data = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    assert "version" not in data, "compose 不应再声明已废弃的 version 字段"

    services = data.get("services") or {}
    assert services, "compose 应包含 services"

    for name, svc in services.items():
        image = (svc or {}).get("image")
        if not image:
            continue
        assert not str(image).endswith(":latest"), f"{name} 不得使用 :latest → {image}"
        if "docassemble" in name.lower() or "docassemble" in str(image).lower():
            assert str(image).startswith("jhpyle/docassemble"), (
                f"docassemble 须使用官方镜像 jhpyle/docassemble，当前: {image}"
            )


def test_compose_text_has_no_banned_tokens():
    text = COMPOSE.read_text(encoding="utf-8")
    assert ("lawflow_secret_key_" + "2026") not in text
    assert "j2r2b" not in text
    # 镜像标签不得为 :latest（允许注释中提及）
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if ":latest" in stripped and "image:" in stripped:
            raise AssertionError(f"镜像仍使用 :latest: {stripped}")
