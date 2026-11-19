# -*- coding: utf-8 -*-
"""
利益冲突审查规则测试（LF-017 AC-1～AC-16 与 T-012 TC1～TC8）。
"""
from __future__ import annotations

import json
import pytest


def test_retainer_opposing_default_prohibited_and_configurable(client):
    """
    AC-11 / TC4: 常年顾问单位作为相对方，默认禁止代理（PROHIBITED）；
    若显式开启 allow_retainer_consent=True，则为可豁免（WAIVABLE_WITH_CONSENT）。
    """
    # 默认从严：PROHIBITED
    resp = client.post(
        "/api/v1/conflict/check",
        json={
            "client_name": "北京知客云服科技有限公司",
            "opposing_party": "北京宏达商贸有限公司",
            "case_subject": "技术合同尾款争议",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["conflict_level"] == "PROHIBITED"
    assert data["has_conflict"] is True
    assert data["requires_consent"] is False

    # 可配置项：允许同意豁免
    resp2 = client.post(
        "/api/v1/conflict/check",
        json={
            "client_name": "北京知客云服科技有限公司",
            "opposing_party": "北京宏达商贸有限公司",
            "case_subject": "技术合同尾款争议",
            "allow_retainer_consent": True,
        },
    )
    assert resp2.status_code == 200, resp2.text
    data2 = resp2.json()
    assert data2["conflict_level"] == "WAIVABLE_WITH_CONSENT"
    assert data2["requires_consent"] is True


def test_dual_clients_is_prohibited_only_for_same_matter(client):
    """
    AC-6: 「双方都是本所客户」不再一律禁止；
    同一案件 (is_same_matter='是') 禁止代理；未确认 (is_same_matter=None) 需人工判断；
    非同一案件 (is_same_matter='否') 经同意可代理。
    """
    # 1. 同一案件 -> PROHIBITED
    resp_same = client.post(
        "/api/v1/conflict/check",
        json={
            "client_name": "李四",
            "opposing_party": "智科云服信息技术（北京）有限公司",
            "case_subject": "合同纠纷",
            "is_same_matter": "是",
        },
    )
    assert resp_same.status_code == 200, resp_same.text
    assert resp_same.json()["conflict_level"] == "PROHIBITED"

    # 2. 未确认同一性 -> MANUAL_REVIEW
    resp_uncertain = client.post(
        "/api/v1/conflict/check",
        json={
            "client_name": "李四",
            "opposing_party": "智科云服信息技术（北京）有限公司",
            "case_subject": "合同纠纷",
        },
    )
    assert resp_uncertain.status_code == 200, resp_uncertain.text
    assert resp_uncertain.json()["conflict_level"] == "MANUAL_REVIEW"

    # 3. 非同一案件 -> WAIVABLE_WITH_CONSENT
    resp_diff = client.post(
        "/api/v1/conflict/check",
        json={
            "client_name": "李四",
            "opposing_party": "智科云服信息技术（北京）有限公司",
            "case_subject": "完全无关侵权争议",
            "is_same_matter": "否",
        },
    )
    assert resp_diff.status_code == 200, resp_diff.text
    assert resp_diff.json()["conflict_level"] == "WAIVABLE_WITH_CONSENT"


def test_rule_basis_lawyer_law_2017_and_prompts(client):
    """
    面向结果的依据写《律师法》（2017年修正文本）第三十九条，不写 2026 修正第四十二条。
    每次必须显示通用合规提示，并提示本所人员及近亲属未检查。
    """
    resp = client.post(
        "/api/v1/conflict/check",
        json={
            "client_name": "北京知客云服科技有限公司",
            "opposing_party": "华腾物流网络技术有限公司",
            "is_same_matter": "是",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    blob = json.dumps(data, ensure_ascii=False)
    assert "《律师法》（2017年修正文本）第三十九条" in blob
    assert "第四十二条" not in blob
    assert "2026 修正" not in blob
    assert "项次待核对" in blob
    assert data.get("general_prompt") is not None
    assert "律师执业管理办法" in data["general_prompt"]
    assert "本所人员及近亲属" in data.get("personnel_and_relatives_check", "")
    assert data["clearance_certificate"]["is_cleared"] is False
    assert not data["clearance_certificate"].get("certificate_no")


def test_batch2_locked_db_still_not_clear(client, monkeypatch):
    """批次2：锁库时不得返回 CLEAR —— 回归。"""
    import sqlite3
    import gateway.utils.conflict_checker as cc

    def boom(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(cc, "get_db_connection", boom)
    resp = client.post(
        "/api/v1/conflict/check",
        json={"client_name": "甲公司", "opposing_party": "乙公司"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data.get("verdict") == "UNABLE_TO_CHECK"
    assert data.get("conflict_level") == "UNABLE_TO_CHECK"
    assert "CLEAR" not in resp.text


def test_demo_seeds_do_not_use_lawyer_verify_placeholder():
    import inspect

    from gateway.utils.agent_task_db import seed_demo_agent_tasks
    from gateway.utils.conflict_checker import seed_demo_conflict_cases
    from gateway.utils.matter_vault_db import seed_demo_matters
    from gateway.utils.review_table_engine import seed_demo_review_tables

    for fn in (
        seed_demo_conflict_cases,
        seed_demo_review_tables,
        seed_demo_matters,
        seed_demo_agent_tasks,
    ):
        source = inspect.getsource(fn)
        assert "TODO(律师核实)" not in source
        assert "请律师核实" not in source


# ==============================================================================
# T-012 自动化用例 TC1 ～ TC8 完整覆盖 (AC-10)
# ==============================================================================
@pytest.fixture
def setup_tc_registry_data():
    """灌装 TC1～TC8 所需的确定性底档记录"""
    from gateway.utils.conflict_checker import init_conflict_registry_table, get_db_connection
    init_conflict_registry_table()
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM conflict_case_registry WHERE case_id LIKE 'TEST-TC-%'")
        
        # 1. 乙丙案：在办诉讼 (TC1, TC2, TC3)
        cur.execute("""
            INSERT INTO conflict_case_registry (
                case_id, case_title, cause_of_action, lead_lawyer, client_name,
                opposing_name, case_status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "TEST-TC-ACTIVE-1", "代理乙诉讼公司诉丙应诉公司买卖合同纠纷", "买卖合同纠纷",
            "张律师", "乙诉讼公司", "丙应诉公司", "ACTIVE", "2026-01-10 10:00:00"
        ))

        # 2. 顾问单位案：常年顾问 (TC4)
        cur.execute("""
            INSERT INTO conflict_case_registry (
                case_id, case_title, cause_of_action, lead_lawyer, client_name,
                opposing_name, case_status, retainer_end_date, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "TEST-TC-RETAINER-4", "乙顾问集团常年法律顾问", "常年法律顾问",
            "李律师", "乙顾问集团", "无特定相对人", "RETAINER", "2027-12-31", "2026-01-01 00:00:00"
        ))

        # 3. 乙丙案（已于2026-03结案，TC5 / TC6）
        cur.execute("""
            INSERT INTO conflict_case_registry (
                case_id, case_title, cause_of_action, lead_lawyer, client_name,
                opposing_name, case_status, retainer_end_date, notes, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "TEST-TC-CLOSED-2026", "代理乙历史客户A诉丙原对方A案（2026一审）", "买卖合同纠纷",
            "王律师", "乙历史客户A", "丙原对方A", "CLOSED", "2026-03-15", "结案日期: 2026-03-15", "2025-01-10 10:00:00"
        ))

        # 4. 乙丙案（已于2024-01结案，超过1年，TC7）
        cur.execute("""
            INSERT INTO conflict_case_registry (
                case_id, case_title, cause_of_action, lead_lawyer, client_name,
                opposing_name, case_status, retainer_end_date, notes, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "TEST-TC-CLOSED-2024", "代理乙历史客户B诉丙原对方B案（2024已结）", "买卖合同纠纷",
            "赵律师", "乙历史客户B", "丙原对方B", "CLOSED", "2024-01-15", "结案日期: 2024-01-15", "2023-01-10 10:00:00"
        ))

        # 5. 异常状态“在办”记录 (TC8)
        cur.execute("""
            INSERT INTO conflict_case_registry (
                case_id, case_title, cause_of_action, lead_lawyer, client_name,
                opposing_name, case_status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "TEST-TC-INVALID-STATUS-8", "异常数据示意案", "民间借贷纠纷",
            "钱律师", "乙异常客户", "丙异常对方", "在办", "2026-01-01 10:00:00"
        ))
        conn.commit()

    yield
    with get_db_connection() as conn:
        conn.execute("DELETE FROM conflict_case_registry WHERE case_id LIKE 'TEST-TC-%'")
        conn.commit()


def test_tc1_active_opposing_same_matter_prohibited(client, setup_tc_registry_data):
    """TC1（复查用例）：丙公司来委托，对方为乙公司，就同一买卖合同纠纷应诉 -> PROHIBITED"""
    resp = client.post(
        "/api/v1/conflict/check",
        json={
            "client_name": "丙应诉公司",
            "opposing_party": "乙诉讼公司",
            "case_subject": "买卖合同纠纷应诉",
            "is_same_matter": "是",
        },
    )
    assert resp.status_code == 200, resp.text
    d = resp.json()
    assert d["conflict_level"] == "PROHIBITED"
    assert d["requires_consent"] is False
    assert "不可豁免" in d["recommendation"]


def test_tc2_active_opposing_uncertain_matter_manual_review(client, setup_tc_registry_data):
    """TC2：丙公司来委托，对方为乙公司，“是否同一案件”未填 -> MANUAL_REVIEW"""
    resp = client.post(
        "/api/v1/conflict/check",
        json={
            "client_name": "丙应诉公司",
            "opposing_party": "乙诉讼公司",
            "case_subject": "买卖合同纠纷",
            "is_same_matter": None,
        },
    )
    assert resp.status_code == 200, resp.text
    d = resp.json()
    assert d["conflict_level"] == "MANUAL_REVIEW"
    assert d["requires_consent"] is False
    assert "系统无法自动判断" in d["recommendation"]


def test_tc3_active_opposing_different_matter_waivable(client, setup_tc_registry_data):
    """TC3：丙公司来委托，起诉丁公司追讨另一笔货款，与乙公司无关 -> WAIVABLE_WITH_CONSENT"""
    resp = client.post(
        "/api/v1/conflict/check",
        json={
            "client_name": "丙应诉公司",
            "opposing_party": "丁公司第三方",
            "case_subject": "追讨另一笔货款，与乙公司无关",
            "is_same_matter": "否",
        },
    )
    assert resp.status_code == 200, resp.text
    d = resp.json()
    assert d["conflict_level"] == "WAIVABLE_WITH_CONSENT"
    assert d["requires_consent"] is True


def test_tc4_retainer_opposing_default_prohibited(client, setup_tc_registry_data):
    """TC4：戊公司来委托，起诉乙顾问集团，事由无关；默认禁止代理 -> PROHIBITED"""
    resp = client.post(
        "/api/v1/conflict/check",
        json={
            "client_name": "戊公司独立方",
            "opposing_party": "乙顾问集团",
            "case_subject": "无关租赁争议",
            "is_same_matter": "否",
        },
    )
    assert resp.status_code == 200, resp.text
    d = resp.json()
    assert d["conflict_level"] == "PROHIBITED"
    assert d["requires_consent"] is False


def test_tc5_closed_subsequent_stage_prohibited(client, setup_tc_registry_data):
    """TC5：底档中乙丙案已于 2026-03 结案，二审期间丙公司来委托二审 -> PROHIBITED"""
    resp = client.post(
        "/api/v1/conflict/check",
        json={
            "client_name": "丙原对方A",
            "opposing_party": "乙历史客户A",
            "case_subject": "二审代理应诉",
            "is_same_matter": "是",
            "subsequent_stage": True,
            "check_date": "2026-10-24",
        },
    )
    assert resp.status_code == 200, resp.text
    d = resp.json()
    assert d["conflict_level"] == "PROHIBITED"
    assert d["requires_consent"] is False


def test_tc6_closed_within_1yr_same_matter_waivable(client, setup_tc_registry_data):
    """TC6：底档中乙丙案已于 2026-03 结案，丙公司 2026-10 就同一合同的后续争议来委托 -> WAIVABLE_WITH_CONSENT"""
    resp = client.post(
        "/api/v1/conflict/check",
        json={
            "client_name": "丙原对方A",
            "opposing_party": "乙历史客户A",
            "case_subject": "同一合同项下货物保修后续纠纷",
            "is_same_matter": "是",
            "subsequent_stage": False,
            "check_date": "2026-10-24",
        },
    )
    assert resp.status_code == 200, resp.text
    d = resp.json()
    assert d["conflict_level"] == "WAIVABLE_WITH_CONSENT"
    assert d["requires_consent"] is True


def test_tc7_closed_over_1yr_unrelated_manual_review(client, setup_tc_registry_data):
    """TC7：底档中乙丙案已于 2024-01 结案，丙公司来委托与乙公司的无关纠纷 -> MANUAL_REVIEW"""
    resp = client.post(
        "/api/v1/conflict/check",
        json={
            "client_name": "丙原对方B",
            "opposing_party": "乙历史客户B",
            "case_subject": "无关知识产权侵权争议",
            "is_same_matter": "否",
            "check_date": "2026-10-24",
        },
    )
    assert resp.status_code == 200, resp.text
    d = resp.json()
    assert d["conflict_level"] == "MANUAL_REVIEW"
    assert d["requires_consent"] is False
    assert "保密信息相关性" in d["recommendation"]


def test_tc8_illegal_status_outputs_unable_to_check(client, setup_tc_registry_data):
    """TC8：底档中某记录状态写为“在办”（非枚举值），拟委托人命中该记录 -> UNABLE_TO_CHECK"""
    resp = client.post(
        "/api/v1/conflict/check",
        json={
            "client_name": "丙异常对方",
            "opposing_party": "某第三方主体",
            "is_same_matter": "是",
        },
    )
    assert resp.status_code == 200, resp.text
    d = resp.json()
    assert d["conflict_level"] == "UNABLE_TO_CHECK"
    assert "CLEAR" not in json.dumps(d, ensure_ascii=False)
    assert "无法识别的数据" in d["recommendation"]
