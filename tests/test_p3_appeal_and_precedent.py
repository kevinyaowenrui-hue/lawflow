# -*- coding: utf-8 -*-
"""
LawFlow 智律工作台 - P3 二审引擎测试（批次8重写）

旧测试曾断言空输入仍输出三大漏洞、默认金额写入文书，属于把错误行为写成断言；
本文件改为验收：空输入无漏洞、买卖合同判决不误报、演示模式带 is_demo、上诉状法定要素与上诉期。
"""

import os
import re

import pytest
from fastapi.testclient import TestClient

from gateway.main import app
from gateway.utils.appeal_and_precedent_engine import (
    SUPREME_COURT_APPELLATE_PRECEDENTS,
    analyze_first_instance_judgment_and_precedents,
)
from gateway.utils.citation_guard import CASE_NUMBER_PATTERN, LEGACY_CASE_NUMBER_PATTERN
from gateway.utils.cn_legal_calc import calculate_appeal_deadline

client = TestClient(app, headers={"X-LawFlow-Token": os.environ.get("LAWFLOW_API_TOKEN", "test-token")})


def test_empty_judgment_no_flaws_and_unrecognized():
    res = analyze_first_instance_judgment_and_precedents(judgment_text="")
    assert res["flaw_diagnostics"] == []
    assert res.get("unrecognized")
    assert any("未识别" in str(u) for u in res["unrecognized"])
    assert res.get("is_demo") is not True


def test_sales_contract_judgment_no_loan_hardship_ld_flaws():
    res = analyze_first_instance_judgment_and_precedents(
        judgment_text="原告诉被告买卖合同纠纷，判决被告支付货款10万元",
        claim_amount=100000.0,
        first_instance_court="某基层人民法院",
    )
    blob = " ".join(
        (f.get("error_type") or "") + " " + (f.get("appellate_attack_point") or "")
        for f in res["flaw_diagnostics"]
    )
    for bad in ("民间借贷", "情势变更", "违约金"):
        assert bad not in blob
    assert not any(f["probe_id"] == "FLAW-01" for f in res["flaw_diagnostics"])
    assert not any(f["probe_id"] == "FLAW-02" for f in res["flaw_diagnostics"])
    assert not any(f["probe_id"] == "FLAW-03" for f in res["flaw_diagnostics"])


def test_keyword_judgment_triggers_three_flaws_neutral_wording():
    judgment_sample = """
    本院认为，原告与被告签订的《增资补充协议》中关于回购本金及固定溢价收益的约定，
    实质上属于“保本保收益”的借贷性质，具有“名为投资实为借贷”的法律特征。
    故原告主张的利息及违约金总和不应超过同期一年期LPR的4倍。
    此外，由于受宏观行业调控政策以及经济下行客观环境影响，属于情势变更。
    鉴于原告未举证证明实际损失，约定年化15%违约金过高，本院依法酌情调减，按一年期LPR计算。
    """
    res = analyze_first_instance_judgment_and_precedents(
        judgment_text=judgment_sample,
        claim_amount=80000000.0,
        first_instance_court="某市第一中级人民法院",
    )
    probe_ids = [f["probe_id"] for f in res["flaw_diagnostics"]]
    assert "FLAW-01" in probe_ids
    assert "FLAW-02" in probe_ids
    assert "FLAW-03" in probe_ids
    all_text = "\n".join(
        str(f.get("appellate_attack_point", "")) + str(f.get("error_type", ""))
        for f in res["flaw_diagnostics"]
    )
    for banned in ("绝不", "无底线", "彻底击穿", "严禁"):
        assert banned not in all_text


def test_demo_mode_sets_is_demo_flag():
    res = analyze_first_instance_judgment_and_precedents(use_demo=True)
    assert res.get("is_demo") is True
    assert "演示数据" in (res.get("demo_notice") or "") or "演示数据" in str(res)
    assert len(res["flaw_diagnostics"]) >= 1


def test_nine_people_minutes_wording_and_retrieval_hierarchy():
    res = analyze_first_instance_judgment_and_precedents(
        judgment_text="名为投资实为借贷，情势变更，违约金过高酌情调减",
        claim_amount=100.0,
        first_instance_court="某中级人民法院",
    )
    timeline_blob = "\n".join(t.get("rule_evolution", "") for t in res["judicial_evolution_timeline"])
    assert "严禁套用民间借贷限额" not in timeline_blob
    assert "九民纪要" in timeline_blob or "法发〔2019〕25号" in timeline_blob

    memo = res["appellate_memo_report"]
    assert "指导性案例" in memo
    assert "参考性案例" in memo
    assert memo.index("指导性案例") < memo.index("参考性案例")
    assert "人民法院案例库" in memo
    assert "TODO(律师核实)" in memo
    assert "京民终580" not in memo
    assert "京民终580" not in res["appellate_pleading_text"]


