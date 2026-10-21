# -*- coding: utf-8 -*-
"""
LawFlow 智律工作台 - P4 阶段自动化实证测试套件
(Test Suite for P4 Enforcement Breakthrough, Asset Penetration & Debtor Piercing)

实务法理测试维度：
1. 四大执行穿透算法探针（未届期转让出资穿透、一人公司混同举证倒置、假离婚撤销权、倒签租赁执行异议之诉）诊断精度；
2. 新《公司法》第47/88条与最高院《追加当事人规定》第17-20条法条逻辑链完备性；
3. 《追加被执行人申请书》与《执行异议之诉起诉状》自动化生成与案号法条验真；
4. FastAPI 全栈路由集成测试（/api/v1/enforcement/penetration-audit 与 Word 原生导出）。
"""

import os
import pytest
from fastapi.testclient import TestClient
from gateway.main import app
from gateway.utils.enforcement_and_asset_engine import (
    analyze_enforcement_and_asset_penetration
)
from gateway.utils.citation_guard import audit_case_numbers

client = TestClient(app)


def test_four_piercing_probes_precision():
    """
    实证实测：执行终本四大穿透探针
    1. 探针 1 (ENF-01)：新《公司法》第47/88条 & 追加规定第17-19条【出资未届期转让与职业背债人穿透】
    2. 探针 2 (ENF-02)：《公司法》第23条第三款 & 追加规定第20条【一人公司混同举证责任倒置】
    3. 探针 3 (ENF-03)：《民法典》第538-539条【协议假离婚无偿转移财产撤销探针】
    4. 探针 4 (ENF-04)：《民诉法》第238条【案外人倒签融资租赁虚假异议破壁探针】
    """
    res = analyze_enforcement_and_asset_penetration(
        case_title="1.2亿元终本借贷及担保执行款财产线索穿透案",
        claim_amount=120000000.0,
        book_balance=342.18,
        debtor_name="北京华腾智达科技有限公司",
        controller_name="张某某",
        transferee_name="赵某某（72岁偏远山区无清偿能力五保人员）",
        share_capital=50000000.0,
        subscribed_share_ratio=0.99,
        ex_wife_name="刘某某",
        divorce_date="2023-06-18",
        debt_origin_date="2022-10-15",
        real_estate_value=45000000.0,
        equipment_value=25000000.0,
        third_party_claimant="某融资租赁（天津）有限公司"
    )

    assert res["status"] == "success"
    assert res["claim_amount"] == 120000000.0
    assert res["book_balance"] == 342.18
    assert res["recoverable_potential"] >= 119500000.0

    probes = res["probes"]
    assert len(probes) == 4

    p_ids = [p["probe_id"] for p in probes]
    assert "ENF-01" in p_ids
    assert "ENF-02" in p_ids
    assert "ENF-03" in p_ids
    assert "ENF-04" in p_ids

    # 验证探针1：未出资股权转让与加速到期补充责任 (4950万)
    p1 = next(p for p in probes if p["probe_id"] == "ENF-01")
    assert "88" in p1["target_statute"] or "第八十八条" in p1["target_statute"]
    assert p1["unpaid_amount"] == 49500000.0
    assert "补充责任" in p1["legal_breakthrough_logic"]

    # 验证探针2：一人公司公私混同与举证责任倒置 (1750万)
    p2 = next(p for p in probes if p["probe_id"] == "ENF-02")
    assert "二十三" in p2["target_statute"] or "23" in p2["target_statute"]
    assert "第二十条" in p2["target_statute"] or "20" in p2["target_statute"]
    assert p2["commingled_amount"] >= 17500000.0
    assert "举证责任" in p2["legal_breakthrough_logic"]

    # 验证探针3：协议假离婚无偿转移豪宅撤销权 (4500万)
    p3 = next(p for p in probes if p["probe_id"] == "ENF-03")
    assert "五百三十八条" in p3["target_statute"] or "538" in p3["target_statute"]
    assert p3["sheltered_asset_value"] == 45000000.0
    assert "撤销权" in p3["legal_breakthrough_logic"]

    # 验证探针4：倒签融资租赁虚假异议击穿 (2500万)
    p4 = next(p for p in probes if p["probe_id"] == "ENF-04")
    assert "二百三十八条" in p4["target_statute"] or "238" in p4["target_statute"]
    assert p4["equipment_value"] == 25000000.0
    assert "执行异议之诉" in p4["legal_breakthrough_logic"]


