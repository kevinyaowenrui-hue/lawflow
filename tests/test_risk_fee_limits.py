# -*- coding: utf-8 -*-
"""告知文案、外发留存和风险代理禁令。"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

ADULT_ID = "110101199003072375"
MINOR_ID = "110101201003072375"
ROOT = Path(__file__).resolve().parents[1]


def _base_matter(**extra):
    payload = {
        "title": "风险代理校验案",
        "cause_of_action": "买卖合同纠纷",
        "plaintiff_name": "校验委托人甲",
        "defendant_name": "校验对方乙",
        "client_role": "原告",
        "is_same_matter": "否",
        "principal_amount": 100000,
    }
    payload.update(extra)
    return payload


@pytest.mark.parametrize(
    "cause,article,label",
    [
        ("离婚纠纷", "第十一条", "婚姻"),
        ("继承纠纷", "第十一条", "继承"),
        ("追索劳动报酬纠纷", "第十一条", "劳动报酬"),
        ("工伤保险待遇纠纷", "第十一条", "工伤赔偿"),
        ("抚养费纠纷", "第十一条", "抚养费"),
        ("社会保险待遇纠纷", "第十一条", "社会保险"),
        ("刑事附带民事诉讼", "第十二条", "刑事"),
        ("行政诉讼", "第十二条", "行政"),
        ("国家赔偿", "第十二条", "国家赔偿"),
        ("群体性诉讼", "第十二条", "群体性诉讼"),
    ],
)
def test_prohibited_causes_cannot_use_risk_fee_even_if_disclosed(cause, article, label):
    from gateway.utils.matter_intake import normalize_matter_intake

    with pytest.raises(ValueError) as exc:
        normalize_matter_intake(_base_matter(
            cause_of_action=cause,
            fee_type="risk",
            risk_disclosed=True,
            practice={"risk_fee_ratio": 20},
        ))
    message = str(exc.value)
    assert "《律师服务收费管理办法》" in message
    assert article in message
    assert label in message
    assert "不能按风险代理保存" in message
    assert "勾选「已说明」不能代替书面风险代理合同。" in message


def test_other_property_case_requires_ratio_and_warns_above_thirty_percent():
    from gateway.utils.matter_intake import normalize_matter_intake

    with pytest.raises(ValueError, match="必须填写约定比例"):
        normalize_matter_intake(_base_matter(fee_type="risk", risk_disclosed=True))

    allowed = normalize_matter_intake(_base_matter(
        fee_type="risk",
        risk_disclosed=True,
        practice={"risk_fee_ratio": "15%"},
    ))
    assert allowed["practice"]["risk_fee_ratio"] == 15
    assert allowed["practice"]["risk_fee_warning"] == ""
    assert "不能代替书面风险代理合同" in allowed["practice"]["risk_fee_contract_note"]

    capped = normalize_matter_intake(_base_matter(
        fee_type="risk",
        risk_disclosed=True,
        risk_fee_ratio=30,
    ))
    assert capped["practice"]["risk_fee_warning"] == ""

    warned = normalize_matter_intake(_base_matter(
        fee_type="risk",
        risk_disclosed=True,
        practice={"risk_fee_ratio": 35},
    ))
    assert warned["practice"]["risk_fee_ratio"] == 35
    assert "超过 30%" in warned["practice"]["risk_fee_warning"]
    assert "当地收费办法可能更严" in warned["practice"]["risk_fee_warning"]

    labor_contract = normalize_matter_intake(_base_matter(
        cause_of_action="劳动合同纠纷",
        fee_type="risk",
        risk_disclosed=True,
        practice={"risk_fee_ratio": 10},
    ))
    assert labor_contract["practice"]["fee_type"] == "risk"

    divorce_fixed = normalize_matter_intake(_base_matter(
        cause_of_action="离婚纠纷",
        fee_type="fixed",
    ))
    assert divorce_fixed["practice"]["fee_type"] == "fixed"


def test_api_blocks_divorce_risk_fee_and_saves_property_warning(client):
    blocked = client.post("/api/v1/vault/matters", json=_base_matter(
        title="接口离婚风险代理",
        cause_of_action="离婚纠纷",
        plaintiff_name="接口委托人丙",
        defendant_name="接口对方丁",
        fee_type="risk",
        risk_disclosed=True,
        practice={"risk_fee_ratio": 20},
    ))
    assert blocked.status_code == 422, blocked.text
    assert "第十一条" in blocked.text
    assert "禁止" in blocked.text
    assert "勾选「已说明」不能代替书面风险代理合同。" in blocked.text

    saved = client.post("/api/v1/vault/matters", json=_base_matter(
        title="接口买卖风险代理",
        plaintiff_name="接口委托人戊",
        defendant_name="接口对方己",
        fee_type="risk",
        risk_disclosed=True,
        practice={"risk_fee_ratio": 40},
    ))
    assert saved.status_code == 200, saved.text
    practice = saved.json()["matter"]["practice"]
    assert practice["risk_fee_ratio"] == 40
    assert "30%" in practice["risk_fee_warning"]
    assert "当地收费办法可能更严" in practice["risk_fee_warning"]