def test_no_builtin_precedents_constant():
    assert SUPREME_COURT_APPELLATE_PRECEDENTS == []
    res = analyze_first_instance_judgment_and_precedents(
        judgment_text="",
        first_instance_court="某法院",
    )
    blob = (res.get("appellate_memo_report") or "") + "\n" + (res.get("appellate_pleading_text") or "")
    assert len(list(CASE_NUMBER_PATTERN.finditer(blob))) == 0
    assert len(list(LEGACY_CASE_NUMBER_PATTERN.finditer(blob))) == 0


def test_appellate_pleading_statutory_elements_no_high_court_preset():
    res = analyze_first_instance_judgment_and_precedents(
        judgment_text="名为投资实为借贷",
        claim_amount=1000000.0,
        first_instance_court="北京市第二中级人民法院",
        first_instance_case_no="（2024）京02民初123号",
        cause_of_action="股权转让纠纷",
        appellant={"name": "甲基金", "address": "北京", "party_type": "legal"},
        appellee={"name": "李某某", "address": "上海", "party_type": "natural"},
        judgment_type="judgment",
    )
    pleading = res["appellate_pleading_text"]
    assert "（2024）京02民初123号" in pleading
    assert "第一百七十三条" in pleading or "通过原审人民法院提出" in pleading
    assert "上一级高级人民法院" not in pleading
    assert "保全责任险" not in pleading
    assert "高级人民法院" not in pleading or "【待填写" in pleading
    assert "甲基金" in pleading
    assert "李某某" in pleading
    assert "股权转让纠纷" in pleading


def test_appeal_deadline_calc_acceptance():
    r1 = calculate_appeal_deadline("2026-11-02", "ruling")
    assert r1["deadline"] == "2026-11-12"
    r2 = calculate_appeal_deadline("2026-11-02", "judgment")
    assert r2["deadline"] == "2026-11-17"
    r3 = calculate_appeal_deadline("2026-11-02", "ruling", holidays=["2026-11-12"])
    assert r3["deadline"] == "2026-11-13"


def test_api_appeal_audit_requires_first_instance_court():
    resp = client.post(
        "/api/v1/litigation/appeal-audit",
        json={"judgment_text": "判决被告支付货款10万元"},
    )
    assert resp.status_code == 422


def test_api_appeal_audit_empty_and_demo():
    empty = client.post(
        "/api/v1/litigation/appeal-audit",
        json={
            "judgment_text": "",
            "first_instance_court": "某中级人民法院",
        },
    )
    assert empty.status_code == 200
    data = empty.json()
    assert data["flaw_diagnostics"] == []

    demo = client.post(
        "/api/v1/litigation/appeal-audit",
        json={"use_demo": True, "first_instance_court": "演示法院"},
    )
    assert demo.status_code == 200
    d = demo.json()
    assert d.get("is_demo") is True


def test_api_appeal_deadline_endpoint():
    resp = client.post(
        "/api/v1/phase1/calc/appeal-deadline",
        json={"service_date": "2026-11-02", "judgment_type": "ruling"},
    )
    assert resp.status_code == 200
    assert resp.json()["deadline"] == "2026-11-12"


def test_api_appeal_export_docx_endpoint():
    import docx
    from gateway.core.paths import get_generated_dir

    pleading_payload = {
        "title": "民事上诉状（要素版）",
        "content_text": (
            "民 事 上 诉 状\n\n"
            "上诉人：甲\n被上诉人：乙\n"
            "原审案号：（2024）京02民初1号\n"
            "上诉状应当通过原审人民法院提出（《民事诉讼法》第一百七十三条）\n"
        ),
        "doc_type": "appeal_pleading",
    }
    resp = client.post("/api/v1/litigation/appeal-export-docx", json=pleading_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["filename"].endswith(".docx")
    storage_path = str(get_generated_dir() / data["filename"])
    assert os.path.exists(storage_path)
    doc = docx.Document(storage_path)
    full_text = "\n".join(p.text for p in doc.paragraphs)
    assert "第一百七十三条" in full_text
