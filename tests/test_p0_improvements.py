# -*- coding: utf-8 -*-
"""
LawFlow Workspace P0 Core Improvements Test Suite.
Covers:
- R1: Court Fees & Preservation Insurance Refinement (cn_legal_calc.py, phase1_litigation.py)
- R2: Supreme People's Court Mobile Court Standard Filing Package (phase1_litigation.py)
- R3: System Environment Health Probing Dashboard (service_probe.py, main.py, security.py)

Deterministic calculations, 4-tier archive structures, security authentication,
dependency resilience, and performance latency bounds.
"""
from __future__ import annotations

import io
import os
import time
import zipfile
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

from gateway.core.service_probe import (
    get_system_health_diagnostics,
    probe_cn_laws_kb,
    probe_libreoffice,
    probe_matter_vault,
    probe_ollama_service,
    probe_pdf_engine,
    reset_probe_cache,
)
from gateway.main import app
from gateway.utils.cn_legal_calc import (
    calculate_court_fees,
    calculate_preservation_insurance,
)

AUTH_TOKEN = os.environ.get("LAWFLOW_API_TOKEN", "test-token")
AUTH_HEADERS = {"X-LawFlow-Token": AUTH_TOKEN}


@pytest.fixture
def no_ollama_mock(monkeypatch):
    """Force offline LLM mode so litigation generation runs deterministic fallback instantly."""
    from gateway.core.ollama_client import ollama_client

    async def _offline(*args, **kwargs):
        return False

    monkeypatch.setattr(ollama_client, "_is_ollama_online", _offline)
    monkeypatch.setattr(
        ollama_client,
        "settings",
        {**ollama_client.settings, "provider": "ollama", "api_key": ""},
    )
    return ollama_client


def _sample_litigation_payload(archive_format: str = "spc_mobile") -> Dict[str, Any]:
    """Build a comprehensive litigation package payload with corporate parties and counsel."""
    return {
        "cause_of_action": "民间借贷纠纷",
        "plaintiff": {
            "name": "北京宏图商贸有限责任公司",
            "id_card_or_uscc": "91110108MA00000001",
            "address": "北京市海淀区中关村南大街1号",
            "phone": "13800000001",
            "party_type": "legal",
            "legal_rep": "张建国",
            "rep_position": "法定代表人",
        },
        "defendant": {
            "name": "北京信达科技有限责任公司",
            "id_card_or_uscc": "91110105MA00000002",
            "address": "北京市朝阳区建国门外大街2号",
            "phone": "13900000002",
            "party_type": "legal",
            "legal_rep": "李立新",
            "rep_position": "执行董事",
        },
        "claims": ["判令被告向原告偿还借款本金 200,000 元整"],
        "claim_amount": 200000.0,
        "raw_case_notes": "2023年6月1日被告向原告借款20万元，约定年化利率6%，到期后未偿还本息。",
        "court_name": "北京市朝阳区人民法院",
        "archive_format": archive_format,
        "auto_generate_sub_docs": True,
        "law_firm": "北京市智律律师事务所",
        "lawyer_name": "王执业",
        "lawyer_license": "11101202010123456",
        "lawyer_phone": "13700000003",
        "sub_documents": [
            "power_of_attorney",
            "service_address",
            "legal_rep_certificate",
            "property_preservation",
            "evidence_catalog",
            "law_firm_letter",
            "id_credential_attachment",
        ],
    }


# ==============================================================================
# 1. R1: Court Fees & Preservation Insurance Refinement
# ==============================================================================

