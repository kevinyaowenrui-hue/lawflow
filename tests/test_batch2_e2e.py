# -*- coding: utf-8 -*-
"""
Batch 2 End-to-End：案件独立空间、核心图谱抽取、人机协同断点工作流。
"""
from __future__ import annotations

import pytest


@pytest.fixture
def vault_ready(client, seed_demo):
    from gateway.utils.matter_vault_db import init_matter_vault_db

    init_matter_vault_db()
    return client


@pytest.fixture
def loan_matter(vault_ready):
    client = vault_ready
    payload = {
        "title": "深圳市腾飞智联供应链民间借贷与股权质押清算纠纷案",
        "cause_of_action": "民间借贷纠纷",
        "case_number": "(2026)粤0305民初9988号",
        "court_name": "深圳市南山区人民法院",
        "principal_amount": 3500000.0,
        "plaintiff_name": "深圳腾飞前海投资合伙企业",
        "defendant_name": "智联创展网络科技（深圳）有限公司",
        "summary": (
            "2023年6月10日借款350万元，年利率14.5%，约定1年期满清偿。"
            "借款人逾期未还，实控人出具最高额个人无限连带责任保证书。"
        ),
    }
    resp = client.post("/api/v1/vault/matters", json=payload)
    assert resp.status_code == 200, resp.text
    matter = resp.json()["matter"]
    matter_id = matter["matter_id"]

    doc_payload = {
        "doc_title": "《借款合同及个人保证书补充协议》.docx",
        "doc_type": "contract",
        "content_text": (
            "甲方出借350万元整，乙方于2024年6月9日前一次性还本付息。"
            "如逾期，按全国银行间同业拆借中心公布的LPR四倍计付逾期利息。"
            "丙方张总承担连带保证责任。"
        ),
    }
    doc_resp = client.post(f"/api/v1/vault/matters/{matter_id}/documents", json=doc_payload)
    assert doc_resp.status_code == 200, doc_resp.text
    return matter_id


STEP2_DECISIONS = {
    "step": 2,
    "human_decisions": {
        "confirmed_claims": [
            "判令被告偿还借款本金人民币3,500,000.00元",
            "判令被告支付利息及逾期利息（严格按借款合同约定年利率14.5%计付至实际清偿日止）",
            "判令保证人张总对上述第一、二项债务承担连带清偿保证责任",
            "判令被告承担本案全部诉讼费、保全费",
        ],
        "confirmed_statutes": [
            "《中华人民共和国民法典》第六百六十七条",
            "《中华人民共和国民法典》第六百七十四条",
            "《中华人民共和国民法典》第六百八十八条",
        ],
        "cause_of_action": "民间借贷纠纷",
        "lawyer_notes": (
            "重点强调张总签署最高额保证协议未约定保证方式，依据民法典686条第2款已推定为一般保证？"
            "不，合同明确约定承担连带保证责任。"
        ),
    },
}

STEP4_DECISIONS = {
    "step": 4,
    "human_decisions": {
        "accepted_counter_strategies": [
            "提交银行大额电汇回单及资金对手方流向凭证，证明350万元款项已实际足额交付借款人账户，借款合同已依法生效履行",
            "提交微信催款记录与中国邮政EMS律师催告函签收回执，封死3年诉讼时效抗辩空间",
            "向法庭出示《借款合同及个人保证书》原件，重点援引合同第8条'承担连带清偿保证责任'明文约定条款",
        ],
        "lawyer_defense_notes": (
            "若被告抗辩利率超标，出具全国银行间同业拆借中心公布的LPR 4倍计算上限对照表，"
            "锁定14.5%合法有效性。"
        ),
    },
}


def test_health_and_matter_vault_available(vault_ready):
    client = vault_ready
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json().get("status") == "healthy"
    matters = client.get("/api/v1/vault/matters")
    assert matters.status_code == 200, matters.text


def test_seeded_matters_list_nonempty(vault_ready):
    client = vault_ready
    resp = client.get("/api/v1/vault/matters")
    assert resp.status_code == 200
    matters_list = resp.json().get("matters", [])
    assert len(matters_list) >= 2


def test_create_matter_and_mount_document(loan_matter, vault_ready):
    client = vault_ready
    matter_id = loan_matter
    resp = client.get(f"/api/v1/vault/matters/{matter_id}/documents")
    assert resp.status_code == 200
    docs = resp.json()["documents"]
    assert len(docs) == 1
    assert docs[0]["doc_title"] == "《借款合同及个人保证书补充协议》.docx"


