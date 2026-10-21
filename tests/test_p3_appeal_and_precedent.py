# -*- coding: utf-8 -*-
"""
LawFlow 智律工作台 - P3 阶段自动化实证测试套件
(Test Suite for P3 Appellate Judgment Flaws Diagnostic & Supreme Court Precedent Discrepancy Matrix)

实务法理测试维度：
1. 一审判决三大致命败诉破绽探针（定性错误、情势变更滥用、违约金畸轻）诊断精度校验；
2. 最高院及高院类案裁判分歧对抗矩阵（支持派权威公报 vs 一审错误观点）准确性与案号验真；
3. 《九民纪要》与《民法典》裁判口径演变时间谱系完整性；
4. 《类案检索法律论证意见书》与《民事上诉状（事实与理由靶向重构版）》自动化生成格式校验；
5. FastAPI 全栈路由集成测试（/api/v1/litigation/appeal-audit 及 Word 原生导出）。
"""

import os
import pytest
from fastapi.testclient import TestClient
from gateway.main import app
from gateway.utils.appeal_and_precedent_engine import (
    analyze_first_instance_judgment_and_precedents,
    SUPREME_COURT_APPELLATE_PRECEDENTS
)
from gateway.utils.citation_guard import audit_case_numbers

client = TestClient(app)


def test_first_instance_three_fatal_flaw_probes():
    """
    实证实测：一审判决三大致命败诉破绽探针
    1. 探针 1：法律关系定性错误（股权回购 错定为 民间借贷/4倍LPR限制）；
    2. 探针 2：违法滥用《民法典》第533条情势变更原则豁免违约责任；
    3. 探针 3：违约金调减畸重，剥夺意思自治与沉没机会成本。
    """
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
            "将约定的年化15%违约金断崖式砍至LPR"
        ]
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

    # 验证探针1：民间借贷定性错误
    f1 = next(f for f in flaws if f["probe_id"] == "FLAW-01")
    assert "借贷" in f1["error_type"] or "定性" in f1["error_type"]
    assert "第四百六十五条" in f1["statute_violated"] or "九民纪要" in f1["statute_violated"]
    assert f1["severity"] == "CRITICAL_FATAL"

    # 验证探针2：情势变更滥用
    f2 = next(f for f in flaws if f["probe_id"] == "FLAW-02")
    assert "第五百三十三条" in f2["statute_violated"]
    assert "固有商业风险" in f2["appellate_attack_point"] or "商业风险" in f2["appellate_attack_point"]

    # 验证探针3：违约金调减畸重
    f3 = next(f for f in flaws if f["probe_id"] == "FLAW-03")
    assert "第五百八十五条" in f3["statute_violated"]
    assert "机会成本" in f3["appellate_attack_point"] or "裁量" in f3["appellate_attack_point"]


def test_supreme_court_precedent_discrepancy_matrix():
    """
    实证实测：最高人民法院与高级法院【类案裁判分歧对抗矩阵】
    1. 权威案例库均来自最高法民终/民再公报判例与省高院生效改判；
    2. 案号防伪检验：所有案号格式规范且经 citation_guard 验真；
    3. 支持派裁判规则直击一审说理漏洞。
    """
    pro_list = [p for p in SUPREME_COURT_APPELLATE_PRECEDENTS if p["stance"] == "PRO_APPELLANT"]
    assert len(pro_list) >= 4

    # 验证包含最高法（2020）最高法民终1067号、（2019）最高法民再330号、（2022）京民终580号、（2021）沪民终1120号
    case_numbers = [p["case_number"] for p in pro_list]
    assert "（2020）最高法民终1067号" in case_numbers
    assert "（2019）最高法民再330号" in case_numbers
    assert "（2022）京民终580号" in case_numbers
    assert "（2021）沪民终1120号" in case_numbers

    # 案号规范验真 (audit_case_numbers 返回 List[Dict])
    audit_list = audit_case_numbers(" ".join(case_numbers))
    assert len(audit_list) >= 4
    assert all(not c.get("is_hallucination") for c in audit_list)

    # 运行矩阵生成
    res = analyze_first_instance_judgment_and_precedents()
    matrix = res["precedent_matrix"]
    assert len(matrix) >= 4

    for row in matrix:
        assert "dispute_focus" in row
        assert "supreme_court_rule" in row
        assert "first_instance_error_view" in row
        sc_rule = row["supreme_court_rule"]
        assert sc_rule["case_number"] in case_numbers
        assert len(sc_rule["holding_ratio"]) > 20
        assert len(sc_rule["rebuttal_brief_quote"]) > 20


def test_judicial_evolution_timeline_completeness():
    """
    实证实测：司法口径演变时间谱系完整性
    从海富案 -> 《九民纪要》第5条 -> 《民法典合同编通则解释》第32、64-65条。
    """
    res = analyze_first_instance_judgment_and_precedents()
    timeline = res["judicial_evolution_timeline"]
    assert len(timeline) == 3

    assert "海富案" in timeline[0]["benchmark_event"]
    assert "九民纪要" in timeline[1]["benchmark_event"]
    assert "民法典" in timeline[2]["benchmark_event"]


