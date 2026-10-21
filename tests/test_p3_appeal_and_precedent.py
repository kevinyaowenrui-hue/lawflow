# -*- coding: utf-8 -*-
"""
LawFlow 智律工作台 - P3 阶段自动化实证测试套件
批次4：默认无内置判例；演示模式判例不得写入文书案号。
（三个 or True 探针的测试在批次 8 处理。）
"""

import os
import pytest
from fastapi.testclient import TestClient
from gateway.main import app
from gateway.utils.appeal_and_precedent_engine import (
    analyze_first_instance_judgment_and_precedents,
    SUPREME_COURT_APPELLATE_PRECEDENTS,
)
from gateway.utils.citation_guard import CASE_NUMBER_PATTERN, LEGACY_CASE_NUMBER_PATTERN, audit_case_numbers

client = TestClient(app, headers={"X-LawFlow-Token": os.environ.get("LAWFLOW_API_TOKEN", "test-token")})


def test_first_instance_three_fatal_flaw_probes():
    judgment_sample = """
    本院认为，原告与被告签订的《增资补充协议》中关于回购本金及固定溢价收益的约定，
    实质上属于“保本保收益”的借贷性质，具有“名为投资实为借贷”的法律特征。
    故原告主张的利息及违约金总和不应超过同期全国银行间同业拆借中心公布的一年期LPR的4倍。
    此外，由于受宏观行业调控政策以及经济下行客观环境影响，目标公司未能如期申报IPO上市，
    该情况属于双方订约时无法预见的不可归责于被告之情势变更。
    鉴于原告未举证证明因逾期回购造成除资金占用以外的直接实际损失，
    原告约定的年化15%违约金畸高，本院依法予以酌减，按一年期LPR计算违约金。
    综上，判决被告李某某偿还原告投资本金并按LPR支付违约金，驳回原告其他诉讼请求。
    """

    res = analyze_first_instance_judgment_and_precedents(
        judgment_text=judgment_sample,
        case_title="8000万对赌协议股权回购及违约金纠纷案",
        claim_amount=80000000.0,
        agreed_repurchase_rate=0.15,
        first_instance_court="某市第一中级人民法院",
        first_instance_errors=[
            "将股权回购强行定性为民间借贷并套用4倍LPR上限",
            "将行业宏观调控滥用为《民法典》第533条情势变更并大幅免责",
            "将约定的年化15%违约金断崖式砍至LPR",
        ],
    )

    assert res["status"] == "success"
    assert res["claim_amount"] == 80000000.0
    assert res["first_instance_court"] == "某市第一中级人民法院"

    flaws = res["flaw_diagnostics"]
    assert len(flaws) >= 3

    probe_ids = [f["probe_id"] for f in flaws]
    assert "FLAW-01" in probe_ids
    assert "FLAW-02" in probe_ids
    assert "FLAW-03" in probe_ids

    f1 = next(f for f in flaws if f["probe_id"] == "FLAW-01")
    assert "借贷" in f1["error_type"] or "定性" in f1["error_type"]
    assert "第四百六十五条" in f1["statute_violated"] or "九民纪要" in f1["statute_violated"]
    assert f1["severity"] == "CRITICAL_FATAL"

    f2 = next(f for f in flaws if f["probe_id"] == "FLAW-02")
    assert "第五百三十三条" in f2["statute_violated"]
    assert "固有商业风险" in f2["appellate_attack_point"] or "商业风险" in f2["appellate_attack_point"]

    f3 = next(f for f in flaws if f["probe_id"] == "FLAW-03")
    assert "第五百八十五条" in f3["statute_violated"]
    assert "机会成本" in f3["appellate_attack_point"] or "裁量" in f3["appellate_attack_point"]


def test_supreme_court_precedent_discrepancy_matrix():
    """
    批次4 修正旧断言（原断言演示判例必然存在，属把错误行为写成断言）：
    - 默认模块常量无判例；
    - 未核验库时矩阵为空，文书不含案号。
    """
    # 内置常量已清空
    assert SUPREME_COURT_APPELLATE_PRECEDENTS == []

    res = analyze_first_instance_judgment_and_precedents()
    assert res["total_pro_precedents"] == 0
    assert res["precedent_matrix"] == []
    blob = (res.get("appellate_memo_report") or "") + "\n" + (res.get("appellate_pleading_text") or "")
    assert "本地无已核验类案" in blob or "【类案案号待律师核验后填写】" in blob
    assert len(list(CASE_NUMBER_PATTERN.finditer(blob))) == 0
    assert len(list(LEGACY_CASE_NUMBER_PATTERN.finditer(blob))) == 0


