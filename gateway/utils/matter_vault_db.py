"""

LawFlow 智律工作台 - 案件独立空间数据库引擎 (Matter Vault Database Engine)

功能：

1. 案件/项目（Matter Vault）为顶层容器，挂载多份证据材料、当事人基本信息、立案文书与深度推演记录；

2. 空间内所有子工具共享同一套文档与全局上下文，支持多案件新建、切换、归档与持久化；

3. 存储案件核心图谱（时间线、主体关系、资金流水）及阶段式人机协同工作流状态。

"""



from __future__ import annotations



import json

import logging

import os

import sqlite3

import uuid

from contextlib import contextmanager

from datetime import datetime

from typing import Any, Dict, Iterator, List, Optional



from gateway.core.db import connect

from gateway.core.paths import get_vault_db_path



logger = logging.getLogger("lawflow.matter_vault")





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



        cursor.execute("""

        CREATE TABLE IF NOT EXISTS audit_log (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            time TEXT NOT NULL,

            action TEXT NOT NULL,

            matter_id TEXT,

            target TEXT,

            client_ip TEXT,

            result TEXT DEFAULT 'success'

        );

        """)



    _ensure_practice_column()
    _ensure_deadline_origin()

    if _should_seed_demo():

        seed_demo_matters()

    scrub_demo_matter_placeholders()





def scrub_demo_matter_placeholders() -> None:

    """已写入的演示案件不再把占位符显示成待律师核实。"""

    try:

        with get_db_connection() as conn:

            cursor = conn.cursor()

            cursor.execute(

                """

                UPDATE matters

                SET case_number = CASE

                        WHEN IFNULL(case_number, '') LIKE '%TODO(律师核实)%' THEN '未录入'

                        ELSE case_number

                    END,

                    plaintiff_info = REPLACE(IFNULL(plaintiff_info, ''), 'TODO(律师核实)', '未录入'),

                    case_summary = REPLACE(IFNULL(case_summary, ''), '案号与细节请律师核实。', '案号、统一社会信用代码和合同条款都没有录入。')

                WHERE title LIKE '%【演示】%'

                  AND (

                    IFNULL(case_number, '') LIKE '%TODO(律师核实)%'

                    OR IFNULL(plaintiff_info, '') LIKE '%TODO(律师核实)%'

                    OR IFNULL(case_summary, '') LIKE '%请律师核实%'

                  )

                """

            )

            cursor.execute(

                """

                UPDATE matter_documents

                SET text_content = REPLACE(IFNULL(text_content, ''), 'TODO(律师核实)', '未录入'),

                    metadata_json = REPLACE(IFNULL(metadata_json, ''), 'TODO(律师核实)', '未录入')

                WHERE matter_id IN (SELECT matter_id FROM matters WHERE title LIKE '%【演示】%')

                  AND (

                    IFNULL(text_content, '') LIKE '%TODO(律师核实)%'

                    OR IFNULL(metadata_json, '') LIKE '%TODO(律师核实)%'

                  )

                """

            )

            cursor.execute(

                """

                UPDATE matter_graphs

                SET cashflow_json = REPLACE(IFNULL(cashflow_json, ''), 'TODO(律师核实)', '未录入')

                WHERE matter_id IN (SELECT matter_id FROM matters WHERE title LIKE '%【演示】%')

                  AND IFNULL(cashflow_json, '') LIKE '%TODO(律师核实)%'

                """

            )

    except Exception as e:

        logger.warning(f"清理演示案件占位符失败: {e}")





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

            "未录入",

            "原告",

            json.dumps({"name": "北京智律未来数据科技有限公司", "type": "企业", "uscc": "未录入", "rep": "李立新"}, ensure_ascii=False),

            json.dumps({"name": "某供应链管理（北京）有限公司", "guarantor": "王建国", "type": "企业+自然人连带"}, ensure_ascii=False),

            5000000.0,

            "【演示】2023-03-15 签署借款合同，2023-03-16 电汇本金500万元，约定借期1年。到期后被告仅付息，本金未还。案号、统一社会信用代码和合同条款都没有录入。",

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

            {"flow_id": "cf1", "date": "2023-03-16", "payer": "原告", "payee": "被告", "amount": 5000000.0, "currency": "CNY", "purpose": "借款本金出借", "voucher": "未录入", "status": "UNVERIFIED"},

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

            "【演示】借款合同示意：丙方自愿以个人名义为主合同债务提供连带保证责任。保证期间和保证范围没有录入。",

            json.dumps({"pages": 4, "signed_date": "未录入"}, ensure_ascii=False),

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

            "未录入",

            "原告",

            json.dumps({"name": "上海启航云智软件技术有限公司", "type": "企业", "uscc": "未录入", "rep": "周鹏"}, ensure_ascii=False),

            json.dumps({"name": "某新零售科技股份有限公司", "type": "企业"}, ensure_ascii=False),

            1850000.0,

            "【演示】软件开发合同尾款纠纷示意案情。案号、统一社会信用代码和合同条款都没有录入。",

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

            _attach_party_aliases(d)

            results.append(d)

        return results





