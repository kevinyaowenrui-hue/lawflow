# -*- coding: utf-8 -*-
"""
扫描 frontend/ 下 .html/.js：凡 .innerHTML 赋值右侧（含跨行至语句结束）模板字符串中的 ${...}
若未包裹 escapeHtml(...) 或 DOMPurify.sanitize(...)，且该插值行 / 赋值首行无 // safe-html: 豁免，
则输出 文件:行号 并以非零退出。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"

ASSIGN_RE = re.compile(r"\.innerHTML\s*=")
INTERP_RE = re.compile(r"\$\{([^{}]+(?:\{[^{}]*\}[^{}]*)*)\}")
SAFE_CALL_IN_EXPR = re.compile(r"\b(?:escapeHtml|DOMPurify\.sanitize)\s*\(")
SAFE_COMMENT_RE = re.compile(r"//\s*safe-html\s*:")


def _iter_frontend_files():
    if not FRONTEND.is_dir():
        return
    for path in FRONTEND.rglob("*"):
        if path.suffix.lower() in (".html", ".js") and path.is_file():
            if "vendor" in path.parts:
                continue
            yield path


def _extract_rhs_statement(lines: list[str], start_idx: int) -> tuple[str, int, int]:
    """
    从 .innerHTML = 所在行起，收集到语句结束（括号/花括号深度归零且遇分号，
    或单行赋值结束）。返回 (block_text, start_line_1based, end_idx_inclusive)。
    """
    line = lines[start_idx]
    # 从 = 之后开始
    eq = line.find("=")
    buf = [line[eq + 1 :]]
    depth_paren = 0
    depth_brace = 0
    depth_bracket = 0
    in_str = None  # ', ", `
    escape = False

    def feed(chunk: str) -> bool:
        """返回 True 表示语句已结束。"""
        nonlocal depth_paren, depth_brace, depth_bracket, in_str, escape
        for ch in chunk:
            if in_str:
                if escape:
                    escape = False
                    continue
                if ch == "\\":
                    escape = True
                    continue
                if ch == in_str:
                    in_str = None
                continue
            if ch in ("'", '"', "`"):
                in_str = ch
                continue
            if ch == "(":
                depth_paren += 1
            elif ch == ")":
                depth_paren = max(0, depth_paren - 1)
            elif ch == "{":
                depth_brace += 1
            elif ch == "}":
                depth_brace = max(0, depth_brace - 1)
            elif ch == "[":
                depth_bracket += 1
            elif ch == "]":
                depth_bracket = max(0, depth_bracket - 1)
            elif ch == ";" and depth_paren == 0 and depth_brace == 0 and depth_bracket == 0:
                return True
        return False

    if feed(buf[0]):
        return buf[0], start_idx + 1, start_idx

    j = start_idx + 1
    while j < len(lines):
        buf.append(lines[j])
        if feed(lines[j]):
            break
        j += 1
        # 安全上限：避免吞掉整个文件
        if j - start_idx > 400:
            break

    return "\n".join(buf), start_idx + 1, min(j, len(lines) - 1)


def _scan_file(path: Path) -> list[tuple[int, str]]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    violations: list[tuple[int, str]] = []
    i = 0
    while i < len(lines):
        if not ASSIGN_RE.search(lines[i]):
            i += 1
            continue

        assign_line = lines[i]
        block, start_line, end_idx = _extract_rhs_statement(lines, i)
        if "${" not in block:
            i = end_idx + 1
            continue

        assign_exempt = bool(SAFE_COMMENT_RE.search(assign_line))

        for m in INTERP_RE.finditer(block):
            expr = m.group(1).strip()
            prefix = block[: m.start()]
            rel = prefix.count("\n")
            abs_line = start_line + rel
            line_text = lines[abs_line - 1] if 0 < abs_line <= len(lines) else assign_line

            if assign_exempt or SAFE_COMMENT_RE.search(line_text):
                continue
            if SAFE_CALL_IN_EXPR.search(expr):
                continue

            violations.append((abs_line, expr[:120]))

        i = end_idx + 1

    return violations


def main() -> int:
    all_violations: list[str] = []
    for path in sorted(_iter_frontend_files()):
        rel = path.relative_to(ROOT).as_posix()
        for lineno, expr in _scan_file(path):
            all_violations.append(f"{rel}:{lineno}: unsafe innerHTML interpolation: ${{{expr}}}")

    for v in all_violations:
        # 避免 Windows GBK 控制台编码问题
        try:
            print(v)
        except UnicodeEncodeError:
            print(v.encode("utf-8", errors="replace").decode("utf-8", errors="replace"))
    if all_violations:
        print(f"\nFound {len(all_violations)} unsafe innerHTML interpolation(s).", file=sys.stderr)
        return 1
    print("OK: no unsafe innerHTML interpolations.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
