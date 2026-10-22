# -*- coding: utf-8 -*-
"""
tests/test_batch16.py:
审查报告修复计划第 16 批（b16.md）验收测试集。
覆盖 6 个条目：
- A-04: 跨 2008 年劳动补偿分段（termination_reason、劳部发〔1994〕481号、不满一年按一年）
- A-05: 诉讼时效中断类型、20年起算日、节假日顺延
- A-06: 离婚案件诉讼费 50~300 元自选
- A-07: 迟延履行加倍利息、违约金调减 30% 测算与备注更正
- A-08: 合同红线规则措辞更正（连接点、竞业限制、涉外因素）
- A-18: 一键成套附属文书自选（保全申请书按需生成）
"""
import subprocess
from decimal import Decimal
import pytest

from gateway.utils.cn_legal_calc import (
    calculate_labor_compensation,
    calculate_statute_of_limitations,
    calculate_court_fees,
    calculate_delayed_performance_interest,
    calculate_penalty_adjustment_reference,
)
from gateway.utils.redline_builder import PLAYBOOK_PRESETS


# -----------------------------------------------------------------------------
# 条目 1/6｜A-04 跨 2008 年劳动补偿分段
# -----------------------------------------------------------------------------
def test_a04_expiry_termination_pre2008_zero():
    """
    入职 2005-03-01、2010-03-01 到期终止（termination_reason="expiry_termination"）
    → 2008 年前段补偿月数为 0，只计 2008 年后段；输出 warnings 含 '481'。
    """
    res = calculate_labor_compensation(
        monthly_salary=10000,
        hire_date="2005-03-01",
        termination_date="2010-03-01",
        termination_reason="expiry_termination",
    )
    seg = res.get("segment_2008")
    assert seg is not None, "跨2008年应有分段信息"
    assert seg["pre_2008_compensation_months"] == 0, "到期终止在2008年前不支付经济补偿"
    assert seg["pre_2008_amount"] == 0.0
    # 2008-01-01 到 2010-03-01 为 2年2个月 -> 2.5 个月
    assert seg["post_2008_compensation_months"] == 2.5
    assert seg["total_segmented_n"] == 25000.0
    all_warnings = " ".join(res.get("warnings", []) + seg.get("warnings", []))
    assert "481" in all_warnings


def test_a04_pre2008_seven_months_rounded_to_one_year():
    """
    同一人 2008 年前段工作 7 个月（如入职 2007-06-01），事由为支付补偿的事由
    → 2008 年前段按 1 个月计（不满一年按一年），而不是 0.5；输出 warnings 含 '481'。
    """
    res = calculate_labor_compensation(
        monthly_salary=10000,
        hire_date="2007-06-01",
        termination_date="2010-03-01",
        termination_reason="employer_dismissal_with_notice",
    )
    seg = res.get("segment_2008")
    assert seg is not None
    # 2007-06-01 至 2007-12-31 为 7 个月，按 481 号不满一年按一年计 1 个月
    assert seg["pre_2008_compensation_months"] == 1.0
    all_warnings = " ".join(res.get("warnings", []) + seg.get("warnings", []))
    assert "481" in all_warnings


def test_a04_invalid_termination_reason(client):
    """未知解除事由抛出 ValueError，API 返回 422。"""
    with pytest.raises(ValueError):
        calculate_labor_compensation(
            monthly_salary=10000,
            hire_date="2007-06-01",
            termination_date="2010-03-01",
            termination_reason="unknown_reason_xyz",
        )
    resp = client.post(
        "/api/v1/phase1/calc/labor-arbitration",
        json={
            "monthly_salary": 10000,
            "hire_date": "2007-06-01",
            "termination_date": "2010-03-01",
            "termination_reason": "unknown_reason_xyz",
        },
    )
    assert resp.status_code == 422


# -----------------------------------------------------------------------------
# 条目 2/6｜A-05 诉讼时效中断类型、20 年起算日、节假日顺延
# -----------------------------------------------------------------------------
def test_a05_r10_compatibility():
    """R10 一般中断场景保持通过（2028-06-01）。"""
    res = calculate_statute_of_limitations(
        "2023-01-01",
        interruption_events=[{"date": "2025-06-01", "type": "催告"}],
        today_date="2026-10-21",
    )
    assert res["final_expire_date"] == "2028-06-01"