def get_matter_by_id(matter_id: str, include_deleted: bool = False) -> Optional[Dict[str, Any]]:

    """获取单案件完整空间数据（含案卷、核心图谱与最新工作流；默认排除已删除案件）"""

    with get_db_connection() as conn:

        cursor = conn.cursor()



        cursor.execute("SELECT * FROM matters WHERE matter_id = ?", (matter_id,))

        row = cursor.fetchone()

        if not row:

            return None

        if not include_deleted and (row["status"] or "").strip().lower() == "deleted":

            return None



        matter = dict(row)

        matter["plaintiff_info"] = json.loads(matter["plaintiff_info"]) if matter["plaintiff_info"] else {}

        matter["defendant_info"] = json.loads(matter["defendant_info"]) if matter["defendant_info"] else {}

        matter["tags"] = json.loads(matter["tags"]) if matter["tags"] else []

        _attach_party_aliases(matter)



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

    """

    删除案件原件并把案件标记为 deleted。

    1. 从磁盘移除关联原件及文件副本；

    2. 清理级联记录（matter_documents, matter_graphs, matter_workflows）；

    3. 案件行仍保留，status 改为 deleted。证件号默认不抹去。

    要连同证件号从案件行抹去，调用 scrub_matter_direct_identifiers。

    """

    with get_db_connection() as conn:

        cursor = conn.cursor()

        # 1. 从磁盘移除关联材料原件。案件行和证件号留到单独动作再抹。

        cursor.execute("SELECT file_path, metadata_json FROM matter_documents WHERE matter_id = ?", (matter_id,))

        for doc_row in cursor.fetchall():

            fp = doc_row["file_path"]

            if fp and os.path.exists(fp):

                try:

                    os.remove(fp)

                except OSError as e:

                    logger.warning(f"删除案件文档物理文件失败: {fp}, {e}")

            try:

                meta = json.loads(doc_row["metadata_json"] or "{}")

                stored = meta.get("stored_name")

                if stored:

                    from gateway.core.paths import get_uploads_dir

                    stored_p = os.path.join(str(get_uploads_dir()), stored)

                    if os.path.exists(stored_p):

                        try:

                            os.remove(stored_p)

                        except OSError as err:
                            logger.debug(f"移除附件副本忽略: {err}")

            except (json.JSONDecodeError, OSError, KeyError) as err:
                logger.debug(f"清理附件忽略非致命异常: {err}")



        # 2. 清理级联子表

        cursor.execute("DELETE FROM matter_documents WHERE matter_id = ?", (matter_id,))

        cursor.execute("DELETE FROM matter_graphs WHERE matter_id = ?", (matter_id,))

        cursor.execute("DELETE FROM matter_workflows WHERE matter_id = ?", (matter_id,))



        # 3. 标记案件状态为 deleted

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute("UPDATE matters SET status = 'deleted', updated_at = ? WHERE matter_id = ?", (now_str, matter_id))

        conn.commit()

        return cursor.rowcount > 0





