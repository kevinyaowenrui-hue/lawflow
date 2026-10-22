import os
os.environ.setdefault("LAWFLOW_SEED_DEMO", "1")
# -*- coding: utf-8 -*-
"""
LawFlow 智律工作台 - P2 阶段自动化实证测试套件
(Test Suite for P2 Cross-Guarantee Topology & Art 561 Cashflow Reconciliation)
"""

import pytest
from datetime import date
from fastapi.testclient import TestClient
from gateway.main import app
from gateway.utils.guarantee_and_cashflow_engine import (
    analyze_guarantee_topology_and_deadlines,
    audit_and_reconcile_cashflow
)
from gateway.utils.matter_vault_db import init_matter_vault_db

init_matter_vault_db()
client = TestClient(app, headers={"X-LawFlow-Token": os.environ.get("LAWFLOW_API_TOKEN", "test-token")})


def test_civil_code_art_561_mathematical_precision():
    """
    实证实测：《民法典》第561条法定冲抵对账引擎（费用 -> 利息 -> 本金）
    验证清偿款先抵利息，利息未抵尽前本金分文不减，彻底粉碎债务人已冲抵本金之抗辩！
    """
    records = [
        # 第1笔还款：30万元
        {
            "flow_id": "cf_01",
            "date": "2023-07-09",
            "amount": 300000.0,
            "payer": "北京弘达科技发展有限公司",
            "payee": "中融泰达（北京）智能装备有限公司",
            "purpose": "归还借款利息及部分款项",
            "voucher": "回单HD-20230709-001"
        },
        # 第2笔还款：100万元
        {
            "flow_id": "cf_02",
            "date": "2023-12-31",
            "amount": 1000000.0,
            "payer": "北京弘达科技发展有限公司",
            "payee": "中融泰达（北京）智能装备有限公司",
            "purpose": "还款",
            "voucher": "回单HD-20231231-002"
        }
    ]

    # 旧测试曾依赖引擎默认年利率 0.144，并把“未钳制的默认利率”写成断言；
    # 批次6去掉业务默认值后，改为显式传入利率，并另测超过 LPR 四倍时被钳制。
    res = audit_and_reconcile_cashflow(
        cashflow_records=records,
        principal_amount=5000000.0,
        annual_rate=0.12,
        start_date="2023-01-01"
    )

    assert res["status"] == "success"
    assert res["principal_claim_initial"] == 5000000.0
    assert res["annual_interest_rate"] == pytest.approx(0.12, abs=1e-9)

    # 2023-01-01 合同成立时一年期 LPR 3.65%，四倍上限 14.6%；约定 24% 应被钳制
    capped = audit_and_reconcile_cashflow(
        cashflow_records=records,
        principal_amount=5000000.0,
        annual_rate=0.24,
        start_date="2023-01-01",
    )
    assert capped["annual_interest_rate"] == pytest.approx(0.146, abs=1e-6)
    assert "超过" in capped.get("rate_note", "")

    ledger = res["reconciliation_ledger"]
    assert len(ledger) == 2

    # 第1笔核算（189天计息，年利率12%）
    step1 = ledger[0]
    assert step1["step_num"] == 1
    assert step1["days_accrued"] == 189
    assert step1["repay_amount"] == 300000.0
    # 30万全部冲抵利息，冲抵本金必须严格为0
    assert step1["offset_to_interest"] == 300000.0
    assert step1["offset_to_principal"] == 0.0
    assert step1["remaining_principal"] == 5000000.0
    assert "不足以清偿" in step1["legal_comment"]
    assert step1["unpaid_interest_after_repay"] > 0.0

    # 第2笔核算
    step2 = ledger[1]
    assert step2["step_num"] == 2
    assert step2["days_accrued"] == 175
    assert step2["repay_amount"] == 1000000.0
    # 100万先抵清累积利息，剩余冲抵本金
    assert step2["offset_to_interest"] == step2["total_interest_before_repay"]
    assert step2["offset_to_principal"] > 0
    assert step2["unpaid_interest_after_repay"] == 0.0
    # 本金冲减至 5,000,000 - offset_to_principal
    assert round(step2["remaining_principal"], 2) == round(5000000.0 - step2["offset_to_principal"], 2)

    # 查验证据代理词生成
    statement = res["court_cross_exam_statement"]
    assert "民法典" in statement
    assert "第五百六十一条" in statement
    assert "5,000,000.00" in statement
    assert "未逾越" not in statement
    assert "强制性" not in statement


