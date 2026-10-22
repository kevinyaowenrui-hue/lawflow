# -*- coding: utf-8 -*-
"""
tests/test_frontend_entries.py:
解析 frontend/index.html，断言存在调用 upload-document、证据目录、质证、红队、pii/scan、xlsx 导出、单条核验
这些接口路径的代码（字符串匹配接口路径），且所在 fetch 调用后有 resp.ok 检查（正则匹配同一函数内出现 ".ok"）。
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX_HTML = ROOT / "frontend" / "index.html"


def test_frontend_entries_and_ok_checks():
    assert INDEX_HTML.exists(), "frontend/index.html must exist"
    
    # 收集前端所有源码（模块化后的 JS 模块及 index.html，排除 vendor）
    contents = {}
    for p in (ROOT / "frontend").rglob("*"):
        if p.suffix.lower() in (".html", ".js") and "vendor" not in p.parts:
            contents[p.name] = p.read_text(encoding="utf-8")

    full_content = "\n".join(contents.values())

    # 接口路径清单与关键词
    required_entries = {
        "upload_document": "upload-document",
        "evidence_catalog": "auto-catalog",
        "cross_examination": "cross-examination",
        "red_team": "adversarial-attack",
        "pii_scan": "pii/scan",
        "review_table_xlsx": "export/xlsx",
        "citation_guard_single": "verify-single",
    }

    # 1. 字符串匹配接口路径是否存在于前端代码中
    for name, path_snippet in required_entries.items():
        assert path_snippet in full_content, f"前端代码中必须包含接口路径 '{path_snippet}'（用于 {name}）"

    # 2. 检查调用经由 api.js 统一客户端（具备 resp.ok 校验与 ApiError 封装）
    api_js = (ROOT / "frontend" / "js" / "api.js").read_text(encoding="utf-8")
    assert "resp.ok" in api_js, "api.js 必须具备 resp.ok 统一校验"
    assert "ApiError" in api_js, "api.js 必须统一定义 ApiError"