def delete_document_from_matter(matter_id: str, doc_id: str) -> bool:

    """删除单份案卷材料（磁盘原件与数据库记录）"""

    with get_db_connection() as conn:

        cursor = conn.cursor()

        cursor.execute(

            "SELECT file_path, metadata_json FROM matter_documents WHERE matter_id = ? AND doc_id = ?",

            (matter_id, doc_id)

        )

        row = cursor.fetchone()

        if not row:

            return False



        fp = row["file_path"]

        if fp and os.path.exists(fp):

            try:

                os.remove(fp)

            except OSError as e:

                logger.warning(f"删除材料物理文件失败: {fp}, {e}")



        try:

            meta = json.loads(row["metadata_json"] or "{}")

            stored = meta.get("stored_name")

            if stored:

                from gateway.core.paths import get_uploads_dir

                stored_p = os.path.join(str(get_uploads_dir()), stored)

                if os.path.exists(stored_p):

                    try:

                        os.remove(stored_p)

                    except OSError as err:
                            logger.debug(f"移除附件副本忽略: {err}")

        except (json.JSONDecodeError, OSError, KeyError) as err:
                logger.debug(f"清理附件忽略非致命异常: {err}")



        cursor.execute("DELETE FROM matter_documents WHERE matter_id = ? AND doc_id = ?", (matter_id, doc_id))

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute("UPDATE matters SET updated_at = ? WHERE matter_id = ?", (now_str, matter_id))

        conn.commit()

        return True





def create_matter_deadline(data: Dict[str, Any]) -> Dict[str, Any]:

    """新增案件期限记录"""

    _ensure_deadline_origin()

    dl_id = data.get("id") or f"DL-{uuid.uuid4().hex[:8]}"

    origin = str(data.get("origin") or "lawyer_note")

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

        cursor.execute("UPDATE matter_deadlines SET origin = ? WHERE id = ?", (origin, dl_id))

        conn.commit()

    saved = {

        "id": dl_id,

        "matter_id": data.get("matter_id"),

        "kind": data.get("kind"),

        "due_date": data.get("due_date"),

        "source": data.get("source", ""),

        "note": data.get("note", ""),

        "done": bool(data.get("done")),

        "created_at": now_str,

        "origin": origin,

    }

    _decorate_deadline(saved)

    return saved





def list_matter_deadlines(

    from_date: Optional[str] = None,

    to_date: Optional[str] = None,

    matter_id: Optional[str] = None

) -> List[Dict[str, Any]]:

    """查询期限日历列表"""

    _ensure_deadline_origin()

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

            _decorate_deadline(d)

            results.append(d)

        return results





def record_audit_log(

    action: str,

    matter_id: Optional[str] = None,

    target: Optional[str] = None,

    client_ip: Optional[str] = None,

    result: str = "success"

) -> int:

    """写入审计日志，不包含当事人敏感信息"""

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with get_db_connection() as conn:

        cursor = conn.cursor()

        cursor.execute(

            "INSERT INTO audit_log (time, action, matter_id, target, client_ip, result) VALUES (?, ?, ?, ?, ?, ?)",

            (now_str, action, matter_id, target, client_ip, result)

        )

        conn.commit()

        return cursor.lastrowid





def get_audit_logs(

    page: int = 1,

    page_size: int = 20,

    action: Optional[str] = None,

    matter_id: Optional[str] = None

) -> Dict[str, Any]:

    """分页获取审计日志"""

    offset = max(0, (page - 1) * page_size)

    with get_db_connection() as conn:

        cursor = conn.cursor()

        where_clauses = ["1=1"]

        params = []

        if action:

            where_clauses.append("action = ?")

            params.append(action)

        if matter_id:

            where_clauses.append("matter_id = ?")

            params.append(matter_id)

        

        where_sql = " AND ".join(where_clauses)

        cursor.execute(f"SELECT COUNT(*) as cnt FROM audit_log WHERE {where_sql}", params)

        total = cursor.fetchone()["cnt"]

        

        cursor.execute(

            f"SELECT id, time, action, matter_id, target, client_ip, result FROM audit_log WHERE {where_sql} ORDER BY id DESC LIMIT ? OFFSET ?",

            params + [page_size, offset]

        )

        rows = cursor.fetchall()

        items = [

            {

                "id": r["id"],

                "time": r["time"],

                "action": r["action"],

                "matter_id": r["matter_id"],

                "target": r["target"],

                "client_ip": r["client_ip"],

                "result": r["result"]

            }

            for r in rows

        ]

        return {

            "total": total,

            "page": page,

            "page_size": page_size,

            "items": items

        }


