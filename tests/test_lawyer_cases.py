# -*- coding: utf-8 -*-
"""
I-20 律师用例测试骨架（批次 2 建立；失败项由后续批次去掉 xfail）。
直接调用引擎函数（不经 HTTP），金额用 approx。
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gateway.utils.cn_legal_calc import (
    calculate_court_fees,
    calculate_labor_compensation,
    calculate_lpr_interest,
    calculate_preservation_renewal,
    calculate_statute_of_limitations,
    validate_and_parse_uscc,
    verify_statutory_validity,
)
from gateway.utils.citation_guard import audit_citations_in_text
from gateway.utils.guarantee_and_cashflow_engine import (
    analyze_guarantee_topology_and_deadlines,
    audit_and_reconcile_cashflow,
)
from gateway.utils.appeal_and_precedent_engine import (
    analyze_first_instance_judgment_and_precedents,
)
from gateway.utils.enforcement_and_asset_engine import (
    analyze_enforcement_and_asset_penetration,
)


# ---------------------------------------------------------------------------
# R1–R3, R6–R8, R10, R20, R24：当前已通过
# ---------------------------------------------------------------------------

def test_R1_court_fees_1m():
    res = calculate_court_fees(1000000)
    assert res["actual_fee"] == 13800
    assert res["preservation_fee"] == 5000


def test_R2_court_fees_summary():
    res = calculate_court_fees(1000000, is_summary_procedure=True)
    assert res["actual_fee"] == 6900


def test_R3_lpr_interest_full_year():
    res = calculate_lpr_interest(100000, "2025-01-01", "2026-01-01", term="1Y")
    assert round(res["total_interest"], 2) == 3038.08


@pytest.mark.xfail(strict=True, reason="待批次5修复")
def test_R4_lpr_interest_partial_2026():
    res = calculate_lpr_interest(100000, "2026-01-01", "2026-10-21", term="1Y")
    assert round(res["total_interest"], 2) == 2408.22


@pytest.mark.xfail(strict=True, reason="待批次5修复")
def test_R5_private_lending_cap():
    res = calculate_lpr_interest(
        100000,
        "2019-12-01",
        "2021-12-01",
        fixed_annual_rate=20,
        rule_mode="private_lending_cap",
        contract_date="2019-12-01",
        filing_date="2021-12-01",
    )
    assert round(res["total_interest"], 2) == 34156.71


def test_R6_labor_compensation_7_months():
    res = calculate_labor_compensation(10000, "2020-03-15", "2026-10-10")
    assert res["compensation_months"] == 7
    assert res["tiers"]["N"]["amount"] == 70000
    assert res["tiers"]["N+1"]["amount"] == 80000
    assert res["tiers"]["2N"]["amount"] == 140000


def test_R7_labor_half_month():
    res = calculate_labor_compensation(10000, "2025-04-11", "2025-10-10")
    assert res["compensation_months"] == 0.5
    assert res["tiers"]["N"]["amount"] == 5000


def test_R8_labor_cap_local_avg():
    res = calculate_labor_compensation(
        50000, "2010-01-01", "2026-01-01", local_avg_salary=10000
    )
    assert res["tiers"]["N"]["amount"] == 360000


@pytest.mark.xfail(strict=True, reason="待批次5修复")
def test_R9_sol_cancel_mistake_90d():
    res = calculate_statute_of_limitations(
        "2026-01-01",
        cause_type="cancel_mistake_90d",
        today_date="2026-10-21",
    )
    assert res["final_expire_date"] == "2026-04-01"


def test_R10_sol_interruption():
    res = calculate_statute_of_limitations(
        "2023-01-01",
        interruption_events=[{"date": "2025-06-01", "type": "催告"}],
        today_date="2026-10-21",
    )
    assert res["final_expire_date"] == "2028-06-01"


@pytest.mark.xfail(strict=True, reason="待批次5修复")
def test_R11_preservation_renewal_7_days():
    res = calculate_preservation_renewal(
        "bank_deposit", "2026-01-01", today_date="2026-10-21"
    )
    assert res["advance_days_required"] == 7
    expire = res.get("expire_date") or res.get("expiry_date")
    assert expire is not None
    d_exp = datetime.strptime(expire[:10], "%Y-%m-%d").date()
    expected = (d_exp - timedelta(days=7)).isoformat()
    assert res["renewal_application_deadline"] == expected


_GUARANTEE_NODES = [
    {"id": "e1", "name": "债权人A", "role": "原告/债权人", "type": "company"},
    {"id": "e2", "name": "债务人B", "role": "主债务人/被告", "type": "company"},
    {"id": "e3", "name": "王某", "role": "保证人", "type": "person"},
]
_GUARANTEE_EDGES = [
    {"source": "e2", "target": "e1", "relation": "主借款合同"},
    {"source": "e3", "target": "e1", "relation": "保证", "detail": "未约定保证方式"},
]


@pytest.mark.xfail(strict=True, reason="待批次6修复")
def test_R12_guarantee_general_not_safe():
    timeline = [
        {
            "date": "2026-05-01",
            "event": "向王某发送律师函催告承担保证责任",
            "legal_tag": "催要主张",
        }
    ]
    res = analyze_guarantee_topology_and_deadlines(
        _GUARANTEE_NODES,
        _GUARANTEE_EDGES,
        timeline,
        principal_due_date="2026-03-31",
        today_date="2026-10-21",
    )
    assert res["statutory_guarantee_expiry"] == "2026-09-30"
    assert res["guarantee_audits"][0]["guarantee_type"].startswith("一般保证")
    assert res["guarantee_audits"][0]["status"] != "SAFE"


@pytest.mark.xfail(strict=True, reason="待批次6修复")
def test_R13_guarantee_insufficient_data():
    res = analyze_guarantee_topology_and_deadlines(
        _GUARANTEE_NODES, _GUARANTEE_EDGES, timeline=[], today_date="2026-10-21"
    )
    assert res["status"] == "insufficient_data"
    assert "principal_due_date" in res.get("missing_fields", [])
    assert res["guarantee_audits"] == []


@pytest.mark.xfail(strict=True, reason="待批次3修复")
def test_R14_verify_labor_contract_law():
    res = verify_statutory_validity("依据《劳动合同法》第四十七条")
    assert res["is_safe"] is True


@pytest.mark.xfail(strict=True, reason="待批次3修复")
def test_R15_abrogated_civil_law_general():
    res = audit_citations_in_text(
        raw_text="依据《民法总则》第一百八十八条", auto_sanitize=False
    )
    assert res["citations"][0]["status"] == "ABROGATED_BLOCKED"
    assert res["overall_status"] != "PERFECT_PASSED"


@pytest.mark.xfail(strict=True, reason="待批次3修复")
def test_R16_unrecognized_law():
    res = audit_citations_in_text(
        raw_text="依据《中华人民共和国智能合约促进法》第3条", auto_sanitize=False
    )
    assert res["citations"][0]["status"] == "UNRECOGNIZED_LAW"
    assert res["badge"]["color"] != "green"


@pytest.mark.xfail(strict=True, reason="待批次3修复")
def test_R17_unindexed_civil_code():
    res = audit_citations_in_text(
        raw_text="依据《民法典》第五百八十四条", auto_sanitize=False
    )
    assert res["citations"][0]["status"] == "UNINDEXED_UNVERIFIABLE"
    assert res["stats"]["verified_valid"] == 0
    assert res["badge"]["color"] != "green"


@pytest.mark.xfail(strict=True, reason="待批次3修复")
def test_R18_case_number_not_perfect():
    res = audit_citations_in_text(
        raw_text="参照（2025）京0105民初12345号判决", auto_sanitize=False
    )
    assert res["overall_status"] != "PERFECT_PASSED"
    assert "验真通过" not in res["badge"]["label"]


@pytest.mark.xfail(strict=True, reason="待批次3修复")
def test_R19_contract_law_no_replace_without_incident_date():
    res = audit_citations_in_text(
        raw_text="2019年签订合同，依据《合同法》第一百一十四条主张违约金。",
        auto_sanitize=True,
    )
    assert "《合同法》第一百一十四条" in res["sanitized_text"]


def test_R20_cashflow_reconcile():
    res = audit_and_reconcile_cashflow(
        [{"date": "2025-07-01", "amount": 5000, "purpose": "还款"}],
        principal_amount=100000,
        annual_rate=0.12,
        start_date="2025-01-01",
    )
    row = res["reconciliation_ledger"][0]
    assert row["days_accrued"] == 181
    assert row["total_interest_before_repay"] == pytest.approx(5950.68, abs=0.005)
    assert row["offset_to_interest"] == 5000
    assert row["offset_to_principal"] == 0
    assert row["unpaid_interest_after_repay"] == pytest.approx(950.68, abs=0.005)


@pytest.mark.xfail(strict=True, reason="待批次6修复")
def test_R20b_cashflow_no_weiyue_phrase():
    res = audit_and_reconcile_cashflow(
        [{"date": "2025-07-01", "amount": 5000, "purpose": "还款"}],
        principal_amount=100000,
        annual_rate=0.144,
        start_date="2025-01-01",
    )
    serialized = json.dumps(res, ensure_ascii=False)
    assert "未逾越" not in serialized


@pytest.mark.xfail(strict=True, reason="待批次8修复")
def test_R21_empty_judgment_no_flaws():
    res = analyze_first_instance_judgment_and_precedents(judgment_text="")
    assert res["flaw_diagnostics"] == []


@pytest.mark.xfail(strict=True, reason="待批次8修复")
def test_R22_enforcement_no_demo_numbers():
    res = analyze_enforcement_and_asset_penetration(claim_amount=50000)
    serialized = json.dumps(res, ensure_ascii=False)
    for bad in ("120000000", "1.2亿", "1.2 亿", "4950", "京01执889"):
        assert bad not in serialized


@pytest.mark.xfail(strict=True, reason="待批次7修复")
@pytest.mark.parametrize("court_name", ["北京市朝阳区人民法院", "北京市朝阳区"])
def test_R23_litigation_package_court_name(court_name, client):
    from gateway.routers.phase1_litigation import GenerateLitigationPackageReq

    payload = {
        "cause_of_action": "民间借贷纠纷",
        "plaintiff": {
            "name": "测试原告",
            "id_number": "110101199001011234",
            "address": "北京市朝阳区测试路1号",
            "phone": "13800000001",
        },
        "defendant": {
            "name": "测试被告",
            "id_number": "110101199002021234",
            "address": "北京市朝阳区测试路2号",
            "phone": "13800000002",
        },
        "claims": ["判令被告偿还借款本金人民币 100000 元；"],
        "claim_amount": 100000.0,
        "raw_case_notes": "2024年1月1日被告向原告借款10万元，出具借条，至今未还。",
        "court_name": court_name,
        "lawyer_name": "测试律师",
        "law_firm": "测试律师事务所",
        "auto_generate_sub_docs": False,
    }
    # 兼容 PartyInfo 字段名差异
    resp = client.post("/api/v1/phase1/generate-litigation-package", json=payload)
    if resp.status_code >= 400:
        # 尝试简化字段
        payload["plaintiff"] = {"name": "测试原告", "address": "北京", "id_card": "110101199001011234"}
        payload["defendant"] = {"name": "测试被告", "address": "北京", "id_card": "110101199002021234"}
        resp = client.post("/api/v1/phase1/generate-litigation-package", json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    # 定位生成的起诉状 docx
    files = data.get("files") or data.get("documents") or data.get("generated_files") or []
    docx_path = None
    if isinstance(files, list):
        for f in files:
            if isinstance(f, dict):
                p = f.get("path") or f.get("file_path") or f.get("filepath") or ""
                name = f.get("filename") or f.get("name") or p
                if str(name).endswith(".docx") and ("起诉" in str(name) or "诉讼" in str(name) or True):
                    docx_path = p or name
                    break
            elif isinstance(f, str) and f.endswith(".docx"):
                docx_path = f
                break
    if not docx_path:
        docx_path = data.get("main_docx_path") or data.get("docx_path")
    assert docx_path, f"未找到起诉状路径: {data.keys()}"
    path = Path(docx_path)
    if not path.is_file():
        # 可能是相对 storage/generated
        from gateway.core.paths import get_generated_dir
        path = get_generated_dir() / Path(docx_path).name
    import docx as python_docx
    doc = python_docx.Document(str(path))
    full = "\n".join(p.text for p in doc.paragraphs)
    assert "北京市朝阳区人民法院" in full
    assert "人民法院人民法院" not in full


@pytest.mark.parametrize(
    "uscc",
    ["914403001922038216", "91440300708461136T", "91330100799655058B"],
)
def test_R24_uscc_valid(uscc):
    res = validate_and_parse_uscc(uscc)
    assert res["valid"] is True
