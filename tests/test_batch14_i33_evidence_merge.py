# -*- coding: utf-8 -*-
"""批次14 I-33：证据合卷应转换 docx，并报告 skipped_files。"""
from __future__ import annotations

import io
from pathlib import Path

import pymupdf as fitz
from docx import Document
from PIL import Image


def _one_page_pdf_bytes() -> bytes:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 72), "证据PDF第1页", fontname="china-s", fontsize=14)
    data = doc.tobytes()
    doc.close()
    return data


def _png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (200, 120), color=(220, 230, 240)).save(buf, format="PNG")
    return buf.getvalue()


def _docx_bytes(text: str = "证据DOCX正文合卷测试") -> bytes:
    d = Document()
    d.add_paragraph(text)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def test_merge_pdf_png_docx_all_merged(client):
    files = [
        ("files", ("e1.pdf", _one_page_pdf_bytes(), "application/pdf")),
        ("files", ("e2.png", _png_bytes(), "image/png")),
        ("files", ("e3.docx", _docx_bytes(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")),
    ]
    resp = client.post(
        "/api/v1/phase2/process-evidence",
        data={"evidence_label": "证据1"},
        files=files,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data.get("skipped_files") in ([], None) or len(data.get("skipped_files") or []) == 0
    merged = data.get("merged_files") or []
    assert len(merged) == 3
    assert data["processed_files_count"] == 3
    assert data["total_pages"] >= 3

    # 合卷 PDF 页数 = 1 + 1 + docx 转出页数
    from gateway.core.paths import get_generated_dir

    out = Path(get_generated_dir()) / data["merged_pdf_filename"]
    assert out.exists()
    pdf = fitz.open(str(out))
    assert pdf.page_count == data["total_pages"]
    pdf.close()


def test_merge_skips_exe_partial(client):
    files = [
        ("files", ("e1.pdf", _one_page_pdf_bytes(), "application/pdf")),
        ("files", ("e2.png", _png_bytes(), "image/png")),
        ("files", ("e3.docx", _docx_bytes(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")),
        ("files", ("malware.exe", b"MZ\x00\x00fake-exe", "application/octet-stream")),
    ]
    resp = client.post(
        "/api/v1/phase2/process-evidence",
        data={"evidence_label": "证据1"},
        files=files,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data.get("status") == "partial"
    skipped = data.get("skipped_files") or []
    assert any("malware.exe" in (s.get("filename") if isinstance(s, dict) else str(s)) for s in skipped)
    assert len(data.get("merged_files") or []) == 3
    assert data["processed_files_count"] == 3
