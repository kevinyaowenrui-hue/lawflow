# -*- coding: utf-8 -*-
"""
三模块行覆盖率门禁（各 >= 80%）。

默认 skip；本地/CI 显式开启：
  set RUN_COVERAGE_GATE=1
  .venv\\Scripts\\python.exe -m pytest tests/test_coverage_gate.py -m slow -q

优先读取已有 coverage.xml（避免嵌套全量套件）；若无则对核心用例做一次聚焦覆盖测量。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE_FILES = (
    "cn_legal_calc.py",
    "citation_guard.py",
    "guarantee_and_cashflow_engine.py",
)
FOCUS_TESTS = [
    "tests/test_coverage_core_modules.py",
    "tests/test_batch5_calc_engine.py",
    "tests/test_calc_validation.py",
    "tests/test_citation_guard_logic.py",
    "tests/test_guarantee_engine.py",
    "tests/test_p2_guarantee_and_cashflow.py",
    "tests/test_lawyer_cases.py",
]


def _scores_from_cobertura(xml_path: Path) -> dict[str, float]:
    root = ET.parse(xml_path).getroot()
    scores: dict[str, float] = {}
    for cls in root.iter("class"):
        filename = (cls.attrib.get("filename") or "").replace("\\", "/")
        name = filename.rsplit("/", 1)[-1]
        if name not in MODULE_FILES:
            continue
        valid = float(cls.attrib.get("lines-valid") or 0)
        covered = float(cls.attrib.get("lines-covered") or 0)
        if valid > 0:
            pct = 100.0 * covered / valid
        else:
            pct = float(cls.attrib.get("line-rate") or 0) * 100.0
        scores[name] = pct
    return scores


def _scores_from_json(report: Path) -> dict[str, float]:
    data = json.loads(report.read_text(encoding="utf-8"))
    scores: dict[str, float] = {}
    for path, meta in (data.get("files") or {}).items():
        norm = path.replace("\\", "/")
        for marker in MODULE_FILES:
            if norm.endswith(marker) or marker in norm:
                pct = float((meta.get("summary") or {}).get("percent_covered") or 0.0)
                scores[marker] = pct
    return scores


@pytest.mark.slow
def test_three_core_modules_line_coverage_ge_80(tmp_path):
    if os.environ.get("RUN_COVERAGE_GATE") != "1":
        pytest.skip("Set RUN_COVERAGE_GATE=1 to enforce three-module coverage gate")
    if os.environ.get("COVERAGE_GATE_CHILD") == "1":
        pytest.skip("nested coverage-gate child")

    existing = ROOT / "coverage.xml"
    scores: dict[str, float] = {}
    if existing.is_file():
        scores = _scores_from_cobertura(existing)

    if len(scores) < len(MODULE_FILES):
        report = tmp_path / "coverage_gate_three.json"
        env = os.environ.copy()
        env["COVERAGE_GATE_CHILD"] = "1"
        cmd = [
            sys.executable,
            "-m",
            "pytest",
            *FOCUS_TESTS,
            "--cov=gateway.utils.cn_legal_calc",
            "--cov=gateway.utils.citation_guard",
            "--cov=gateway.utils.guarantee_and_cashflow_engine",
            f"--cov-report=json:{report}",
            "--cov-report=term",
            "-q",
            "--disable-warnings",
        ]
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if not report.is_file():
            pytest.fail(
                "coverage JSON missing.\n"
                f"exit={proc.returncode}\nstdout:\n{proc.stdout[-2000:]}\nstderr:\n{proc.stderr[-2000:]}"
            )
        scores = _scores_from_json(report)

    missing = [m for m in MODULE_FILES if m not in scores]
    if missing:
        pytest.fail(f"coverage report missing modules: {missing}; got={list(scores)}")

    failed = {k: v for k, v in scores.items() if v < 80.0}
    assert not failed, (
        "line coverage must be >= 80% for each module; "
        f"below={failed}; all={scores}"
    )