def test_civil_code_art_692_guarantee_expiry_deadlines():
    """
    实证实测：《民法典》第692条保证期间生死线检测
    测试法定6个月除斥期间、及时催告锁定诉讼时效、逾期主张保证责任灭失等情形。
    """
    nodes = [
        {"id": "e1", "name": "中融泰达有限公司", "role": "原告/债权人", "type": "company"},
        {"id": "e2", "name": "北京弘达科技发展有限公司", "role": "主债务人/被告", "type": "company"},
        {"id": "e3", "name": "华夏智融融资租赁有限公司", "role": "连带责任保证人", "type": "company"},
        {"id": "e4", "name": "张某某", "role": "连带保证人", "type": "person"},
        {"id": "e5", "name": "李某某", "role": "连带保证人", "type": "person"}
    ]

    edges = [
        {"source": "e2", "target": "e1", "relation": "主借款合同", "detail": "本金500万"},
        {"source": "e3", "target": "e1", "relation": "企业连带担保", "detail": "最高额保证"},
        {"source": "e4", "target": "e1", "relation": "个人连带保证", "detail": "无限连带责任"},
        {"source": "e5", "target": "e1", "relation": "连带保证", "detail": "一般或连带保证"}
    ]

    # 时间线：借款2023-01-01借，2023-07-01届满；
    # 法定6个月届满日为 2024-01-01。
    timeline = [
        {"date": "2023-01-01", "event": "签订借款合同与担保合同", "legal_tag": "合同成立"},
        {"date": "2023-07-01", "event": "借款到期届满，债务人违约", "legal_tag": "主债务到期"},
        {"date": "2023-11-15", "event": "原告向华夏智融融资租赁有限公司发送EMS催告函要求承担保证", "legal_tag": "催要主张"},
        {"date": "2024-03-20", "event": "原告向张某某发送律师函催告", "legal_tag": "逾期催要"}
    ]

    # 今日设为 2024-05-01
    res = analyze_guarantee_topology_and_deadlines(
        nodes=nodes,
        edges=edges,
        timeline=timeline,
        principal_due_date="2023-07-01",
        today_date="2024-05-01"
    )

    assert res["status"] == "success"
    assert res["principal_due_date"] == "2023-07-01"
    assert res["statutory_guarantee_expiry"] == "2024-01-01"

    g_audits = {g["guarantor_name"]: g for g in res["guarantee_audits"]}
    
    # 1. 华夏智融在 2023-11-15 催告（早于 2024-01-01） -> 保证期间已依法阻断，SAFE
    assert g_audits["华夏智融融资租赁有限公司"]["status"] == "SAFE"
    assert g_audits["华夏智融融资租赁有限公司"]["has_demanded_in_time"] is True
    # 批次6：有效主张引用第693条要点，不再对律师函一律套用第694条
    assert "693" in g_audits["华夏智融融资租赁有限公司"]["warning_message"]
    assert "694" not in g_audits["华夏智融融资租赁有限公司"]["warning_message"]
    # 作为企业，statute_basis 以担保制度解释为主，并保留公司法第15条
    assert g_audits["华夏智融融资租赁有限公司"]["corporate_resolution_check"] is not None
    corp_basis = g_audits["华夏智融融资租赁有限公司"]["corporate_resolution_check"]["statute_basis"]
    assert "担保制度解释" in corp_basis
    assert "公司法》第15条" in corp_basis
    assert "仅承担" not in g_audits["华夏智融融资租赁有限公司"]["corporate_resolution_check"]["audit_note"]

    # 2. 张某某在 2024-03-20 催告（晚于 2024-01-01） -> 逾期主张，CRITICAL_EXPIRED
    assert g_audits["张某某"]["status"] == "CRITICAL_EXPIRED"
    assert "免除保证责任" in g_audits["张某某"]["warning_message"]

    # 3. 李某某未催告，且今日（2024-05-01）已过 2024-01-01 -> CRITICAL_EXPIRED
    assert g_audits["李某某"]["status"] == "CRITICAL_EXPIRED"
    assert "法定灭失" in g_audits["李某某"]["status_label"]


