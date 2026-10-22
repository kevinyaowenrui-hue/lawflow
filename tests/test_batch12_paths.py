# -*- coding: utf-8 -*-
"""I-21：LAWFLOW_* 路径环境变量由 paths 模块解析。"""
from __future__ import annotations

from pathlib import Path


def test_paths_respect_frontend_storage_templates_env(tmp_path, monkeypatch):
    frontend = tmp_path / "fe"
    storage = tmp_path / "st"
    templates = tmp_path / "tpl"
    frontend.mkdir()
    storage.mkdir()
    templates.mkdir()

    monkeypatch.setenv("LAWFLOW_FRONTEND_DIR", str(frontend))
    monkeypatch.setenv("LAWFLOW_STORAGE_DIR", str(storage))
    monkeypatch.setenv("LAWFLOW_TEMPLATES_DIR", str(templates))

    from gateway.core import paths

    assert paths.get_frontend_dir() == frontend.resolve()
    assert paths.get_storage_dir() == storage.resolve()
    assert paths.get_templates_dir() == templates.resolve()


def test_cjk_font_candidates_include_fonts_dir(tmp_path, monkeypatch):
    fonts = tmp_path / "fonts"
    fonts.mkdir()
    sample = fonts / "NotoSansSC.otf"
    sample.write_bytes(b"fake")
    monkeypatch.setenv("LAWFLOW_FONTS_DIR", str(fonts))

    from gateway.core import paths

    cands = paths.get_cjk_font_candidates()
    assert any(Path(p) == sample.resolve() or Path(p).parent == fonts.resolve() for p in cands)
    assert str(sample.resolve()) in [str(Path(p).resolve()) for p in cands] or any(
        Path(p).name == "NotoSansSC.otf" for p in cands
    )
