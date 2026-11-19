# -*- coding: utf-8 -*-
"""公函身份与函号：京师所全称可以入文书，示例身份和示例字号不能由系统写出来。"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime

import docx
import pytest


def _docx_full_text(path: str) -> str:
    document = docx.Document(path)
    parts = [p.text for p in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                parts.append(cell.text)
    return "\n".join(parts)


@pytest.fixture
def no_ollama(monkeypatch):
    from gateway.core.ollama_client import ollama_client

    async def _offline(*args, **kwargs):
        return False

    monkeypatch.setattr(ollama_client, "_is_ollama_online", _offline)
    monkeypatch.setattr(ollama_client, "settings", {**ollama_client.settings, "provider": "ollama", "api_key": ""})
    return ollama_client


def _generate_letter(client, plaintiff_name="函号原告甲", defendant_name="函号被告乙", **extra):
    payload = {
        "cause_of_action": "买卖合同纠纷",
        "claim_amount": 10000,
        "raw_case_notes": "被告欠付货款一万元，催告后未付。",
        "court_name": "北京市海淀区人民法院",
        "plaintiff": {"name": plaintiff_name, "address": "北京市海淀区测试路1号", "phone": "13800000001"},
        "defendant": {"name": defendant_name, "address": "北京市朝阳区测试路2号", "phone": "13800000002"},
        "claims": ["判令被告支付货款10000元"],
        "sub_documents": ["law_firm_letter"],
    }
    payload.update(extra)
    resp = client.post("/api/v1/phase1/generate-litigation-package", json=payload)
    assert resp.status_code == 200, resp.text
    docs = {item["doc_type"]: item["path"] for item in resp.json()["generated_documents"]}
    assert "律师事务所公函" in docs
    return _docx_full_text(docs["律师事务所公函"])


def test_jingshi_firm_name_is_saved_and_written_into_letter(client, no_ollama):
    direct = _generate_letter(
        client,
        plaintiff_name="京师原告甲",
        defendant_name="京师被告乙",
        lawyer_name="李承办",
        law_firm="北京市京师律师事务所",
    )
    assert "北京市京师律师事务所" in direct
    assert "李承办" in direct
    assert "执业证号：【待填写】" in direct
    assert "联系电话：【待填写】" in direct
    for fake in ("王律师", "13900008888", "11101201510123456", "京律函字"):
        assert fake not in direct

    saved = client.post("/api/v1/vault/firm-roster", json={
        "lawyer_name": "赵承办",
        "license_no": "11101202010543210",
        "law_firm": "北京市京师律师事务所",
        "phone": "13800006666",
        "is_default": True,
    })
    assert saved.status_code == 200, saved.text
    assert saved.json()["lawyer"]["law_firm"] == "北京市京师律师事务所"

    from_roster = _generate_letter(
        client,
        plaintiff_name="京师原告丙",
        defendant_name="京师被告丁",
    )
    assert "北京市京师律师事务所" in from_roster
    assert "赵承办" in from_roster
    assert "11101202010543210" in from_roster
    for fake in ("王律师", "13900008888", "11101201510123456", "京律函字"):
        assert fake not in from_roster


def test_empty_prefix_does_not_invent_demo_identity(client, no_ollama):
    storage = os.environ["LAWFLOW_STORAGE_DIR"]
    assert "lawflow-pytest-tmp" in storage.replace("/", "\\").lower()

    rejected = client.post("/api/v1/phase1/letter-prefix", json={"prefix": "京律函字"})
    assert rejected.status_code == 422
    assert client.get("/api/v1/phase1/letter-prefix").json()["prefix"] == ""

    text = _generate_letter(
        client,
        plaintiff_name="空前缀原告",
        defendant_name="空前缀被告",
    )
    for fake in ("王律师", "13900008888", "11101201510123456", "京律函字", "北京市京师律师事务所"):
        assert fake not in text
    assert "【待填写函号前缀】" in text
    assert "【待填写】" in text

    db_file = os.path.join(storage, "letter_sequence.db")
    assert os.path.isfile(db_file)
    with sqlite3.connect(db_file) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM letter_sequence WHERE kind = 'counter'"
        ).fetchone()[0]
    assert count == 0


def test_letter_numbers_increase_after_prefix_is_set(client, no_ollama):
    year = datetime.now().year
    saved = client.post("/api/v1/phase1/letter-prefix", json={"prefix": "京师函"})
    assert saved.status_code == 200, saved.text
    assert saved.json()["prefix"] == "京师函"

    first = _generate_letter(
        client,
        plaintiff_name="流水原告一",
        defendant_name="流水被告一",
        lawyer_name="钱承办",
        law_firm="北京市测试律师事务所",
        lawyer_license="11101201910101010",
        lawyer_phone="13700001111",
    )
    second = _generate_letter(
        client,
        plaintiff_name="流水原告二",
        defendant_name="流水被告二",
        lawyer_name="钱承办",
        law_firm="北京市测试律师事务所",
        lawyer_license="11101201910101010",
        lawyer_phone="13700001111",
    )
    assert f"京师函〔{year}〕第1号" in first
    assert f"京师函〔{year}〕第2号" not in first
    assert f"京师函〔{year}〕第2号" in second
    assert f"京师函〔{year}〕第1号" not in second
    assert "【待填写函号前缀】" not in first
    assert "【待填写函号前缀】" not in second
    for fake in ("京律函字", "王律师", "11101201510123456", "13900008888"):
        assert fake not in first
        assert fake not in second

    storage = os.environ["LAWFLOW_STORAGE_DIR"]
    db_file = os.path.join(storage, "letter_sequence.db")
    with sqlite3.connect(db_file) as conn:
        last_no = conn.execute(
            "SELECT last_no FROM letter_sequence WHERE kind = 'counter' AND year = ?",
            (year,),
        ).fetchone()[0]
    assert last_no == 2


def test_demo_identity_combo_is_not_written(client, no_ollama):
    text = _generate_letter(
        client,
        plaintiff_name="演示原告甲",
        defendant_name="演示被告乙",
        lawyer_name="王律师",
        law_firm="北京市京师律师事务所",
        lawyer_license="11101201510123456",
        lawyer_phone="13900008888",
    )
    for fake in ("王律师", "北京市京师律师事务所", "13900008888", "11101201510123456", "京律函字"):
        assert fake not in text
    assert "【待填写】" in text
    assert "【待填写函号前缀】" in text