@pytest.mark.parametrize(
    "claim_amount,expected_standard,expected_actual,expected_preservation",
    [
        (500000.0, 8800.0, 4400.0, 3020.0),
        (100000.0, 2300.0, 1150.0, 1020.0),
        (10000.0, 50.0, 25.0, 120.0),
        (1000.0, 50.0, 25.0, 30.0),
        (2500000.0, 26800.0, 13400.0, 5000.0),
    ],
)
def test_court_fee_summary_procedure_half_rate(
    claim_amount: float,
    expected_standard: float,
    expected_actual: float,
    expected_preservation: float,
):
    """
    Verify property claim court fee under summary procedure:
    - standard_fee matches statutory cumulative tier rates
    - actual_fee is exact 50% of standard_fee
    - fee_reduction_ratio == 0.5
    - reduction_amount == standard_fee - actual_fee
    - fee_amount alias strictly equals actual_fee
    - preservation_fee respects statutory tiers and 5000 RMB cap
    """
    res_summary = calculate_court_fees(claim_amount, is_summary_procedure=True)

    assert res_summary["standard_fee"] == expected_standard
    assert res_summary["actual_fee"] == expected_actual
    assert res_summary["fee_reduction_ratio"] == 0.5
    assert res_summary["reduction_amount"] == expected_standard - expected_actual
    assert res_summary["fee_amount"] == expected_actual
    assert res_summary["court_fee"] == expected_actual
    assert res_summary["preservation_fee"] == expected_preservation
    assert res_summary["statutory_reduction_rule"] is not None
    assert "《诉讼费用交纳办法》第十五条" in res_summary["statutory_reduction_rule"]

    # Contrast with ordinary procedure
    res_ordinary = calculate_court_fees(claim_amount, is_summary_procedure=False)
    assert res_ordinary["standard_fee"] == expected_standard
    assert res_ordinary["actual_fee"] == expected_standard
    assert res_ordinary["fee_reduction_ratio"] == 1.0
    assert res_ordinary["reduction_amount"] == 0.0
    assert res_ordinary["fee_amount"] == expected_standard
    assert res_ordinary["statutory_reduction_rule"] is None


def test_court_fee_summary_procedure_divorce():
    """
    Verify divorce case fee under ordinary and summary procedures:
    - claim <= 200,000 RMB: base fee only (default 100 RMB), half is 50 RMB
    - claim > 200,000 RMB: base fee + 0.5% excess, halved under summary procedure
    - custom divorce_base_fee (e.g. 200 RMB) handled accurately
    """
    # Case A: claim <= 200k with default 100 base fee
    res_div_low = calculate_court_fees(150000.0, case_type="divorce", is_summary_procedure=True)
    assert res_div_low["standard_fee"] == 100.0
    assert res_div_low["actual_fee"] == 50.0
    assert res_div_low["reduction_amount"] == 50.0
    assert res_div_low["fee_reduction_ratio"] == 0.5
    assert res_div_low["fee_amount"] == 50.0

    # Case B: claim > 200k (e.g. 500k -> 300k excess * 0.5% = 1500; total standard = 1600)
    res_div_high = calculate_court_fees(500000.0, case_type="离婚", is_summary_procedure=True)
    assert res_div_high["standard_fee"] == 1600.0
    assert res_div_high["actual_fee"] == 800.0
    assert res_div_high["reduction_amount"] == 800.0
    assert res_div_high["fee_reduction_ratio"] == 0.5
    assert res_div_high["fee_amount"] == 800.0

    # Case C: custom divorce_base_fee = 200.0
    res_div_custom = calculate_court_fees(
        100000.0, case_type="divorce", is_summary_procedure=True, divorce_base_fee=200.0
    )
    assert res_div_custom["standard_fee"] == 200.0
    assert res_div_custom["actual_fee"] == 100.0
    assert res_div_custom["reduction_amount"] == 100.0