def test_enforcement_documents_generation_and_citation_guard():
    """
    实证实测：执行审查标准文书自动化生成与案号法条验真
    1. 《追加被执行人申请书》要素完备性；
    2. 《执行异议之诉起诉状》请求与要件完整性；
    3. 全文通过 citation_guard 案号后验。
    """
    res = analyze_enforcement_and_asset_penetration(
        claim_amount=120000000.0,
        book_balance=342.18
    )

    app_doc = res["addition_application_text"]
    lawsuit_doc = res["objection_lawsuit_text"]

    # 验证《追加被执行人申请书》
    assert "追 加 被 执 行 人 申 请 书" in app_doc
    assert "49,500,000.00" in app_doc
    assert "120,000,000.00" in app_doc
    assert "第八十八条第一款" in app_doc
    assert "第二十条" in app_doc
    assert "一人有限责任公司" in app_doc

    # 验证《执行异议之诉起诉状》
    assert "民 事 起 诉 状" in lawsuit_doc
    assert "案外人执行异议之诉" in lawsuit_doc
    assert "25,000,000.00" in lawsuit_doc
    assert "第二百三十八条" in lawsuit_doc
    assert "继续执行" in lawsuit_doc

    # 验证案号后验
    cases_verified = res["cases_verified"]
    assert isinstance(cases_verified, list)
    assert all(not c.get("is_hallucination") for c in cases_verified)


def test_api_enforcement_penetration_audit_endpoint():
    """
    实证实测：FastAPI /api/v1/enforcement/penetration-audit 接口集成测试
    """
    payload = {
        "case_title": "1.2亿元终本借贷及担保执行款财产线索穿透案",
        "claim_amount": 120000000.0,
        "book_balance": 342.18,
        "debtor_name": "北京华腾智达科技有限公司",
        "controller_name": "张某某",
        "share_capital": 50000000.0,
        "subscribed_share_ratio": 0.99,
        "real_estate_value": 45000000.0,
        "equipment_value": 25000000.0
    }

    # 测试主路由
    resp = client.post("/api/v1/enforcement/penetration-audit", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["claim_amount"] == 120000000.0
    assert len(data["probes"]) == 4
    assert data["recoverable_potential"] >= 119500000.0

    # 测试别名路由
    alias_resp = client.post("/api/v1/deep-matrix/enforcement-audit", json=payload)
    assert alias_resp.status_code == 200
    assert alias_resp.json()["status"] == "success"


def test_api_enforcement_export_docx_endpoint():
    """
    实证实测：Word 原生司法公文导出接口测试 (/api/v1/enforcement/export-docx)
    1. 成功生成 .docx 司法公文文件；
    2. 文件保存在 storage/generated 目录下，大小 > 0；
    3. 返回标准下载链接 /api/documents/download/...；
    4. 验证导出的 Word 文档段落及内容完整性。
    """
    import docx

    # 1. 导出追加被执行人申请书
    app_payload = {
        "title": "追加被执行人申请书（原出资股东及实控人）",
        "content_text": (
            "追 加 被 执 行 人 申 请 书\n\n"
            "申请执行人：某大型金融投资发展控股集团有限公司\n"
            "被执行人：北京华腾智达科技有限公司\n"
            "被申请人一：张某某\n\n"
            "【申请请求】\n"
            "1. 依法裁定追加被申请人一【张某某】为被执行人；\n"
            "2. 判令其在未实缴出资4950万元范围内承担补充责任。\n\n"
            "【事实与理由】\n"
            "一、原股东未届出资期转让股权，受让人未按期足额缴纳，原股东依法承担补充清偿责任；\n"
            "二、被执行人系一人公司，张某某公私财产混同，依法承担连带责任。"
        ),
        "doc_type": "addition_application"
    }

    resp = client.post("/api/v1/enforcement/export-docx", json=app_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["filename"].endswith(".docx")
    assert "/api/documents/download/" in data["download_url"]
    assert data["file_size"] > 0

    storage_path = os.path.join("storage", "generated", data["filename"])
    assert os.path.exists(storage_path)

    doc = docx.Document(storage_path)
    assert len(doc.paragraphs) > 0
    full_text = "\n".join([p.text for p in doc.paragraphs])
    assert "追加被执行人申请书" in full_text
    assert "4950万元" in full_text

    # 2. 导出执行异议之诉起诉状
    lawsuit_payload = {
        "title": "民事起诉状（案外人虚假租赁执行异议之诉）",
        "content_text": (
            "民 事 起 诉 状\n"
            "（案外人执行异议之诉·申请执行人提起）\n\n"
            "原告：某大型金融投资发展控股集团有限公司\n"
            "被告：某融资租赁（天津）有限公司\n\n"
            "【诉讼请求】\n"
            "判令对贵院查封的精密数控机床设备准予继续执行。"
        ),
        "doc_type": "objection_lawsuit"
    }

    resp_law = client.post("/api/v1/deep-matrix/enforcement-export-docx", json=lawsuit_payload)
    assert resp_law.status_code == 200
    data_law = resp_law.json()
    assert data_law["file_size"] > 0
    law_path = os.path.join("storage", "generated", data_law["filename"])
    assert os.path.exists(law_path)
