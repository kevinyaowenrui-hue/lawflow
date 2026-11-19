# -*- coding: utf-8 -*-
"""本所人员利冲：规范化姓名、证件号、姓名相近与空名册。"""
from __future__ import annotations

import os
from pathlib import Path


def test_conflict_matching_storage_uses_lawflow_pytest_tmp(tmp_path):
    storage = Path(os.environ["LAWFLOW_STORAGE_DIR"])
    assert storage.drive.upper() == "D:"
    assert "lawflow-pytest-tmp" in str(storage)
    assert "lawflow-pytest-tmp" in str(tmp_path)


def test_name_and_credential_normalization():
    from gateway.utils.firm_roster import (
        names_are_similar,
        normalize_credential,
        normalize_person_name,
    )

    assert normalize_person_name("　Ｍａ·　Ｌｉ　") == normalize_person_name("Ma Li")
    assert normalize_person_name("阙·承昭") == normalize_person_name("阙承昭")
    assert normalize_person_name("阙・承昭") == normalize_person_name("阙承昭")
    assert normalize_person_name("阙•承昭") == normalize_person_name("阙承昭")
    assert normalize_credential("１１０１０１ １９９００３０７４３２１") == "110101199003074321"
    assert normalize_credential("未录入") == ""
    assert names_are_similar("张三", "张四") is False
    assert names_are_similar("张三", "李三") is False
    assert names_are_similar("沈禾", "沈木") is False
    assert names_are_similar("张", "张三") is False
    assert names_are_similar("张三", "张三") is False
    assert names_are_similar("阙承昭", "阙承招") is True
    assert names_are_similar("阙承昭", "阙承昭二") is True
    assert names_are_similar("张三", "张三丰") is True


def _matter(client, **overrides):
    payload = {
        "title": "利冲比对案",
        "cause_of_action": "买卖合同纠纷",
        "plaintiff_name": "利冲委托人甲",
        "defendant_name": "利冲对方乙",
        "client_role": "原告",
        "is_same_matter": "否",
    }
    payload.update(overrides)
    return client.post("/api/v1/vault/matters", json=payload)


def _assert_not_created(client, title):
    listed = client.get("/api/v1/vault/matters", params={"search": title})
    assert listed.status_code == 200, listed.text
    assert listed.json()["total"] == 0


def test_fullwidth_space_and_dot_same_name_blocks(client):
    saved = client.post("/api/v1/vault/firm-roster", json={
        "lawyer_name": "Ma Li",
        "license_no": "13101202610111001",
        "law_firm": "利冲比对律师事务所",
        "is_default": True,
    })
    assert saved.status_code == 200, saved.text
    chinese = client.post("/api/v1/vault/firm-roster", json={
        "lawyer_name": "阙承昭",
        "license_no": "13101202610111002",
        "law_firm": "利冲比对律师事务所",
    })
    assert chinese.status_code == 200, chinese.text

    spaced = _matter(
        client,
        title="全角空格同名案",
        plaintiff_name="利冲委托人甲",
        defendant_name="　Ｍａ·　Ｌｉ　",
    )
    assert spaced.status_code == 409, spaced.text
    assert "同名" in spaced.json()["detail"]
    assert "未确认前不能建案" in spaced.json()["detail"]
    assert "姓名相近" not in spaced.json()["detail"]
    _assert_not_created(client, "全角空格同名案")

    dotted = _matter(
        client,
        title="中点空格同名案",
        plaintiff_name="利冲委托人乙",
        defendant_name="阙 承·昭",
    )
    assert dotted.status_code == 409, dotted.text
    assert "同名" in dotted.json()["detail"]
    assert "未确认前不能建案" in dotted.json()["detail"]
    _assert_not_created(client, "中点空格同名案")

    confirmed = _matter(
        client,
        title="全角同名确认后建档",
        plaintiff_name="利冲委托人丙",
        defendant_name="Ｍａ・Ｌｉ",
        acknowledge_personnel_conflict=True,
    )
    assert confirmed.status_code == 200, confirmed.text
    assert "已确认" in confirmed.json()["message"]
    assert "不是静默建案" in confirmed.json()["message"]
    assert confirmed.json()["matter"]["practice"]["personnel_status"] == "HIT"


