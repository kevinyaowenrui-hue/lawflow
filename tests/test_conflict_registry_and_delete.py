# -*- coding: utf-8 -*-
"""利冲底档空库、建案入底档、删除文案与证件号抹去。"""
from __future__ import annotations

import json


def _party_payload(**overrides):
    payload = {
        "title": "底档同步买卖合同案",
        "cause_of_action": "买卖合同纠纷",
        "client_role": "原告",
        "plaintiff_name": "底档同步委托人甲辰",
        "defendant_name": "底档同步相对人乙巳",
        "plaintiff_id": "110101199001011234",
        "plaintiff_phone": "13800001111",
        "defendant_id": "110101199202021111",
        "defendant_phone": "13900002222",
        "is_same_matter": "是",
    }
    payload.update(overrides)
    return payload


def test_empty_registry_does_not_issue_certificate(client):
    from gateway.utils.conflict_checker import get_db_connection

    with get_db_connection() as conn:
        conn.execute("DELETE FROM conflict_case_registry")

    resp = client.post(
        "/api/v1/conflict/check",
        json={"client_name": "空底档委托人", "opposing_party": "空底档相对人"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    blob = json.dumps(data, ensure_ascii=False)
    assert data["status_label"] == "未比对到已登记记录"
    assert data["has_conflict"] is None
    assert data["clearance_certificate"]["is_cleared"] is False
    assert data["clearance_certificate"]["certificate_no"] in ("", None)
    assert not data["clearance_certificate"].get("sha256_fingerprint")
    assert "第四十二条" not in blob
    assert "2026 修正" not in blob
    assert "《律师法》（2017年修正文本）第三十九条" in blob
    assert "诉讼归档留底有效" not in blob
    for item in (
        "刑事案件被害人代理与辩护",
        "分所及品牌关联所",
        "本所人员近亲属以外的其他任职",
    ):
        assert item in data["not_checked"]
        assert item in blob
    assert "本所人员未录入" in data["personnel_and_relatives_check"]
    assert data["registered_record_count"] == 0


def test_recorded_miss_has_no_clearance_certificate(client):
    resp = client.post(
        "/api/v1/conflict/check",
        json={
            "client_name": "未命中委托人戊午",
            "opposing_party": "未命中相对人己未",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    blob = json.dumps(data, ensure_ascii=False)
    assert data["registered_record_count"] >= 1
    assert data["status_label"] == f"在已登记的 {data['registered_record_count']} 条记录中未发现冲突"
    assert data["clearance_certificate"]["is_cleared"] is False
    assert not data["clearance_certificate"].get("certificate_no")
    assert "第四十二条" not in blob
    assert "项次待核对" in blob
    assert all(item.get("rule_verified") is not True for item in data.get("conflict_items") or [])


def test_hit_does_not_mark_unverified_conduct_items(client):
    resp = client.post(
        "/api/v1/conflict/check",
        json={
            "client_name": "华腾物流网络技术有限公司",
            "opposing_party": "智科云服信息技术（北京）有限公司",
            "is_same_matter": "是",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    blob = json.dumps(data, ensure_ascii=False)
    assert data["conflict_level"] == "PROHIBITED"
    assert data["conflict_items"]
    for item in data["conflict_items"]:
        assert item["rule_verified"] is False
        assert "项次待核对" in item["rule_basis"]
        assert "第五十一" not in item["rule_basis"]
        assert "第五十二" not in item["rule_basis"]
    assert "《律师法》（2017年修正文本）第三十九条" in blob
    assert "第四十二条" not in blob

    closed = client.post(
        "/api/v1/conflict/check",
        json={
            "client_name": "北京宏远实业开发有限公司",
            "opposing_party": "中建天成建设工程集团有限公司",
            "is_same_matter": "否",
            "check_date": "2026-10-24",
        },
    )
    assert closed.status_code == 200, closed.text
    closed_data = closed.json()
    closed_blob = json.dumps(closed_data, ensure_ascii=False)
    assert closed_data["conflict_level"] == "MANUAL_REVIEW"
    assert "《律师法》（2017年修正文本）第三十八条" in closed_blob
    assert "第四十一条" not in closed_blob
    assert all(item["rule_verified"] is False for item in closed_data["conflict_items"])


def test_create_matter_writes_parties_into_conflict_registry(client):
    created = client.post("/api/v1/vault/matters", json=_party_payload())
    assert created.status_code == 200, created.text
    matter_id = created.json()["matter"]["matter_id"]

    listed = client.get("/api/v1/conflict/registry")
    assert listed.status_code == 200, listed.text
    row = next(item for item in listed.json()["registry"] if item["case_id"] == matter_id)
    assert row["client_name"] == "底档同步委托人甲辰"
    assert row["opposing_name"] == "底档同步相对人乙巳"
    assert row["client_uscc_id"] == "110101199001011234"

    switched = client.post(
        "/api/v1/conflict/check",
        json={
            "client_name": "底档同步相对人乙巳",
            "opposing_party": "底档同步委托人甲辰",
            "is_same_matter": "是",
        },
    )
    assert switched.status_code == 200, switched.text
    assert switched.json()["conflict_level"] == "PROHIBITED"

    updated = client.put(
        f"/api/v1/vault/matters/{matter_id}",
        json={"defendant_name": "底档同步改后相对人丙午"},
    )
    assert updated.status_code == 200, updated.text
    listed_again = client.get("/api/v1/conflict/registry")
    row = next(item for item in listed_again.json()["registry"] if item["case_id"] == matter_id)
    assert row["client_name"] == "底档同步委托人甲辰"
    assert row["opposing_name"] == "底档同步改后相对人丙午"

    old_name = client.post(
        "/api/v1/conflict/check",
        json={
            "client_name": "底档同步相对人乙巳",
            "opposing_party": "与本案无关的第三方庚申",
            "is_same_matter": "是",
        },
    )
    assert old_name.status_code == 200, old_name.text
    assert old_name.json()["conflict_level"] != "PROHIBITED"
    matched_ids = {item.get("matched_case_id") for item in old_name.json().get("conflict_items") or []}
    assert matter_id not in matched_ids

    renamed = client.post(
        "/api/v1/conflict/check",
        json={
            "client_name": "底档同步改后相对人丙午",
            "opposing_party": "底档同步委托人甲辰",
            "is_same_matter": "是",
        },
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["conflict_level"] == "PROHIBITED"


def test_delete_keeps_identifiers_until_explicit_scrub(client):
    from gateway.utils.matter_vault_db import get_matter_by_id

    kept = client.post(
        "/api/v1/vault/matters",
        json=_party_payload(title="默删保留证件号案", plaintiff_name="默删委托人甲", defendant_name="默删相对人乙"),
    )
    assert kept.status_code == 200, kept.text
    kept_id = kept.json()["matter"]["matter_id"]
    deleted = client.delete(f"/api/v1/vault/matters/{kept_id}?confirm=true")
    assert deleted.status_code == 200, deleted.text
    message = deleted.json()["message"]
    assert "原件已删，案件索引和证件号仍保留" in message
    assert "物理删除" not in message
    assert deleted.json()["identifiers_retained"] is True
    stored = get_matter_by_id(kept_id, include_deleted=True)
    assert stored["status"] == "deleted"
    assert stored["plaintiff_info"]["id_no"] == "110101199001011234"
    assert stored["plaintiff_info"]["phone"] == "13800001111"
    assert stored["defendant_info"]["id_no"] == "110101199202021111"

    scrubbed = client.post(
        "/api/v1/vault/matters",
        json=_party_payload(
            title="抹去证件号案",
            plaintiff_name="抹去委托人甲辰",
            defendant_name="抹去相对人乙巳",
        ),
    )
    assert scrubbed.status_code == 200, scrubbed.text
    scrub_id = scrubbed.json()["matter"]["matter_id"]
    wiped = client.delete(f"/api/v1/vault/matters/{scrub_id}?confirm=true&scrub_identifiers=true")
    assert wiped.status_code == 200, wiped.text
    wiped_message = wiped.json()["message"]
    assert "物理删除" not in wiped_message
    assert "连同证件号从案件行抹去" in wiped_message
    assert "利冲底档仍保留当事人姓名" in wiped_message
    assert "抹去委托人甲辰" in wiped_message
    row = get_matter_by_id(scrub_id, include_deleted=True)
    party_blob = json.dumps(
        {"plaintiff_info": row["plaintiff_info"], "defendant_info": row["defendant_info"]},
        ensure_ascii=False,
    )
    assert "110101199001011234" not in party_blob
    assert "13800001111" not in party_blob
    assert "110101199202021111" not in party_blob
    assert "13900002222" not in party_blob
    assert row["plaintiff_info"].get("name") == "抹去委托人甲辰"
    assert row["defendant_info"].get("name") == "抹去相对人乙巳"
    assert "id_no" not in row["plaintiff_info"]
    assert "phone" not in row["plaintiff_info"]

    listed = client.get("/api/v1/conflict/registry")
    registry_row = next(item for item in listed.json()["registry"] if item["case_id"] == scrub_id)
    assert registry_row["client_name"] == "抹去委托人甲辰"
    assert registry_row["opposing_name"] == "抹去相对人乙巳"
    assert not registry_row.get("client_uscc_id")
    assert not registry_row.get("opposing_uscc_id")


def test_delete_matter_ui_explains_retention_and_confirms_scrub():
    """前端删除确认写明默认保留证件号；抹去动作确认后才带 scrub_identifiers。"""
    from pathlib import Path

    text = (Path(__file__).resolve().parents[1] / "frontend/js/modules/07_matters.js").read_text(encoding="utf-8")
    start = text.index("async function deleteMatterUI")
    end = text.index("async function exportReviewTableXlsxUI")
    fn = text[start:end]
    assert "已物理删除" not in fn
    assert "物理删除" not in fn
    assert "默认只删原件，案件索引和证件号仍保留" in fn
    assert "证件号和电话会从案件行清掉" in fn
    assert "姓名仍会留在利冲底档里" in fn
    assert "scrubIdentifiers === true" in fn
    assert "if (!confirm(prompt)) return;" in fn
    assert fn.index("if (!confirm(prompt)) return;") < fn.index("scrub_identifiers=true")
    assert "confirm=true&scrub_identifiers=true" in fn
    assert ": 'confirm=true'" in fn
    assert "showMatterDeleteNotice" in fn
    assert "res.message" in fn
    assert "showToast(res.message" not in fn
    assert "setTimeout" not in fn
    assert "连同证件号从案件行抹去" in text
    assert "点「连同证件号从案件行抹去」之前：证件号和电话会从案件行清掉，姓名仍会留在利冲底档里。" in text
    assert "vault-matter-delete-hint" in text
    assert "vault-matter-delete-notice" in text
    assert """onclick="deleteMatterUI('${escapeHtml(m.matter_id)}', '${escapeHtml(m.title)}')" """.strip() in text
    assert """onclick="deleteMatterUI('${escapeHtml(m.matter_id)}', '${escapeHtml(m.title)}', true)" """ in text
    assert "未选择案件" in text
    assert "describeCaseOverwrites" in text
    assert "CALC_SYNC_EMPTY_MESSAGE" in text
    render_start = text.index("function renderWorkflowStepUI")
    render_end = text.index("async function advanceWorkflowStep2UI")
    render_block = text[render_start:render_end]
    for name in ("wf-claim-item", "wf-statute-item", "wf-counter-item"):
        input_at = render_block.index(f'name="{name}"')
        input_tag = render_block[input_at:render_block.index(">", input_at)]
        assert "checked" not in input_tag, name
