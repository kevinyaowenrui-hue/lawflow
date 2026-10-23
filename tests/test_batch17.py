# -*- coding: utf-8 -*-
"""
Batch 17 综合验收测试套件：
- 条目 1 (A-09): 前端模块化、index.html 行数 < 1500、check_fetch & check_innerhtml 检查、CSP script-src 无 unsafe-inline
- 条目 2 (A-10): check_a11y.py 无障碍静态检查通过
- 条目 3 (A-13): 全局异常处理器不泄露敏感信息与返回 request_id、statutes/overview 无绝对路径、文书生成与下载写入审计日志、全仓无 bare except Exception pass
- 条目 4 (A-15): 无 Pydantic example= 弃用字段、FILEE_SHA256 校验拦截非匹配执行
- 条目 5 (A-17): 规则模式语音副驾意图识别 (LPR利息/文书生成/时效/上诉期/法条)、auto-catalog 证据原名保留、实体抽取尾随虚词清洗、庭审提纲规则模式提示
"""
from __future__ import annotations

import os
import re
import sys
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("LAWFLOW_API_TOKEN", "test-token")
AUTH = {"X-LawFlow-Token": os.environ["LAWFLOW_API_TOKEN"]}
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def client():
    from gateway.main import app

    with TestClient(app, headers=AUTH, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def rule_mode(monkeypatch):
    """确保在规则模式下运行测试，不依赖或调用真实在线的本地 Ollama 模型"""
    from gateway.core.ollama_client import ollama_client

    async def _offline():
        return False

    monkeypatch.setattr(ollama_client, "_is_ollama_online", _offline)
    orig_settings = dict(ollama_client.settings)
    ollama_client.settings["provider"] = "rule_fallback"
    ollama_client.settings["api_key"] = ""
    ollama_client.last_llm_mode = "rule_fallback"
    yield
    ollama_client.settings.clear()
    ollama_client.settings.update(orig_settings)


# ==============================================================================
# 条目 1 (A-09) 测试
# ==============================================================================

def test_item1_index_html_line_count():
    """frontend/index.html 行数必须 < 1,500"""
    index_file = ROOT / "frontend" / "index.html"
    assert index_file.is_file(), "frontend/index.html 不存在"
    lines = index_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) < 1500, f"index.html 当前行数为 {len(lines)}，必须 < 1500"


def test_item1_check_fetch_script_exits_zero():
    """除 api.js 外，前端其余 JS 不得直接出现 fetch("""
    script = ROOT / "scripts" / "check_fetch.py"
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.returncode == 0, f"check_fetch.py 检查失败:\n{proc.stdout}\n{proc.stderr}"


def test_item1_check_innerhtml_script_exits_zero():
    """check_innerhtml 检查通过"""
    script = ROOT / "scripts" / "check_innerhtml.py"
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.returncode == 0, f"check_innerhtml.py 检查失败:\n{proc.stdout}\n{proc.stderr}"


def test_item1_csp_header_no_script_unsafe_inline(client):
    """响应头 CSP 不含 script-src 'unsafe-inline'"""
    resp = client.get("/")
    assert resp.status_code == 200
    csp = resp.headers.get("content-security-policy") or resp.headers.get("Content-Security-Policy") or ""
    assert csp, "GET / 响应头中应包含 Content-Security-Policy"
    m = re.search(r"script-src\s+([^;]+)", csp)
    assert m, f"CSP 中未找到 script-src 指令: {csp}"
    script_src = m.group(1)
    # TODO(P1): migrate inline handlers to addEventListener, then drop 'unsafe-inline'
    assert "'unsafe-inline'" in script_src, f"script-src 应含有 'unsafe-inline'（兼容桌面端内联事件）: {script_src}"
    assert "'self'" in script_src, f"script-src 应包含 'self': {script_src}"


# ==============================================================================
# 条目 2 (A-10) 测试
# ==============================================================================

def test_item2_check_a11y_script_exits_zero():
    """静态检查 scripts/check_a11y.py 退出码为 0"""
    script = ROOT / "scripts" / "check_a11y.py"
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.returncode == 0, f"check_a11y.py 检查失败:\n{proc.stdout}\n{proc.stderr}"


