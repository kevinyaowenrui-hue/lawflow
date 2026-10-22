# -*- coding: utf-8 -*-
import io
import pytest
from PIL import Image
from fastapi.testclient import TestClient

AUTH = {"X-LawFlow-Token": "test-token"}


def test_upload_png_ocr_unavailable(tmp_path, monkeypatch):
    """monkeypatch 使 easyocr 不可导入，上传 png -> status == 'ocr_unavailable'"""
    import gateway.utils.ocr_engine as ocr_engine
    monkeypatch.setattr(ocr_engine, "get_easyocr_reader", lambda: None)

    from gateway.main import app
    from gateway.utils.matter_vault_db import create_new_matter

    matter = create_new_matter({
        "title": "测试案件",
        "cause_of_action": "民间借贷纠纷",
    })
    matter_id = matter["matter_id"]

    # 创建一个简单的测试 PNG 图片
    img = Image.new("RGB", (100, 100), color=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    with TestClient(app, headers=AUTH) as client:
        resp = client.post(
            f"/api/v1/vault/matters/{matter_id}/upload-document",
            files={"file": ("test_evidence.png", buf, "image/png")},
            data={"doc_type": "evidence", "redact_on_ingest": "true"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["status"] == "ocr_unavailable"
        assert data["extracted_text"] == ""
        assert "未安装 OCR 组件（easyocr）" in data["message"]

        # /api/v1/converter/status 与 /health 中返回 ocr_available
        status_resp = client.get("/api/v1/converter/status")
        assert status_resp.status_code == 200
        assert "ocr_available" in status_resp.json()
        assert status_resp.json()["ocr_available"] is False

        health_resp = client.get("/health")
        assert health_resp.status_code == 200
        assert "ocr_available" in health_resp.json()
        assert health_resp.json()["ocr_available"] is False
