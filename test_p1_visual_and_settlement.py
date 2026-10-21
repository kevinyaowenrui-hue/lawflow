"""
LawFlow 智律工作台 - P1 阶段全面实证测试套件
测试范围：
1. 商业和解与以物抵债现值/回收率精算引擎 (calculate_settlement_npv_and_recovery)
2. 商业和解精算 API 接口 (POST /api/v1/phase1/calc/settlement-simulation)
3. 案卷原件高分辨率视觉切片与琥珀金高亮加框 (api_get_source_grounding_excerpt with visual_crop_base64)
4. 真实物理 PDF 文件与内存合成文书的双链路切片验证
"""

import os
import re
import base64
import pytest
from fastapi.testclient import TestClient
import pymupdf as fitz

from gateway.main import app
from gateway.utils.cn_legal_calc import calculate_settlement_npv_and_recovery
from gateway.utils.matter_vault_db import get_matter_by_id

client = TestClient(app, headers={"X-LawFlow-Token": os.environ.get("LAWFLOW_API_TOKEN", "test-token")})


def test_settlement_npv_installments_pure():
    """测试 1: 纯现金分期和解净现值折现"""
    claim = 1000000.0
    installments = [
        {"months": 3, "amount": 300000.0, "note": "首期付款"},
        {"months": 6, "amount": 300000.0, "note": "第二期付款"},
        {"months": 12, "amount": 400000.0, "note": "结清尾款"}
    ]
    res = calculate_settlement_npv_and_recovery(
        total_claim_nominal=claim,
        plan_type="cash_installments",
        annual_discount_rate=0.08,
        installments=installments
    )
    assert res["status"] == "success"
    metrics = res["metrics"]
    assert metrics["total_claim_nominal"] == claim
    assert metrics["total_nominal_settlement"] == 1000000.0
    assert metrics["nominal_recovery_rate"] == 100.0
    # 由于存在8%年化折现，真实现值必然小于名义值 100万
    assert metrics["total_npv_settlement"] < 1000000.0
    assert metrics["total_npv_settlement"] > 900000.0
    assert metrics["effective_recovery_rate"] < 100.0
    assert metrics["illusion_gap"] > 0.0
    assert len(res["installments_breakdown"]) == 3
    assert "合伙人核心财务审定" in res["partner_tactical_memo"]


def test_settlement_npv_debt_for_asset_pure():
    """测试 2: 纯工抵房/不动产以物抵债 (穿透在先抵押、法拍折价、税费及周期)"""
    claim = 5000000.0
    asset_plan = {
        "asset_name": "某商业大厦抵债商办写字楼",
        "nominal_asset_valuation": 6000000.0, # 虚高评估价 600万
        "prior_liens": 2500000.0,             # 在先银行第一顺位抵押 250万
        "auction_discount_rate": 0.70,        # 一拍评估价7折
        "liquidation_costs_rate": 0.12,       # 税费12%
        "time_to_liquidate_months": 18,       # 18个月变现周期
        "encumbrance_status": "存在在先抵押登记"
    }
    res = calculate_settlement_npv_and_recovery(
        total_claim_nominal=claim,
        plan_type="debt_for_asset",
        annual_discount_rate=0.08,
        asset_plan=asset_plan
    )
    assert res["status"] == "success"
    metrics = res["metrics"]
    # 名义上对方抵了 600 万，名义清偿率 120%
    assert metrics["total_nominal_settlement"] == 6000000.0
    assert metrics["nominal_recovery_rate"] == 120.0
    
    # 穿透计算核验：
    # 法拍估值: 6,000,000 * 0.70 = 4,200,000
    # 扣除在先优先权: 4,200,000 - 2,500,000 = 1,700,000
    # 扣除税费 12%: 1,700,000 * (1 - 0.12) = 1,496,000
    # 折现 18个月 (0.08): 1,496,000 / (1.08 ^ 1.5) = 1,496,000 / 1.1224 = ~1,332,854.76
    expected_npv = 1496000.0 / ((1.0 + 0.08) ** (18 / 12.0))
    assert abs(metrics["total_npv_settlement"] - expected_npv) < 1.0
    # 真实回收率仅约 26.6%，虚胖差额高达 93.3%！
    assert metrics["effective_recovery_rate"] < 30.0
    assert metrics["illusion_gap"] > 90.0
    assert "虚胖差额高达" in res["partner_tactical_memo"]
    assert "九民纪要" in res["partner_tactical_memo"]