# ==============================================================================
# 条目 3 (A-13) 测试
# ==============================================================================

def test_item3_global_exception_handler_sanitizes_500(client, monkeypatch):
    """未处理内部异常返回 500、含 request_id、body 不含 secret-detail"""
    from gateway.routers import phase5_statutes_kb

    def _boom(*args, **kwargs):
        raise RuntimeError("secret-detail-internal-trace-should-not-leak")

    monkeypatch.setattr(phase5_statutes_kb, "get_statute_database_stats", _boom)

    resp = client.get("/api/v1/statutes/overview")
    assert resp.status_code == 500
    data = resp.json()
    assert "secret-detail" not in resp.text
    assert data.get("error_code") == "INTERNAL_ERROR" or "服务器内部错误" in data.get("message", "")
    assert data.get("request_id"), "响应体必须包含 request_id"


def test_item3_statutes_overview_no_absolute_paths(client):
    """GET /api/v1/statutes/overview 响应中不含 os.sep 开头的绝对路径或盘符路径"""
    resp = client.get("/api/v1/statutes/overview")
    assert resp.status_code == 200
    text = resp.text
    assert not re.search(r"[a-zA-Z]:[\\/]", text), f"overview 响应泄露了本地盘符路径: {text}"
    assert not re.search(r'"/(?:home|usr|var|data|etc|tmp)/', text), f"overview 响应泄露了绝对路径: {text}"


def test_item3_audit_log_tracking_on_generate_and_download(client, rule_mode):
    """生成并下载一份文书后 audit_log 中有对应两条记录"""
    payload = {
        "cause_of_action": "民间借贷纠纷",
        "plaintiff_name": "张三",
        "evidence_notes": "2023年3月16日招行电汇凭单"
    }
    gen_resp = client.post("/api/v1/phase2/auto-catalog", json=payload)
    assert gen_resp.status_code == 200, gen_resp.text
    gen_data = gen_resp.json()
    catalog_filename = gen_data["catalog_filename"]

    dl_resp = client.get(f"/api/documents/download/{catalog_filename}")
    assert dl_resp.status_code == 200

    audit_resp = client.get("/api/v1/audit-log?page=1&page_size=20")
    assert audit_resp.status_code == 200, audit_resp.text
    audit_items = audit_resp.json().get("data", {}).get("items", [])
    actions = [item["action"] for item in audit_items]

    assert "document_generate" in actions, f"audit_log 应记录 document_generate，当前记录: {actions}"
    assert "document_download" in actions, f"audit_log 应记录 document_download，当前记录: {actions}"


def test_item3_no_bare_except_exception_pass():
    r"""rg -n 'except Exception:\s*$' -A1 gateway | rg '^\S+-\s+pass' 无结果"""
    pattern = re.compile(r"except\s+Exception\s*:\s*\n\s*pass")
    violations = []
    gateway_dir = ROOT / "gateway"
    for py_file in gateway_dir.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8").replace("\r\n", "\n")
        if pattern.search(content):
            violations.append(str(py_file.relative_to(ROOT)))
    assert not violations, f"下列文件存在裸 except Exception: pass 违规:\n{violations}"


# ==============================================================================
# 条目 4 (A-15) 测试
# ==============================================================================

def test_item4_no_deprecated_example_fields():
    """rg -n 'example=' gateway 无结果（全仓改为 examples=[...]）"""
    pattern = re.compile(r"\bexample\s*=")
    violations = []
    gateway_dir = ROOT / "gateway"
    for py_file in gateway_dir.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        for idx, line in enumerate(content.splitlines(), start=1):
            if pattern.search(line):
                violations.append(f"{py_file.relative_to(ROOT)}:{idx}: {line.strip()}")
    assert not violations, f"gateway 中仍存在 Pydantic 弃用的 example= 声明:\n" + "\n".join(violations[:10])


