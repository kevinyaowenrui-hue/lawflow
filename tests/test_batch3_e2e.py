# -*- coding: utf-8 -*-
"""
Batch 3 端到端：阅卷表、单元格重刷、原文定位、多版本比对与 Word 修订导出。
"""
from __future__ import annotations

import pytest

from gateway.core.paths import get_generated_dir


MATTER_ID = "MATTER-2026-001"


@pytest.fixture
def batch3_client(client, seed_demo):
    return client


@pytest.fixture
def seed_review_table(batch3_client):
    client = batch3_client
    resp = client.get(f"/api/v1/vault/matters/{MATTER_ID}/review-tables")
    assert resp.status_code == 200, resp.text
    tables_data = resp.json()
    assert tables_data["status"] == "success"
    target_tbl = next(
        (t for t in tables_data["tables"] if t["table_id"] == "TABLE-2026-SEED-01"),
        tables_data["tables"][0],
    )
    return target_tbl["table_id"]


@pytest.fixture
def table_detail(batch3_client, seed_review_table):
    client = batch3_client
    table_id = seed_review_table
    resp = client.get(f"/api/v1/vault/review-tables/{table_id}")
    assert resp.status_code == 200, resp.text
    return resp.json()["table"]


VERSION_PAYLOAD = {
    "base_title": "《企业间借款合同·律所标准母本版》",
    "base_text": """
第一条 借款金额：借款金额为人民币5,000,000.00元整。
第二条 借款期限：借款期限自2025年1月10日起至2026年1月9日止。
第三条 借款利息：年利率固定为12%，按季度结息，逾期加收日万分之五罚息。
第四条 保证担保：丙方自然人股东承担连带保证责任，保证范围包括本金、利息、违约金及律师费。
第五条 争议解决：因履行本合同引起的争议，由出借人所在地人民法院管辖。
""",
    "target_title": "《企业间借款合同·相对方修订草案》",
    "target_text": """
第一条 借款金额：借款金额为人民币5,000,000.00元整。
第二条 借款期限：借款期限经双方协商延长至2026年7月9日止。
第三条 借款利息：年利率固定为6%，到期一次性还本付息，取消逾期罚息。
第五条 争议解决：发生争议由中国国际经济贸易仲裁委员会北京分会仲裁。
第六条 提前还款：借款人提前偿还本金的，不承担任何违约赔偿责任。
""",
}


def test_health_probe(batch3_client):
    resp = batch3_client.get("/health")
    assert resp.status_code == 200
    assert resp.json().get("status") == "healthy"


def test_list_review_tables(batch3_client, seed_review_table):
    resp = batch3_client.get(f"/api/v1/vault/matters/{MATTER_ID}/review-tables")
    assert resp.status_code == 200
    tables_data = resp.json()
    assert tables_data["status"] == "success"
    assert tables_data["total"] >= 1
    assert seed_review_table


def test_review_table_grid_has_columns_and_rows(table_detail):
    columns = table_detail.get("columns", [])
    rows = table_detail.get("rows", [])
    assert len(columns) >= 4
    assert len(rows) >= 2


@pytest.mark.requires_ollama
def test_cell_level_refresh(batch3_client, seed_review_table, table_detail):
    client = batch3_client
    table_id = seed_review_table
    test_row = table_detail["rows"][0]
    test_col = table_detail["columns"][0]
    resp = client.post(
        f"/api/v1/vault/review-tables/{table_id}/cells/{test_row['id']}/{test_col['id']}/refresh"
    )
    assert resp.status_code == 200, resp.text
    cell_res = resp.json()
    assert cell_res["status"] == "success"
    assert cell_res["cell"].get("value")


@pytest.mark.requires_ollama
def test_add_column_and_refresh_new_cell(batch3_client, seed_review_table, table_detail):
    client = batch3_client
    table_id = seed_review_table
    test_row = table_detail["rows"][0]
    new_col_payload = {
        "name": "约定管辖法院与争议解决",
        "instruction": "提取合同或协议中明确约定的纠纷管辖法院或仲裁条款，包括原告所在地或被告所在地法院。",
        "type": "text",
    }
    resp = client.post(f"/api/v1/vault/review-tables/{table_id}/columns", json=new_col_payload)
    assert resp.status_code == 200, resp.text
    add_col_res = resp.json()
    assert add_col_res["status"] == "success"
    updated_columns = add_col_res["table"]["columns"]
    added_col = next((c for c in reversed(updated_columns) if "约定管辖法院" in c["name"]), None)
    assert added_col is not None
    refresh = client.post(
        f"/api/v1/vault/review-tables/{table_id}/cells/{test_row['id']}/{added_col['id']}/refresh"
    )
    assert refresh.status_code == 200, refresh.text


@pytest.mark.requires_ollama
def test_run_all_on_lightweight_table(batch3_client):
    client = batch3_client
    test_tbl_resp = client.post(
        f"/api/v1/vault/matters/{MATTER_ID}/review-tables",
        json={
            "title": "并发提取专用评阅表",
            "description": "轻量测试全表并发",
            "columns": [
                {"id": "col_fast_1", "name": "核心当事人", "instruction": "提取当事人名称", "type": "text"}
            ],
        },
    )
    assert test_tbl_resp.status_code == 200, test_tbl_resp.text
    test_tbl_id = test_tbl_resp.json()["table"]["table_id"]
    resp = client.post(f"/api/v1/vault/review-tables/{test_tbl_id}/run-all")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "success"


def test_export_review_table_csv(batch3_client, seed_review_table):
    resp = batch3_client.get(f"/api/v1/vault/review-tables/{seed_review_table}/export/csv")
    assert resp.status_code == 200, resp.text
    csv_content = resp.content.decode("utf-8-sig")
    assert (
        "案卷材料名称" in csv_content
        or "doc_title" in csv_content
        or "签约主体" in csv_content
        or "原告" in csv_content
    )


def test_source_grounding_excerpt(batch3_client):
    resp = batch3_client.get(
        f"/api/v1/vault/matters/{MATTER_ID}/grounding/excerpt",
        params={"doc_title": "借款合同", "page_no": 1, "query_text": "连带保证责任"},
    )
    assert resp.status_code == 200, resp.text
    grounding_res = resp.json()
    assert grounding_res["status"] == "success"
    assert grounding_res["found"] is True
    assert grounding_res["char_start"] >= 0


def test_compare_versions_detects_delete_and_add(batch3_client):
    resp = batch3_client.post("/api/v1/contract/compare-versions", json=VERSION_PAYLOAD)
    assert resp.status_code == 200, resp.text
    cmp_res = resp.json()
    assert cmp_res["status"] == "success"
    stats = cmp_res["comparison"]["stats"]
    clauses = cmp_res["comparison"]["aligned_clauses"]
    assert stats["deleted_count"] >= 1
    assert stats["added_count"] >= 1
    deleted_clause = next((c for c in clauses if c["status"] == "DELETED"), None)
    assert deleted_clause is not None


def test_export_version_diff_docx_to_storage(batch3_client):
    resp = batch3_client.post("/api/v1/contract/export-version-diff", json=VERSION_PAYLOAD)
    assert resp.status_code == 200, resp.text
    docx_res = resp.json()
    assert docx_res["status"] == "success"
    filename = docx_res["filename"]
    assert filename.endswith(".docx")
    file_disk_path = get_generated_dir() / filename
    assert file_disk_path.exists()
    assert file_disk_path.stat().st_size > 1000