def test_same_credential_different_name_blocks(client):
    saved = client.post("/api/v1/vault/firm-roster", json={
        "lawyer_name": "阙证件",
        "license_no": "13101202610111222",
        "id_no": "110101199003074321",
        "law_firm": "利冲比对律师事务所",
        "relatives": [{
            "name": "阙亲属",
            "relation": "配偶",
            "id_no": "110101198805056789",
        }],
    })
    assert saved.status_code == 200, saved.text
    lawyer = saved.json()["lawyer"]
    assert lawyer["id_no"] == "110101199003074321"
    assert lawyer["relatives"][0]["id_no"] == "110101198805056789"

    by_id = _matter(
        client,
        title="证件号相同姓名不同案",
        plaintiff_name="利冲委托人丁",
        defendant_name="毫无关系甲",
        defendant_id="１１０１０１１９９００３０７４３２１",
    )
    assert by_id.status_code == 409, by_id.text
    detail = by_id.json()["detail"]
    assert "证件号" in detail
    assert "不能静默建案" in detail
    assert "未确认前不能建案" in detail
    assert "禁止代理" not in detail
    _assert_not_created(client, "证件号相同姓名不同案")

    by_license = _matter(
        client,
        title="执业证号相同姓名不同案",
        plaintiff_name="利冲委托人戊",
        defendant_name="毫无关系乙",
        defendant_id="13101202610111222",
    )
    assert by_license.status_code == 409, by_license.text
    assert "证件号" in by_license.json()["detail"]
    _assert_not_created(client, "执业证号相同姓名不同案")

    by_relative = _matter(
        client,
        title="近亲属证件号相同案",
        plaintiff_name="利冲委托人己",
        defendant_name="毫无关系丙",
        defendant_id="110101 19880505 6789",
    )
    assert by_relative.status_code == 409, by_relative.text
    assert "证件号" in by_relative.json()["detail"]
    _assert_not_created(client, "近亲属证件号相同案")

    by_client_id = _matter(
        client,
        title="委托人证件号相同案",
        plaintiff_name="另一个委托人",
        plaintiff_id="110101199003074321",
        defendant_name="毫无关系丁",
    )
    assert by_client_id.status_code == 409, by_client_id.text
    assert "证件号" in by_client_id.json()["detail"]

    checked = client.post("/api/v1/conflict/check", json={
        "client_name": "利冲委托人丁",
        "opposing_party": "毫无关系甲",
        "opposing_id_or_code": "110101199003074321",
        "is_same_matter": "否",
    })
    assert checked.status_code == 200, checked.text
    text = checked.json()["personnel_and_relatives_check"]
    assert "证件号" in text
    assert "不能静默建案" in text
    assert checked.json()["conflict_level"] != "PROHIBITED"

    confirmed = _matter(
        client,
        title="证件号确认后建档",
        plaintiff_name="利冲委托人庚",
        defendant_name="毫无关系戊",
        defendant_id="110101199003074321",
        acknowledge_personnel_conflict=True,
    )
    assert confirmed.status_code == 200, confirmed.text
    assert "已确认" in confirmed.json()["message"]
    assert "不是静默建案" in confirmed.json()["message"]
    assert "证件号" in confirmed.json()["message"]