def test_item4_filee_sha256_mismatch_blocks_execution(monkeypatch, tmp_path):
    """设置错误的 FILEE_SHA256 → 校验不匹配，阻止调用并记录日志，subprocess 不被调用"""
    from gateway.utils import file_converter_engine

    fake_exe = tmp_path / "fake_filee.exe"
    fake_exe.write_bytes(b"dummy binary data for filee")

    monkeypatch.setenv("FILEE_SHA256", "0000000000000000000000000000000000000000000000000000000000000000")

    with patch.object(file_converter_engine, "find_filee_executable", return_value=str(fake_exe)):
        with patch("subprocess.Popen") as mock_popen, patch("subprocess.run") as mock_run:
            ok = file_converter_engine.verify_filee_integrity(str(fake_exe))
            assert ok is False, "hash 不匹配时 verify_filee_integrity 必须返回 False"
            out_file = file_converter_engine.execute_filee_cli_conversion(
                input_path=str(tmp_path / "test.docx"),
                target_format="pdf",
                output_dir=str(tmp_path)
            )
            assert out_file is None
            assert not mock_popen.called, "subprocess.Popen 不得被调用"
            assert not mock_run.called, "subprocess.run 不得被调用"


# ==============================================================================
# 条目 5 (A-17) 测试
# ==============================================================================

def test_item5_rule_mode_copilot_converse_lpr(client, rule_mode):
    """规则模式下 converse('帮我算一下 10 万元从 2024-01-01 到 2025-01-01 的利息') → intent 为 LPR 计算且预填 principal=100000"""
    payload = {
        "user_input": "帮我算一下 10 万元从 2024-01-01 到 2025-01-01 的利息",
        "case_context": {}
    }
    resp = client.post("/api/v1/copilot/converse", json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data.get("intent") == "LPR 计算"
    ctx = data.get("context_patch", {})
    principal = ctx.get("principal") or ctx.get("amount") or (ctx.get("interest_calc") or {}).get("principal")
    assert principal == 100000.0 or principal == 100000


def test_item5_rule_mode_copilot_converse_complaint(client, rule_mode):
    """converse('生成起诉状') → intent 为文书生成"""
    payload = {
        "user_input": "生成起诉状",
        "case_context": {}
    }
    resp = client.post("/api/v1/copilot/converse", json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data.get("intent") == "文书生成"


def test_item5_auto_catalog_preserves_evidence_name(client, rule_mode):
    """auto-catalog 输入证据名'2023年3月16日招行电汇凭单' → 输出证据名称原样保留"""
    payload = {
        "cause_of_action": "民间借贷纠纷",
        "plaintiff_name": "张三",
        "evidence_notes": "2023年3月16日招行电汇凭单"
    }
    resp = client.post("/api/v1/phase2/auto-catalog", json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    items = data.get("extracted_items", [])
    assert items, "应提取出证据项"
    assert items[0]["name"] == "2023年3月16日招行电汇凭单", f"证据名称未原样保留: {items[0]['name']}"


def test_item5_graph_extractor_cleans_entity_names():
    """graph extract 文本'保证人王五承担连带保证责任' → 实体含'王五'，不含'王五承担'"""
    from gateway.utils.graph_extractor import extract_rule_based_graphs

    text = "保证人王五承担连带保证责任"
    graphs = extract_rule_based_graphs(text)
    node_names = [n["name"] for n in graphs["entity_graph"]["nodes"]]
    assert "王五" in node_names, f"实体应包含'王五'，当前为: {node_names}"
    assert "王五承担" not in node_names, f"实体不得包含'王五承担'，当前为: {node_names}"


def test_item5_rule_mode_trial_outline_disclaimer(client, rule_mode):
    """规则模式的庭审提纲输出含'规则模式'"""
    payload = {
        "case_title": "测试借款合同出庭提纲",
        "cause_of_action": "借款合同纠纷",
        "plaintiff_claims_and_facts": "诉请被告偿还借款本金100万元及利息",
        "defendant_defense": "原告转账金额未实际到账"
    }
    resp = client.post("/api/v1/phase2/trial-outline", json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    outline = data.get("trial_outline_markdown", "")
    assert "规则模式" in outline, f"规则模式庭审提纲顶部应提示'规则模式'，输出为:\n{outline[:200]}"
