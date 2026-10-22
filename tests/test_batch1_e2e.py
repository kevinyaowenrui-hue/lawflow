# -*- coding: utf-8 -*-
"""
Batch 1 端到端实证：PII 脱敏、案号防火墙、审查 Playbook、Word 原生修订导出。
"""
from __future__ import annotations

import os
import zipfile

import pytest

from gateway.utils.pii_sanitizer import PIISanitizer
from gateway.core.ollama_client import UniversalLLMClient
from gateway.utils.citation_guard import (
    verify_single_case_number,
    audit_citations_in_text,
)
from gateway.utils.redline_builder import (
    PLAYBOOK_PRESETS,
    compute_text_diff_chunks,
    build_redline_contract_docx,
)
from gateway.core.paths import get_generated_dir


SAMPLE_PII_PROMPT = (
    "甲方：北京智律科技有限公司（统一社会信用代码：91110108MA01XXXXXX），"
    "法定代表人：张伟，身份证号：110101199003072345，联系电话：13800138000，"
    "收款银行卡号：6222021001001234567，电子邮箱：zhangwei@lawtech.com。"
)


def test_pii_mask_removes_sensitive_fields():
    masked, mapping = PIISanitizer.mask_text(
        SAMPLE_PII_PROMPT, known_parties=["北京智律科技有限公司", "张伟"]
    )
    assert "110101199003072345" not in masked
    assert "13800138000" not in masked
    assert "6222021001001234567" not in masked
    assert "91110108MA01XXXXXX" not in masked
    assert "zhangwei@lawtech.com" not in masked
    assert "张伟" not in masked
    assert len(mapping) >= 5


def test_pii_unmask_roundtrip_exact():
    masked, mapping = PIISanitizer.mask_text(
        SAMPLE_PII_PROMPT, known_parties=["北京智律科技有限公司", "张伟"]
    )
    unmasked = PIISanitizer.unmask_text(masked, mapping)
    assert unmasked == SAMPLE_PII_PROMPT


def test_universal_llm_client_pii_shield_enabled_by_default():
    llm = UniversalLLMClient()
    assert llm.pii_shield_enabled is True


def test_verified_precedent_case_number():
    """原脚本断言 VERIFIED_PRECEDENT；批次4起演示判例须标 is_demo 并拦截为 DEMO_DATA_BLOCKED。"""
    true_case_res = verify_single_case_number("（2023）最高法民终123号")
    assert true_case_res["status"] == "DEMO_DATA_BLOCKED"
    assert true_case_res.get("risk_level") == "CRITICAL_BLOCKED"
    notes = true_case_res.get("notes") or ""
    assert "演示" in notes or "不可用于正式文书" in notes


def test_hallucinated_case_number_blocked():
    fake_case_res = verify_single_case_number("（2099）最高法知民终9999号")
    assert fake_case_res["is_hallucination"] is True
    assert fake_case_res["risk_level"] == "CRITICAL_BLOCKED"


def test_hybrid_document_citation_audit_detects_abrogated_and_hallucination():
    hybrid_doc = """
    依据《中华人民共和国合同法》第五十二条及《中华人民共和国民法典》第五百七十七条，
    参照最高人民法院（2023）最高法民终123号裁判要旨，
    并注意避免（2099）京01民初8888号判例中认定的无效情形。
    """
    full_audit = audit_citations_in_text(hybrid_doc, auto_sanitize=True)
    assert full_audit["has_abrogated_laws"] is True
    assert full_audit["has_hallucinations"] is True
    assert len(full_audit["case_numbers"]) == 2


def test_playbook_presets_loaded():
    assert "tech_service" in PLAYBOOK_PRESETS
    assert "procurement" in PLAYBOOK_PRESETS
    tech_preset = PLAYBOOK_PRESETS["tech_service"]
    assert tech_preset.get("name")
    assert len(tech_preset["rules"]) >= 1


@pytest.mark.requires_ollama
def test_contract_review_playbook_deviation():
    import asyncio
    from gateway.routers.phase2_evidence import review_contract_clauses, ContractReviewReq

    sample_contract = (
        "第3条 知识产权归属：乙方为甲方开发的所有源代码及交付物，其全部知识产权归甲方独家所有。\n"
        "第6条 违约责任：乙方迟延交付每日需支付总合同金额 5% 的违约金，累计无上限。"
    )
    req = ContractReviewReq(
        perspective="乙方 (开发方/受托方)",
        contract_text=sample_contract,
        playbook_preset="tech_service",
    )
    review_resp = asyncio.run(review_contract_clauses(req))
    assert review_resp["status"] == "success"
    clauses = review_resp["review"].get("clause_reviews", [])
    assert len(clauses) >= 1
    assert clauses[0].get("playbook_deviation") in [
        "OUT_OF_SCOPE_DEVIATION",
        "CRITICAL_BREACH",
        "COMPLIANT",
    ]


def test_text_diff_chunks_have_insert_and_delete():
    orig_clause = "乙方迟延交付每日按总价款 5% 支付违约金，且上不封顶。"
    sugg_clause = (
        "乙方迟延交付每日按未履约部分金额 0.05% 支付违约金，"
        "累计违约金总额不超过合同总金额的 10%。"
    )
    diff_chunks = compute_text_diff_chunks(orig_clause, sugg_clause)
    assert any(c.get("type") == "insert" for c in diff_chunks)
    assert any(c.get("type") == "delete" for c in diff_chunks)


def test_build_redline_docx_contains_track_changes_markup(tmp_path, monkeypatch):
    monkeypatch.setenv("LAWFLOW_STORAGE_DIR", str(tmp_path))
    orig_clause = "乙方迟延交付每日按总价款 5% 支付违约金，且上不封顶。"
    sugg_clause = (
        "乙方迟延交付每日按未履约部分金额 0.05% 支付违约金，"
        "累计违约金总额不超过合同总金额的 10%。"
    )
    output_docx = str(get_generated_dir() / "test_verified_redline.docx")
    mock_reviews = [
        {
            "clause_id": 1,
            "clause_title": "第6条 违约责任与封顶",
            "risk_analysis": "单日 5% 违约金严重过高且无上限，将导致乙方承担无法预测的倾覆性履约风险。",
            "original_clause": orig_clause,
            "suggested_clause": sugg_clause,
            "negotiation_tip": "提出最高法院司法解释 30% 实际损失上限抗辩，并要求违约金基数限定为未交付部分。",
            "playbook_deviation": "CRITICAL_BREACH",
            "matched_playbook_rule": "违约金总额必须设定封顶线（通常不超过合同金额 10%~20%）",
            "deviation_reason": "单日5%且无封顶突破行业红线",
        }
    ]
    docx_path = build_redline_contract_docx(
        contract_title="软件服务外包协议_修订版",
        original_contract_text=orig_clause,
        clause_reviews=mock_reviews,
        perspective="乙方防御版",
        playbook_name="软件开发与技术服务红线库",
        playbook_rules=["违约金总额必须设定封顶线（通常不超过合同金额 10%~20%）"],
        output_path=output_docx,
    )
    assert os.path.exists(docx_path)
    assert os.path.getsize(docx_path) > 0

    with zipfile.ZipFile(docx_path, "r") as zf:
        doc_xml = zf.read("word/document.xml").decode("utf-8")
        assert "<w:del " in doc_xml
        assert "<w:ins " in doc_xml
        assert "<w:delText" in doc_xml
        settings_xml = zf.read("word/settings.xml").decode("utf-8")
        assert "w:trackRevisions" in settings_xml
