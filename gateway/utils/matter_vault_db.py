"""
LawFlow 智律工作台 - 案件独立空间数据库引擎 (Matter Vault Database Engine)
功能：
1. 案件/项目（Matter Vault）为顶层容器，挂载多份证据材料、当事人基本信息、立案文书与深度推演记录；
2. 空间内所有子工具共享同一套文档与全局上下文，支持多案件新建、切换、归档与持久化；
3. 存储案件核心图谱（时间线、主体关系、资金流水）及阶段式人机协同工作流状态。
"""

from __future__ import annotations

import json
import os
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


def init_matter_vault_db():
    """初始化 Matter Vault 空间数据表；演示案件仅在 LAWFLOW_SEED_DEMO=1 时写入。"""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS matters (
            matter_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            cause_of_action TEXT NOT NULL,
            court_name TEXT,
            case_number TEXT,
            client_role TEXT DEFAULT '原告',
            plaintiff_info TEXT,
            defendant_info TEXT,
            principal_amount REAL DEFAULT 0.0,
            case_summary TEXT,
            status TEXT DEFAULT 'active',
            tags TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS matter_documents (
            doc_id TEXT PRIMARY KEY,
            matter_id TEXT NOT NULL,
            doc_type TEXT NOT NULL,
            title TEXT NOT NULL,
            file_path TEXT,
            file_size INTEGER DEFAULT 0,
            text_content TEXT,
            metadata_json TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (matter_id) REFERENCES matters (matter_id) ON DELETE CASCADE
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS matter_graphs (
            graph_id TEXT PRIMARY KEY,
            matter_id TEXT UNIQUE NOT NULL,
            timeline_json TEXT,
            entity_graph_json TEXT,
            cashflow_json TEXT,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (matter_id) REFERENCES matters (matter_id) ON DELETE CASCADE
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS matter_workflows (
            workflow_id TEXT PRIMARY KEY,
            matter_id TEXT NOT NULL,
            workflow_type TEXT NOT NULL DEFAULT 'litigation_drafting',
            current_step INTEGER NOT NULL DEFAULT 1,
            step_status TEXT NOT NULL DEFAULT 'IN_PROGRESS',
            step_data_json TEXT NOT NULL,
            is_completed INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (matter_id) REFERENCES matters (matter_id) ON DELETE CASCADE
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS matter_deadlines (
            id TEXT PRIMARY KEY,
            matter_id TEXT,
            kind TEXT NOT NULL,
            due_date TEXT NOT NULL,
            source TEXT,
            note TEXT,
            done INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (matter_id) REFERENCES matters (matter_id) ON DELETE CASCADE
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS signing_envelopes (
            envelope_id TEXT PRIMARY KEY,
            matter_id TEXT,
            client_name TEXT,
            status TEXT NOT NULL,
            file_path TEXT,
            file_sha256 TEXT,
            view_token TEXT NOT NULL,
            created_at TEXT NOT NULL,
            completed_at TEXT,
            payload_json TEXT NOT NULL DEFAULT '{}'
        );
        """)

    if _should_seed_demo():
        seed_demo_matters()


def seed_demo_matters() -> int:
    """写入带【演示】前缀的种子案件；已存在则跳过。返回新写入条数。"""
    inserted = 0
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) AS cnt FROM matters;")
        count = cursor.fetchone()["cnt"]
        if count > 0:
            return 0

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        m1_id = "MATTER-2026-001"
        cursor.execute("""
        INSERT INTO matters (
            matter_id, title, cause_of_action, court_name, case_number, client_role,
            plaintiff_info, defendant_info, principal_amount, case_summary, status, tags, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            m1_id,
            "【演示】北京某数据科技公司诉某供应链管理公司借款纠纷及连带保证责任案",
            "企业间民间借贷纠纷",
            "北京市海淀区人民法院",
            "TODO(律师核实)",
            "原告",
            json.dumps({"name": "北京智律未来数据科技有限公司", "type": "企业", "uscc": "TODO(律师核实)", "rep": "李立新"}, ensure_ascii=False),
            json.dumps({"name": "某供应链管理（北京）有限公司", "guarantor": "王建国", "type": "企业+自然人连带"}, ensure_ascii=False),
            5000000.0,
            "【演示】原告于某日向被告出借人民币500万元，约定借期1年。到期后被告仅付息，本金未还。案号与细节请律师核实。",
            "active",
            json.dumps(["【演示】", "企业间借贷", "连带保证"], ensure_ascii=False),
            now_str,
            now_str
        ))
        inserted += 1

        timeline_seed = [
            {"date": "2023-03-15", "event": "【演示】双方签署借款合同及保证合同", "evidence_ref": "证据一", "legal_tag": "合同订立生效"},
            {"date": "2023-03-16", "event": "【演示】原告向被告电汇本金", "evidence_ref": "证据二", "legal_tag": "借款实际交付"},
        ]
        entities_seed = [
            {"id": "e1", "name": "北京智律未来数据科技", "role": "原告/出借人", "type": "企业主体"},
            {"id": "e2", "name": "某供应链管理(北京)公司", "role": "被告/主债务人", "type": "企业主体"},
            {"id": "e3", "name": "王建国", "role": "第二被告/连带保证人", "type": "自然人(法定代表人)"}
        ]
        relations_seed = [
            {"source": "e1", "target": "e2", "type": "借贷主合同法律关系", "detail": "本金500万"},
            {"source": "e3", "target": "e1", "type": "个人无限连带保证法律关系", "detail": "担保范围涵盖本金、利息"}
        ]
        cashflow_seed = [
            {"flow_id": "cf1", "date": "2023-03-16", "payer": "原告", "payee": "被告", "amount": 5000000.0, "currency": "CNY", "purpose": "借款本金出借", "voucher": "TODO(律师核实)", "status": "CONFIRMED"},
        ]

        cursor.execute("""
        INSERT INTO matter_graphs (graph_id, matter_id, timeline_json, entity_graph_json, cashflow_json, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            str(uuid.uuid4()),
            m1_id,
            json.dumps(timeline_seed, ensure_ascii=False),
            json.dumps({"nodes": entities_seed, "edges": relations_seed}, ensure_ascii=False),
            json.dumps(cashflow_seed, ensure_ascii=False),
            now_str
        ))

        cursor.execute("""
        INSERT INTO matter_documents (doc_id, matter_id, doc_type, title, text_content, metadata_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            str(uuid.uuid4()),
            m1_id,
            "contract",
            "【演示】《企业间借款合同及保证协议书》.pdf",
            "【演示】借款合同示意：丙方自愿以个人名义为主合同债务提供连带保证责任。具体条款 TODO(律师核实)。",
            json.dumps({"pages": 4, "signed_date": "TODO(律师核实)"}, ensure_ascii=False),
            now_str
        ))

        m2_id = "MATTER-2026-002"
        cursor.execute("""
        INSERT INTO matters (
            matter_id, title, cause_of_action, court_name, case_number, client_role,
            plaintiff_info, defendant_info, principal_amount, case_summary, status, tags, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            m2_id,
            "【演示】上海某软件技术开发公司与某新零售集团软件著作权交付与服务费结算纠纷",
            "技术开发与软件服务合同纠纷",
            "上海市浦东新区人民法院",
            "TODO(律师核实)",
            "原告",
            json.dumps({"name": "上海启航云智软件技术有限公司", "type": "企业", "uscc": "TODO(律师核实)", "rep": "周鹏"}, ensure_ascii=False),
            json.dumps({"name": "某新零售科技股份有限公司", "type": "企业"}, ensure_ascii=False),
            1850000.0,
            "【演示】软件开发合同尾款纠纷示意案情。细节 TODO(律师核实)。",
            "active",
            json.dumps(["【演示】", "软件开发", "知识产权"], ensure_ascii=False),
            now_str,
            now_str
        ))
        inserted += 1

    return inserted


def delete_demo_matters() -> int:
    """删除标题含【演示】的案件及其级联数据。"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT matter_id FROM matters WHERE title LIKE ?", ("%【演示】%",))
        ids = [r["matter_id"] for r in cursor.fetchall()]
        for mid in ids:
            cursor.execute("DELETE FROM matter_documents WHERE matter_id = ?", (mid,))
            cursor.execute("DELETE FROM matter_graphs WHERE matter_id = ?", (mid,))
            cursor.execute("DELETE FROM matter_workflows WHERE matter_id = ?", (mid,))
            cursor.execute("DELETE FROM matters WHERE matter_id = ?", (mid,))
        return len(ids)


def list_all_matters(status: Optional[str] = None, search: Optional[str] = None) -> List[Dict[str, Any]]:
    """查询案件列表"""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        sql = "SELECT * FROM matters WHERE 1=1"
        params: List[Any] = []
        if status:
            if status != "all":
                sql += " AND status = ?"
                params.append(status)
        else:
            sql += " AND status != 'deleted'"
        if search:
            sql += " AND (title LIKE ? OR cause_of_action LIKE ? OR case_number LIKE ?)"
            wild = f"%{search}%"
            params.extend([wild, wild, wild])

        sql += " ORDER BY updated_at DESC"
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        results = []
        for r in rows:
            d = dict(r)
            d["plaintiff_info"] = json.loads(d["plaintiff_info"]) if d["plaintiff_info"] else {}
            d["defendant_info"] = json.loads(d["defendant_info"]) if d["defendant_info"] else {}
            d["tags"] = json.loads(d["tags"]) if d["tags"] else []
            results.append(d)
        return results


def get_matter_by_id(matter_id: str) -> Optional[Dict[str, Any]]:
    """获取单案件完整空间数据（含案卷、核心图谱与最新工作流）"""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM matters WHERE matter_id = ?", (matter_id,))
        row = cursor.fetchone()
        if not row:
            return None

        matter = dict(row)
        matter["plaintiff_info"] = json.loads(matter["plaintiff_info"]) if matter["plaintiff_info"] else {}
        matter["defendant_info"] = json.loads(matter["defendant_info"]) if matter["defendant_info"] else {}
        matter["tags"] = json.loads(matter["tags"]) if matter["tags"] else []

        cursor.execute("SELECT * FROM matter_documents WHERE matter_id = ? ORDER BY created_at ASC", (matter_id,))
        documents = []
        for dr in cursor.fetchall():
            dd = dict(dr)
            dd["metadata_json"] = json.loads(dd["metadata_json"]) if dd["metadata_json"] else {}
            documents.append(dd)
        matter["documents"] = documents

        cursor.execute("SELECT * FROM matter_graphs WHERE matter_id = ?", (matter_id,))
        graph_row = cursor.fetchone()
        if graph_row:
            matter["graphs"] = {
                "timeline": json.loads(graph_row["timeline_json"]) if graph_row["timeline_json"] else [],
                "entity_graph": json.loads(graph_row["entity_graph_json"]) if graph_row["entity_graph_json"] else {"nodes": [], "edges": []},
                "cashflow": json.loads(graph_row["cashflow_json"]) if graph_row["cashflow_json"] else []
            }
        else:
            matter["graphs"] = {
                "timeline": [],
                "entity_graph": {"nodes": [], "edges": []},
                "cashflow": []
            }

        cursor.execute("SELECT * FROM matter_workflows WHERE matter_id = ? ORDER BY updated_at DESC LIMIT 1", (matter_id,))
        wf_row = cursor.fetchone()
        if wf_row:
            matter["active_workflow"] = {
                "workflow_id": wf_row["workflow_id"],
                "workflow_type": wf_row["workflow_type"],
                "current_step": wf_row["current_step"],
                "step_status": wf_row["step_status"],
                "step_data": json.loads(wf_row["step_data_json"]) if wf_row["step_data_json"] else {},
                "is_completed": bool(wf_row["is_completed"])
            }
        else:
            matter["active_workflow"] = None

        return matter


def create_new_matter(data: Dict[str, Any]) -> Dict[str, Any]:
    """新建案件独立空间"""
    date_part = datetime.now().strftime("%Y%m%d")
    matter_id = data.get("matter_id") or f"MATTER-{date_part}-{uuid.uuid4().hex[:8]}"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    title = data.get("title") or "新收立案案件"
    cause = data.get("cause_of_action") or "民商事纠纷"
    court = data.get("court_name") or ""
    c_num = data.get("case_number") or ""
    client_role = data.get("client_role") or "原告"
    p_info = json.dumps(data.get("plaintiff_info") or {}, ensure_ascii=False)
    d_info = json.dumps(data.get("defendant_info") or {}, ensure_ascii=False)
    principal = float(data.get("principal_amount") or 0.0)
    summary = data.get("case_summary") or ""
    tags = json.dumps(data.get("tags") or [], ensure_ascii=False)

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO matters (
            matter_id, title, cause_of_action, court_name, case_number, client_role,
            plaintiff_info, defendant_info, principal_amount, case_summary, status, tags, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            matter_id, title, cause, court, c_num, client_role,
            p_info, d_info, principal, summary, 'active', tags, now_str, now_str
        ))

        cursor.execute("""
        INSERT INTO matter_graphs (graph_id, matter_id, timeline_json, entity_graph_json, cashflow_json, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (str(uuid.uuid4()), matter_id, "[]", '{"nodes":[],"edges":[]}', "[]", now_str))

    return get_matter_by_id(matter_id)


def update_matter_record(matter_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """更新案件信息"""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM matters WHERE matter_id = ?", (matter_id,))
        if not cursor.fetchone():
            return None

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        fields = []
        values: List[Any] = []

        for k in ["title", "cause_of_action", "court_name", "case_number", "client_role", "principal_amount", "case_summary", "status"]:
            if k in data:
                fields.append(f"{k} = ?")
                values.append(data[k])

        if "plaintiff_info" in data:
            fields.append("plaintiff_info = ?")
            values.append(json.dumps(data["plaintiff_info"], ensure_ascii=False))

        if "defendant_info" in data:
            fields.append("defendant_info = ?")
            values.append(json.dumps(data["defendant_info"], ensure_ascii=False))

        if "tags" in data:
            fields.append("tags = ?")
            values.append(json.dumps(data["tags"], ensure_ascii=False))

        fields.append("updated_at = ?")
        values.append(now_str)
        values.append(matter_id)

        sql = f"UPDATE matters SET {', '.join(fields)} WHERE matter_id = ?"
        cursor.execute(sql, values)

    return get_matter_by_id(matter_id)


def save_matter_graphs_db(matter_id: str, timeline: List[Dict[str, Any]], entity_graph: Dict[str, Any], cashflow: List[Dict[str, Any]]) -> bool:
    """持久化保存案件三大核心图谱"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute("""
        INSERT INTO matter_graphs (graph_id, matter_id, timeline_json, entity_graph_json, cashflow_json, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(matter_id) DO UPDATE SET
            timeline_json = excluded.timeline_json,
            entity_graph_json = excluded.entity_graph_json,
            cashflow_json = excluded.cashflow_json,
            updated_at = excluded.updated_at;
        """, (
            str(uuid.uuid4()),
            matter_id,
            json.dumps(timeline, ensure_ascii=False),
            json.dumps(entity_graph, ensure_ascii=False),
            json.dumps(cashflow, ensure_ascii=False),
            now_str
        ))

        cursor.execute("UPDATE matters SET updated_at = ? WHERE matter_id = ?", (now_str, matter_id))
    return True


def add_document_to_matter(matter_id: str, doc_data: Dict[str, Any]) -> Dict[str, Any]:
    """向案件空间挂载案卷材料"""
    doc_id = str(uuid.uuid4())
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
        INSERT INTO matter_documents (
            doc_id, matter_id, doc_type, title, file_path, file_size, text_content, metadata_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            doc_id,
            matter_id,
            doc_data.get("doc_type", "evidence"),
            doc_data.get("title", "未命名材料"),
            doc_data.get("file_path", ""),
            doc_data.get("file_size", 0),
            doc_data.get("text_content", ""),
            json.dumps(doc_data.get("metadata", {}), ensure_ascii=False),
            now_str
        ))

        cursor.execute("UPDATE matters SET updated_at = ? WHERE matter_id = ?", (now_str, matter_id))

    doc_data["doc_id"] = doc_id
    doc_data["matter_id"] = matter_id
    doc_data["created_at"] = now_str
    return doc_data


def update_matter_status(matter_id: str, target_status: str) -> Optional[Dict[str, Any]]:
    """
    流转案件状态：
    合法流转：active <-> archived, draft -> active
    非法流转：抛出 ValueError
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM matters WHERE matter_id = ?", (matter_id,))
        row = cursor.fetchone()
        if not row:
            return None
        curr = row["status"] or "active"
        valid = (
            (curr == "active" and target_status == "archived") or
            (curr == "archived" and target_status == "active") or
            (curr == "draft" and target_status == "active")
        )
        if not valid:
            raise ValueError(f"非法状态流转：不支持从 {curr} 流转至 {target_status}")

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("UPDATE matters SET status = ?, updated_at = ? WHERE matter_id = ?", (target_status, now_str, matter_id))
        conn.commit()

    return get_matter_by_id(matter_id)


def soft_delete_matter(matter_id: str) -> bool:
    """软删除案件：status='deleted'"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("UPDATE matters SET status = 'deleted', updated_at = ? WHERE matter_id = ?", (now_str, matter_id))
        conn.commit()
        return cursor.rowcount > 0


def create_matter_deadline(data: Dict[str, Any]) -> Dict[str, Any]:
    """新增案件期限记录"""
    dl_id = data.get("id") or f"DL-{uuid.uuid4().hex[:8]}"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO matter_deadlines (id, matter_id, kind, due_date, source, note, done, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            dl_id,
            data.get("matter_id"),
            data.get("kind"),
            data.get("due_date"),
            data.get("source", ""),
            data.get("note", ""),
            1 if data.get("done") else 0,
            now_str
        ))
        conn.commit()
    return {
        "id": dl_id,
        "matter_id": data.get("matter_id"),
        "kind": data.get("kind"),
        "due_date": data.get("due_date"),
        "source": data.get("source", ""),
        "note": data.get("note", ""),
        "done": bool(data.get("done")),
        "created_at": now_str
    }


def list_matter_deadlines(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    matter_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """查询期限日历列表"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        sql = "SELECT d.*, m.title AS matter_title FROM matter_deadlines d LEFT JOIN matters m ON d.matter_id = m.matter_id WHERE 1=1"
        params = []
        if from_date:
            sql += " AND d.due_date >= ?"
            params.append(from_date)
        if to_date:
            sql += " AND d.due_date <= ?"
            params.append(to_date if len(to_date) > 10 else f"{to_date} 23:59:59")
        if matter_id:
            sql += " AND d.matter_id = ?"
            params.append(matter_id)
        sql += " ORDER BY d.due_date ASC"
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        results = []
        for r in rows:
            d = dict(r)
            d["done"] = bool(d["done"])
            results.append(d)
        return results
