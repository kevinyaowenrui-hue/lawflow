# -*- coding: utf-8 -*-
"""批次14 I-34：转码文件名唯一、txt→pdf、音频501、export-version-diff 下载链接。"""
from __future__ import annotations

import io
from pathlib import Path

import pymupdf as fitz
from PIL import Image


VERSION_PAYLOAD = {
    "base_title": "基准版",
    "base_text": "第一条 借款金额为人民币100万元。\n第二条 争议由法院管辖。",
    "target_title": "修改版",
    "target_text": "第一条 借款金额为人民币80万元。\n第二条 争议由仲裁解决。",
}


def _png_file(name: str = "a.png"):
    buf = io.BytesIO()
    Image.new("RGB", (80, 60), color=(180, 190, 200)).save(buf, format="PNG")
    return (name, buf.getvalue(), "image/png")


def test_two_conversions_same_second_unique_names(client):
    from gateway.core.paths import get_generated_dir

    r1 = client.post(
        "/api/v1/converter/convert",
        data={"target_format": "pdf", "stamp_bates": "false"},
        files={"file": _png_file("shot_a.png")},
    )
    r2 = client.post(
        "/api/v1/converter/convert",
        data={"target_format": "pdf", "stamp_bates": "false"},
        files={"file": _png_file("shot_b.png")},
    )
    assert r1.status_code == 200, r1.text
    assert r2.status_code == 200, r2.text
    f1 = r1.json()["output_filename"]
    f2 = r2.json()["output_filename"]
    assert f1 != f2
    assert (Path(get_generated_dir()) / f1).exists()
    assert (Path(get_generated_dir()) / f2).exists()


def test_txt_to_pdf_contains_source_text(client):
    from gateway.core.paths import get_generated_dir

    text = "智律工作台TXT转PDF验收原文UNIQUE_TXT_MARKER_8848"
    resp = client.post(
        "/api/v1/converter/convert",
        data={"target_format": "pdf"},
        files={"file": ("notes.txt", text.encode("utf-8"), "text/plain")},
    )
    assert resp.status_code == 200, resp.text
    out = Path(get_generated_dir()) / resp.json()["output_filename"]
    assert out.exists()
    doc = fitz.open(str(out))
    extracted = "".join(page.get_text() for page in doc)
    doc.close()
    assert "UNIQUE_TXT_MARKER_8848" in extracted


def test_audio_without_pydub_returns_501(client, monkeypatch):
    import builtins

    real_import = builtins.__import__

    def _block_pydub(name, *args, **kwargs):
        if name == "pydub" or name.startswith("pydub."):
            raise ImportError("pydub blocked for test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _block_pydub)

    # 假 wav：无魔数强制规则时跳过；converter 允许 .wav
    resp = client.post(
        "/api/v1/converter/convert",
        data={"target_format": "mp3"},
        files={"file": ("talk.wav", b"RIFF....WAVEfmt ", "audio/wav")},
    )
    assert resp.status_code == 501, resp.text
    assert "pydub" in resp.text.lower() or "ffmpeg" in resp.text.lower()


def test_export_version_diff_download_url(client):
    resp = client.post("/api/v1/contract/export-version-diff", json=VERSION_PAYLOAD)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    url = data.get("download_url") or ""
    assert url.startswith("/api/documents/download/")
    get = client.get(url)
    assert get.status_code == 200, get.text
    assert len(get.content) > 100