@pytest.mark.requires_ollama
def test_core_case_graphs_extraction(loan_matter, vault_ready):
    client = vault_ready
    resp = client.post(f"/api/v1/vault/matters/{loan_matter}/graphs/extract")
    assert resp.status_code == 200, resp.text
    graphs = resp.json()["graphs"]
    timeline = graphs.get("timeline", [])
    entity_graph = graphs.get("entity_graph", {})
    cashflow = graphs.get("cashflow", [])
    assert len(timeline) >= 1
    assert len(entity_graph.get("nodes", [])) >= 2
    assert len(cashflow) >= 1


@pytest.fixture
def started_workflow(loan_matter, vault_ready):
    client = vault_ready
    start_payload = {
        "matter_id": loan_matter,
        "initial_facts": (
            "原告于2023年6月10日向被告转账350万元，约定借期1年，年利率14.5%，"
            "保证人张总签字承诺承担连带保证责任。借款到期后原告多次通过电话催收无果，"
            "被告至今拖欠本金及利息。"
        ),
        "cause_of_action": "民间借贷纠纷",
    }
    resp = client.post("/api/v1/vault/workflows/start", json=start_payload)
    assert resp.status_code == 200, resp.text
    return resp.json()["workflow"]


@pytest.mark.requires_ollama
def test_workflow_starts_at_step2_waiting_human(started_workflow):
    wf = started_workflow
    assert wf["current_step"] == 2
    assert wf["status"] == "WAITING_HUMAN_CONFIRMATION"
    assert len(wf["step2_claims"]["candidate_claims"]) >= 2
    assert len(wf["step2_claims"]["applicable_statutes"]) >= 2


@pytest.mark.requires_ollama
def test_workflow_advance_step2_to_step4(vault_ready, started_workflow):
    client = vault_ready
    wf_id = started_workflow["workflow_id"]
    resp = client.post(f"/api/v1/vault/workflows/{wf_id}/advance", json=STEP2_DECISIONS)
    assert resp.status_code == 200, resp.text
    wf = resp.json()["workflow"]
    assert wf["current_step"] == 4
    assert wf["status"] == "WAITING_HUMAN_CONFIRMATION"
    assert len(wf["step3_statutes"]["opponent_defense_predictions"]) >= 2


@pytest.mark.requires_ollama
def test_workflow_rollback_to_step2(vault_ready, started_workflow):
    client = vault_ready
    wf_id = started_workflow["workflow_id"]
    adv = client.post(f"/api/v1/vault/workflows/{wf_id}/advance", json=STEP2_DECISIONS)
    assert adv.status_code == 200, adv.text
    resp = client.post(f"/api/v1/vault/workflows/{wf_id}/rollback", json={"target_step": 2})
    assert resp.status_code == 200, resp.text
    wf_rolled = resp.json()["workflow"]
    assert wf_rolled["current_step"] == 2
    assert wf_rolled["status"] == "WAITING_HUMAN_CONFIRMATION"


@pytest.mark.requires_ollama
def test_workflow_completes_with_final_draft(vault_ready, started_workflow):
    client = vault_ready
    wf_id = started_workflow["workflow_id"]
    adv2 = client.post(f"/api/v1/vault/workflows/{wf_id}/advance", json=STEP2_DECISIONS)
    assert adv2.status_code == 200, adv2.text
    # may already be at step 4; if rollback was not done, re-advance from step 2 path
    wf = adv2.json()["workflow"]
    if wf["current_step"] == 2:
        adv2 = client.post(f"/api/v1/vault/workflows/{wf_id}/advance", json=STEP2_DECISIONS)
        assert adv2.status_code == 200, adv2.text
    resp = client.post(f"/api/v1/vault/workflows/{wf_id}/advance", json=STEP4_DECISIONS)
    assert resp.status_code == 200, resp.text
    wf_final = resp.json()["workflow"]
    assert wf_final["current_step"] == 5
    assert wf_final["status"] == "COMPLETED"
    final_draft = wf_final["step5_final_draft"]
    assert "民事起诉状" in final_draft["final_pleading_text"]
    assert "诉讼请求：" in final_draft["final_pleading_text"]
    assert "事实与理由：" in final_draft["final_pleading_text"]
    assert len(final_draft["final_pleading_text"]) > 400
    assert "citation_audit" in final_draft
    assert final_draft["citation_audit"].get("has_abrogated_laws") is False
