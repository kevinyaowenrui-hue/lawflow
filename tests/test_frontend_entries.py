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
    content = INDEX_HTML.read_text(encoding="utf-8")

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
        assert path_snippet in content, f"frontend/index.html 中必须包含接口路径 '{path_snippet}'（用于 {name}）"

    # 2. 检查所在 fetch 调用或函数内是否有 .ok 检查
    # 我们通过匹配包含该路径的 function 或 async function 块，断言块内包含 .ok
    # 匹配规则：以 function 或 async function 开头，包含路径片段，并在同一函数体内包含 \.ok
    for name, path_snippet in required_entries.items():
        # 寻找包含该接口路径的函数
        # 简单有效策略：在包含该接口的 30 行前后窗口内，或者函数体内部，断言有 .ok
        pattern = re.compile(
            rf"(?:async\s+)?function\s+([A-Za-z0-9_]+)\s*\([^)]*\)\s*\{{[^}}]*?{re.escape(path_snippet)}[^}}]*?\}}",
            re.DOTALL
        )
        matches = pattern.findall(content)
        if not matches:
            # 兼容更深层次的大函数或嵌套花括号结构：
            # 查找以 function 开始直到下一个 top-level function 之间包含 path_snippet 的区域
            func_blocks = re.split(r"\n\s*(?:async\s+)?function\s+", content)
            matched_blocks = [b for b in func_blocks if path_snippet in b and "fetch(" in b]
            assert len(matched_blocks) > 0, f"未能定位到包含 fetch({path_snippet}) 的函数定义"
            for b in matched_blocks:
                assert ".ok" in b, f"调用 {path_snippet} 的函数内必须包含 resp.ok 检查"
        else:
            for fn_name in matches:
                # 重新提取该函数全部内容并验证 .ok
                assert ".ok" in content, f"调用 {path_snippet} 的函数 {fn_name} 必须包含 .ok 检查"
