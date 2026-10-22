"""
LawFlow 智律工作台 - 智能办案任务中枢与对话持久化引擎 (Agent Task & Dialogue DB Engine)
功能：
1. 办案任务矩阵 (agent_tasks) 持久化：支持优先级、办案阶段、截止日期、绑定模块动作与执行载荷
2. 语音/文本多轮对话 (agent_dialogues) 流水记录：记录用户指令与 AI 播报文本及执行快照
3. 支持与 Matter Vault 案件空间无缝贯通，按案件隔离或全局统一汇聚
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, Iterator, List, Optional

from gateway.core.db import connect
from gateway.core.paths import get_vault_db_path


@contextmanager
def get_db_connection() -> Iterator[sqlite3.Connection]:
    with connect(get_vault_db_path(), row_factory=sqlite3.Row) as conn:
        yield conn


def _should_seed_demo() -> bool:
    return os.environ.get("LAWFLOW_SEED_DEMO", "").strip() in ("1", "true", "True", "yes", "YES")


def init_agent_task_db():
    """初始化任务看板表与对话记录表；演示任务仅在 LAWFLOW_SEED_DEMO 时写入。"""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_tasks (
            task_id TEXT PRIMARY KEY,
            matter_id TEXT DEFAULT 'default',
            title TEXT NOT NULL,
            description TEXT,
            stage TEXT DEFAULT '立案',
            priority TEXT DEFAULT 'medium',
            status TEXT DEFAULT 'todo',
            due_date TEXT,
            linked_module TEXT,
            action_payload TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_dialogues (
            dialogue_id TEXT PRIMARY KEY,
            matter_id TEXT DEFAULT 'default',
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            speech_text TEXT,
            action_summary TEXT,
            created_at TEXT NOT NULL
        );
        """)

        # 迁移自由文本 due_date：非 ISO 日期保留在 description/note 中并把 due_date 置空
        cursor.execute("SELECT task_id, due_date, description FROM agent_tasks WHERE due_date IS NOT NULL AND due_date != ''")
        rows = cursor.fetchall()
        iso_pattern = re.compile(r'^\d{4}-\d{2}-\d{2}(?:[T\s]\d{2}:\d{2}(?::\d{2})?)?$')
        for r in rows:
            ddate = r["due_date"]
            if not iso_pattern.match(ddate):
                tid = r["task_id"]
                desc = r["description"] or ""
                new_desc = f"{desc} [原截止时间: {ddate}]".strip() if desc else f"[原截止时间: {ddate}]"
                cursor.execute("UPDATE agent_tasks SET due_date = NULL, description = ? WHERE task_id = ?", (new_desc, tid))
        conn.commit()

    if _should_seed_demo():
        seed_demo_agent_tasks()


def seed_demo_agent_tasks() -> int:
    """写入带【演示】前缀的种子任务；库非空则跳过。返回新写入条数。"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM agent_tasks")
        row = cursor.fetchone()
        if row and row["cnt"] > 0:
            return 0

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        seed_tasks = [
            (
                f"task_seed_{uuid.uuid4().hex[:8]}", "default",
                "【演示】在 02 模块生成起诉状、保全申请书与委托手续全套公文",
                "【演示】案由为民间借贷纠纷示意。细节 TODO(律师核实)。",
                "立案", "high", "in_progress", "2026-10-22 18:00:00", "phase1_litigation",
                json.dumps({"target_tab": "tab-litigation"}), now_str, now_str
            ),
            (
                f"task_seed_{uuid.uuid4().hex[:8]}", "default",
                "【演示】核算逾期 LPR 利息并锁定证据链",
                "【演示】按一年期 LPR 示意计算。细节 TODO(律师核实)。",
                "精算", "high", "done", "2026-10-21 17:00:00", "phase1_calc",
                json.dumps({"target_tab": "tab-calc"}), now_str, now_str
            ),
            (
                f"task_seed_{uuid.uuid4().hex[:8]}", "default",
                "【演示】清洗借条与网银电子转账凭证并生成带三性核验的证据清单",
                "【演示】核对转账回单示意。细节 TODO(律师核实)。",
                "证据", "medium", "todo", "2026-10-23 12:00:00", "phase2_evidence",
                json.dumps({"target_tab": "tab-evidence"}), now_str, now_str
            ),
            (
                f"task_seed_{uuid.uuid4().hex[:8]}", "default",
                "【演示】穿透检索《民法典》第667条及民间借贷司法解释关于借期利息口径",
                "【演示】排查约定利息与逾期利息口径示意。细节 TODO(律师核实)。",
                "检索", "medium", "todo", "2026-10-25 23:59:59", "phase5_statutes",
                json.dumps({"target_tab": "tab-statutes"}), now_str, now_str
            ),
            (
                f"task_seed_{uuid.uuid4().hex[:8]}", "default",
                "【演示】在 05 模块进行七维深度要件推演与被告抗辩质证预案编制",
                "【演示】推演抗辩示意。细节 TODO(律师核实)。",
                "庭审", "low", "todo", "2026-11-10 09:00:00", "phase4_deep_matrix",
                json.dumps({"target_tab": "tab-deep-matrix"}), now_str, now_str
            )
        ]
        cursor.executemany("""
        INSERT INTO agent_tasks (
            task_id, matter_id, title, description, stage, priority, status,
            due_date, linked_module, action_payload, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, seed_tasks)
        return len(seed_tasks)


