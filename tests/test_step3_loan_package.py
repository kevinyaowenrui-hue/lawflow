# -*- coding: utf-8 -*-
"""
阶段一验证：民间借贷纠纷立案公文包端到端生成。
"""
from __future__ import annotations

import pytest

from gateway.core.paths import get_generated_dir


LOAN_PAYLOAD = {
    "cause_of_action": "民间借贷纠纷",
    "plaintiff": {
        "name": "李四",
        "id_card_or_uscc": "110101199003072375",
        "gender": "男",
        "birth": "1990年3月7日",
        "ethnicity": "汉族",
        "address": "北京市海淀区中关村南大街1号科技大厦B座1201室",
        "phone": "13800138000",
    },
    "defendant": {
        "name": "张三",
        "id_card_or_uscc": "110101198505121232",
        "gender": "男",
        "birth": "1985年5月12日",
        "ethnicity": "汉族",
        "address": "北京市朝阳区建国路88号现代城A座608室",
        "phone": "13900139000",
    },
    "claims": [
        "判令被告立即向原告偿还借款本金人民币 500,000.00 元；",
        "判令被告向原告支付逾期还款利息（自借款届满之日起至实际清偿之日止，按年利率6%计算，暂计至起诉日为人民币 26,701.02 元）；",
        "判令本案全部诉讼费用及保全费用由被告全额承担。",
    ],
    "claim_amount": 500000.0,
    "raw_case_notes": (
        "被告张三因承揽土建工程周转资金困难，于2023年3月1日向原告借款50万元整，约定借期6个月，年化利率6%。"
        "原告当天通过招商银行手机网银向被告实名账户转账50万元，附言注明'借款'。被告出具借条原件。"
        "2023年9月1日借期届满后，原告多次通过微信及电话要求被告归还借款本息，"
        "被告均以发包方工程进度款未到账为由故意推诿拖延，至今分文未还。"
    ),
    "court_name": "北京市海淀区人民法院",
    "lawyer_name": "王大状",
    "law_firm": "北京智律律师事务所",
    "lawyer_phone": "13600001111",
    "lawyer_license": "11101201510123456",
    "auto_generate_sub_docs": True,
}


def test_gateway_health(client):
    res = client.get("/health")
    assert res.status_code == 200, res.text
    assert res.json().get("status") == "healthy"


@pytest.mark.requires_ollama
def test_loan_litigation_package_generates(client):
    resp = client.post("/api/v1/phase1/generate-litigation-package", json=LOAN_PAYLOAD)
    assert resp.status_code == 200, resp.text
    pkg = resp.json()
    assert pkg.get("package_id")
    assert pkg.get("cause_of_action") == "民间借贷纠纷"
    fees = pkg.get("court_fees_estimate") or {}
    assert fees.get("standard_fee") is not None
    facts = (pkg.get("facts_and_reasons_polished") or "").strip()
    assert len(facts) > 0


@pytest.mark.requires_ollama
def test_loan_package_documents_exist_on_disk(client):
    resp = client.post("/api/v1/phase1/generate-litigation-package", json=LOAN_PAYLOAD)
    assert resp.status_code == 200, resp.text
    pkg = resp.json()
    docs = pkg.get("generated_documents") or []
    assert len(docs) >= 1
    generated = get_generated_dir()
    for d in docs:
        docx_name = d.get("filename_docx") or ""
        assert docx_name, f"missing filename_docx for {d.get('doc_type')}"
        assert (generated / docx_name).exists(), f"missing docx: {docx_name}"
