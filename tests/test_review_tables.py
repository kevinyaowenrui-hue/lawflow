# -*- coding: utf-8 -*-
"""批次14 I-31：阅卷表列缺 id 不再导致 500。"""
from __future__ import annotations

import pytest


@pytest.fixture
def matter_id(client):
    resp = client.post(
        "/api/v1/vault/matters",
        json={
            "title": "阅卷表缺id验收案",
            "cause_of_action": "买卖合同纠纷",
            "plaintiff_name": "甲",
            "defendant_name": "乙",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    matter = body.get("matter") or body
    mid = matter.get("matter_id") or body.get("matter_id")
    assert mid
    return mid


def test_columns_without_id_get_unique_ids_and_apis_ok(client, matter_id, monkeypatch):
    from gateway.core import ollama_client as oc_mod

    async def _fake_generate(*args, **kwargs):
        return '{"value": "测试值", "confidence": 0.9, "source_quote": "原文"}'

    monkeypatch.setattr(oc_mod.ollama_client, "generate", _fake_generate)

    create = client.post(
        f"/api/v1/vault/matters/{matter_id}/review-tables",
        json={
            "title": "无id列验收表",
            "description": "I-31",
            "columns": [
                {"name": "签约主体", "instruction": "提取签约双方", "type": "text"},
                {"name": "涉案金额", "instruction": "提取金额", "type": "currency"},
            ],
        },
    )
    assert create.status_code == 200, create.text
    table = create.json()["table"]
    cols = table["columns"]
    assert len(cols) == 2
    ids = [c["id"] for c in cols]
    assert all(ids)
    assert len(set(ids)) == 2

    table_id = table["table_id"]

    # 确保有至少一行
    if not table.get("rows"):
        add_row = client.post(
            f"/api/v1/vault/review-tables/{table_id}/rows",
            json={
                "doc_title": "测试合同.pdf",
                "doc_type": "contract",
                "content_text": "甲方测试公司与乙方测试商号签订合同，货款30万元。",
            },
        )
        assert add_row.status_code == 200, add_row.text
        table = add_row.json()["table"]

    row_id = table["rows"][0]["row_id"]
    col_id = cols[0]["id"]

    run_all = client.post(f"/api/v1/vault/review-tables/{table_id}/run-all")
    assert 200 <= run_all.status_code < 300, run_all.text

    cell = client.post(
        f"/api/v1/vault/review-tables/{table_id}/cells/{row_id}/{col_id}/refresh"
    )
    assert 200 <= cell.status_code < 300, cell.text

    col_ref = client.post(
        f"/api/v1/vault/review-tables/{table_id}/columns/{col_id}/refresh"
    )
    assert 200 <= col_ref.status_code < 300, col_ref.text

    csv_resp = client.get(f"/api/v1/vault/review-tables/{table_id}/export/csv")
    assert 200 <= csv_resp.status_code < 300, csv_resp.text

    xlsx_resp = client.get(f"/api/v1/vault/review-tables/{table_id}/export/xlsx")
    assert 200 <= xlsx_resp.status_code < 300, xlsx_resp.text

    # 删除列
    del_col = client.delete(
        f"/api/v1/vault/review-tables/{table_id}/columns/{cols[1]['id']}"
    )
    assert 200 <= del_col.status_code < 300, del_col.text

    missing = client.post(
        f"/api/v1/vault/review-tables/{table_id}/columns/col_does_not_exist/refresh"
    )
    assert missing.status_code == 404
    assert "列不存在" in missing.text
