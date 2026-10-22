# -*- coding: utf-8 -*-
"""批次10 S-20：禁用绝对化/虚假背书表述；代表性接口与起诉状页脚含统一免责声明。"""
from __future__ import annotations

import os
from pathlib import Path

import docx
import pytest

from gateway.utils.disclaimer import DISCLAIMER

ROOT = Path(__file__).resolve().parents[1]

BANNED = [
    "零幻觉",
    "100%现行有效",
    "官方现行有效",
    "验真通过",
    "符合最高人民法院",
    "符合最高院",
    "绝对",
    "彻底",
    "顶格",
    "红圈所",
    "生死局",
    "粉碎",
    "铁证",
    "必胜",
]

SCAN_ROOTS = [
    ROOT / "gateway",
    ROOT / "frontend",
    ROOT / "templates" / "scripts",
    ROOT / "README.md",
]
SCAN_EXTS = {".py", ".html", ".md", ".yml", ".yaml"}


def _iter_scan_files():
    for root in SCAN_ROOTS:
        if root.is_file():
            yield root
            continue
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            if p.suffix.lower() not in SCAN_EXTS:
                continue
            parts = set(p.parts)
            if "tests" in parts or "demo" in parts or "__pycache__" in parts:
                continue
            yield p


def test_no_banned_wording_in_product_sources():
    offenders = []
    for path in _iter_scan_files():
        text = path.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), 1):
            for word in BANNED:
                if word in line:
                    offenders.append(f"{path.relative_to(ROOT)}:{i}: 含「{word}」")
    assert not offenders, "发现禁用表述:\n" + "\n".join(offenders[:50])


def test_disclaimer_constant():
    assert DISCLAIMER == "本输出由软件自动生成，仅供执业律师参考，不构成法律意见，须经律师审核后使用。"


@pytest.mark.parametrize(
    "path,payload",
    [
        (
            "/api/v1/phase1/calc/lpr-interest",
            {
                "principal": 100000,
                "start_date": "2023-01-01",
                "end_date": "2023-07-01",
                "multiplier": 1.0,
                "term": "1Y",
            },
        ),
        (
            "/api/v1/guard/audit-citations",
            {"text": "依据《中华人民共和国民法典》第五百七十九条之规定。", "auto_sanitize": True},
        ),
        (
            "/api/v1/conflict/check",
            {
                "client_name": "北京创新未来科技有限公司",
                "opposing_party": "广州星海传媒有限公司",
                "case_subject": "商标权纠纷",
            },
        ),
        (
            "/api/v1/enforcement/penetration-audit",
            {
                "case_title": "测试执行案",
                "claim_amount": 1000000,
                "debtor_name": "某公司",
                "use_demo": False,
            },
        ),
    ],
)
def test_representative_apis_include_disclaimer(client, path, payload):
    resp = client.post(path, json=payload)
    assert resp.status_code == 200, f"{path} -> {resp.status_code}: {resp.text[:400]}"
    data = resp.json()
    assert isinstance(data, dict)
    assert data.get("disclaimer") == DISCLAIMER


def test_litigation_package_and_docx_footer_disclaimer(client, monkeypatch):
    from gateway.core.ollama_client import ollama_client

    async def _offline(*args, **kwargs):
        return False

    monkeypatch.setattr(ollama_client, "_is_ollama_online", _offline)
    monkeypatch.setattr(
        ollama_client, "settings", {**ollama_client.settings, "provider": "ollama", "api_key": ""}
    )

    resp = client.post(
        "/api/v1/phase1/generate-litigation-package",
        json={
            "cause_of_action": "民间借贷纠纷",
            "claim_amount": 200000,
            "raw_case_notes": "2023年1月1日被告向原告借款20万元，约定借期一年，到期未还。",
            "court_name": "北京市朝阳区人民法院",
            "plaintiff": {
                "name": "测试原告甲",
                "id_card_or_uscc": "110101199003072340",
                "address": "北京市朝阳区测试路1号",
                "phone": "13800000001",
            },
            "defendant": {
                "name": "测试被告乙",
                "id_card_or_uscc": "110101199003072351",
                "address": "北京市海淀区测试路2号",
                "phone": "13800000002",
            },
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data.get("disclaimer") == DISCLAIMER

    docs = data.get("generated_documents") or data.get("documents") or []
    docx_path = None
    for d in docs:
        p = d.get("path") or ""
        if p.endswith(".docx") and ("起诉状" in (d.get("doc_type") or "") or "起诉状" in p or "民事" in p):
            docx_path = p
            break
    if not docx_path and docs:
        docx_path = docs[0].get("path")
    if not docx_path:
        # 兼容字段名
        docx_path = data.get("main_docx_path")
    assert docx_path and os.path.isfile(docx_path), f"未找到起诉状 docx: {data.keys()}"

    d = docx.Document(docx_path)
    footer_text = []
    for section in d.sections:
        for p in section.footer.paragraphs:
            footer_text.append(p.text or "")
    blob = "\n".join(footer_text)
    assert DISCLAIMER in blob, f"页脚未含免责声明: {blob!r}"