def test_judicial_evolution_timeline_completeness():
    res = analyze_first_instance_judgment_and_precedents()
    timeline = res["judicial_evolution_timeline"]
    assert len(timeline) == 3

    assert "海富案" in timeline[0]["benchmark_event"]
    # 海富案案号不得硬编码写入
    assert "民提字第11号" not in timeline[0]["benchmark_event"]
    assert "九民纪要" in timeline[1]["benchmark_event"]
    assert "法发〔2019〕25号" in timeline[1]["benchmark_event"]
    assert "254号" not in timeline[1]["benchmark_event"]
    assert "民法典" in timeline[2]["benchmark_event"]


def test_appellate_legal_memo_and_pleading_generation():
    res = analyze_first_instance_judgment_and_precedents(
        claim_amount=80000000.0,
        agreed_repurchase_rate=0.15,
        first_instance_court="北京市第二中级人民法院",
    )

    memo = res["appellate_memo_report"]
    pleading = res["appellate_pleading_text"]

    assert "【类案检索与统一法律适用裁判尺度对抗论证意见书】" in memo
    assert "80,000,000.00" in memo
    assert "法发〔2020〕24号" in memo
    assert "（2020）最高法民终1067号" not in memo
    assert "【类案案号待律师核验后填写】" in memo or "本地无已核验类案" in memo

    assert "民 事 上 诉 状" in pleading
    assert "80,000,000.00" in pleading
    assert "15.0%" in pleading
    assert "依法撤销一审判决" in pleading
    assert "民间借贷" in pleading
    assert "情势变更" in pleading
    assert "自由裁量权" in pleading
    assert "最高法民终1067" not in pleading

    cases_verified = res["cases_verified"]
    # 无案号则审计列表可为空
    assert all(not c.get("is_hallucination") for c in cases_verified)


def test_api_appeal_audit_endpoint():
    payload = {
        "judgment_text": "一审判决认定本案具有名为投资实为借贷特征，以不可归责的情势变更为由，将违约金酌减至LPR。",
        "case_title": "8000万回购二审再审案",
        "claim_amount": 80000000.0,
        "agreed_repurchase_rate": 0.15,
        "first_instance_court": "江苏省苏州市中级人民法院",
        "first_instance_errors": [
            "股权回购定性为民间借贷",
            "滥用情势变更免除违约责任",
            "违约金砍至LPR",
        ],
    }

    resp = client.post("/api/v1/litigation/appeal-audit", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["claim_amount"] == 80000000.0
    assert len(data["flaw_diagnostics"]) >= 3
    # 默认无已核验判例 → 矩阵为空
    assert len(data["precedent_matrix"]) == 0
    assert "80,000,000.00" in data["appellate_pleading_text"]
    assert "最高法民终1067" not in data["appellate_pleading_text"]

    alias_resp = client.post("/api/v1/phase1/appeal-audit", json=payload)
    assert alias_resp.status_code == 200
    assert alias_resp.json()["status"] == "success"


def test_api_appeal_export_docx_endpoint():
    import docx

    pleading_payload = {
        "title": "民事上诉状（事实与理由靶向重构版）",
        "content_text": (
            "民 事 上 诉 状\n\n"
            "上诉人：某科技创业投资基金\n"
            "被上诉人：李某某\n\n"
            "【上诉请求】\n"
            "1. 依法撤销一审判决；\n"
            "2. 依法改判被上诉人支付股权回购款8000万元及约定违约金。\n\n"
            "【事实与理由】\n"
            "一、一审判决将股权回购性质错定为民间借贷，严重违法；\n"
            "二、一审判决滥用情势变更原则，破坏商事契约稳定性；\n"
            "三、一审法院畸重调减违约金，缺乏事实与法律依据。"
        ),
        "doc_type": "appeal_pleading",
    }

    resp = client.post("/api/v1/litigation/appeal-export-docx", json=pleading_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["filename"].endswith(".docx")
    assert "/api/documents/download/" in data["download_url"]
    assert data["file_size"] > 0

    from gateway.core.paths import get_generated_dir

    storage_path = str(get_generated_dir() / data["filename"])
    assert os.path.exists(storage_path)

    doc = docx.Document(storage_path)
    assert len(doc.paragraphs) > 0
    full_text = "\n".join([p.text for p in doc.paragraphs])
    assert "民事上诉状（事实与理由靶向重构版）" in full_text
    assert "8000万元" in full_text

    memo_payload = {
        "title": "类案检索与统一法律适用裁判尺度对抗论证意见书",
        "content_text": (
            "【类案检索与统一法律适用裁判尺度对抗论证意见书】\n"
            "【类案案号待律师核验后填写】\n"
            "恳请二审法院依法撤销原判，全额改判！"
        ),
        "doc_type": "appeal_memo",
    }

    resp_memo = client.post("/api/v1/litigation/appeal-export-docx", json=memo_payload)
    assert resp_memo.status_code == 200
    data_memo = resp_memo.json()
    assert data_memo["file_size"] > 0
    memo_path = str(get_generated_dir() / data_memo["filename"])
    assert os.path.exists(memo_path)