def test_civil_code_art_392_collateral_priority():
    """
    实证实测：《民法典》第392条人保与物保并存受偿顺位
    主债务人自有的抵押物必须法定优先执行处置（第一顺位）；第三人抵押物与保证人并列。
    """
    nodes = [
        {"id": "e1", "name": "债权人银行", "role": "原告/债权人", "type": "company"},
        {"id": "e2", "name": "借款人企业", "role": "主债务人/被告", "type": "company"},
        {"id": "e3", "name": "第三方资产公司", "role": "第三人物保提供方", "type": "company"}
    ]

    edges = [
        {"source": "e2", "target": "e1", "relation": "债务人自有厂房抵押", "detail": "最高额抵押登记"},
        {"source": "e3", "target": "e1", "relation": "第三人商铺抵押", "detail": "抵押担保"}
    ]

    res = analyze_guarantee_topology_and_deadlines(
        nodes=nodes,
        edges=edges,
        principal_due_date="2024-01-01",
        today_date="2024-02-01"
    )

    c_audits = {c["collateral_provider"]: c for c in res["collateral_audits"]}
    
    # 借款人自有的抵押物 -> 无约定时先就物保实现（删除“不可绕过/必须”绝对化表述）
    assert c_audits["借款人企业"]["is_debtor_own_property"] is True
    assert c_audits["借款人企业"]["priority_level"] == 1
    assert "第一顺位" in c_audits["借款人企业"]["priority_rank"]
    assert "先就该物的担保实现债权" in c_audits["借款人企业"]["statutory_rule"]
    assert "不可绕过" not in c_audits["借款人企业"]["action_warning"]

    # 第三人的抵押物 -> 并列顺位 (债权人选择权)
    assert c_audits["第三方资产公司"]["is_debtor_own_property"] is False
    assert c_audits["第三方资产公司"]["priority_level"] == 2
    assert "并列顺位" in c_audits["第三方资产公司"]["priority_rank"]


def test_cashflow_anomaly_probes():
    """
    实证实测：资金穿透流水三大异常探针（同日回流砍头息、第三方代收无授权、附言性质冲突）
    """
    records = [
        # 探针A：同日出借与快速回流（砍头息）
        {
            "flow_id": "cf_out",
            "date": "2023-01-01",
            "amount": 5000000.0,
            "payer": "出借人",
            "payee": "借款人",
            "purpose": "借款出借交付",
            "voucher": "网银001"
        },
        {
            "flow_id": "cf_back",
            "date": "2023-01-01",
            "amount": 500000.0,
            "payer": "借款人",
            "payee": "出借人关联方",
            "purpose": "顾问服务费",
            "voucher": "网银002"
        },
        # 探针B：第三方代付未见授权
        {
            "flow_id": "cf_third",
            "date": "2023-03-01",
            "amount": 200000.0,
            "payer": "神秘外省空壳公司",
            "payee": "出借人",
            "purpose": "代还借款",
            "voucher": "回单003"
        },
        # 探针C：附言定性冲突（货款）
        {
            "flow_id": "cf_conflict",
            "date": "2023-05-01",
            "amount": 100000.0,
            "payer": "借款人",
            "payee": "出借人",
            "purpose": "支付第一季度定金及货款",
            "voucher": "回单004"
        }
    ]

    res = audit_and_reconcile_cashflow(
        cashflow_records=records,
        principal_amount=5000000.0,
        annual_rate=0.12,
        start_date="2023-01-01",
        debtor_name="借款人",
        creditor_name="出借人"
    )

    red_flags = res["red_flags"]
    assert len(red_flags) >= 3

    types = [rf["risk_type"] for rf in red_flags]
    assert any("同日快速回流" in t for t in types)
    assert any("第三方代付未见授权" in t for t in types)
    assert any("银行附言与借款性质冲突" in t for t in types)


def test_api_guarantee_and_cashflow_endpoints():
    """
    实证实测：FastAPI 接口端到端联调测试
    POST /api/v1/vault/matters/MATTER-2026-001/guarantee-analysis
    POST /api/v1/vault/matters/MATTER-2026-001/cashflow-audit
    """
    # 1. 担保分析端点（演示案图谱无明确到期日时须显式传入，避免编造到期日）
    resp_g = client.post(
        "/api/v1/vault/matters/MATTER-2026-001/guarantee-analysis",
        json={"today_date": "2026-03-01", "principal_due_date": "2024-03-15"}
    )
    assert resp_g.status_code == 200
    g_data = resp_g.json()
    assert g_data["status"] == "success"
    assert "guarantee_audits" in g_data
    assert len(g_data["guarantee_audits"]) >= 1
    assert "collateral_audits" in g_data
    assert "topology" in g_data
    assert "partner_tactical_memo" in g_data

    # 2. 资金审计与法定冲抵端点（显式传入利率；本金可取案件记录）
    resp_cf = client.post(
        "/api/v1/vault/matters/MATTER-2026-001/cashflow-audit",
        json={"annual_interest_rate": 0.12, "principal_amount": 5000000.0}
    )
    assert resp_cf.status_code == 200
    cf_data = resp_cf.json()
    assert cf_data["status"] == "success"
    assert "reconciliation_ledger" in cf_data
    assert "red_flags" in cf_data
    assert "court_cross_exam_statement" in cf_data
    assert cf_data["principal_claim_initial"] > 0
    assert cf_data["current_principal_unpaid"] > 0
    assert "未逾越" not in cf_data["court_cross_exam_statement"]
