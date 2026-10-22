# -*- coding: utf-8 -*-
"""
LawFlow 智律工作台 - P1 阶段：和解 NPV 精算与案卷视觉切片。
"""
from __future__ import annotations

import base64
import os

import pymupdf as fitz

from gateway.utils.cn_legal_calc import calculate_settlement_npv_and_recovery
from gateway.routers.review_and_diff import generate_source_grounding_visual_crop


def test_settlement_npv_installments_pure():
    claim = 1000000.0
    installments = [
        {"months": 3, "amount": 300000.0, "note": "首期付款"},
        {"months": 6, "amount": 300000.0, "note": "第二期付款"},
        {"months": 12, "amount": 400000.0, "note": "结清尾款"},
    ]
    res = calculate_settlement_npv_and_recovery(
        total_claim_nominal=claim,
        plan_type="cash_installments",
        annual_discount_rate=0.08,
        installments=installments,
    )
    assert res["status"] == "success"
    metrics = res["metrics"]
    assert metrics["total_claim_nominal"] == claim
    assert metrics["total_nominal_settlement"] == 1000000.0
    assert metrics["nominal_recovery_rate"] == 100.0
    assert metrics["total_npv_settlement"] < 1000000.0
    assert metrics["total_npv_settlement"] > 900000.0
    assert metrics["effective_recovery_rate"] < 100.0
    assert metrics["illusion_gap"] > 0.0
    assert len(res["installments_breakdown"]) == 3
    assert "合伙人核心财务审定" in res["partner_tactical_memo"]


def test_settlement_npv_debt_for_asset_pure():
    claim = 5000000.0
    asset_plan = {
        "asset_name": "某商业大厦抵债商办写字楼",
        "nominal_asset_valuation": 6000000.0,
        "prior_liens": 2500000.0,
        "auction_discount_rate": 0.70,
        "liquidation_costs_rate": 0.12,
        "time_to_liquidate_months": 18,
        "encumbrance_status": "存在在先抵押登记",
    }
    res = calculate_settlement_npv_and_recovery(
        total_claim_nominal=claim,
        plan_type="debt_for_asset",
        annual_discount_rate=0.08,
        asset_plan=asset_plan,
    )
    assert res["status"] == "success"
    metrics = res["metrics"]
    assert metrics["total_nominal_settlement"] == 6000000.0
    assert metrics["nominal_recovery_rate"] == 120.0
    expected_npv = 1496000.0 / ((1.0 + 0.08) ** (18 / 12.0))
    assert abs(metrics["total_npv_settlement"] - expected_npv) < 1.0
    assert metrics["effective_recovery_rate"] < 30.0
    assert metrics["illusion_gap"] > 90.0
    assert "虚胖差额高达" in res["partner_tactical_memo"]
    assert "九民纪要" in res["partner_tactical_memo"]


def test_settlement_api_hybrid_route(client):
    payload = {
        "total_claim_nominal": 5000000.0,
        "plan_type": "hybrid",
        "annual_discount_rate": 0.08,
        "installments": [
            {"months": 3, "amount": 500000.0, "note": "首付款"},
            {"months": 6, "amount": 500000.0, "note": "第二期"},
        ],
        "asset_plan": {
            "asset_name": "朝阳区商办写字楼3套",
            "nominal_asset_valuation": 4500000.0,
            "prior_liens": 1500000.0,
            "auction_discount_rate": 0.70,
            "liquidation_costs_rate": 0.12,
            "time_to_liquidate_months": 18,
            "encumbrance_status": "银行第一顺位在先抵押150万元",
        },
    }
    resp = client.post("/api/v1/phase1/calc/settlement-simulation", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    m = data["metrics"]
    assert m["total_claim_nominal"] == 5000000.0
    assert m["total_nominal_settlement"] == 5500000.0
    assert m["nominal_recovery_rate"] == 110.0
    assert m["effective_recovery_rate"] == 45.31
    assert m["illusion_gap"] == 64.69
    assert len(data["installments_breakdown"]) == 2
    assert data["asset_breakdown"]["nominal_valuation"] == 4500000.0


def test_visual_crop_synthesized_grounding(client, seed_demo):
    resp = client.get(
        "/api/v1/vault/matters/MATTER-2026-001/grounding/excerpt"
        "?doc_title=借款合同&page_no=1&query_text=连带保证责任"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["found"] is True
    assert data["visual_crop_base64"] is not None
    assert data["visual_crop_base64"].startswith("data:image/png;base64,")
    raw_b64 = data["visual_crop_base64"].split(",", 1)[1]
    img_bytes = base64.b64decode(raw_b64)
    assert len(img_bytes) > 2000
    assert img_bytes[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(data["bounding_boxes"]) >= 1
    box = data["bounding_boxes"][0]
    assert box["x0"] >= 0 and box["y0"] >= 0
    assert box["width"] > 0 and box["height"] > 0
    crop = data["crop_rect"]
    assert crop["width"] >= 200 and crop["height"] >= 100


def test_visual_crop_physical_pdf(tmp_path):
    pdf_path = os.path.join(tmp_path, "real_evidence_test.pdf")
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_textbox(
        fitz.Rect(54, 72, 541, 700),
        "第七条 争议解决与管辖法院：\n"
        "因本采购合同履行发生之任何争议，双方应协商解决；"
        "协商不成的，任何一方均有权向原告住所地人民法院提起诉讼。\n"
        "违约方应承担守约方因此支出之全部合理诉讼费与律师费。",
        fontsize=12,
        fontname="china-s",
    )
    doc.save(pdf_path)
    doc.close()

    target_doc = {
        "title": "真实测试证据文件.pdf",
        "file_path": pdf_path,
        "doc_type": "contract",
    }
    visual_info = generate_source_grounding_visual_crop(
        target_doc=target_doc,
        full_text="第七条 争议解决与管辖法院...",
        page_no=1,
        highlight_snippet="住所地人民法院提起诉讼",
    )
    assert visual_info["visual_crop_base64"] is not None
    assert visual_info["visual_crop_base64"].startswith("data:image/png;base64,")
    assert visual_info["page_count"] == 1
    assert visual_info["is_synthesized"] is False
    raw_b64 = visual_info["visual_crop_base64"].split(",", 1)[1]
    img_bytes = base64.b64decode(raw_b64)
    assert len(img_bytes) > 2000
    assert img_bytes[:8] == b"\x89PNG\r\n\x1a\n"
