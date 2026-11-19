# -*- coding: utf-8 -*-
"""
LawFlow 实用性缺陷（2026-11-08）综合验收测试套件
覆盖 task.md 要求的各项指标：
1. 民间借贷利息修复（T-010 N3/C/T-007）
2. 上诉期测算修复（T-010 N1, C4）
3. 引用核验修复（T-010 问题 3/第 5 项）
4. 买卖合同审查不得返回预置成功（T-010 3.4, RICE 600）
5. 保密：上传合同彻底删除（T-004）
"""
import os
import shutil
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from gateway.utils.cn_legal_calc import (
    calculate_lpr_interest,
    calculate_appeal_deadline,
)
from gateway.utils.citation_guard import audit_citations_in_text
from gateway.main import app
from gateway.core.paths import get_uploads_dir
from gateway.utils.matter_vault_db import (
    init_matter_vault_db,
    create_new_matter,
    get_matter_by_id,
    soft_delete_matter,
    add_document_to_matter,
    delete_document_from_matter,
)

AUTH_TOKEN = os.environ.get("LAWFLOW_API_TOKEN", "test-token")
AUTH_HEADERS = {"X-LawFlow-Token": AUTH_TOKEN}


@pytest.fixture
def client():
    return TestClient(app)


# ==============================================================================
# 1. 民间借贷利息（T-010 N3 / C 相关，T-007）
# ==============================================================================

def test_private_lending_no_agreed_rate_not_4x_lpr():
    """未填约定利率时，不得按 4 倍 LPR 计息；借期利息为 0，逾期按 1.0x LPR 且有醒目说明。"""
    res = calculate_lpr_interest(
        principal=100000,
        start_date="2024-01-01",
        end_date="2025-01-01",
        rule_mode="private_lending_cap",
        contract_date="2024-01-01",
        fixed_annual_rate=None,
    )
    # multiplier 必须为 1.0，绝非 4 倍
    assert res.get("multiplier") == 1.0
    for seg in res.get("segments", []):
        assert seg.get("multiplier") == 1.0
    # 必须有醒目警示说明未约定利率不得主张借期利息
    warnings_text = " ".join(res.get("warnings", []))
    assert "未填写约定年利率" in warnings_text or "未约定利率" in warnings_text
    assert "民法典" in warnings_text and "第六百八十条第二款" in warnings_text
    assert "第二十四条第一款" in warnings_text
    assert "四倍 LPR 是约定利率的司法保护上限，绝非未约定利率时的计息标准" in warnings_text


def test_private_lending_citation_articles_2020():
    """法条引用：2020-08-20 后合同引用第二十五条，且称利息而非逾期违约利息。"""
    res_after = calculate_lpr_interest(
        principal=100000,
        start_date="2021-01-01",
        end_date="2022-01-01",
        rule_mode="private_lending_cap",
        contract_date="2021-01-01",
        fixed_annual_rate=10.0,
    )
    stmt_after = res_after.get("complaint_statement", "")
    assert "第二十五条" in stmt_after
    assert "逾期违约利息" not in stmt_after

    res_before = calculate_lpr_interest(
        principal=100000,
        start_date="2019-01-01",
        end_date="2021-01-01",
        rule_mode="private_lending_cap",
        contract_date="2019-01-01",
        filing_date="2021-01-01",
        fixed_annual_rate=20.0,
    )
    stmt_before = res_before.get("complaint_statement", "")
    assert "第三十一条第二款" in stmt_before


# ==============================================================================
# 2. 上诉期（T-010 N1、C4）
# ==============================================================================

def test_appeal_deadline_c4_workday_no_postpone():
    """C4: 2026-09-25 收到判决书，算 15 日届满为 2026-10-10（周六调休上班日），不得顺延至 10-12。"""
    res = calculate_appeal_deadline("2026-09-25", judgment_type="judgment")
    assert res["deadline"] == "2026-10-10"
    assert res["extended_for_holiday_or_weekend"] is False


def test_appeal_deadline_2027_missing_calendar_warning():
    """已公布的 2027 年不再报缺失；尚未公布的年份仍必须警告，不得静默编造。"""
    known = calculate_appeal_deadline("2026-12-25", judgment_type="judgment")
    assert not any("2027" in w and "尚未收录" in w for w in known["warnings"])
    res = calculate_appeal_deadline("2027-12-20", judgment_type="judgment")
    assert "warnings" in res
    assert any("2028" in w and "节假日" in w for w in res["warnings"])


