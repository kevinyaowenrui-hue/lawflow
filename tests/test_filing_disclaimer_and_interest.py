# -*- coding: utf-8 -*-
"""提交件不带软件页脚；没有到期日时不把笔记第一个日期算成利息。"""
from __future__ import annotations

import io
import zipfile
from datetime import datetime
from pathlib import Path

import docx
import pytest

from gateway.utils.disclaimer import DISCLAIMER, DisclaimerStampError, stamp_disclaimer_on_pdf
from gateway.utils.text_utils import extract_first_date_iso

ROOT = Path(__file__).resolve().parents[1]
FOOTER_MARK = "本输出由软件自动生成"


def _party(name: str, id_no: str) -> dict:
    return {
        "name": name,
        "id_card_or_uscc": id_no,
        "address": "北京市朝阳区测试路1号",
        "phone": "13800000001",
    }


def _footer_and_body(path: str) -> str:
    document = docx.Document(path)
    parts = [p.text or "" for p in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                parts.append(cell.text or "")
    for section in document.sections:
        for paragraph in section.footer.paragraphs:
            parts.append(paragraph.text or "")
        for paragraph in section.header.paragraphs:
            parts.append(paragraph.text or "")
    return "\n".join(parts)


def _facts_section(path: str) -> str:
    text = _footer_and_body(path)
    start = text.find("事实与理由")
    end = text.find("证据和证据来源")
    if start < 0:
        return text
    if end < 0:
        return text[start:]
    return text[start:end]


@pytest.fixture
def no_ollama(monkeypatch):
    from gateway.core.ollama_client import ollama_client

    async def _offline(*args, **kwargs):
        return False

    monkeypatch.setattr(ollama_client, "_is_ollama_online", _offline)
    monkeypatch.setattr(
        ollama_client, "settings", {**ollama_client.settings, "provider": "ollama", "api_key": ""}
    )
    return ollama_client


@pytest.fixture
def fast_pdf(monkeypatch):
    async def _ok(*args, **kwargs):
        return True

    monkeypatch.setattr("gateway.routers.phase1_litigation.convert_docx_to_pdf", _ok)


def test_stamp_disclaimer_failure_is_not_swallowed(tmp_path):
    missing = tmp_path / "missing.pdf"
    with pytest.raises(DisclaimerStampError):
        stamp_disclaimer_on_pdf(str(missing))


def test_pdf_watermark_failure_is_not_conversion_success(tmp_path, monkeypatch):
    import asyncio

    from gateway.routers.phase1_litigation import convert_docx_to_pdf, get_last_pdf_error

    source = tmp_path / "note.docx"
    target = tmp_path / "note.pdf"
    document = docx.Document()
    document.add_paragraph("起诉状正文")
    document.save(source)

    def _boom(path: str) -> None:
        raise DisclaimerStampError("写入失败")

    monkeypatch.setattr("gateway.utils.disclaimer.stamp_disclaimer_on_pdf", _boom)
    ok = asyncio.run(
        convert_docx_to_pdf(str(source), str(target), title="起诉状", include_disclaimer=True)
    )
    assert ok is False
    assert "水印失败" in get_last_pdf_error()


def test_pymupdf_filing_pdf_has_no_disclaimer(tmp_path):
    import pymupdf as fitz

    from gateway.routers.phase1_litigation import _pymupdf_paginated_render

    pdf_path = tmp_path / "filing.pdf"
    assert _pymupdf_paginated_render(["起诉状正文，提交法院。"], str(pdf_path), include_disclaimer=False)
    doc = fitz.open(pdf_path)
    text = "\n".join(page.get_text() for page in doc)
    doc.close()
    assert FOOTER_MARK not in text


def test_filing_package_omits_disclaimer_footer(client, no_ollama, fast_pdf):
    resp = client.post(
        "/api/v1/phase1/generate-litigation-package",
        json={
            "cause_of_action": "民间借贷纠纷",
            "claim_amount": 100000,
            "claims": ["判令被告偿还借款本金人民币100000元"],
            "raw_case_notes": "被告向原告借款10万元，尚未归还。",
            "court_name": "北京市朝阳区人民法院",
            "lawyer_name": "周承办",
            "law_firm": "测试律师事务所",
            "lawyer_license": "13101202010123456",
            "lawyer_phone": "13800002002",
            "plaintiff": _party("测试原告甲", "110101199003072340"),
            "defendant": _party("测试被告乙", "110101199003072351"),
            "auto_generate_sub_docs": False,
            "sub_documents": [
                "power_of_attorney",
                "law_firm_letter",
                "property_preservation",
                "demand_letter",
            ],
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    by_type = {item["doc_type"]: item for item in data["generated_documents"]}
    for doc_type in ("民事起诉状(民间借贷版)", "民事授权委托书", "律师事务所公函", "财产保全申请书"):
        assert doc_type in by_type, doc_type
        text = _footer_and_body(by_type[doc_type]["path"])
        assert FOOTER_MARK not in text, doc_type
        assert DISCLAIMER not in text, doc_type

    from gateway.core.paths import get_generated_dir

    archive = zipfile.ZipFile(Path(get_generated_dir()) / data["package_zip_name"])
    for name in archive.namelist():
        if not name.endswith(".docx"):
            continue
        inner = docx.Document(io.BytesIO(archive.read(name)))
        blob = "\n".join(
            [p.text or "" for p in inner.paragraphs]
            + [p.text or "" for section in inner.sections for p in section.footer.paragraphs]
        )
        assert FOOTER_MARK not in blob, name
    archive.close()

    draft = by_type["律师函"]["path"]
    assert FOOTER_MARK in _footer_and_body(draft)


def test_no_due_date_does_not_write_interest_from_first_note_date(client, no_ollama, fast_pdf):
    from gateway.utils.cn_legal_calc import calculate_lpr_interest

    notes = "2023年3月8日原告与被告见面喝茶。被告后来向原告借款10万元，借条没有写到期日。"
    guessed_start = extract_first_date_iso(notes)
    assert guessed_start == "2023-03-08"
    guessed = calculate_lpr_interest(
        principal=100000,
        start_date=guessed_start,
        end_date=datetime.now().strftime("%Y-%m-%d"),
        fixed_annual_rate=None,
        rule_mode="private_lending_cap",
        contract_date=guessed_start,
    )
    assert guessed["total_interest"] > 0
    amount = f"{guessed['total_interest']:,.2f}"

    created = client.post(
        "/api/v1/vault/matters",
        json={
            "title": "无到期日借贷案",
            "cause_of_action": "民间借贷纠纷",
            "plaintiff_name": "测试原告甲",
            "defendant_name": "测试被告乙",
            "court_name": "北京市朝阳区人民法院",
        },
    )
    assert created.status_code == 200, created.text
    matter_id = created.json()["matter"]["matter_id"]
    from gateway.utils.matter_vault_db import save_matter_practice

    save_matter_practice(
        matter_id,
        {"jurisdiction": {"confirmed_forum": "北京市朝阳区人民法院", "tracks": []}},
    )

    resp = client.post(
        "/api/v1/phase1/generate-litigation-package",
        json={
            "cause_of_action": "民间借贷纠纷",
            "matter_id": matter_id,
            "claim_amount": 100000,
            "claims": ["判令被告偿还借款本金人民币100000元"],
            "raw_case_notes": notes,
            "court_name": "北京市朝阳区人民法院",
            "plaintiff": _party("测试原告甲", "110101199003072340"),
            "defendant": _party("测试被告乙", "110101199003072351"),
            "auto_generate_sub_docs": False,
            "sub_documents": [],
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    facts = _facts_section(data["main_docx_path"])
    assert "判令被告偿还借款本金人民币100000元" in _footer_and_body(data["main_docx_path"])
    assert amount not in facts
    assert guessed_start not in facts
    assert "共计产生利息" not in facts
    assert data.get("matter_document_ids")
    listed = client.get(f"/api/v1/vault/matters/{matter_id}/documents")
    assert listed.status_code == 200, listed.text
    titles = " ".join(item.get("title") or item.get("doc_title") or "" for item in listed.json().get("documents") or [])
    assert "起诉状" in titles


def test_settled_interest_is_used_when_present(client, no_ollama, fast_pdf):
    statement = "以本金100000.00元为基数，自2024-01-01起至2024-06-01止，利息人民币1234.56元。"
    resp = client.post(
        "/api/v1/phase1/generate-litigation-package",
        json={
            "cause_of_action": "民间借贷纠纷",
            "claim_amount": 100000,
            "claims": ["判令被告偿还借款本金并支付利息"],
            "raw_case_notes": "2020年1月2日双方相识。借款尚未约定到期日。",
            "court_name": "北京市朝阳区人民法院",
            "plaintiff": _party("测试原告甲", "110101199003072340"),
            "defendant": _party("测试被告乙", "110101199003072351"),
            "auto_generate_sub_docs": False,
            "sub_documents": [],
            "settled_interest": {
                "principal": 100000,
                "start_date": "2024-01-01",
                "end_date": "2024-06-01",
                "annual_rate": 3.45,
                "interest_total": 1234.56,
                "formal_statement": statement,
            },
        },
    )
    assert resp.status_code == 200, resp.text
    facts = _facts_section(resp.json()["main_docx_path"])
    assert "1234.56" in facts
    assert "2024-01-01" in facts
    assert "2020-01-02" not in facts


def test_missing_claims_are_not_placeholder(client, no_ollama):
    resp = client.post(
        "/api/v1/phase1/generate-litigation-package",
        json={
            "cause_of_action": "买卖合同纠纷",
            "claim_amount": 1000,
            "claims": ["【待填写】"],
            "raw_case_notes": "货款未付。",
            "court_name": "北京市朝阳区人民法院",
            "plaintiff": _party("测试原告甲", "110101199003072340"),
            "defendant": _party("测试被告乙", "110101199003072351"),
            "auto_generate_sub_docs": False,
            "sub_documents": [],
        },
    )
    assert resp.status_code == 422
    assert "诉讼请求" in str(resp.json().get("detail"))


def test_litigation_form_has_claims_ack_and_preview_style():
    js = (ROOT / "frontend" / "js" / "modules" / "02_litigation.js").read_text(encoding="utf-8")
    css = (ROOT / "frontend" / "css" / "style.css").read_text(encoding="utf-8")
    appeal = (ROOT / "frontend" / "js" / "modules" / "04_appeal_signing.js").read_text(encoding="utf-8")
    assert 'for="pkg-p-name"' in js and 'id="pkg-p-name"' in js
    assert 'for="pkg-d-name"' in js and 'id="pkg-d-name"' in js
    assert 'for="pkg-amount"' in js and 'id="pkg-amount"' in js
    assert 'for="pkg-court"' in js and 'id="pkg-court"' in js
    assert 'for="pkg-notes"' in js and 'id="pkg-notes"' in js
    assert 'id="pkg-claims"' in js and 'for="pkg-claims"' in js
    assert "我已审阅，提交件由承办律师负责" in js
    assert "max-height: 360px" not in js
    assert "official-doc-preview" in js
    assert "official-doc-preview" in css
    assert "仿宋" in css and "宋体" in css
    assert "line-height: 2" in css
    assert "exportAppealDocxUI" in appeal
    preview_tag = appeal.split('id="appeal-doc-preview"', 1)[1].split(">", 1)[0]
    assert "official-doc-preview" in preview_tag
    assert "220px" not in preview_tag
    assert "11.5px" not in preview_tag
    main_js = (ROOT / "frontend" / "js" / "main.js").read_text(encoding="utf-8")
    assert "shouldSkipSoftwareDisclaimer" in main_js
    assert "data-no-software-disclaimer" in js
    assert "data-internal-draft" in js
    architecture = (ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")
    assert "演示签署" not in architecture
    assert "不伪造链接" in architecture
