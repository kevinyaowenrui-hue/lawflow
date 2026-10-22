# -*- coding: utf-8 -*-
"""
LawFlow 智律工作台 - P4 执行引擎测试（批次8重写）

旧测试曾断言默认参数必然输出 CRITICAL_PIERCING、1.2亿/4950万等演示数字，
属于把错误行为写成断言；本文件改为验收空输入 INSUFFICIENT_FACTS、演示模式、律师意见措辞。
"""

import json
import os

from fastapi.testclient import TestClient

from gateway.main import app
from gateway.utils.enforcement_and_asset_engine import analyze_enforcement_and_asset_penetration

client = TestClient(app, headers={"X-LawFlow-Token": os.environ.get("LAWFLOW_API_TOKEN", "test-token")})


def test_empty_facts_all_probes_insufficient():
    res = analyze_enforcement_and_asset_penetration()
    assert len(res["probes"]) == 4
    for p in res["probes"]:
        assert p["status"] == "INSUFFICIENT_FACTS"
        assert p.get("missing_facts")
        assert p.get("severity") != "CRITICAL_PIERCING"
    assert res.get("recoverable_potential") in (0, 0.0, None)
    serialized = json.dumps(res, ensure_ascii=False)
    for bad in ("120000000", "1.2亿", "1.2 亿", "4950", "京01执889", "小舅子", "五保"):
        assert bad not in serialized


def test_claim_amount_only_no_demo_leak():
    res = analyze_enforcement_and_asset_penetration(claim_amount=50000)
    serialized = json.dumps(res, ensure_ascii=False)
    for bad in ("120000000", "1.2亿", "1.2 亿", "4950", "京01执889"):
        assert bad not in serialized
    assert all(p["status"] == "INSUFFICIENT_FACTS" for p in res["probes"])


def test_demo_mode_is_demo_true():
    res = analyze_enforcement_and_asset_penetration(use_demo=True)
    assert res.get("is_demo") is True
    assert "演示数据" in (res.get("demo_notice") or "") or "演示数据" in json.dumps(res, ensure_ascii=False)
    assert any(p.get("severity") == "CRITICAL_PIERCING" or p.get("status") == "READY" for p in res["probes"])


def test_full_facts_legal_wording_i11():
    res = analyze_enforcement_and_asset_penetration(
        claim_amount=1000000.0,
        debtor_name="甲公司",
        controller_name="王某某",
        applicant_name="乙公司",
        execution_case_no="（2025）京01执1号",
        court_name="北京市第一中级人民法院",
        is_one_person_company=True,
        equity_transfers=[
            {
                "transferor": "王某某",
                "transferee": "赵某",
                "consideration": 0,
                "unpaid_capital": 100000.0,
                "evidence_note": "未届出资期限转让股权",
            }
        ],
        capital_flows=[
            {
                "flow_id": "F-1",
                "date": "2024-01-01",
                "amount": 50000.0,
                "source": "甲公司",
                "target": "王某某个人账户",
                "summary": "备用金",
            }
        ],
        divorce_transfer={
            "ex_spouse": "刘某",
            "divorce_date": "2024-06-01",
            "debt_origin_date": "2023-01-01",
            "transferred_assets_value": 2000000.0,
            "description": "协议离婚无偿转移房产",
        },
        third_party_objection={
            "claimant": "某融资租赁公司",
            "asset_description": "数控机床",
            "asset_value": 800000.0,
            "evidence_note": "提出融资租赁异议",
        },
        related_company_hint=True,
    )

    app_doc = res["addition_application_text"]
    assert "判令" not in app_doc
    assert "举证责任立即" not in app_doc
    assert "直接裁定追加" not in app_doc
    # 加速到期仅可在带公司不能清偿到期债务条件时出现
    if "加速到期" in app_doc:
        assert "公司不能清偿到期债务" in app_doc
    assert "裁定追加" in app_doc or "申请追加" in app_doc

    probes_blob = json.dumps(res["probes"], ensure_ascii=False)
    assert "另行提起诉讼" in probes_blob
    assert "第28条" not in probes_blob and "第31条" not in probes_blob
    assert "第二十八条" not in probes_blob and "第三十一条" not in probes_blob
    assert "第七百四十五条" in probes_blob or "第745条" in probes_blob
    assert "第五百四十一条" in probes_blob or "第541条" in probes_blob
    assert "所有权保留" not in probes_blob or "融资租赁" in probes_blob

    lawsuit = res["objection_lawsuit_text"]
    assert "判令" in lawsuit  # 执行异议之诉起诉状可保留判令
    assert "第二十八条" not in lawsuit and "第三十一条" not in lawsuit


def test_qualitative_labels_only_with_evidence():
    res = analyze_enforcement_and_asset_penetration(
        claim_amount=100000.0,
        debtor_name="甲公司",
        controller_name="王某某",
        equity_transfers=[
            {
                "transferor": "王某某",
                "transferee": "赵某",
                "unpaid_capital": 50000.0,
                "evidence_note": "普通股权转让",
            }
        ],
    )
    blob = json.dumps(res, ensure_ascii=False)
    assert "职业背债人" not in blob
    assert "勾结中介" not in blob
    assert "倒签" not in blob


def test_api_enforcement_empty_and_demo():
    resp = client.post("/api/v1/enforcement/penetration-audit", json={})
    assert resp.status_code == 200
    data = resp.json()
    assert all(p["status"] == "INSUFFICIENT_FACTS" for p in data["probes"])

    demo = client.post(
        "/api/v1/enforcement/penetration-audit",
        json={"use_demo": True},
    )
    assert demo.status_code == 200
    assert demo.json().get("is_demo") is True


def test_api_enforcement_export_docx_endpoint():
    import docx
    from gateway.core.paths import get_generated_dir

    app_payload = {
        "title": "追加被执行人申请书",
        "content_text": "追 加 被 执 行 人 申 请 书\n\n裁定追加被申请人为被执行人。\n",
        "doc_type": "addition_application",
    }
    resp = client.post("/api/v1/enforcement/export-docx", json=app_payload)
    assert resp.status_code == 200
    data = resp.json()
    storage_path = str(get_generated_dir() / data["filename"])
    assert os.path.exists(storage_path)
    doc = docx.Document(storage_path)
    assert "裁定追加" in "\n".join(p.text for p in doc.paragraphs)