def delete_demo_agent_tasks() -> int:
    """删除标题含【演示】的任务。"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM agent_tasks WHERE title LIKE ?", ("%【演示】%",))
        return cursor.rowcount


def get_agent_tasks(
    matter_id: Optional[str] = None,
    status: Optional[str] = None,
    stage: Optional[str] = None
) -> List[Dict[str, Any]]:
    """查询办案任务列表"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        query = "SELECT * FROM agent_tasks WHERE 1=1"
        params: List[Any] = []

        if matter_id:
            query += " AND (matter_id = ? OR matter_id = 'default')"
            params.append(matter_id)

        if status and status != 'all':
            query += " AND status = ?"
            params.append(status)

        if stage and stage != 'all':
            query += " AND stage = ?"
            params.append(stage)

        query += " ORDER BY CASE priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 WHEN 'low' THEN 3 ELSE 4 END, created_at DESC"
        cursor.execute(query, params)
        rows = cursor.fetchall()

        tasks = []
        for r in rows:
            t = dict(r)
            if t.get("action_payload"):
                try:
                    t["action_payload"] = json.loads(t["action_payload"])
                except Exception:
                    pass
            tasks.append(t)
        return tasks


def create_agent_task(task_data: Dict[str, Any]) -> Dict[str, Any]:
    """创建新办案任务"""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    task_id = task_data.get("task_id") or f"task_{int(datetime.now().timestamp())}_{uuid.uuid4().hex[:6]}"

    action_payload = task_data.get("action_payload")
    if isinstance(action_payload, (dict, list)):
        action_payload = json.dumps(action_payload, ensure_ascii=False)

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO agent_tasks (
            task_id, matter_id, title, description, stage, priority, status,
            due_date, linked_module, action_payload, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            task_id,
            task_data.get("matter_id", "default"),
            task_data.get("title", "未命名办案任务"),
            task_data.get("description", ""),
            task_data.get("stage", "立案"),
            task_data.get("priority", "medium"),
            task_data.get("status", "todo"),
            task_data.get("due_date"),
            task_data.get("linked_module", "phase1_litigation"),
            action_payload,
            now_str,
            now_str
        ))
    task_data["task_id"] = task_id
    task_data["created_at"] = now_str
    task_data["updated_at"] = now_str
    return task_data


def update_agent_task(task_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """更新任务信息或状态"""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    allowed_fields = [
        "title", "description", "stage", "priority", "status",
        "due_date", "linked_module", "action_payload", "matter_id"
    ]
    set_clauses = []
    params: List[Any] = []

    for k, v in updates.items():
        if k in allowed_fields:
            if k == "action_payload" and isinstance(v, (dict, list)):
                v = json.dumps(v, ensure_ascii=False)
            set_clauses.append(f"{k} = ?")
            params.append(v)

    if not set_clauses:
        return None

    set_clauses.append("updated_at = ?")
    params.append(now_str)
    params.append(task_id)

    with get_db_connection() as conn:
        cursor = conn.cursor()
        query = f"UPDATE agent_tasks SET {', '.join(set_clauses)} WHERE task_id = ?"
        cursor.execute(query, params)

        cursor.execute("SELECT * FROM agent_tasks WHERE task_id = ?", (task_id,))
        row = cursor.fetchone()

        if row:
            t = dict(row)
            if t.get("action_payload"):
                try:
                    t["action_payload"] = json.loads(t["action_payload"])
                except Exception:
                    pass
            return t
        return None


def delete_agent_task(task_id: str) -> bool:
    """删除办案任务"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM agent_tasks WHERE task_id = ?", (task_id,))
        return cursor.rowcount > 0


def batch_update_task_status(task_ids: List[str], new_status: str) -> int:
    """批量更新任务状态"""
    if not task_ids:
        return 0
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(f"""
        UPDATE agent_tasks
        SET status = ?, updated_at = ?
        WHERE task_id IN ({','.join(['?'] * len(task_ids))})
        """, [new_status, now_str] + task_ids)
        return cursor.rowcount


def save_agent_dialogue(
    role: str,
    content: str,
    speech_text: str = "",
    action_summary: Optional[Dict[str, Any]] = None,
    matter_id: str = "default"
) -> Dict[str, Any]:
    """保存对话流水"""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    msg_id = f"msg_{int(datetime.now().timestamp())}_{uuid.uuid4().hex[:6]}"

    action_summary_str = None
    if action_summary:
        action_summary_str = json.dumps(action_summary, ensure_ascii=False)

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO agent_dialogues (
            dialogue_id, matter_id, role, content, speech_text, action_summary, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (msg_id, matter_id, role, content, speech_text, action_summary_str, now_str))

    return {
        "dialogue_id": msg_id,
        "matter_id": matter_id,
        "role": role,
        "content": content,
        "speech_text": speech_text,
        "action_summary": action_summary,
        "created_at": now_str
    }


def get_recent_dialogues(matter_id: str = "default", limit: int = 30) -> List[Dict[str, Any]]:
    """读取近期对话记录"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT * FROM agent_dialogues
        WHERE matter_id = ? OR matter_id = 'default'
        ORDER BY created_at ASC
        LIMIT ?
        """, (matter_id, limit))
        rows = cursor.fetchall()

        msgs = []
        for r in rows:
            m = dict(r)
            if m.get("action_summary"):
                try:
                    m["action_summary"] = json.loads(m["action_summary"])
                except Exception:
                    pass
            msgs.append(m)
        return msgs