def test_one_character_difference_requires_confirmation(client):
    saved = client.post("/api/v1/vault/firm-roster", json={
        "lawyer_name": "阙承昭",
        "license_no": "13101202610111333",
        "law_firm": "利冲比对律师事务所",
    })
    assert saved.status_code == 200, saved.text

    preview = client.post("/api/v1/vault/personnel-screen", json={
        "client_role": "原告",
        "plaintiff_name": "利冲委托人辛",
        "defendant_name": "阙承招",
    })
    assert preview.status_code == 200, preview.text
    personnel = preview.json()["personnel"]
    assert personnel["status"] == "SIMILAR"
    assert "姓名相近，需人工核对" in personnel["personnel_and_relatives_check"]
    assert "禁止代理" not in personnel["personnel_and_relatives_check"]
    assert "禁止代理" not in personnel["block_message"]

    blocked = _matter(
        client,
        title="差一字需核对案",
        plaintiff_name="利冲委托人辛",
        defendant_name="阙承招",
    )
    assert blocked.status_code == 409, blocked.text
    assert "姓名相近，需人工核对" in blocked.json()["detail"]
    assert "未勾选书面确认前不能建案" in blocked.json()["detail"]
    assert "禁止代理" not in blocked.json()["detail"]
    _assert_not_created(client, "差一字需核对案")

    confirmed = _matter(
        client,
        title="差一字确认后建档",
        plaintiff_name="利冲委托人壬",
        defendant_name="阙承招",
        acknowledge_personnel_conflict=True,
    )
    assert confirmed.status_code == 200, confirmed.text
    body = confirmed.json()
    assert "姓名相近，需人工核对" in body["message"]
    assert body["conflict"]["conflict_level"] != "PROHIBITED"
    assert body["matter"]["practice"]["personnel_status"] == "SIMILAR"
    assert "禁止代理" not in body["message"]


def test_contained_name_requires_confirmation_not_prohibition(client):
    saved = client.post("/api/v1/vault/firm-roster", json={
        "lawyer_name": "阙承昭",
        "license_no": "13101202610111444",
        "law_firm": "利冲比对律师事务所",
    })
    assert saved.status_code == 200, saved.text
    blocked = _matter(
        client,
        title="姓名包含需核对案",
        plaintiff_name="利冲委托人癸",
        defendant_name="阙承昭二",
    )
    assert blocked.status_code == 409, blocked.text
    assert "姓名相近，需人工核对" in blocked.json()["detail"]
    assert "禁止代理" not in blocked.json()["detail"]
    _assert_not_created(client, "姓名包含需核对案")


def test_two_character_same_surname_does_not_alarm(client):
    saved = client.post("/api/v1/vault/firm-roster", json={
        "lawyer_name": "沈禾",
        "license_no": "13101202610111555",
        "law_firm": "利冲比对律师事务所",
    })
    assert saved.status_code == 200, saved.text
    created = _matter(
        client,
        title="二字同姓不误报案",
        plaintiff_name="利冲委托人子",
        defendant_name="沈木",
    )
    assert created.status_code == 200, created.text
    message = created.json()["message"]
    assert "已核对本所名册" in message
    assert "姓名相近" not in message
    assert "未确认前不能建案" not in message
    assert created.json()["matter"]["practice"]["personnel_status"] == "CHECKED"


def test_empty_roster_stays_unchecked(client):
    created = _matter(
        client,
        title="空名册仍未检查案",
        plaintiff_name="利冲委托人丑",
        defendant_name="利冲对方寅",
    )
    assert created.status_code == 200, created.text
    message = created.json()["message"]
    assert "本所人员未录入，此项未检查" in message
    assert "已排除冲突" not in message
    assert "已核对本所名册" not in message
    assert created.json()["matter"]["practice"]["personnel_status"] == "NOT_RECORDED"

    preview = client.post("/api/v1/vault/personnel-screen", json={
        "client_role": "原告",
        "plaintiff_name": "利冲委托人丑",
        "defendant_name": "利冲对方寅",
    })
    assert preview.status_code == 200, preview.text
    assert preview.json()["personnel"]["status"] == "NOT_RECORDED"
    assert "本所人员未录入，此项未检查" in preview.json()["personnel"]["personnel_and_relatives_check"]

    checked = client.post("/api/v1/conflict/check", json={
        "client_name": "利冲委托人丑",
        "opposing_party": "利冲对方寅",
        "is_same_matter": "否",
    })
    assert checked.status_code == 200, checked.text
    text = checked.json()["personnel_and_relatives_check"]
    assert "本所人员未录入，此项未检查" in text
    assert "本所人员及近亲属" in text
    assert "已排除冲突" not in text