def test_settlement_api_hybrid_route():
    """测试 3: 商业和解与抵债 API 接口 (POST /api/v1/phase1/calc/settlement-simulation)"""
    payload = {
        "total_claim_nominal": 5000000.0,
        "plan_type": "hybrid",
        "annual_discount_rate": 0.08,
        "installments": [
            {"months": 3, "amount": 500000.0, "note": "首付款"},
            {"months": 6, "amount": 500000.0, "note": "第二期"}
        ],
        "asset_plan": {
            "asset_name": "朝阳区商办写字楼3套",
            "nominal_asset_valuation": 4500000.0,
            "prior_liens": 1500000.0,
            "auction_discount_rate": 0.70,
            "liquidation_costs_rate": 0.12,
            "time_to_liquidate_months": 18,
            "encumbrance_status": "银行第一顺位在先抵押150万元"
        }
    }
    resp = client.post("/api/v1/phase1/calc/settlement-simulation", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    m = data["metrics"]
    assert m["total_claim_nominal"] == 5000000.0
    assert m["total_nominal_settlement"] == 5500000.0 # 100万现金 + 450万房产
    assert m["nominal_recovery_rate"] == 110.0
    assert m["effective_recovery_rate"] == 45.31
    assert m["illusion_gap"] == 64.69
    assert len(data["installments_breakdown"]) == 2
    assert data["asset_breakdown"]["nominal_valuation"] == 4500000.0


def test_visual_crop_synthesized_grounding():
    """测试 4: 案卷穿透原文定位高分辨率切片与琥珀金高亮加框 (内存合成存证页面)"""
    resp = client.get(
        "/api/v1/vault/matters/MATTER-2026-001/grounding/excerpt"
        "?doc_title=借款合同&page_no=1&query_text=连带保证责任"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["found"] is True
    # 验证是否返回高分辨率 PNG 切片
    assert data["visual_crop_base64"] is not None
    assert data["visual_crop_base64"].startswith("data:image/png;base64,")
    # 验证图片字节合法性
    raw_b64 = data["visual_crop_base64"].split(",", 1)[1]
    img_bytes = base64.b64decode(raw_b64)
    assert len(img_bytes) > 2000 # 至少2KB的高清PNG
    assert img_bytes[:8] == b"\x89PNG\r\n\x1a\n" # 标准 PNG Magic Number
    
    # 验证绝对边界框坐标
    assert len(data["bounding_boxes"]) >= 1
    box = data["bounding_boxes"][0]
    assert box["x0"] >= 0 and box["y0"] >= 0
    assert box["width"] > 0 and box["height"] > 0
    # 验证切片裁剪区域
    crop = data["crop_rect"]
    assert crop["width"] >= 200 and crop["height"] >= 100


def test_visual_crop_physical_pdf(tmp_path):
    """测试 5: 针对磁盘上真实物理 PDF 文件的切片定位与高亮"""
    # 1. 动态生成一个物理 PDF 证据文件
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
        fontname="china-s"
    )
    doc.save(pdf_path)
    doc.close()

    # 2. 模拟 target_doc 指向该物理文件
    from gateway.routers.review_and_diff import generate_source_grounding_visual_crop
    target_doc = {
        "title": "真实测试证据文件.pdf",
        "file_path": pdf_path,
        "doc_type": "contract"
    }
    visual_info = generate_source_grounding_visual_crop(
        target_doc=target_doc,
        full_text="第七条 争议解决与管辖法院...",
        page_no=1,
        highlight_snippet="住所地人民法院提起诉讼"
    )
    assert visual_info["visual_crop_base64"] is not None
    assert visual_info["visual_crop_base64"].startswith("data:image/png;base64,")
    assert visual_info["page_count"] == 1
    assert visual_info["is_synthesized"] is False # 必须成功读取真实物理文件而非合成
    # 验证裁剪区域与图片大小
    raw_b64 = visual_info["visual_crop_base64"].split(",", 1)[1]
    img_bytes = base64.b64decode(raw_b64)
    assert len(img_bytes) > 2000
    assert img_bytes[:8] == b"\x89PNG\r\n\x1a\n"


if __name__ == "__main__":
    pytest.main(["-v", "test_p1_visual_and_settlement.py"])