def test_a05_lawsuit_with_proceeding_end_date():
    """起算 2023-01-01，lawsuit 事件 2024-06-01、proceeding_end_date 2025-03-01 → final_expire_date == '2028-03-01'。"""
    res = calculate_statute_of_limitations(
        "2023-01-01",
        interruption_events=[
            {
                "date": "2024-06-01",
                "type": "lawsuit",
                "proceeding_end_date": "2025-03-01",
            }
        ],
        today_date="2026-10-21",
        holidays=[],
    )
    assert res["final_expire_date"] == "2028-03-01"


def test_a05_lawsuit_without_proceeding_end_date_warns():
    """lawsuit 事件无 proceeding_end_date → warnings 非空，不计算新届满日。"""
    res = calculate_statute_of_limitations(
        "2023-01-01",
        interruption_events=[{"date": "2024-06-01", "type": "lawsuit"}],
        today_date="2026-10-21",
    )
    assert len(res.get("warnings", [])) > 0
    assert any("程序未终结或终结日未知" in w for w in res["warnings"])
    # 初始 3 年届满日 2026-01-01（若顺延至 2026-01-04）
    assert res["final_expire_date"] in ("2026-01-01", "2026-01-04")


def test_a05_holiday_extension():
    """用 holidays 参数构造届满日为节假日的情形 → 顺延到下一非节假日。"""
    # 2023-01-01 起算 3 年届满日为 2026-01-01；设置 2026-01-01 与 2026-01-02 为节假日
    res = calculate_statute_of_limitations(
        "2023-01-01",
        cause_type="general_3y",
        holidays=["2026-01-01", "2026-01-02"],
        today_date="2026-10-21",
    )
    assert res["final_expire_date"] == "2026-01-03"
    assert any("顺延" in t.get("event", "") for t in res.get("timeline_log", []))


def test_a05_damage_date_20y():
    """最长 20 年期间从 damage_date 起算；未提供时沿用原起算日并提示。"""
    res_with_damage = calculate_statute_of_limitations(
        "2023-01-01",
        damage_date="2020-01-01",
        cause_type="general_3y",
        today_date="2026-10-21",
        holidays=[],
    )
    assert res_with_damage["max_20y_expire"] == "2040-01-01"

    res_no_damage = calculate_statute_of_limitations(
        "2023-01-01",
        cause_type="general_3y",
        today_date="2026-10-21",
        holidays=[],
    )
    assert any("未提供权利受到损害之日" in w for w in res_no_damage.get("warnings", []))


# -----------------------------------------------------------------------------
# 条目 3/6｜A-06 离婚案件诉讼费固定 100 元改为 50–300 元
# -----------------------------------------------------------------------------
def test_a06_divorce_court_fees(client):
    """默认 100 元与改动前一致；divorce_base_fee=300 → 300；divorce_base_fee=400 → 422；breakdown 含 '以当地标准为准'。"""
    res_default = calculate_court_fees(100000, case_type="divorce")
    assert res_default["actual_fee"] == 100.0

    res_300 = calculate_court_fees(100000, case_type="divorce", divorce_base_fee=300)
    assert res_300["actual_fee"] == 300.0
    assert any("以当地标准为准" in b["rate"] for b in res_300["tier_breakdown"])

    with pytest.raises(ValueError):
        calculate_court_fees(100000, case_type="divorce", divorce_base_fee=400)

    resp_400 = client.post(
        "/api/v1/phase1/calc/court-fees",
        json={"claim_amount": 100000, "case_type": "divorce", "divorce_base_fee": 400},
    )
    assert resp_400.status_code == 422


# -----------------------------------------------------------------------------
# 条目 4/6｜A-07 补充计算器并更正 30% 备注
# -----------------------------------------------------------------------------
def test_a07_delayed_performance_interest():
    """迟延履行：本金 100000、2026-01-01 至 2026-01-31（30 天）、默认日利率 → 525.00，warnings 非空。"""
    res = calculate_delayed_performance_interest(
        principal_unpaid=100000,
        start_date="2026-01-01",
        end_date="2026-01-31",
    )
    assert round(res["interest"], 2) == 525.00
    assert len(res.get("warnings", [])) > 0
    assert "日利率依据需律师核实" in " ".join(res["warnings"])
    assert "第二百六十四条" in res.get("legal_basis", "")


