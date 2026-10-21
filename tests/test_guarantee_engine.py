# -*- coding: utf-8 -*-
"""
批次 6：保证与资金流水引擎验收用例（S-17 / I-06 / I-08 / I-09 / I-10）。
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient

from gateway.main import app
from gateway.utils.cn_legal_calc import add_months_exact
from gateway.utils.guarantee_and_cashflow_engine import (
    analyze_guarantee_topology_and_deadlines,
    audit_and_reconcile_cashflow,
)
from gateway.utils.matter_vault_db import (
    create_new_matter,
    init_matter_vault_db,
    save_matter_graphs_db,
)

AUTH = {"X-LawFlow-Token": os.environ.get("LAWFLOW_API_TOKEN", "test-token")}
client = TestClient(app, headers=AUTH)
init_matter_vault_db()


# ---------------------------------------------------------------------------
# I-06 add_months_exact
# ---------------------------------------------------------------------------

def test_add_months_exact_march_31_plus_6():
    assert add_months_exact(date(2026, 3, 31), 6) == date(2026, 9, 30)


def test_add_months_exact_aug_31_plus_6_non_leap():
    assert add_months_exact(date(2026, 8, 31), 6) == date(2027, 2, 28)


def test_add_months_exact_aug_31_plus_6_leap():
    assert add_months_exact(date(2027, 8, 31), 6) == date(2028, 2, 29)


def test_agreed_expiry_before_principal_due_treated_as_no_agreement():
    nodes = [
        {"id": "e1", "name": "债权人", "role": "原告/债权人", "type": "person"},
        {"id": "e2", "name": "债务人", "role": "主债务人/被告", "type": "person"},
        {"id": "e3", "name": "保证人甲", "role": "保证人", "type": "person"},
    ]
    edges = [
        {
            "source": "e3",
            "target": "e1",
            "relation": "保证",
            "detail": "连带保证",
            "guarantee_mode": "joint",
            "agreed_guarantee_expiry": "2026-03-01",
        }
    ]
    res = analyze_guarantee_topology_and_deadlines(
        nodes, edges, principal_due_date="2026-03-31", today_date="2026-04-01"
    )
    g = res["guarantee_audits"][0]
    assert g["guarantee_expiry_date"] == "2026-09-30"
    assert "视为没有约定" in g.get("period_basis", "")


def test_agreed_period_text_until_paid_treated_as_unclear():
    nodes = [
        {"id": "e1", "name": "债权人", "role": "原告/债权人", "type": "person"},
        {"id": "e2", "name": "债务人", "role": "主债务人/被告", "type": "person"},
        {"id": "e3", "name": "保证人乙", "role": "保证人", "type": "person"},
    ]
    edges = [
        {
            "source": "e3",
            "target": "e1",
            "relation": "保证",
            "detail": "连带",
            "guarantee_mode": "joint",
            "agreed_period_text": "保证期间直至主债务本息还清时为止",
        }
    ]
    res = analyze_guarantee_topology_and_deadlines(
        nodes, edges, principal_due_date="2026-03-31", today_date="2026-04-01"
    )
    g = res["guarantee_audits"][0]
    assert g["guarantee_expiry_date"] == "2026-09-30"
    assert "约定不明" in g.get("period_basis", "") or "六个月" in g.get("period_basis", "")


# ---------------------------------------------------------------------------
# S-17 guarantee mode / demand / insufficient_data
# ---------------------------------------------------------------------------

def test_s17_joint_lawyer_letter_safe():
    nodes = [
        {"id": "e1", "name": "债权人A", "role": "原告/债权人", "type": "person"},
        {"id": "e2", "name": "债务人B", "role": "主债务人/被告", "type": "person"},
        {"id": "e3", "name": "保证人丙", "role": "保证人", "type": "person"},
    ]
    edges = [
        {
            "source": "e3",
            "target": "e1",
            "relation": "保证",
            "detail": "承担连带保证责任",
        }
    ]
    timeline = [
        {
            "date": "2026-05-01",
            "event": "向保证人丙发送律师函催告承担保证责任",
            "legal_tag": "催要主张",
        }
    ]
    res = analyze_guarantee_topology_and_deadlines(
        nodes,
        edges,
        timeline,
        principal_due_date="2026-03-31",
        today_date="2026-10-21",
    )
    g = res["guarantee_audits"][0]
    assert g["guarantee_type"].startswith("连带责任保证")
    assert g["status"] == "SAFE" or g["status"].startswith("SAFE")
    assert "694" not in g["warning_message"]


def test_s17_general_sue_debtor_safe_lawyer_letter_not():
    nodes = [
        {"id": "e1", "name": "债权人A", "role": "原告/债权人", "type": "person"},
        {"id": "e2", "name": "债务人B", "role": "主债务人/被告", "type": "person"},
        {"id": "e3", "name": "保证人丁", "role": "一般保证人", "type": "person"},
    ]
    edges = [
        {
            "source": "e3",
            "target": "e1",
            "relation": "保证",
            "detail": "一般保证",
            "guarantee_mode": "general",
        }
    ]
    timeline_sue = [
        {
            "date": "2026-05-01",
            "event": "债权人对债务人B提起诉讼",
            "legal_tag": "起诉",
        }
    ]
    res_ok = analyze_guarantee_topology_and_deadlines(
        nodes,
        edges,
        timeline_sue,
        principal_due_date="2026-03-31",
        today_date="2026-10-21",
    )
    assert res_ok["guarantee_audits"][0]["status"] == "SAFE" or res_ok["guarantee_audits"][0]["status"].startswith("SAFE")

    timeline_letter = [
        {
            "date": "2026-05-01",
            "event": "向保证人丁发送律师函",
            "legal_tag": "催要主张",
        }
    ]
    res_bad = analyze_guarantee_topology_and_deadlines(
        nodes,
        edges,
        timeline_letter,
        principal_due_date="2026-03-31",
        today_date="2026-10-21",
    )
    assert res_bad["guarantee_audits"][0]["status"] != "SAFE"
    assert not res_bad["guarantee_audits"][0]["status"].startswith("SAFE")


def test_s17_insufficient_data_no_fabricated_due_date():
    nodes = [
        {"id": "e1", "name": "债权人A", "role": "原告/债权人", "type": "person"},
        {"id": "e2", "name": "债务人B", "role": "主债务人/被告", "type": "person"},
        {"id": "e3", "name": "王某", "role": "保证人", "type": "person"},
    ]
    edges = [{"source": "e3", "target": "e1", "relation": "保证", "detail": "未约定保证方式"}]
    res = analyze_guarantee_topology_and_deadlines(
        nodes, edges, timeline=[], today_date="2026-10-21"
    )
    assert res["status"] == "insufficient_data"
    assert "principal_due_date" in res["missing_fields"]
    assert res["guarantee_audits"] == []


def test_s17_graph_api_wangwu_joint_due_2023_12_31():
    mid = f"MATTER-B06-{uuid.uuid4().hex[:8]}"
    create_new_matter(
        {
            "matter_id": mid,
            "title": "批次6保证审查图谱用例",
            "cause_of_action": "民间借贷纠纷",
            "client_role": "原告",
            "principal_amount": 100000.0,
            "case_summary": "保证人王五承担连带保证责任，主债务到期 2023-12-31",
        }
    )
    save_matter_graphs_db(
        matter_id=mid,
        timeline=[
            {
                "date": "2023-01-01",
                "event": "借款合同约定到期 2023-12-31",
                "legal_tag": "合同订立",
            }
        ],
        entity_graph={
            "nodes": [
                {"id": "e1", "name": "债权人甲", "role": "原告/债权人", "type": "person"},
                {"id": "e2", "name": "债务人乙", "role": "主债务人/被告", "type": "person"},
                {"id": "e3", "name": "王五", "role": "保证人", "type": "person"},
            ],
            "edges": [
                {
                    "source": "e3",
                    "target": "e1",
                    "type": "保证",
                    "detail": "保证人王五承担连带保证责任",
                }
            ],
        },
        cashflow=[],
    )
    resp = client.post(f"/api/v1/vault/matters/{mid}/guarantee-analysis", json={})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["guarantee_audits"]) == 1
    assert data["principal_due_date"] == "2023-12-31"
    assert data["guarantee_audits"][0]["guarantee_type"].startswith("连带责任保证")


# ---------------------------------------------------------------------------
# I-08 人保物保约定顺序
# ---------------------------------------------------------------------------

def test_i08_with_enforcement_order_agreement():
    nodes = [
        {"id": "e1", "name": "债权人", "role": "原告/债权人", "type": "company"},
        {"id": "e2", "name": "借款人企业", "role": "主债务人/被告", "type": "company"},
    ]
    edges = [
        {
            "source": "e2",
            "target": "e1",
            "relation": "债务人自有厂房抵押",
            "detail": "双方约定实现顺序：先执行保证人",
            "has_enforcement_order_agreement": True,
        }
    ]
    res = analyze_guarantee_topology_and_deadlines(
        nodes, edges, principal_due_date="2024-01-01", today_date="2024-02-01"
    )
    c = res["collateral_audits"][0]
    blob = json.dumps(c, ensure_ascii=False)
    assert "按照约定实现债权" in blob
    assert "不可绕过" not in blob
    assert "必须" not in c.get("action_warning", "")


def test_i08_no_agreement_debtor_collateral():
    nodes = [
        {"id": "e1", "name": "债权人", "role": "原告/债权人", "type": "company"},
        {"id": "e2", "name": "借款人企业", "role": "主债务人/被告", "type": "company"},
    ]
    edges = [
        {
            "source": "e2",
            "target": "e1",
            "relation": "债务人自有厂房抵押",
            "detail": "最高额抵押登记",
        }
    ]
    res = analyze_guarantee_topology_and_deadlines(
        nodes, edges, principal_due_date="2024-01-01", today_date="2024-02-01"
    )
    c = res["collateral_audits"][0]
    blob = json.dumps(c, ensure_ascii=False)
    assert "先就该物的担保实现债权" in blob
    assert "免责抗辩" in blob
    assert "不可绕过" not in blob


def test_i08_no_bypassing_phrase_in_gateway():
    root = os.path.join(os.path.dirname(__file__), "..", "gateway")
    hits = []
    for dirpath, _, files in os.walk(root):
        for fn in files:
            if not fn.endswith(".py"):
                continue
            path = os.path.join(dirpath, fn)
            text = open(path, encoding="utf-8").read()
            if "不可绕过" in text:
                hits.append(path)
    assert hits == []


# ---------------------------------------------------------------------------
# I-09 公司越权担保
# ---------------------------------------------------------------------------

def test_i09_corporate_resolution_three_fault_cases():
    nodes = [
        {"id": "e1", "name": "债权人", "role": "原告/债权人", "type": "company"},
        {"id": "e2", "name": "债务人", "role": "主债务人/被告", "type": "company"},
        {
            "id": "e3",
            "name": "华夏智融融资租赁有限公司",
            "role": "保证人",
            "type": "company",
        },
    ]
    edges = [
        {
            "source": "e3",
            "target": "e1",
            "relation": "企业连带担保",
            "detail": "连带责任保证",
        }
    ]
    res = analyze_guarantee_topology_and_deadlines(
        nodes, edges, principal_due_date="2024-01-01", today_date="2024-02-01"
    )
    corp = res["guarantee_audits"][0]["corporate_resolution_check"]
    assert corp is not None
    assert "担保制度解释" in corp["statute_basis"]
    note = corp["audit_note"]
    assert "二分之一" in note
    assert "不能清偿的部分承担赔偿责任" in note
    assert "不承担赔偿责任" in note
    assert "仅承担" not in note
    assert "第8条" in note and "律师核实" in note


# ---------------------------------------------------------------------------
# I-10 流水对账
# ---------------------------------------------------------------------------

def test_i10_r20b_rate_cap_message():
    res = audit_and_reconcile_cashflow(
        [{"date": "2025-07-01", "amount": 5000, "purpose": "还款"}],
        principal_amount=100000,
        annual_rate=0.144,
        start_date="2025-01-01",
    )
    serialized = json.dumps(res, ensure_ascii=False)
    assert "未逾越" not in serialized
    assert "超过" in serialized
    assert "12.4" in serialized
    assert "强制性" not in serialized


def test_i10_unclassified_transfer_purpose():
    res = audit_and_reconcile_cashflow(
        [{"date": "2025-07-01", "amount": 5000, "purpose": "转账"}],
        principal_amount=100000,
        annual_interest_rate=0.12,
        start_date="2025-01-01",
    )
    assert any(r.get("purpose") == "转账" for r in res.get("unclassified_records", []))
    assert "未能识别性质" in json.dumps(res, ensure_ascii=False)


def test_i10_fees_offset_first():
    res = audit_and_reconcile_cashflow(
        [{"date": "2025-07-01", "amount": 5000, "purpose": "还款"}],
        principal_amount=100000,
        annual_interest_rate=0.12,
        start_date="2025-01-01",
        fees=1000,
    )
    row = res["reconciliation_ledger"][0]
    assert row.get("offset_to_fees", row.get("offset_fees")) == 1000


def test_i10_missing_principal_or_rate_raises():
    with pytest.raises((TypeError, ValueError)):
        audit_and_reconcile_cashflow(
            [{"date": "2025-07-01", "amount": 5000, "purpose": "还款"}],
            start_date="2025-01-01",
        )