def test_appeal_deadline_api(client):
    """验证 POST /api/v1/phase1/calc/appeal-deadline API 正常返回。"""
    resp = client.post(
        "/api/v1/phase1/calc/appeal-deadline",
        json={"service_date": "2026-09-25", "judgment_type": "judgment"},
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["deadline"] == "2026-10-10"
    assert "warnings" in data


# ==============================================================================
# 3. 引用核验（T-010 问题 3 / 第 5 项）
# ==============================================================================

def test_citation_guard_valid_and_recognized_laws():
    """现行有效条号不误判为虚构，认识律师法与仲裁法，废止法仍拦住。"""
    # 1. 行政诉讼法 103 条不判 HALLUCINATION_EXCEEDED
    r_admin103 = audit_citations_in_text("依据《行政诉讼法》第一百零三条")
    assert r_admin103["citations"][0]["status"] != "HALLUCINATION_EXCEEDED"

    # 2. 网络安全法 81 条不判 HALLUCINATION_EXCEEDED
    r_cyber81 = audit_citations_in_text("依据《网络安全法》第八十一条")
    assert r_cyber81["citations"][0]["status"] != "HALLUCINATION_EXCEEDED"

    # 3. 超出真实条数上限则判虚构
    r_admin104 = audit_citations_in_text("依据《行政诉讼法》第一百零四条")
    assert r_admin104["citations"][0]["status"] == "HALLUCINATION_EXCEEDED"

    r_cyber82 = audit_citations_in_text("依据《网络安全法》第八十二条")
    assert r_cyber82["citations"][0]["status"] == "HALLUCINATION_EXCEEDED"

    # 4. 认识律师法和仲裁法
    r_lawyer = audit_citations_in_text("依据《律师法》第三十九条")
    assert r_lawyer["citations"][0]["status"] != "UNRECOGNIZED_LAW"

    r_arb = audit_citations_in_text("依据《仲裁法》第十条")
    assert r_arb["citations"][0]["status"] != "UNRECOGNIZED_LAW"

    # 5. 废止法仍拦住
    r_contract = audit_citations_in_text("依据《合同法》第一百一十四条")
    assert r_contract["citations"][0]["status"] == "ABROGATED_BLOCKED"


# ==============================================================================
# 4. 买卖合同审查不得返回预置成功结果（T-010 3.4，RICE 600）
# ==============================================================================

def test_contract_review_requires_perspective(client):
    """审查前必须选择立场（买方 / 卖方），未选出 422 错误。"""
    resp = client.post(
        "/api/v1/phase2/contract-review",
        json={"contract_text": "甲方向乙方采购机械设备一批，总价 10 万元。"},
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 422
    data = resp.json()
    assert "必须选择立场" in str(data)


@pytest.fixture
def offline_llm(monkeypatch):
    """这条用例锁的是未连接模型，不能让本机 Ollama 把结果变成已审查。"""
    from gateway.core.ollama_client import ollama_client

    async def _offline():
        return False

    monkeypatch.setattr(ollama_client, "_is_ollama_online", _offline)
    monkeypatch.setattr(
        ollama_client,
        "settings",
        {**ollama_client.settings, "provider": "ollama", "api_key": ""},
    )


@pytest.mark.usefixtures("offline_llm")
@pytest.mark.parametrize(
    "text_idx,sample_text",
    [
        (1, "第一条 甲方订购钢材50吨，单价4000元，款到发货。"),
        (2, "出卖人交付办公电脑100台，买受人验收合格后30日内支付90%货款。"),
        (3, "买方采购原材料一批，质保期为自交付之日起十二个月。"),
        (4, "供方应于每月25日前按需方订单交货，运费由供方承担。"),
        (5, "合同总金额人民币伍拾万元整，分三期支付，首期预付款30%。"),
    ],
)
@pytest.mark.parametrize("perspective", ["buyer", "seller"])
def test_contract_review_unconnected_never_returns_preset_success(client, text_idx, sample_text, perspective):
    """
    规则模式 / 未连模型时：
    1. 不得返回与合同无关的预置条款（如预置的20%违约金、仲裁委员会条款）。
    2. 不得返回 success 状态，必须为 unreviewed。
    3. 响应中必须附带 LF-001 第 11 节的免责提示。
    """
    resp = client.post(
        "/api/v1/phase2/contract-review",
        json={"contract_text": sample_text, "perspective": perspective},
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 200
    data = resp.json()

    # 状态不得为 success，必须为 unreviewed
    assert data.get("status") != "success"
    assert data.get("status") == "unreviewed"

    # 不得返回假预置条款
    rev = data.get("review") or {}
    clause_reviews = rev.get("clause_reviews", [])
    assert len(clause_reviews) == 0

    # 必须包含免责提示
    disclaimer = data.get("disclaimer", "")
    assert "律师" in disclaimer or "仅供参考" in disclaimer


# ==============================================================================
# 5. 保密：上传合同彻底删除（T-004）
# ==============================================================================

def test_document_and_matter_physical_deletion():
    """
    用户删除上传的合同时，磁盘上的原件及副本必须真正删除（unlink），
    后续访问返回 404。
    """
    upload_dir = get_uploads_dir()
    upload_dir.mkdir(parents=True, exist_ok=True)

    # 1. 物理创建测试文件
    real_file = upload_dir / "test_contract_secret.pdf"
    real_file.write_text("保密买卖合同核心条款：保密期三年。", encoding="utf-8")
    assert real_file.exists()

    # 2. 创建案件空间并挂载文档
    matter = create_new_matter({"title": "保密买卖合同案件"})
    matter_id = matter["matter_id"]
    doc = add_document_to_matter(
        matter_id=matter_id,
        doc_data={
            "title": "test_contract_secret.pdf",
            "file_path": str(real_file),
            "doc_type": "contract",
        },
    )
    doc_id = doc["doc_id"]

    # 3. 验证删除单个文档：磁盘物理文件必须被删除
    del_doc_res = delete_document_from_matter(matter_id, doc_id)
    assert del_doc_res is True
    assert not real_file.exists(), "磁盘原件未被物理删除！"

    # 4. 创建另一个文件挂载到该案件，测试整案删除级联物理清理
    real_file2 = upload_dir / "test_evidence2.pdf"
    real_file2.write_text("保密证据原件二", encoding="utf-8")
    assert real_file2.exists()
    add_document_to_matter(
        matter_id=matter_id,
        doc_data={
            "title": "test_evidence2.pdf",
            "file_path": str(real_file2),
            "doc_type": "evidence",
        },
    )

    # 软删除/彻底删除案件
    del_matter_res = soft_delete_matter(matter_id)
    assert del_matter_res is True
    # 磁盘文件必须已被清除
    assert not real_file2.exists(), "案件删除后关联磁盘文件未被物理清除！"
    # 后续查询该案件必须返回 None（单用户下触发 404）
    assert get_matter_by_id(matter_id) is None
