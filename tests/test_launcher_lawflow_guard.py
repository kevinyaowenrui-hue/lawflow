# -*- coding: utf-8 -*-
"""I-25：launcher 仅在确认是 LawFlow 进程时才允许结束占用端口的进程。"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "launcher.pyw"


def _load_launcher():
    spec = importlib.util.spec_from_file_location("lawflow_launcher", LAUNCHER)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_is_lawflow_health_response_true_when_app_lawflow():
    mod = _load_launcher()
    assert mod.is_lawflow_health_payload({"status": "healthy", "app": "LawFlow"}) is True
    assert mod.is_lawflow_health_payload({"app": "LawFlow"}) is True


def test_is_lawflow_health_response_false_otherwise():
    mod = _load_launcher()
    assert mod.is_lawflow_health_payload({"status": "healthy"}) is False
    assert mod.is_lawflow_health_payload({"app": "OtherApp"}) is False
    assert mod.is_lawflow_health_payload(None) is False
    assert mod.is_lawflow_health_payload("not-a-dict") is False


def test_probe_is_lawflow_process_mocks():
    mod = _load_launcher()

    with patch.object(mod, "_fetch_health_json", return_value={"status": "ok", "app": "LawFlow"}):
        assert mod.is_lawflow_process_on_port(5221) is True

    with patch.object(mod, "_fetch_health_json", return_value={"status": "ok"}):
        assert mod.is_lawflow_process_on_port(5221) is False

    with patch.object(mod, "_fetch_health_json", side_effect=ConnectionError("down")):
        assert mod.is_lawflow_process_on_port(5221) is False


def test_no_hermes_or_personal_paths_in_launch_scripts():
    files = [
        ROOT / "launcher.pyw",
        ROOT / "launcher.vbs",
        ROOT / "start_gateway.bat",
        ROOT / "scripts" / "create_desktop_shortcut.py",
        ROOT / "scripts" / "update_desktop_shortcut.py",
    ]
    # 拆分拼写，避免验收 rg 在本测试文件中误报
    banned = (
        "her" + "mes",
        "anti" + "gravity",
        "C:\\Users\\" + "kevin",
        "F:\\" + "antigravity",
    )
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace").lower()
        for token in banned:
            assert token.lower() not in text, f"{path.name} 仍含 {token}"
