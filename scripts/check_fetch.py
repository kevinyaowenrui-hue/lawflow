# -*- coding: utf-8 -*-
"""
扫描 frontend/ 下 .html/.js 文件：
除 frontend/js/api.js 与 vendor/ 外，不得直接出现 'fetch('。
若发现违规直接打印 文件:行号 并以状态码 1 退出。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
FETCH_RE = re.compile(r"\bfetch\s*\(")


def _iter_frontend_files():
    if not FRONTEND.is_dir():
        return
    for path in FRONTEND.rglob("*"):
        if path.suffix.lower() in (".html", ".js") and path.is_file():
            parts = [p.lower() for p in path.parts]
            if "vendor" in parts:
                continue
            # 豁免 frontend/js/api.js 内部的底层 fetch 调用
            if path.resolve() == (FRONTEND / "js" / "api.js").resolve():
                continue
            yield path


def main() -> int:
    violations: list[str] = []
    for path in sorted(_iter_frontend_files()):
        rel = path.relative_to(ROOT).as_posix()
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except Exception as e:
            print(f"Error reading {rel}: {e}", file=sys.stderr)
            continue
        for lineno, line in enumerate(lines, start=1):
            if FETCH_RE.search(line):
                violations.append(f"{rel}:{lineno}: direct fetch() call found: {line.strip()[:100]}")

    for v in violations:
        try:
            print(v)
        except UnicodeEncodeError:
            print(v.encode("utf-8", errors="replace").decode("utf-8", errors="replace"))

    if violations:
        print(f"\nFound {len(violations)} direct fetch() call(s) outside api.js.", file=sys.stderr)
        return 1
    print("OK: no direct fetch() calls outside api.js.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