def test_appellate_legal_memo_and_pleading_generation():
    """
    实证实测：二审文书自动化生成与防伪案号后验
    1. 《类案检索与统一法律适用裁判尺度对抗论证意见书》符合最高法2020类案检索规范；
    2. 《民事上诉状（事实与理由靶向重构版）》具备4项上诉请求和3大部分事实与理由靶向反驳；
    3. 文书内的所有案号引用均自动通过 citation_guard 验真。
    """
    res = analyze_first_instance_judgment_and_precedents(
        claim_amount=80000000.0,
        agreed_repurchase_rate=0.15,
        first_instance_court="北京市第二中级人民法院"
    )

    memo = res["appellate_memo_report"]
    pleading = res["appellate_pleading_text"]

    # 校验论证报告
    assert "【类案检索与统一法律适用裁判尺度对抗论证意见书】" in memo
    assert "80,000,000.00" in memo
    assert "法发〔2020〕24号" in memo
    assert "（2020）最高法民终1067号" in memo

    # 校验上诉状
    assert "民 事 上 诉 状" in pleading
    assert "80,000,000.00" in pleading
    assert "15.0%" in pleading
    assert "依法撤销一审判决" in pleading
    assert "民间借贷" in pleading
    assert "情势变更" in pleading
    assert "自由裁量权" in pleading

    # 校验案号后验验真结果 (List[Dict])
    cases_verified = res["cases_verified"]
    assert len(cases_verified) >= 4
    assert all(not c.get("is_hallucination") for c in cases_verified)


def test_api_appeal_audit_endpoint():
    """
    实证实测：FastAPI /api/v1/litigation/appeal-audit 接口集成测试
    """
    payload = {
        "judgment_text": "一审判决认定本案具有名为投资实为借贷特征，以不可归责的情势变更为由，将违约金酌减至LPR。",
        "case_title": "8000万回购二审再审案",
        "claim_amount": 80000000.0,
        "agreed_repurchase_rate": 0.15,
        "first_instance_court": "江苏省苏州市中级人民法院",
        "first_instance_errors": [
            "股权回购定性为民间借贷",
            "滥用情势变更免除违约责任",
            "违约金砍至LPR"
        ]
    }

    # 测试主路由
    resp = client.post("/api/v1/litigation/appeal-audit", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["claim_amount"] == 80000000.0
    assert len(data["flaw_diagnostics"]) >= 3
    assert len(data["precedent_matrix"]) >= 4
    assert "80,000,000.00" in data["appellate_pleading_text"]

    # 测试别名路由
    alias_resp = client.post("/api/v1/phase1/appeal-audit", json=payload)
    assert alias_resp.status_code == 200
    assert alias_resp.json()["status"] == "success"


def test_api_appeal_export_docx_endpoint():
    """
    实证实测：Word 原生司法公文导出接口测试 (/api/v1/litigation/appeal-export-docx)
    1. 成功生成 .docx 司法公文文件；
    2. 文件保存在 storage/generated 目录下，大小 > 0；
    3. 返回标准下载链接 /api/documents/download/...；
    4. 验证导出的 Word 文档结构与标题格式。
    """
    import docx

    # 1. 导出民事上诉状
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
        "doc_type": "appeal_pleading"
    }

    resp = client.post("/api/v1/litigation/appeal-export-docx", json=pleading_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["filename"].endswith(".docx")
    assert "/api/documents/download/" in data["download_url"]
    assert data["file_size"] > 0

    # 校验磁盘上生成的实际 docx 文件有效性
    storage_path = os.path.join("storage", "generated", data["filename"])
    assert os.path.exists(storage_path)

    doc = docx.Document(storage_path)
    assert len(doc.paragraphs) > 0
    full_text = "\n".join([p.text for p in doc.paragraphs])
    assert "民事上诉状（事实与理由靶向重构版）" in full_text
    assert "8000万元" in full_text

    # 2. 导出类案检索论证报告
    memo_payload = {
        "title": "类案检索与统一法律适用裁判尺度对抗论证意见书",
        "content_text": (
            "【类案检索与统一法律适用裁判尺度对抗论证意见书】\n"
            "最高人民法院（2020）最高法民终1067号公报判例确立商事对赌不适用民间借贷限制规则。\n"
            "恳请二审法院依法撤销原判，全额改判！"
        ),
        "doc_type": "appeal_memo"
    }

    resp_memo = client.post("/api/v1/litigation/appeal-export-docx", json=memo_payload)
    assert resp_memo.status_code == 200
    data_memo = resp_memo.json()
    assert data_memo["file_size"] > 0
    memo_path = os.path.join("storage", "generated", data_memo["filename"])
    assert os.path.exists(memo_path)