def test_court_fee_zero_and_negative_handling(client: TestClient):
    """
    Verify zero and negative edge cases:
    - Negative claim_amount: raises ValueError in engine and returns HTTP 422 via API
    - Zero claim_amount for property case: raises ValueError in engine and returns HTTP 422 via API
    - Zero preservation_amount: preservation fee & insurance cost return 0.0 without errors
    - Negative preservation_amount: raises ValueError in engine and returns HTTP 422 via API
    """
    # 1. Engine negative claim_amount raises ValueError
    with pytest.raises(ValueError, match="诉讼标的额不能为负数"):
        calculate_court_fees(-1.0)

    # 2. Engine zero claim_amount for property case raises ValueError
    with pytest.raises(ValueError, match="财产案件标的额须大于 0"):
        calculate_court_fees(0.0, case_type="property")

    # 3. Engine zero preservation_amount returns 0.0 preservation fee and 0.0 insurance
    res_zero_preserv = calculate_court_fees(100000.0, preservation_amount=0.0)
    assert res_zero_preserv["preservation_fee"] == 0.0
    assert res_zero_preserv["preservation_insurance"]["cost_low"] == 0.0
    assert res_zero_preserv["preservation_insurance"]["cost_high"] == 0.0

    # 4. Engine negative preservation_amount raises ValueError
    with pytest.raises(ValueError, match="保全金额不能为负数"):
        calculate_court_fees(100000.0, preservation_amount=-50.0)

    # 5. API negative claim_amount returns 422
    resp_neg = client.post(
        "/api/v1/phase1/calc/court-fees",
        json={"claim_amount": -100.0, "case_type": "property"},
        headers=AUTH_HEADERS,
    )
    assert resp_neg.status_code == 422

    # 6. API zero claim_amount for property returns 422
    resp_zero = client.post(
        "/api/v1/phase1/calc/court-fees",
        json={"claim_amount": 0.0, "case_type": "property"},
        headers=AUTH_HEADERS,
    )
    assert resp_zero.status_code == 422

    # 7. API negative preservation_amount returns 422
    resp_neg_p = client.post(
        "/api/v1/phase1/calc/court-fees",
        json={"claim_amount": 100000.0, "preservation_amount": -200.0},
        headers=AUTH_HEADERS,
    )
    assert resp_neg_p.status_code == 422


def test_preservation_insurance_calculation():
    """
    Verify preservation liability insurance calculation:
    - 100,000 RMB: 80 / 150 < 500 RMB floor -> min premium applied: 500 RMB low and high
    - 1,000,000 RMB: 800 RMB low, 1500 RMB high -> min premium not applied
    - Custom rates and min premium (e.g. 0.0010 ~ 0.0020, min 1000 RMB)
    - preservation_amount == 0 -> 0.0 cost without floor enforcement
    - preservation_amount < 0 -> ValueError
    - Invalid rates (min > max or negative) -> ValueError
    """
    # 1. 100k RMB with default rates (0.08%~0.15%, min 500 RMB)
    ins_100k = calculate_preservation_insurance(100000.0)
    assert ins_100k["cost_low"] == 500.0
    assert ins_100k["cost_high"] == 500.0
    assert ins_100k["is_minimum_charge_applied_low"] is True
    assert ins_100k["is_minimum_charge_applied_high"] is True
    assert ins_100k["min_rate_pct"] == "0.08%"
    assert ins_100k["max_rate_pct"] == "0.15%"
    assert ins_100k["cost_range_display"] == "¥ 500.00 ~ ¥ 500.00"
    assert "法释〔2016〕22号" in ins_100k["statutory_basis"]

    # 2. 1M RMB
    ins_1m = calculate_preservation_insurance(1000000.0)
    assert ins_1m["cost_low"] == 800.0
    assert ins_1m["cost_high"] == 1500.0
    assert ins_1m["is_minimum_charge_applied_low"] is False
    assert ins_1m["is_minimum_charge_applied_high"] is False
    assert ins_1m["cost_range_display"] == "¥ 800.00 ~ ¥ 1,500.00"

    # 3. Custom rates & custom min premium
    # 500k with 0.10% ~ 0.20%, min 1000:
    # 500k * 0.0010 = 500 < 1000 -> 1000 (min applied)
    # 500k * 0.0020 = 1000 == 1000 -> 1000 (not strictly less than min)
    ins_custom = calculate_preservation_insurance(
        500000.0,
        min_rate=Decimal("0.0010"),
        max_rate=Decimal("0.0020"),
        min_premium=Decimal("1000.00"),
    )
    assert ins_custom["cost_low"] == 1000.0
    assert ins_custom["cost_high"] == 1000.0
    assert ins_custom["is_minimum_charge_applied_low"] is True
    assert ins_custom["is_minimum_charge_applied_high"] is False

    # 4. Zero preservation amount returns 0.0
    ins_zero = calculate_preservation_insurance(0.0)
    assert ins_zero["cost_low"] == 0.0
    assert ins_zero["cost_high"] == 0.0
    assert ins_zero["is_minimum_charge_applied_low"] is False
    assert ins_zero["is_minimum_charge_applied_high"] is False

    # 5. Negative preservation amount raises ValueError
    with pytest.raises(ValueError, match="保全金额不能为负数"):
        calculate_preservation_insurance(-100.0)

    # 6. Invalid rates raise ValueError
    with pytest.raises(ValueError, match="费率"):
        calculate_preservation_insurance(100000.0, min_rate=0.002, max_rate=0.001)

    with pytest.raises(ValueError, match="费率"):
        calculate_preservation_insurance(100000.0, min_rate=-0.001)

    with pytest.raises(ValueError, match="最低保费不能为负数"):
        calculate_preservation_insurance(100000.0, min_premium=-10.0)


