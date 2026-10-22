# -*- coding: utf-8 -*-
"""
tests/test_matter_lifecycle.py
验收标准：
- 案件状态流转：归档 (active -> archived)、恢复 (archived -> active)、draft -> active
- 非法流转 422
- 软删除：DELETE /api/v1/vault/matters/{matter_id}?confirm=true 后默认列表不含该案件
- 期限日历：POST /api/v1/vault/deadlines -> GET /api/v1/vault/deadlines 能查到且 due_date 一致
- 任务截止时间结构化校验：tasks due_date="下周三" -> 422
- README 含"当前不支持"段落
"""
from __future__ import annotations

from pathlib import Path
import pytest
from fastapi.testclient import TestClient

AUTH = {"X-LawFlow-Token": "test-token"}
ROOT = Path(__file__).resolve().parents[1]


def test_matter_lifecycle_and_status_transitions(tmp_path):
    from gateway.main import app
    from gateway.utils.matter_vault_db import create_new_matter

    # 1. 创建案件（默认 active）
    m = create_new_matter({
        "title": "生命周期测试案件",
        "cause_of_action": "买卖合同纠纷",
        "status": "active"
    })
    mid = m["matter_id"]

    with TestClient(app, headers=AUTH) as client:
        # active -> archived
        r1 = client.patch(f"/api/v1/vault/matters/{mid}/status", json={"status": "archived"})
        assert r1.status_code == 200, r1.text
        assert r1.json()["matter"]["status"] == "archived"

        # archived -> active
        r2 = client.patch(f"/api/v1/vault/matters/{mid}/status", json={"status": "active"})
        assert r2.status_code == 200, r2.text
        assert r2.json()["matter"]["status"] == "active"

        # 非法流转 -> 422 (例如 active -> draft 或非法状态)
        r3 = client.patch(f"/api/v1/vault/matters/{mid}/status", json={"status": "draft"})
        assert r3.status_code == 422, r3.text

        r3b = client.patch(f"/api/v1/vault/matters/{mid}/status", json={"status": "invalid_status"})
        assert r3b.status_code == 422, r3b.text

        # 软删除：未传 confirm=true 应拒绝
        r_del_no_confirm = client.delete(f"/api/v1/vault/matters/{mid}")
        assert r_del_no_confirm.status_code in (400, 422)

        # 软删除：传 confirm=true
        r_del = client.delete(f"/api/v1/vault/matters/{mid}?confirm=true")
        assert r_del.status_code == 200, r_del.text

        # 软删除后默认列表不显示该案件
        r_list = client.get("/api/v1/vault/matters")
        assert r_list.status_code == 200
        matters = r_list.json().get("matters", [])
        mids = [item["matter_id"] for item in matters]
        assert mid not in mids, f"软删除后默认列表不应包含 {mid}"


def test_deadlines_calendar_and_calculator_integration(tmp_path):
    from gateway.main import app
    from gateway.utils.matter_vault_db import create_new_matter

    m = create_new_matter({
        "title": "期限测试案件",
        "cause_of_action": "民间借贷纠纷",
    })
    mid = m["matter_id"]

    with TestClient(app, headers=AUTH) as client:
        # 1. 模拟上诉期计算后加入案件期限
        dl_payload = {
            "matter_id": mid,
            "kind": "appeal",
            "due_date": "2026-11-05",
            "source": "上诉期计算器（民事一审判决送达之日起15日）",
            "note": "注意末日顺延至工作日"
        }
        r_add = client.post("/api/v1/vault/deadlines", json=dl_payload)
        assert r_add.status_code == 200, r_add.text
        dl_data = r_add.json()
        assert dl_data["status"] == "success"

        # 2. 查询期限列表 GET /api/v1/vault/deadlines
        r_get = client.get(f"/api/v1/vault/deadlines?from=2026-11-01&to=2026-11-30")
        assert r_get.status_code == 200, r_get.text
        deadlines = r_get.json().get("deadlines", [])
        assert len(deadlines) >= 1
        found = next((d for d in deadlines if d.get("matter_id") == mid), None)
        assert found is not None
        assert found["due_date"] == "2026-11-05"
        assert found["kind"] == "appeal"


def test_task_due_date_iso_validation(tmp_path):
    from gateway.main import app

    with TestClient(app, headers=AUTH) as client:
        # tasks due_date="下周三" -> 422
        bad_task = {
            "title": "非法日期任务",
            "due_date": "下周三",
            "priority": "medium",
            "stage": "立案"
        }
        r_bad = client.post("/api/v1/copilot/tasks", json=bad_task)
        assert r_bad.status_code == 422, f"tasks due_date='下周三' 必须返回 422，实际返回 {r_bad.status_code}"

        # 正确 ISO 日期
        good_task = {
            "title": "合法日期任务",
            "due_date": "2026-10-30",
            "priority": "high",
            "stage": "证据"
        }
        r_good = client.post("/api/v1/copilot/tasks", json=good_task)
        assert r_good.status_code in (200, 201), r_good.text


def test_readme_unsupported_section():
    readme_path = ROOT / "README.md"
    assert readme_path.exists(), "README.md must exist"
    readme_text = readme_path.read_text(encoding="utf-8")

    # README 增加"当前不支持"段落：计费工时、多人协作与权限、文书审批与用印、企业法务合同台账与审批流、外聘律所管理
    assert "当前不支持" in readme_text or "暂不支持" in readme_text
    required_keywords = ["计费工时", "多人协作与权限", "文书审批与用印", "企业法务合同台账与审批流", "外聘律所管理"]
    for kw in required_keywords:
        assert kw in readme_text, f"README.md 中必须包含不支持项 '{kw}'"