def test_a07_penalty_adjustment_reference():
    """违约金：约定 140000、损失 100000 → 超过 30% 为 True，断言含 '不是调减后的上限'，不输出调减后金额。"""
    res = calculate_penalty_adjustment_reference(
        agreed_penalty=140000,
        actual_loss=100000,
    )
    assert res["exceeds_30_percent"] is True
    assert round(res["ratio"], 2) == 0.4
    assert "不是调减后的上限" in res["note"]
    assert "adjusted_amount" not in res
    assert "调减后金额" not in str(res)


def test_a07_no_misleading_notes_in_gateway_data():
    """rg '损失上限红线' gateway data 无结果。"""
    res = subprocess.run(
        ["git", "grep", "损失上限红线", "--", "gateway", "data"],
        capture_output=True,
        text=True,
    )
    # git grep 返回 1 表示未找到匹配，0 表示找到匹配
    assert res.returncode != 0, f"发现遗留的'损失上限红线'文案: {res.stdout}"


# -----------------------------------------------------------------------------
# 条目 5/6｜A-08 合同红线规则措辞
# -----------------------------------------------------------------------------
def test_a08_redline_rule_wordings():
    """
    测试读取规则列表：
    - 不含 '原告所在地人民法院'
    - 竞业限制规则不含 '必须明确按月支付不低于'
    - 跨境规则含 '涉外因素'
    """
    general_rules = " ".join(PLAYBOOK_PRESETS["general"]["rules"])
    assert "原告所在地人民法院" not in general_rules
    assert "甲方住所地" in general_rules

    labor_rules = " ".join(PLAYBOOK_PRESETS["labor"]["rules"])
    assert "必须明确按月支付不低于" not in labor_rules
    assert "30%" in labor_rules

    cross_rules = " ".join(PLAYBOOK_PRESETS["cross_border_procurement"]["rules"])
    assert "涉外因素" in cross_rules


# -----------------------------------------------------------------------------
# 条目 6/6｜A-18 一键成套默认生成保全申请书
# -----------------------------------------------------------------------------
def test_a18_sub_documents_preservation_choice(client):
    """
    测试：
    - 不传 sub_documents → 生成文件列表不含保全申请书；
    - sub_documents 含 'property_preservation' → 含保全申请书；
    - 非法值 → 422。
    """
    payload_base = {
        "cause_of_action": "买卖合同纠纷",
        "claim_amount": 200000.0,
        "raw_case_notes": "被告拖欠货款20万元，经多次催讨未果。",
        "court_name": "北京市海淀区人民法院",
        "plaintiff": {
            "name": "北京信达商贸有限公司",
            "id_card_or_uscc": "91110108MA00TEST11",
            "address": "北京市海淀区中关村南大街1号",
        },
        "defendant": {
            "name": "北京宏达科技开发有限公司",
            "id_card_or_uscc": "91110105MA00TEST22",
            "address": "北京市朝阳区建国门外大街2号",
        },
    }

    # 1. 不传 sub_documents → 默认列表不含保全申请书
    resp1 = client.post("/api/v1/phase1/generate-litigation-package", json=payload_base)
    assert resp1.status_code == 200, resp1.text
    docs1 = resp1.json().get("generated_documents", [])
    doc_types1 = [d.get("doc_type") for d in docs1]
    assert "财产保全申请书" not in doc_types1

    # 2. 传入 sub_documents 含 property_preservation → 生成保全申请书
    payload_with_preserv = dict(payload_base)
    payload_with_preserv["sub_documents"] = ["property_preservation", "power_of_attorney"]
    resp2 = client.post("/api/v1/phase1/generate-litigation-package", json=payload_with_preserv)
    assert resp2.status_code == 200, resp2.text
    docs2 = resp2.json().get("generated_documents", [])
    doc_types2 = [d.get("doc_type") for d in docs2]
    assert "财产保全申请书" in doc_types2

    # 3. 非法值 → 422
    payload_invalid = dict(payload_base)
    payload_invalid["sub_documents"] = ["invalid_doc_type"]
    resp3 = client.post("/api/v1/phase1/generate-litigation-package", json=payload_invalid)
    assert resp3.status_code == 422