def test_court_fees_api_endpoint(client: TestClient):
    """Verify POST /api/v1/phase1/calc/court-fees with token, summary procedure, and preservation insurance."""
    payload = {
        "claim_amount": 500000.0,
        "case_type": "property",
        "is_summary_procedure": True,
        "preservation_amount": 200000.0,
    }
    resp = client.post(
        "/api/v1/phase1/calc/court-fees",
        json=payload,
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["standard_fee"] == 8800.0
    assert data["actual_fee"] == 4400.0
    assert data["fee_reduction_ratio"] == 0.5
    assert data["reduction_amount"] == 4400.0
    assert data["fee_amount"] == 4400.0
    assert data["preservation_fee"] == 1520.0  # 30 + 990 + (100k * 0.005) = 1520.0
    assert "preservation_insurance" in data
    ins = data["preservation_insurance"]
    # 200k: 160 / 300 < 500 -> 500
    assert ins["cost_low"] == 500.0
    assert ins["cost_high"] == 500.0


def test_preservation_insurance_api_endpoint(client: TestClient):
    """Verify POST /api/v1/phase1/calc/preservation-insurance with token and parameter variations."""
    payload = {
        "preservation_amount": 1000000.0,
        "min_rate": 0.0008,
        "max_rate": 0.0015,
        "min_premium": 500.0,
    }
    resp = client.post(
        "/api/v1/phase1/calc/preservation-insurance",
        json=payload,
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["cost_low"] == 800.0
    assert data["cost_high"] == 1500.0
    assert data["is_minimum_charge_applied_low"] is False
    assert data["is_minimum_charge_applied_high"] is False
    assert data["min_rate_pct"] == "0.08%"
    assert data["max_rate_pct"] == "0.15%"

    # Zero preservation amount via API
    resp_zero = client.post(
        "/api/v1/phase1/calc/preservation-insurance",
        json={"preservation_amount": 0.0},
        headers=AUTH_HEADERS,
    )
    assert resp_zero.status_code == 200
    assert resp_zero.json()["cost_low"] == 0.0
    assert resp_zero.json()["cost_high"] == 0.0

    # Negative preservation amount via API
    resp_neg = client.post(
        "/api/v1/phase1/calc/preservation-insurance",
        json={"preservation_amount": -100.0},
        headers=AUTH_HEADERS,
    )
    assert resp_neg.status_code == 422


# ==============================================================================
# 2. R2: Supreme People's Court Mobile Court Standard Filing Package
# ==============================================================================

def test_mobile_court_zip_structure(client: TestClient, no_ollama_mock):
    """
    Generate litigation package with format 'spc_mobile', extract ZIP archive, and verify:
    - Exact existence of the 4 Supreme People's Court mobile service categorized directories:
      1. 01_起诉状及身份证明/
      2. 02_委托代理材料/
      3. 03_送达地址确认书/
      4. 04_证据清单与证据材料/
    - Court supporting documents generated in 02_委托代理材料/: '律师事务所公函', '民事授权委托书'
    - Supporting documents generated in 01_起诉状及身份证明/: '法定代表人身份证明书', '民事起诉状'
    """
    payload = _sample_litigation_payload(archive_format="spc_mobile")
    resp = client.post(
        "/api/v1/phase1/generate-litigation-package",
        json=payload,
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    package_id = data.get("package_id")
    assert package_id, "Missing package_id"
    assert "package_zip_url" in data
    assert "archive_categories" in data

    # Check category structure in response payload
    categories = data["archive_categories"]
    expected_dirs = [
        "01_起诉状及身份证明",
        "02_委托代理材料",
        "03_送达地址确认书",
        "04_证据清单与证据材料",
    ]
    for cat in expected_dirs:
        assert cat in categories, f"Missing category {cat} in response archive_categories"

    # Download the generated ZIP file
    zip_resp = client.get(data["package_zip_url"], headers=AUTH_HEADERS)
    assert zip_resp.status_code == 200, zip_resp.text
    assert zip_resp.headers.get("content-type") == "application/zip"

    # Inspect ZIP archive contents
    zf = zipfile.ZipFile(io.BytesIO(zip_resp.content), "r")
    namelist = zf.namelist()

    # 1. Verify existence of the 4 standard categorized directories
    assert any(n.startswith("01_起诉状及身份证明/") for n in namelist), "Missing category 01"
    assert any(n.startswith("02_委托代理材料/") for n in namelist), "Missing category 02"
    assert any(n.startswith("03_送达地址确认书/") for n in namelist), "Missing category 03"
    assert any(n.startswith("04_证据清单与证据材料/") for n in namelist), "Missing category 04"

    # 2. Verify court supporting documents in 02_委托代理材料/
    files_cat_02 = [n for n in namelist if n.startswith("02_委托代理材料/")]
    assert any("律师事务所公函" in n for n in files_cat_02), "Missing 律师事务所公函 in 02_委托代理材料"
    assert any("民事授权委托书" in n for n in files_cat_02), "Missing 民事授权委托书 in 02_委托代理材料"

    # 3. Verify court supporting documents in 01_起诉状及身份证明/
    files_cat_01 = [n for n in namelist if n.startswith("01_起诉状及身份证明/")]
    assert any("起诉状" in n for n in files_cat_01), "Missing 起诉状 in 01_起诉状及身份证明"
    assert any(
        ("法定代表人身份证明" in n or "原告身份证明材料说明页" in n) for n in files_cat_01
    ), "Missing 法定代表人身份证明 in 01_起诉状及身份证明"

    # 4. Verify 03_送达地址确认书/
    files_cat_03 = [n for n in namelist if n.startswith("03_送达地址确认书/")]
    assert any("送达地址确认书" in n for n in files_cat_03), "Missing 送达地址确认书 in 03_送达地址确认书"

    # 5. Verify 04_证据清单与证据材料/
    files_cat_04 = [n for n in namelist if n.startswith("04_证据清单与证据材料/")]
    assert any("证据目录" in n for n in files_cat_04), "Missing 证据目录 in 04_证据清单与证据材料"


def test_flat_zip_structure(client: TestClient, no_ollama_mock):
    """Verify legacy flat archive layout produces single-level archive without categorized subdirectories."""
    payload = _sample_litigation_payload(archive_format="flat")
    resp = client.post(
        "/api/v1/phase1/generate-litigation-package",
        json=payload,
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    flat_url = data["package_flat_zip_url"]
    zip_resp = client.get(flat_url, headers=AUTH_HEADERS)
    assert zip_resp.status_code == 200
    assert zip_resp.headers.get("content-type") == "application/zip"

    zf = zipfile.ZipFile(io.BytesIO(zip_resp.content), "r")
    namelist = zf.namelist()
    assert len(namelist) > 0

    # In flat layout, files must reside at the root level without 01_, 02_, 03_, 04_ prefixes
    for name in namelist:
        assert not name.startswith("01_")
        assert not name.startswith("02_")
        assert not name.startswith("03_")
        assert not name.startswith("04_")
        assert "/" not in name, f"Flat archive should not contain directory separators: {name}"


def test_package_download_endpoint_security(client: TestClient, client_no_auth: TestClient, no_ollama_mock):
    """
    Verify download endpoint security:
    - Valid header token or query token: returns application/zip with '立案公文包_' Content-Disposition
    - Non-existent package_id: strictly returns HTTP 404 (does NOT leak other packages)
    - Missing token on protected endpoints: returns HTTP 401
    """
    # Step 1: Generate a valid package
    payload = _sample_litigation_payload()
    resp = client.post(
        "/api/v1/phase1/generate-litigation-package",
        json=payload,
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 200
    pkg_id = resp.json()["package_id"]

    # Step 2: Download with valid header token
    resp_hdr = client.get(
        f"/api/v1/phase1/package/{pkg_id}/download?format=spc_mobile",
        headers=AUTH_HEADERS,
    )
    assert resp_hdr.status_code == 200
    assert resp_hdr.headers.get("content-type") == "application/zip"
    content_disp = resp_hdr.headers.get("content-disposition", "")
    assert "立案公文包_" in content_disp or "attachment" in content_disp

    # Step 3: Download with query parameter token (?token=...) using client_no_auth
    resp_query = client_no_auth.get(
        f"/api/v1/phase1/package/{pkg_id}/download?format=spc_mobile&token={AUTH_TOKEN}"
    )
    assert resp_query.status_code == 200
    assert resp_query.headers.get("content-type") == "application/zip"

    # Step 4: Query invalid package_id must strictly return HTTP 404 without leaking disk files
    resp_invalid = client.get(
        "/api/v1/phase1/package/pkg-invalid-nonexistent-9999999/download",
        headers=AUTH_HEADERS,
    )
    assert resp_invalid.status_code == 404
    assert "未找到" in str(resp_invalid.json()) or "404" in str(resp_invalid.json())

    # Step 5: Unauthenticated access without token returns HTTP 401
    resp_unauth = client_no_auth.get(f"/api/v1/phase1/package/{pkg_id}/download?format=spc_mobile")
    assert resp_unauth.status_code == 401

    resp_unauth_gen = client_no_auth.post(
        "/api/v1/phase1/generate-litigation-package",
        json=payload,
    )
    assert resp_unauth_gen.status_code == 401


# ==============================================================================
# 3. R3: System Environment Health Probing Dashboard
# ==============================================================================

@pytest.mark.parametrize(
    "endpoint_path",
    [
        "/api/system/health",
        "/api/system/health/",
        "/health",
        "/health/",
        "/api/health",
        "/api/v1/health",
    ],
)
def test_system_health_endpoint_contract(client_no_auth: TestClient, endpoint_path: str):
    """
    Verify system health endpoint contract:
    - Returns 200 OK without any authentication token (exempt in security middleware)
    - Handles trailing slashes gracefully without 401 interception
    - Conforms to standard response schema containing overall_status, diagnostics, and engine flags
    """
    resp = client_no_auth.get(endpoint_path)
    assert resp.status_code == 200, f"{endpoint_path} failed with {resp.status_code}: {resp.text}"
    data = resp.json()

    assert isinstance(data, dict)
    assert data.get("app") == "LawFlow"
    assert data.get("overall_status") in ("OK", "DEGRADED", "MISSING")
    assert data.get("status") in ("healthy", "degraded")
    assert isinstance(data.get("ocr_available"), bool)
    assert isinstance(data.get("llm_mode"), str)
    assert isinstance(data.get("model_ready"), bool)
    assert isinstance(data.get("summary"), str) and len(data["summary"]) > 0

    # Validate diagnostics dictionary and required keys
    assert "diagnostics" in data
    diag = data["diagnostics"]
    required_keys = ["libreoffice", "ollama", "cn_laws_kb", "matter_vault", "pdf_engine"]
    for key in required_keys:
        assert key in diag, f"Missing diagnostic key: {key}"
        assert "status" in diag[key], f"Missing status in {key} diagnostic"
        assert "remediation" in diag[key], f"Missing remediation in {key} diagnostic"
        assert diag[key]["status"] in ("OK", "DEGRADED", "MISSING")

    assert "dependencies" in data
    assert data["dependencies"] == diag


def test_system_health_missing_soffice_resilience(monkeypatch):
    """Verify LibreOffice absence is gracefully detected with MISSING status and actionable remediation."""
    reset_probe_cache()
    monkeypatch.setattr("gateway.routers.phase1_litigation._find_soffice", lambda: None)

    diag = probe_libreoffice()
    assert diag["status"] == "MISSING"
    assert diag["path"] is None
    assert "LibreOffice" in diag["remediation"]
    assert "PyMuPDF" in diag["remediation"]


def test_system_health_missing_ollama_resilience(monkeypatch):
    """Verify Ollama offline state is gracefully detected with MISSING status and 'ollama serve' remediation."""
    reset_probe_cache()
    monkeypatch.setattr("gateway.core.service_probe.is_ollama_available", lambda force=False: False)

    diag = probe_ollama_service(force=True)
    assert diag["status"] == "MISSING"
    assert diag["active_model"] is None
    assert "ollama serve" in diag["remediation"]


def test_system_health_database_resilience(monkeypatch, tmp_path: Path):
    """
    Verify SQLite database resilience:
    - Non-existent database path returns MISSING or DEGRADED without throwing unhandled HTTP 500
    - Corrupted or 0-byte database file returns DEGRADED without throwing unhandled HTTP 500
    """
    # 1. Non-existent database path
    non_existent_kb = tmp_path / "non_existent_kb.db"
    non_existent_vault = tmp_path / "non_existent_vault.db"

    monkeypatch.setattr("gateway.core.paths.get_laws_db_path", lambda: non_existent_kb)
    monkeypatch.setattr("gateway.core.paths.get_vault_db_path", lambda: non_existent_vault)

    kb_diag_missing = probe_cn_laws_kb()
    assert kb_diag_missing["status"] == "MISSING"
    assert kb_diag_missing["laws_count"] == 0

    vault_diag_missing = probe_matter_vault()
    assert vault_diag_missing["status"] == "MISSING"
    assert vault_diag_missing["matters_count"] == 0

    # Full diagnostics pipeline survives non-existent DBs
    full_diag_missing = get_system_health_diagnostics(force=True)
    assert full_diag_missing["overall_status"] in ("MISSING", "DEGRADED")

    # 2. Corrupted / 0-byte database file
    corrupt_kb = tmp_path / "corrupt_kb.db"
    corrupt_kb.write_bytes(b"")
    corrupt_vault = tmp_path / "corrupt_vault.db"
    corrupt_vault.write_bytes(b"")

    monkeypatch.setattr("gateway.core.paths.get_laws_db_path", lambda: corrupt_kb)
    monkeypatch.setattr("gateway.core.paths.get_vault_db_path", lambda: corrupt_vault)

    kb_diag_corrupt = probe_cn_laws_kb()
    assert kb_diag_corrupt["status"] == "DEGRADED"

    vault_diag_corrupt = probe_matter_vault()
    assert vault_diag_corrupt["status"] == "DEGRADED"

    full_diag_corrupt = get_system_health_diagnostics(force=True)
    assert full_diag_corrupt["overall_status"] in ("DEGRADED", "MISSING")


def test_system_health_latency_under_launcher_timeout(client_no_auth: TestClient):
    """
    Verify health check warm latency:
    Must resolve in < 0.20s (well below launcher.pyw's 0.8s readiness timeout)
    to prevent desktop application startup freezes.
    """
    # Warm up probe cache
    resp_warmup = client_no_auth.get("/api/system/health")
    assert resp_warmup.status_code == 200

    # Measure warm latency over multiple iterations
    latencies = []
    for _ in range(5):
        t0 = time.perf_counter()
        resp = client_no_auth.get("/api/system/health")
        t1 = time.perf_counter()
        assert resp.status_code == 200
        latencies.append(t1 - t0)

    avg_latency = sum(latencies) / len(latencies)
    max_latency = max(latencies)

    assert max_latency < 0.20, f"Max health check latency {max_latency:.3f}s exceeds 0.20s threshold"
    assert avg_latency < 0.05, f"Average health check latency {avg_latency:.3f}s exceeds 0.05s threshold"
