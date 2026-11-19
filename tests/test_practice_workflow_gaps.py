# -*- coding: utf-8 -*-
"""执业审查缺口：期限板、利冲闸门、并列请求、管辖、案由、期间和结案。"""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def no_ollama(monkeypatch):
    from gateway.core.ollama_client import ollama_client

    async def _offline(*args, **kwargs):
        return False

    monkeypatch.setattr(ollama_client, "_is_ollama_online", _offline)
    monkeypatch.setattr(ollama_client, "settings", {**ollama_client.settings, "provider": "ollama", "api_key": ""})
    return ollama_client


def _party():
    return {
        "name": "测试原告甲",
        "id_card_or_uscc": "110101199003072340",
        "address": "北京市朝阳区测试路1号",
        "phone": "13800000001",
    }


def _company():
    return {
        "name": "测试被告乙有限公司",
        "id_card_or_uscc": "91350100M000100Y43",
        "address": "福州市鼓楼区测试路2号",
        "phone": "13800000002",
        "party_type": "legal",
        "legal_rep": "王某某",
        "rep_position": "执行董事",
    }


def _create(client, **extra):
    payload = {
        "title": extra.pop("title", "缺口测试案件"),
        "cause_of_action": extra.pop("cause_of_action", "买卖合同纠纷"),
        "plaintiff_name": "测试原告甲",
        "defendant_name": "测试被告乙有限公司",
    }
    payload.update(extra)
    resp = client.post("/api/v1/vault/matters", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()["matter"]


def test_source_has_the_practice_fixes():
    intake = (ROOT / "frontend/js/modules/modals.js").read_text(encoding="utf-8")
    litigation = (ROOT / "frontend/js/modules/02_litigation.js").read_text(encoding="utf-8")
    matters = (ROOT / "frontend/js/modules/07_matters.js").read_text(encoding="utf-8")
    evidence = (ROOT / "frontend/js/modules/03_evidence.js").read_text(encoding="utf-8")
    index = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
    calc = (ROOT / "frontend/js/modules/01_calc.js").read_text(encoding="utf-8")
    assert "new-matter-hourly-rate" not in intake
    assert "new-matter-fee-amount" not in intake
    assert "请选择文书类型，不要默认民间借贷" in litigation
    assert "不会按民间借贷生成" in litigation
    assert "getElementById('pkg-notes')" in matters
    assert "getElementById('pkg-facts')" not in matters
    assert "today-deadlines-board" in index
    assert "id=\"ev-thick-file-tools\"" in evidence
    assert "id=\"ev-cross-track\"" in evidence
    assert "labor_arbitration_1y" in calc
    assert "notice_due_date" in calc
    assert "不要按六个月" in calc


def test_deadline_board_groups_urgent_first(client):
    soon = _create(client, title="临期货款案")
    later = _create(client, title="远期货款案")
    client.post("/api/v1/vault/deadlines", json={
        "matter_id": later["matter_id"], "kind": "appeal", "due_date": "2027-06-01", "origin": "statutory_calc",
    })
    client.post("/api/v1/vault/deadlines", json={
        "matter_id": soon["matter_id"], "kind": "labor_award_sue", "due_date": "2026-11-01", "origin": "statutory_calc",
    })
    board = client.get("/api/v1/vault/deadlines/board")
    assert board.status_code == 200, board.text
    titles = [group["matter_title"] for group in board.json()["groups"]]
    assert titles.index("临期货款案") < titles.index("远期货款案")
    urgent = next(group for group in board.json()["groups"] if group["matter_title"] == "临期货款案")
    assert urgent["urgent"] is True


def test_conflict_blocks_draft_filing_and_workflow_until_conclusion(client, no_ollama):
    matter = _create(client, title="利冲未结论案", cause_of_action="买卖合同纠纷")
    from gateway.utils.matter_vault_db import save_matter_practice
    save_matter_practice(matter["matter_id"], {"conflict": {"conflict_level": "MANUAL_REVIEW", "status_label": "需人工判断"}})
    generated = client.post("/api/v1/phase1/generate-litigation-package", json={
        "cause_of_action": "买卖合同纠纷",
        "matter_id": matter["matter_id"],
        "plaintiff": _party(),
        "defendant": _company(),
        "claims": ["判令被告支付货款 1000 元"],
        "claim_amount": 1000,
        "raw_case_notes": "2024年1月1日交货，货款未付。",
        "court_name": "北京市朝阳区人民法院",
        "auto_generate_sub_docs": False,
    })
    assert generated.status_code == 409, generated.text
    filed = client.patch(f"/api/v1/vault/matters/{matter['matter_id']}/ledger", json={
        "filing_checklist": [{"key": "complaint", "status": "已线下提交"}],
    })
    assert filed.status_code == 422, filed.text
    started = client.post("/api/v1/vault/workflows/start", json={
        "matter_id": matter["matter_id"],
        "facts_text": "货款未付。",
    })
    assert started.status_code == 409, started.text
    concluded = client.post(f"/api/v1/vault/matters/{matter['matter_id']}/practice-desk", json={
        "conflict_conclusion": {"decision": "可以代理", "text": "核对底档后不是同一争议，可以代理。", "written_consent": False},
    })
    assert concluded.status_code == 200, concluded.text
    started_again = client.post("/api/v1/vault/workflows/start", json={
        "matter_id": matter["matter_id"],
        "facts_text": "2024年1月交货，货款未付。",
    })
    assert started_again.status_code == 200, started_again.text


def test_parallel_claims_and_jurisdiction_paths(client, no_ollama):
    from gateway.utils.practice_workflow import recommend_jurisdiction, suggest_claim_tracks
    mixed = "用人单位违法解除劳动合同，同时拖欠货款。另有名誉侵权。"
    tracks = suggest_claim_tracks(mixed)
    assert len(tracks) > 1
    causes = {item["cause"] for item in tracks}
    assert "劳动争议" in causes
    assert "买卖合同纠纷" in causes
    assert "名誉权纠纷" in causes
    clause = recommend_jurisdiction("合同约定提交北京仲裁委员会仲裁。")
    assert clause["tracks"][0]["blocks_court"] is True
    defective = recommend_jurisdiction("合同约定提交北京仲裁委员会仲裁，也可以向人民法院起诉。")
    assert defective["tracks"][0]["blocks_court"] is False
    assert defective["tracks"][0]["track"] != "commercial_arbitration"
    exclusive = recommend_jurisdiction("争议房屋属于不动产。")
    assert any(item.get("exclusive") for item in exclusive["tracks"])
    matter = _create(client, title="并列请求案", cause_of_action="买卖合同纠纷")
    saved = client.post(f"/api/v1/vault/matters/{matter['matter_id']}/practice-desk", json={
        "claims": [
            {"cause": "买卖合同纠纷", "track": "civil_court", "forum": "被告住所地人民法院"},
            {"cause": "劳动争议", "track": "labor_arbitration", "forum": "劳动人事争议仲裁委员会"},
        ],
        "extra_parties": [{"role": "共同被告", "name": "丙"}],
        "defendant_posture": {"jurisdiction_objection": {"prepared": True, "basis": "仲裁条款"}, "counterclaim": {"prepared": True, "claims": "反请求质量款"}},
        "jurisdiction_facts": mixed,
    })
    assert saved.status_code == 200, saved.text
    practice = saved.json()["matter"]["practice"]
    assert practice["jurisdiction"]["must_split"] is True
    assert len(practice["claims"]) == 2
    assert practice["extra_parties"][0]["role"] == "共同被告"
    bad_role = client.post(f"/api/v1/vault/matters/{matter['matter_id']}/practice-desk", json={
        "extra_parties": [{"role": "案外人", "name": "丁"}],
    })
    assert bad_role.status_code == 422
    started = client.post("/api/v1/vault/workflows/start", json={
        "matter_id": matter["matter_id"],
        "facts_text": mixed,
    })
    assert started.status_code == 200, started.text
    assert started.json()["step_data"]["step1"]["must_split"] is True


def test_generate_refuses_placeholder_unknown_and_wrong_forum(client, no_ollama):
    empty = client.post("/api/v1/phase1/generate-litigation-package", json={
        "cause_of_action": "",
        "plaintiff": _party(),
        "defendant": _company(),
        "raw_case_notes": "事实。",
        "court_name": "北京市朝阳区人民法院",
    })
    assert empty.status_code == 422
    assert "民间借贷" in empty.text
    placeholder = client.post("/api/v1/phase1/generate-litigation-package", json={
        "cause_of_action": "请选择文书类型",
        "plaintiff": _party(),
        "defendant": _company(),
        "raw_case_notes": "事实。",
        "court_name": "北京市朝阳区人民法院",
    })
    assert placeholder.status_code == 422
    unknown = client.post("/api/v1/phase1/generate-litigation-package", json={
        "cause_of_action": "星际采矿纠纷",
        "plaintiff": _party(),
        "defendant": _company(),
        "claims": ["请求停止开采"],
        "claim_amount": 1000,
        "raw_case_notes": "2024年1月1日发生争议。",
        "court_name": "北京市朝阳区人民法院",
        "auto_generate_sub_docs": False,
    })
    assert unknown.status_code == 422
    assert "不会按民间借贷" in unknown.text
    matter = _create(client, cause_of_action="买卖合同纠纷")
    mismatch = client.post("/api/v1/phase1/generate-litigation-package", json={
        "cause_of_action": "名誉权纠纷",
        "matter_id": matter["matter_id"],
        "plaintiff": _party(),
        "defendant": _company(),
        "claims": ["请求赔礼道歉"],
        "claim_amount": 1000,
        "raw_case_notes": "2024年1月1日发表文章。",
        "court_name": "北京市朝阳区人民法院",
        "auto_generate_sub_docs": False,
    })
    assert mismatch.status_code == 422
    forum = client.post("/api/v1/phase1/generate-litigation-package", json={
        "cause_of_action": "买卖合同纠纷",
        "matter_id": matter["matter_id"],
        "plaintiff": _party(),
        "defendant": _company(),
        "claims": ["判令被告支付货款 1000 元"],
        "claim_amount": 1000,
        "raw_case_notes": "2024年1月1日交货。",
        "court_name": "北京市朝阳区人民法院",
        "auto_generate_sub_docs": False,
    })
    assert forum.status_code == 422
    assert "受理机关" in forum.text


def test_reputation_uses_generic_and_finance_loan_is_not_private_lending(client, no_ollama):
    reputation = client.post("/api/v1/phase1/generate-litigation-package", json={
        "cause_of_action": "名誉权纠纷",
        "plaintiff": _party(),
        "defendant": _company(),
        "claims": ["判令被告赔礼道歉"],
        "claim_amount": 1000,
        "raw_case_notes": "2024年3月1日被告发表不实文章。",
        "court_name": "北京市朝阳区人民法院",
        "auto_generate_sub_docs": False,
    })
    assert reputation.status_code == 200, reputation.text
    assert "民间借贷" not in Path(reputation.json()["main_docx_path"]).name
    finance = client.post("/api/v1/phase1/generate-litigation-package", json={
        "cause_of_action": "金融借款合同纠纷",
        "plaintiff": _party(),
        "defendant": _company(),
        "claims": ["判令被告偿还借款 1000 元"],
        "claim_amount": 1000,
        "raw_case_notes": "2024年3月1日发放贷款，约定年利率 8%。",
        "court_name": "北京市朝阳区人民法院",
        "auto_generate_sub_docs": False,
    })
    assert finance.status_code == 200, finance.text
    assert "民间借贷" not in Path(finance.json()["main_docx_path"]).name


def test_labor_package_and_commercial_arbitration_do_not_use_court_complaint(client, no_ollama):
    labor = client.post("/api/v1/phase1/generate-litigation-package", json={
        "cause_of_action": "劳动人事争议",
        "plaintiff": _party(),
        "defendant": _company(),
        "claims": ["裁决被申请人支付劳动报酬 1000 元"],
        "claim_amount": 1000,
        "raw_case_notes": "2024年1月1日入职，2025年1月1日解除。",
        "court_name": "北京市朝阳区",
        "auto_generate_sub_docs": False,
    })
    assert labor.status_code == 200, labor.text
    body = labor.json()
    assert body["filing_route"] == "labor_arbitration"
    assert body["recommended_archive_format"] == "flat"
    assert body["micro_court_package"] is False
    assert "仲裁申请书" in Path(body["main_docx_path"]).name
    blocked = client.post("/api/v1/phase1/generate-litigation-package", json={
        "cause_of_action": "买卖合同纠纷",
        "procedure": "arbitration",
        "plaintiff": _party(),
        "defendant": _company(),
        "claims": ["请求支付货款"],
        "claim_amount": 1000,
        "raw_case_notes": "合同约定仲裁。",
        "court_name": "北京市朝阳区人民法院",
        "auto_generate_sub_docs": False,
    })
    assert blocked.status_code == 422
    assert "不能生成法院起诉状" in blocked.text
    created = _create(client, title="商事仲裁案", cause_of_action="买卖合同纠纷", procedure="arbitration")
    labels = [item["label"] for item in created["practice"]["local_filing_items"]]
    assert "仲裁申请书" in labels
    assert created["practice"]["filing_route"] == "arbitration"


def test_periods_labor_award_set_aside_and_notice(client):
    open_ended = client.post("/api/v1/phase1/calc/statute-limitations", json={
        "start_date": "2024-01-01",
        "cause_type": "labor_arbitration_1y",
        "employment_ongoing": True,
        "wage_arrears": True,
        "today_date": "2026-11-11",
    })
    assert open_ended.status_code == 200, open_ended.text
    assert open_ended.json()["open_ended"] is True
    assert open_ended.json()["final_expire_date"] is None
    assert "三年" not in open_ended.json()["rule_name"]
    after_end = client.post("/api/v1/phase1/calc/statute-limitations", json={
        "start_date": "2022-01-01",
        "cause_type": "labor_arbitration_1y",
        "wage_arrears": True,
        "employment_end_date": "2025-12-31",
        "today_date": "2026-01-15",
    })
    assert after_end.status_code == 200, after_end.text
    assert after_end.json()["final_expire_date"].startswith("2026-")
    restarted = client.post("/api/v1/phase1/calc/statute-limitations", json={
        "start_date": "2020-01-01",
        "cause_type": "labor_arbitration_1y",
        "interruption_events": [{"date": "2026-02-02", "description": "催告"}],
        "today_date": "2026-03-01",
    })
    assert restarted.json()["final_expire_date"].startswith("2027-")
    worker = client.post("/api/v1/phase1/calc/labor-award-deadline", json={"receipt_date": "2026-03-02", "path": "worker_final_15"})
    either = client.post("/api/v1/phase1/calc/labor-award-deadline", json={"receipt_date": "2026-03-02", "path": "either_party_nonfinal_15"})
    employer = client.post("/api/v1/phase1/calc/labor-award-deadline", json={"receipt_date": "2026-03-02", "path": "employer_revoke_30"})
    assert worker.json()["deadline"] == either.json()["deadline"]
    assert employer.json()["deadline"] > worker.json()["deadline"]
    assert "用人单位不能" in "".join(worker.json()["notes"])
    assert "不是十五日" in "".join(employer.json()["notes"])
    set_aside = client.post("/api/v1/phase1/calc/arbitration-set-aside", json={"receipt_date": "2026-01-15"})
    assert set_aside.status_code == 200, set_aside.text
    payload = set_aside.json()
    assert payload["deadline"].startswith("2026-04-")
    assert "三个月" in payload["period_label"]
    assert "第七十二条" in payload["legal_basis"]
    assert "六个月" not in payload["period_label"]
    joined = "".join(payload.get("notes") or []) + "".join(payload.get("warnings") or [])
    assert "不要按" in joined and "六个月" in joined
    notice = client.post("/api/v1/phase1/calc/evidence-period", json={
        "anchor_date": "2026-11-14",
        "mode": "notice_due_date",
    })
    assert notice.status_code == 200, notice.text
    assert notice.json()["deadline"] == "2026-11-14"
    assert notice.json()["extended_for_holiday_or_weekend"] is False


def test_archive_closeout_catalog_and_local_item(client):
    catalog = client.get("/api/v1/vault/cause-catalog")
    assert catalog.status_code == 200
    causes = [item["cause"] for item in catalog.json()["catalog"]]
    assert "金融借款合同纠纷" in causes
    assert "民间借贷纠纷" in causes
    matter = _create(client, title="结案闸门案")
    missing = client.patch(f"/api/v1/vault/matters/{matter['matter_id']}/status", json={"status": "archived"})
    assert missing.status_code == 422
    assert "裁判" in missing.text
    fee = client.patch(f"/api/v1/vault/matters/{matter['matter_id']}/ledger", json={
        "fee_amount": 1000,
        "fee_received": 0,
        "local_filing_items": [{"label": "某中院送达确认附表", "status": "未准备"}],
    })
    assert fee.status_code == 200, fee.text
    assert fee.json()["matter"]["practice"]["local_filing_items"][0]["label"] == "某中院送达确认附表"
    unpaid = client.patch(f"/api/v1/vault/matters/{matter['matter_id']}/status", json={
        "status": "archived",
        "closeout": {
            "judgment_result": "判决支付货款",
            "appeal_window_cleared": True,
            "originals_returned": True,
            "fees_settled": True,
            "conflict_closed_on": "2026-11-11",
        },
    })
    assert unpaid.status_code == 422
    assert "律师费" in unpaid.text
    accepted = client.patch(f"/api/v1/vault/matters/{matter['matter_id']}/ledger", json={
        "local_filing_items": [{"label": "某中院送达确认附表", "status": "已受理"}],
    })
    assert accepted.status_code == 422
    done = client.patch(f"/api/v1/vault/matters/{matter['matter_id']}/status", json={
        "status": "archived",
        "closeout": {
            "judgment_result": "判决支付货款",
            "appeal_window_cleared": True,
            "originals_returned": True,
            "fees_settled": True,
            "fees_note": "剩余律师费已书面减免",
            "conflict_closed_on": "2026-11-11",
        },
    })
    assert done.status_code == 200, done.text


def test_cross_exam_labor_burden(client, no_ollama):
    resp = client.post("/api/v1/phase2/cross-examination", json={
        "evidence_name": "解除通知",
        "evidence_category": "书证",
        "opponent_purpose": "证明解除合法",
        "client_facts": "没有书面通知，也没有公示规章制度。",
        "cause_of_action": "劳动争议",
        "track": "labor",
    })
    assert resp.status_code == 200, resp.text
    items = "".join(resp.json()["burden"]["items"])
    assert resp.json()["burden"]["mode"] == "labor_employer"
    assert "用人单位" in items
    assert "第六条" in items
