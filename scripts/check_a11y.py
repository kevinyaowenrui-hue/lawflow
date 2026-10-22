# -*- coding: utf-8 -*-
"""
scripts/check_a11y.py:
静态无障碍 (Accessibility) 检查工具：
1. 检查所有出现 onclick 的 <div> 或 <span> 必须声明 role 或 tabindex；
2. 检查所有 <input>、<select>、<textarea>（除 type="hidden" 外）必须有关联的 label（<label for=...>）或 aria-label/aria-labelledby。
凡违规项输出 文件:行号 并以退出码 1 退出。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"

DIV_SPAN_CLICK_RE = re.compile(r"<(div|span)\b([^>]*?onclick=[^>]*?)>", re.IGNORECASE | re.DOTALL)
ROLE_RE = re.compile(r"\brole\s*=", re.IGNORECASE)
TABINDEX_RE = re.compile(r"\btabindex\s*=", re.IGNORECASE)

FORM_CONTROL_RE = re.compile(r"<(input|select|textarea)\b([^>]*?)>", re.IGNORECASE | re.DOTALL)
ARIA_LABEL_RE = re.compile(r"\baria-label(?:ledby)?\s*=", re.IGNORECASE)
TYPE_HIDDEN_RE = re.compile(r"\btype\s*=\s*['\"]hidden['\"]", re.IGNORECASE)
ID_RE = re.compile(r"\bid\s*=\s*['\"]([^'\"]+)['\"]", re.IGNORECASE)
LABEL_FOR_RE = re.compile(r"<label\b[^>]*?\bfor\s*=\s*['\"]([^'\"]+)['\"]", re.IGNORECASE)


def _iter_frontend_files():
    if not FRONTEND.is_dir():
        return
    for path in FRONTEND.rglob("*"):
        if path.suffix.lower() in (".html", ".js") and path.is_file():
            parts = [p.lower() for p in path.parts]
            if "vendor" in parts:
                continue
            yield path


def collect_labels(content: str) -> set[str]:
    return set(LABEL_FOR_RE.findall(content))


def check_file(path: Path, all_label_ids: set[str]) -> list[str]:
    text = path.read_text(encoding="utf-8")
    rel = path.relative_to(ROOT).as_posix()
    violations: list[str] = []

    # 1. 检查 div / span onclick 具备 role 或 tabindex
    for m in DIV_SPAN_CLICK_RE.finditer(text):
        tag_name = m.group(1).lower()
        attrs = m.group(2)
        if not ROLE_RE.search(attrs) and not TABINDEX_RE.search(attrs):
            line_no = text[: m.start()].count("\n") + 1
            snippet = m.group(0).replace("\n", " ")[:90]
            violations.append(
                f"{rel}:{line_no}: <{tag_name}> with onclick missing role and tabindex: {snippet}"
            )

    # 2. 检查表单控件具名
    file_labels = collect_labels(text) | all_label_ids
    for m in FORM_CONTROL_RE.finditer(text):
        tag_name = m.group(1).lower()
        attrs = m.group(2)
        if tag_name == "input" and TYPE_HIDDEN_RE.search(attrs):
            continue
        if ARIA_LABEL_RE.search(attrs):
            continue
        id_m = ID_RE.search(attrs)
        if id_m and id_m.group(1) in file_labels:
            continue
        line_no = text[: m.start()].count("\n") + 1
        snippet = m.group(0).replace("\n", " ")[:90]
        violations.append(
            f"{rel}:{line_no}: <{tag_name}> missing label / aria-label: {snippet}"
        )

    return violations


def count_a11y_metrics():
    total_aria = 0
    total_label_for = 0
    total_clickable_div_span = 0

    aria_pattern = re.compile(r"\baria-[a-z\-]+\s*=", re.IGNORECASE)
    div_span_pattern = re.compile(r"<(?:div|span)\b[^>]*?onclick=", re.IGNORECASE)

    for path in _iter_frontend_files():
        try:
            content = path.read_text(encoding="utf-8")
        except Exception:
            continue
        total_aria += len(aria_pattern.findall(content))
        total_label_for += len(LABEL_FOR_RE.findall(content))
        total_clickable_div_span += len(div_span_pattern.findall(content))

    return {
        "aria_attributes": total_aria,
        "label_for_count": total_label_for,
        "clickable_div_span": total_clickable_div_span,
    }


def main() -> int:
    all_label_ids: set[str] = set()
    files = list(_iter_frontend_files())
    for p in files:
        try:
            all_label_ids |= collect_labels(p.read_text(encoding="utf-8"))
        except Exception:
            pass

    all_violations: list[str] = []
    for p in sorted(files):
        all_violations.extend(check_file(p, all_label_ids))

    for v in all_violations:
        try:
            print(v)
        except UnicodeEncodeError:
            print(v.encode("utf-8", errors="replace").decode("utf-8", errors="replace"))

    metrics = count_a11y_metrics()
    print(f"\n[A11Y Metrics] aria-* attributes: {metrics['aria_attributes']}, <label for>: {metrics['label_for_count']}, clickable div/span: {metrics['clickable_div_span']}")

    if all_violations:
        print(f"Found {len(all_violations)} accessibility violation(s).", file=sys.stderr)
        return 1
    print("OK: no accessibility violations found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