def _ensure_practice_column(cursor=None) -> None:
    """给已有案件库补上办案字段。新库在建表之后调用。"""
    def _apply(cur) -> None:
        tables = {row[0] for row in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "matters" not in tables:
            return
        cols = {row[1] for row in cur.execute("PRAGMA table_info(matters)")}
        if "practice_json" not in cols:
            cur.execute("ALTER TABLE matters ADD COLUMN practice_json TEXT NOT NULL DEFAULT '{}'")

    if cursor is not None:
        _apply(cursor)
        return
    with get_db_connection() as conn:
        _apply(conn.cursor())


def _attach_party_aliases(matter: Dict[str, Any]) -> Dict[str, Any]:
    """列表和详情都带上当事人姓名、摘要和收费/程序，避免界面只显示“原告 VS 被告”。"""
    plaintiff = matter.get("plaintiff_info") or {}
    defendant = matter.get("defendant_info") or {}
    if isinstance(plaintiff, str):
        plaintiff = json.loads(plaintiff) if plaintiff else {}
        matter["plaintiff_info"] = plaintiff
    if isinstance(defendant, str):
        defendant = json.loads(defendant) if defendant else {}
        matter["defendant_info"] = defendant
    if not isinstance(plaintiff, dict):
        plaintiff = {}
    if not isinstance(defendant, dict):
        defendant = {}
    matter["plaintiff_name"] = plaintiff.get("name") or matter.get("plaintiff_name") or ""
    matter["defendant_name"] = defendant.get("name") or matter.get("defendant_name") or ""
    matter["summary"] = matter.get("case_summary") or matter.get("summary") or ""
    raw_practice = matter.get("practice_json")
    if isinstance(raw_practice, str):
        try:
            practice = json.loads(raw_practice) if raw_practice else {}
        except json.JSONDecodeError:
            practice = {}
    elif isinstance(raw_practice, dict):
        practice = raw_practice
    else:
        practice = matter.get("practice") if isinstance(matter.get("practice"), dict) else {}
    if not isinstance(practice, dict):
        practice = {}
    matter["practice"] = practice
    return matter


def save_matter_practice(matter_id: str, practice: Optional[Dict[str, Any]]) -> None:
    if not isinstance(practice, dict):
        return
    _ensure_practice_column()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT practice_json FROM matters WHERE matter_id = ?", (matter_id,))
        row = cursor.fetchone()
        if not row:
            return
        current: Dict[str, Any] = {}
        raw = row["practice_json"] if row["practice_json"] else ""
        if raw:
            try:
                loaded = json.loads(raw)
                if isinstance(loaded, dict):
                    current = loaded
            except json.JSONDecodeError:
                current = {}
        current.update(practice)
        cursor.execute(
            "UPDATE matters SET practice_json = ?, updated_at = ? WHERE matter_id = ?",
            (
                json.dumps(current, ensure_ascii=False),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                matter_id,
            ),
        )


DEADLINE_ORIGIN_LABELS = {
    "court_notice": "法院通知",
    "statutory_calc": "法定推算",
    "lawyer_note": "律师备忘",
}


def _ensure_deadline_origin() -> None:
    """给已有期限表补 origin。列已在就跳过，不再 ALTER，避免空库二次初始化报 duplicate column。"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        tables = {row[0] for row in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "matter_deadlines" not in tables:
            return
        cols = {
            str(row[1]).lower()
            for row in cursor.execute("PRAGMA table_info(matter_deadlines)")
        }
        if "origin" in cols:
            return
        try:
            cursor.execute(
                "ALTER TABLE matter_deadlines ADD COLUMN origin TEXT NOT NULL DEFAULT 'lawyer_note'"
            )
        except sqlite3.OperationalError as exc:
            # 并发初始化可能刚加上同名列；列已在就结束，不要把启动打成失败。
            if "duplicate column" not in str(exc).lower():
                raise


def _decorate_deadline(row: Dict[str, Any]) -> None:
    origin = str(row.get("origin") or "lawyer_note")
    if origin not in DEADLINE_ORIGIN_LABELS:
        origin = "lawyer_note"
    row["origin"] = origin
    row["origin_label"] = DEADLINE_ORIGIN_LABELS[origin]


_DIRECT_IDENTIFIER_KEYS = {
    "id_no",
    "id_card",
    "idcard",
    "id_number",
    "identity_no",
    "identity_card",
    "uscc",
    "credit_code",
    "unified_social_credit_code",
    "social_credit_code",
    "phone",
    "mobile",
    "tel",
    "telephone",
    "phone_number",
    "email",
    "address",
    "bank_account",
    "account_no",
    "bank_card",
}


def _is_direct_identifier_key(key: Any) -> bool:
    text = str(key or "").strip().lower().replace("-", "_")
    if text in _DIRECT_IDENTIFIER_KEYS:
        return True
    if text.endswith("_phone") or text.endswith("_mobile") or text.endswith("_email"):
        return True
    if "id_no" in text or "id_card" in text or "idcard" in text or text.endswith("_uscc"):
        return True
    return False


def _scrub_identifier_tree(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _scrub_identifier_tree(item)
            for key, item in value.items()
            if not _is_direct_identifier_key(key)
        }
    if isinstance(value, list):
        return [_scrub_identifier_tree(item) for item in value]
    return value


def scrub_matter_direct_identifiers(matter_id: str) -> Dict[str, Any]:
    """从案件行抹去证件号、电话等直接识别信息，保留姓名。利冲底档姓名另作说明。"""
    _ensure_practice_column()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM matters WHERE matter_id = ?", (matter_id,))
        row = cursor.fetchone()
        if not row:
            return {
                "scrubbed": False,
                "keeps_names": False,
                "registry_note": "案件行不存在。",
            }
        data = dict(row)
        plaintiff_raw = data.get("plaintiff_info") or "{}"
        defendant_raw = data.get("defendant_info") or "{}"
        try:
            plaintiff = json.loads(plaintiff_raw) if isinstance(plaintiff_raw, str) else (plaintiff_raw or {})
        except json.JSONDecodeError:
            plaintiff = {}
        try:
            defendant = json.loads(defendant_raw) if isinstance(defendant_raw, str) else (defendant_raw or {})
        except json.JSONDecodeError:
            defendant = {}
        practice_raw = data.get("practice_json") or "{}"
        try:
            practice = json.loads(practice_raw) if isinstance(practice_raw, str) else (practice_raw or {})
        except json.JSONDecodeError:
            practice = {}
        plaintiff = _scrub_identifier_tree(plaintiff if isinstance(plaintiff, dict) else {})
        defendant = _scrub_identifier_tree(defendant if isinstance(defendant, dict) else {})
        practice = _scrub_identifier_tree(practice if isinstance(practice, dict) else {})
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            """
            UPDATE matters
            SET plaintiff_info = ?, defendant_info = ?, practice_json = ?, updated_at = ?
            WHERE matter_id = ?
            """,
            (
                json.dumps(plaintiff, ensure_ascii=False),
                json.dumps(defendant, ensure_ascii=False),
                json.dumps(practice, ensure_ascii=False),
                now_str,
                matter_id,
            ),
        )
    from gateway.utils.conflict_checker import clear_conflict_registry_credentials

    registry = clear_conflict_registry_credentials(matter_id)
    return {
        "scrubbed": True,
        "keeps_names": bool(registry.get("keeps_names")),
        "registry_note": registry.get("note") or "",
    }

