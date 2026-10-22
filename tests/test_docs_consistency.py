# -*- coding: utf-8 -*-
"""I-29：README / ARCHITECTURE / ROADMAP 中的 /api/... 须真实存在，且不得写 :8000。"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOC_FILES = ("README.md", "ARCHITECTURE.md", "ROADMAP.md")
# 路径段不含省略号；不把 /api/v1/foo/... 当成真实路由
API_PATH_RE = re.compile(r"/api/[A-Za-z0-9_\-/{}]+")


def _collect_app_paths():
    from gateway.main import app

    paths = set()

    def walk(routes):
        for r in routes:
            if hasattr(r, "path") and getattr(r, "methods", None) is not None:
                paths.add(r.path)
            if hasattr(r, "routes"):
                walk(r.routes)
            if hasattr(r, "original_router"):
                walk(r.original_router.routes)

    walk(app.routes)
    # OpenAPI 补充（含 include_in_schema 默认路径）
    try:
        paths.update(app.openapi().get("paths", {}).keys())
    except Exception:
        pass
    return paths


def _template_to_regex(route: str) -> re.Pattern:
    """将 FastAPI 风格 /x/{id} 转为可匹配文档路径的正则。"""
    parts = []
    for seg in route.strip("/").split("/"):
        if seg.startswith("{") and seg.endswith("}"):
            parts.append(r"[^/]+")
        else:
            parts.append(re.escape(seg))
    return re.compile("^/" + "/".join(parts) + "$")


def _path_exists_in_app(doc_path: str, app_paths: set[str]) -> bool:
    # 去掉文档中可能的尾随标点
    doc_path = doc_path.rstrip(").,;`'\"")
    if doc_path in app_paths:
        return True
    for ap in app_paths:
        if _template_to_regex(ap).match(doc_path):
            return True
        # 文档也可能写了模板形式
        if _template_to_regex(doc_path).pattern == _template_to_regex(ap).pattern:
            return True
    return False


@pytest.mark.parametrize("doc_name", DOC_FILES)
def test_doc_api_paths_exist_in_app(doc_name):
    text = (ROOT / doc_name).read_text(encoding="utf-8")
    found = sorted({
        p.rstrip("/")
        for p in API_PATH_RE.findall(text)
        if "..." not in p and not p.endswith(".")
    })
    app_paths = _collect_app_paths()
    missing = [p for p in found if not _path_exists_in_app(p, app_paths)]
    assert missing == [], f"{doc_name} 中以下路径不在 app.routes: {missing}"


@pytest.mark.parametrize("doc_name", DOC_FILES)
def test_docs_do_not_mention_port_8000(doc_name):
    text = (ROOT / doc_name).read_text(encoding="utf-8")
    assert ":8000" not in text, f"{doc_name} 仍出现 :8000"
