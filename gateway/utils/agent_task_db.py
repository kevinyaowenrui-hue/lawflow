"""
LawFlow 智律工作台 - 智能办案任务中枢与对话持久化引擎 (Agent Task & Dialogue DB Engine)
功能：
1. 办案任务矩阵 (agent_tasks) 持久化：支持优先级、办案阶段、截止日期、绑定模块动作与执行载荷
2. 语音/文本多轮对话 (agent_dialogues) 流水记录：记录用户指令与 AI 播报文本及执行快照
3. 支持与 Matter Vault 案件空间无缝贯通，按案件隔离或全局统一汇聚
"""

import os
import json
import sqlite3
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
VAULT_DB_PATH = os.path.join(BASE_DIR, "storage", "matter_vault.db")


def get_db_connection() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(VAULT_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(VAULT_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_agent_task_db():
    """初始化任务看板表与对话记录表，并预置专业律师办案种子任务"""
    conn = get_db_connection()
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

    # 检查是否已有任务，没有则写入专业种子任务
    cursor.execute("SELECT COUNT(*) as cnt FROM agent_tasks")
    row = cursor.fetchone()
    if row and row["cnt"] == 0:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        seed_tasks = [
            (
                "task_seed_01", "default",
                "在 02 模块生成起诉状、保全申请书与委托手续全套公文",
                "案由为民间借贷纠纷，自动结合 LPR 计息说明与借条、网银流水事实",
                "立案", "high", "in_progress", "今日 18:00", "phase1_litigation",
                json.dumps({"target_tab": "tab-litigation"}), now_str, now_str
            ),
            (
                "task_seed_02", "default",
                "核算2023年1月1日至2024年1月1日 50万元逾期LPR利息并锁定证据链",
                "按一年期 LPR 同期报价利率计算，利息合计 ¥26,701.37，一键同步案情总线",
                "精算", "high", "done", "已完成", "phase1_calc",
                json.dumps({"target_tab": "tab-calc"}), now_str, now_str
            ),
            (
                "task_seed_03", "default",
                "清洗借条与网银电子转账凭证并生成带三性核验的证据清单",
                "核对转账回单业务流水号及公证书电子数据哈希值，标注证明目的",
                "证据", "medium", "todo", "明日 12:00", "phase2_evidence",
                json.dumps({"target_tab": "tab-evidence"}), now_str, now_str
            ),
            (
                "task_seed_04", "default",
                "穿透检索《民法典》第667条及民间借贷司法解释关于借期利息口径",
                "排查约定利息与逾期利息并发计算上限（一年期LPR四倍与合同约定衔接）",
                "检索", "medium", "todo", "本周内", "phase5_statutes",
                json.dumps({"target_tab": "tab-statutes"}), now_str, now_str
            ),
            (
                "task_seed_05", "default",
                "在 05 模块进行七维深度要件推演与被告抗辩质证预案编制",
                "推演被告若主张部分还款现金交付或诉讼时效届满时的反驳事实与证明责任分配",
                "庭审", "low", "todo", "开庭前3日", "phase4_deep_matrix",
                json.dumps({"target_tab": "tab-deep-matrix"}), now_str, now_str
            )
        ]
        cursor.executemany("""
        INSERT INTO agent_tasks (
            task_id, matter_id, title, description, stage, priority, status,
            due_date, linked_module, action_payload, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, seed_tasks)

    conn.commit()
    conn.close()


def get_agent_tasks(
    matter_id: Optional[str] = None,
    status: Optional[str] = None,
    stage: Optional[str] = None
) -> List[Dict[str, Any]]:
    """查询办案任务列表"""
    conn = get_db_connection()
    cursor = conn.cursor()
    query = "SELECT * FROM agent_tasks WHERE 1=1"
    params = []

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
    conn.close()

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
    conn = get_db_connection()
    cursor = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    task_id = task_data.get("task_id") or f"task_{int(datetime.now().timestamp())}_{uuid.uuid4().hex[:6]}"

    action_payload = task_data.get("action_payload")
    if isinstance(action_payload, (dict, list)):
        action_payload = json.dumps(action_payload, ensure_ascii=False)

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
        task_data.get("due_date", "待定"),
        task_data.get("linked_module", "phase1_litigation"),
        action_payload,
        now_str,
        now_str
    ))
    conn.commit()
    conn.close()
    task_data["task_id"] = task_id
    task_data["created_at"] = now_str
    task_data["updated_at"] = now_str
    return task_data


def update_agent_task(task_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """更新任务信息或状态"""
    conn = get_db_connection()
    cursor = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    allowed_fields = [
        "title", "description", "stage", "priority", "status",
        "due_date", "linked_module", "action_payload", "matter_id"
    ]
    set_clauses = []
    params = []

    for k, v in updates.items():
        if k in allowed_fields:
            if k == "action_payload" and isinstance(v, (dict, list)):
                v = json.dumps(v, ensure_ascii=False)
            set_clauses.append(f"{k} = ?")
            params.append(v)

    if not set_clauses:
        conn.close()
        return None

    set_clauses.append("updated_at = ?")
    params.append(now_str)
    params.append(task_id)

    query = f"UPDATE agent_tasks SET {', '.join(set_clauses)} WHERE task_id = ?"
    cursor.execute(query, params)
    conn.commit()

    cursor.execute("SELECT * FROM agent_tasks WHERE task_id = ?", (task_id,))
    row = cursor.fetchone()
    conn.close()

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
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM agent_tasks WHERE task_id = ?", (task_id,))
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected > 0


def batch_update_task_status(task_ids: List[str], new_status: str) -> int:
    """批量更新任务状态"""
    conn = get_db_connection()
    cursor = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(f"""
    UPDATE agent_tasks
    SET status = ?, updated_at = ?
    WHERE task_id IN ({','.join(['?'] * len(task_ids))})
    """, [new_status, now_str] + task_ids)
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected


def save_agent_dialogue(
    role: str,
    content: str,
    speech_text: str = "",
    action_summary: Optional[Dict[str, Any]] = None,
    matter_id: str = "default"
) -> Dict[str, Any]:
    """保存对话流水"""
    conn = get_db_connection()
    cursor = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    msg_id = f"msg_{int(datetime.now().timestamp())}_{uuid.uuid4().hex[:6]}"

    action_summary_str = None
    if action_summary:
        action_summary_str = json.dumps(action_summary, ensure_ascii=False)

    cursor.execute("""
    INSERT INTO agent_dialogues (
        dialogue_id, matter_id, role, content, speech_text, action_summary, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (msg_id, matter_id, role, content, speech_text, action_summary_str, now_str))
    conn.commit()
    conn.close()

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
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT * FROM agent_dialogues
    WHERE matter_id = ? OR matter_id = 'default'
    ORDER BY created_at ASC
    LIMIT ?
    """, (matter_id, limit))
    rows = cursor.fetchall()
    conn.close()

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
