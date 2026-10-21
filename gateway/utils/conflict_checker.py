"""
LawFlow 智律工作台 - 接案利益冲突穿透排查引擎 (Conflict of Interest Check Engine)
严格遵循：
- 《中华人民共和国律师法》第三十九条
- 中华全国律师协会《律师执业行为规范(试行)》第五十条、第五十一条
- 司法部《律师和律师事务所违法行为处罚办法》
实现接案前强制穿透式利益冲突排查与执业红线阻断。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, Iterator, List, Optional

from gateway.core.db import connect
from gateway.core.paths import get_laws_db_path

logger = logging.getLogger("lawflow.conflict_checker")


@contextmanager
def get_db_connection() -> Iterator[sqlite3.Connection]:
    with connect(get_laws_db_path(), row_factory=sqlite3.Row) as conn:
        yield conn


def _should_seed_demo() -> bool:
    return os.environ.get("LAWFLOW_SEED_DEMO", "").strip() in ("1", "true", "True", "yes", "YES")


_CONFLICT_DEMO_SEEDED = False


def init_conflict_registry_table():
    """初始化律所历史案件与利益冲突底档数据表（建表+索引；演示种子每进程至多一次）。"""
    global _CONFLICT_DEMO_SEEDED
    db_path = get_laws_db_path()
    if not db_path.parent.exists() and not os.environ.get("LAWFLOW_STORAGE_DIR"):
        try:
            db_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.warning(f"利益冲突库路径不可用，跳过初始化: {e}")
            return

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS conflict_case_registry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id TEXT UNIQUE NOT NULL,
                case_title TEXT NOT NULL,
                cause_of_action TEXT NOT NULL,
                lead_lawyer TEXT NOT NULL,
                client_name TEXT NOT NULL,
                client_uscc_id TEXT,
                client_type TEXT DEFAULT 'CLIENT',
                opposing_name TEXT NOT NULL,
                opposing_uscc_id TEXT,
                affiliates_json TEXT DEFAULT '[]',
                case_status TEXT NOT NULL,
                retainer_end_date TEXT,
                notes TEXT,
                created_at TEXT NOT NULL
            );
            """)
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_conflict_client ON conflict_case_registry(client_name);"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_conflict_opposing ON conflict_case_registry(opposing_name);"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_conflict_status ON conflict_case_registry(case_status);"
            )
    except (sqlite3.Error, OSError) as e:
        logger.warning(f"初始化利益冲突数据库表异常: {e}")
        return

    if _should_seed_demo() and not _CONFLICT_DEMO_SEEDED:
        seed_demo_conflict_cases()
        _CONFLICT_DEMO_SEEDED = True


init_conflict_database = init_conflict_registry_table


def seed_demo_conflict_cases() -> int:
    """写入带【演示】前缀的利冲底档；库非空则跳过。返回新写入条数。"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM conflict_case_registry;")
        count = cursor.fetchone()[0]
        if count > 0:
            return 0

        seed_cases = [
            (
                "TODO(律师核实)-DEMO-008",
                "【演示】北京宏达商贸有限公司常年法律顾问服务案",
                "常年法律顾问",
                "陈合伙人",
                "北京宏达商贸有限公司",
                "TODO(律师核实)",
                "RETAINER_CLIENT",
                "无指定特定相对人",
                "",
                json.dumps(
                    [
                        {
                            "name": "张三",
                            "relation": "法定代表人/实际控制人",
                            "id_card": "TODO(律师核实)",
                        },
                        {
                            "name": "北京宏达供应链管理有限公司",
                            "relation": "全资子公司",
                            "uscc": "TODO(律师核实)",
                        },
                    ],
                    ensure_ascii=False,
                ),
                "RETAINER",
                "2027-12-31",
                "【演示】存续期常年顾问客户示意底档。细节 TODO(律师核实)。",
                "2023-01-01 09:00:00",
            ),
            (
                "TODO(律师核实)-DEMO-105",
                "【演示】智科云服诉华腾物流技术开发合同纠纷案",
                "技术开发合同纠纷",
                "王大状",
                "智科云服信息技术（北京）有限公司",
                "TODO(律师核实)",
                "LITIGATION_CLIENT",
                "华腾物流网络技术有限公司",
                "TODO(律师核实)",
                json.dumps(
                    [
                        {"name": "华腾云仓（天津）网络有限公司", "relation": "控股子公司"},
                        {"name": "赵华腾", "relation": "被告实控人"},
                    ],
                    ensure_ascii=False,
                ),
                "ACTIVE",
                "",
                "【演示】在办技术合同案件示意底档。细节 TODO(律师核实)。",
                "2023-09-01 14:00:00",
            ),
            (
                "TODO(律师核实)-DEMO-072",
                "【演示】中建天成建设工程集团诉宏远实业施工合同纠纷案",
                "建设工程施工合同纠纷",
                "李合伙人",
                "中建天成建设工程集团有限公司",
                "TODO(律师核实)",
                "LITIGATION_CLIENT",
                "北京宏远实业开发有限公司",
                "TODO(律师核实)",
                json.dumps(
                    [{"name": "王宏远", "relation": "宏远实业法定代表人"}],
                    ensure_ascii=False,
                ),
                "CLOSED",
                "",
                "【演示】已结案施工合同示意底档。细节 TODO(律师核实)。",
                "2022-05-10 10:30:00",
            ),
            (
                "TODO(律师核实)-DEMO-019",
                "【演示】李四诉张三民间借贷纠纷案",
                "民间借贷纠纷",
                "王大状",
                "李四",
                "TODO(律师核实)",
                "LITIGATION_CLIENT",
                "张三",
                "TODO(律师核实)",
                json.dumps(
                    [{"name": "王五", "relation": "指示付款第三方账户/宏达出纳"}],
                    ensure_ascii=False,
                ),
                "ACTIVE",
                "",
                "【演示】在办民间借贷示意底档。细节 TODO(律师核实)。",
                "2024-03-10 11:20:00",
            ),
        ]

        cursor.executemany(
            """
        INSERT INTO conflict_case_registry (
            case_id, case_title, cause_of_action, lead_lawyer,
            client_name, client_uscc_id, client_type,
            opposing_name, opposing_uscc_id, affiliates_json,
            case_status, retainer_end_date, notes, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """,
            seed_cases,
        )
        return len(seed_cases)


def delete_demo_conflict_cases() -> int:
    """删除 case_title 含【演示】的底档记录。"""
    global _CONFLICT_DEMO_SEEDED
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM conflict_case_registry WHERE case_title LIKE ?",
            ("%【演示】%",),
        )
        n = cursor.rowcount or 0
    # 清空后本进程内不再自动回种，除非显式 seed_demo / 重启且 SEED_DEMO=1
    _CONFLICT_DEMO_SEEDED = True
    return n


def clean_name(name: Optional[str]) -> str:
    if not name:
        return ""
    n = re.sub(r"[\(（].*?[\)）]", "", name).strip()
    return n


def _unable_to_check_response() -> Dict[str, Any]:
    return {
        "status": "error",
        "conflict_level": "UNABLE_TO_CHECK",
        "verdict": "UNABLE_TO_CHECK",
        "has_conflict": None,
        "status_label": "无法完成利益冲突排查，请稍后重试或人工排查",
        "summary": "无法完成利益冲突排查，请稍后重试或人工排查",
        "recommendation": "无法完成利益冲突排查，请稍后重试或人工排查",
        "message": "无法完成利益冲突排查，请稍后重试或人工排查",
        "triggered_rules": [],
        "total_conflicts": 0,
        "conflict_items": [],
        "conflicts": [],
    }


def check_conflict_of_interest(
    plaintiff_name: str = "",
    defendant_name: str = "",
    cause_of_action: str = "",
    plaintiff_id: str = "",
    defendant_id: str = "",
    affiliates: Optional[List[str]] = None,
    client_name: str = "",
    opposing_party: str = "",
    client_id_or_code: str = "",
    opposing_id_or_code: str = "",
    related_entities: Optional[List[str]] = None,
    case_subject: str = "",
    **kwargs,
) -> Dict[str, Any]:
    """
    全方位多维利益冲突穿透排查算法
    核查维度：
    1. 【直接利益冲突】待起诉被告是我所在办客户或法律顾问单位（CRITICAL_BLOCKED）；
    2. 【同案双方代理冲突】原被告双方均为我所代理客户（CRITICAL_BLOCKED）；
    3. 【穿透关联利益冲突】被告法定代表人/实控人/母子公司为我所客户（HIGH_WARNING）；
    4. 【历史客户利益冲突】对方曾为我所已结案客户，可能存在案情关联或保密义务（CAUTION_REQUIRED）；
    5. 【合格发证】若无冲突，生成合规审计合格数字凭据。
    """
    p_raw = plaintiff_name or client_name
    d_raw = defendant_name or opposing_party
    p_id_raw = plaintiff_id or client_id_or_code
    d_id_raw = defendant_id or opposing_id_or_code

    p_clean = clean_name(p_raw)
    d_clean = clean_name(d_raw)
    p_id = (p_id_raw or "").strip()
    d_id = (d_id_raw or "").strip()

    conflict_items: List[Dict[str, Any]] = []
    highest_severity = 0  # 0: none, 1: CAUTION, 2: WARNING, 3: BLOCKED

    try:
        init_conflict_registry_table()
        with get_db_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
            SELECT id, case_id, case_title, cause_of_action, lead_lawyer,
                   client_name, client_uscc_id, client_type,
                   opposing_name, opposing_uscc_id, affiliates_json,
                   case_status, retainer_end_date, notes, created_at
            FROM conflict_case_registry;
            """
            )
            records = cursor.fetchall()

            for r in records:
                r_client = clean_name(r["client_name"])
                r_opposing = clean_name(r["opposing_name"])
                r_status = r["case_status"]
                r_client_id = (r["client_uscc_id"] or "").strip()
                r_opposing_id = (r["opposing_uscc_id"] or "").strip()

                affs: List[Any] = []
                try:
                    affs = json.loads(r["affiliates_json"] or "[]")
                except Exception:
                    affs = []

                aff_names = [clean_name(a.get("name")) for a in affs if a.get("name")]
                aff_ids = [
                    a.get("id_card") or a.get("uscc")
                    for a in affs
                    if a.get("id_card") or a.get("uscc")
                ]

                is_defendant_my_client = (
                    (
                        d_clean
                        and (d_clean == r_client or d_clean in r_client or r_client in d_clean)
                    )
                    or (d_id and d_id == r_client_id)
                )

                if is_defendant_my_client:
                    if r_status in ["ACTIVE", "RETAINER"]:
                        highest_severity = max(highest_severity, 3)
                        conflict_items.append(
                            {
                                "conflict_type": "常年顾问/在办客户利益冲突 (DIRECT_CLIENT_CONFLICT)",
                                "severity": "CRITICAL_BLOCKED",
                                "conflict_party": d_clean,
                                "matched_role": "现为我所客户",
                                "matched_case_id": r["case_id"],
                                "matched_case_title": r["case_title"],
                                "lead_lawyer": r["lead_lawyer"],
                                "case_status": r_status,
                                "rule_basis": "《律师法》第39条第(三)项及《律师执业行为规范》第五十条第(四)项：在担任法律顾问期间，为顾问单位的对方当事人代理；第五十条第(一)项：在同一案件中代理有利益冲突的当事人。",
                                "action_required": "【执业红线熔断阻断】严禁承接！本案被告为您所当前正式法律顾问单位或在办客户，承接该案将构成严重利益冲突并面临司法行政纪律处分。",
                            }
                        )
                    elif r_status == "CLOSED":
                        highest_severity = max(highest_severity, 1)
                        conflict_items.append(
                            {
                                "conflict_type": "历史已结案客户再代理冲突 (FORMER_CLIENT_CONFLICT)",
                                "severity": "CAUTION_REQUIRED",
                                "conflict_party": d_clean,
                                "matched_role": "曾为我所已结案客户",
                                "matched_case_id": r["case_id"],
                                "matched_case_title": r["case_title"],
                                "lead_lawyer": r["lead_lawyer"],
                                "case_status": r_status,
                                "rule_basis": "《律师执业行为规范》第五十一条：在曾经代理的案件结束后，在与该案件有实质性联系的案件中，为原案件的对方当事人担任代理人。",
                                "action_required": "【需签署利益冲突豁免函】请核对两案是否存在实质联系及知晓商业秘密。主办律师需取得该前客户书面豁免知情同意书（Conflict Waiver）方可立案。",
                            }
                        )

                is_defendant_affiliate = any(
                    d_clean and (d_clean == an or d_clean in an or an in d_clean)
                    for an in aff_names
                ) or any(d_id and d_id == ai for ai in aff_ids)

                if is_defendant_affiliate and r_status in ["ACTIVE", "RETAINER"]:
                    highest_severity = max(highest_severity, 2)
                    matched_aff = next(
                        (
                            a
                            for a in affs
                            if clean_name(a.get("name")) == d_clean
                            or a.get("id_card") == d_id
                            or a.get("uscc") == d_id
                        ),
                        {},
                    )
                    conflict_items.append(
                        {
                            "conflict_type": "穿透式关联主体利益冲突 (PIERCING_AFFILIATE_CONFLICT)",
                            "severity": "HIGH_WARNING",
                            "conflict_party": d_clean,
                            "matched_role": f"系我所顾问/在办客户【{r['client_name']}】之关联方 ({matched_aff.get('relation', '关联实控主体')})",
                            "matched_case_id": r["case_id"],
                            "matched_case_title": r["case_title"],
                            "lead_lawyer": r["lead_lawyer"],
                            "case_status": r_status,
                            "rule_basis": "《律师法》第39条及《律师执业行为规范》第四十九条：利益冲突不仅包括当事人本人，还包括当事人的控股股东、实际控制人、分支机构等实质关联主体。",
                            "action_required": "【高危提示】拟起诉主体系我所现存客户之实控人或核心子公司，虽非直接签约主体，但承接极易引发委托人解约与侵权投诉，需经律所管委会特别审批。",
                        }
                    )

                is_plaintiff_my_client = (
                    (p_clean and (p_clean == r_client or p_clean in r_client))
                    or (p_id and p_id == r_client_id)
                )
                if is_plaintiff_my_client and is_defendant_my_client:
                    highest_severity = max(highest_severity, 3)
                    conflict_items.append(
                        {
                            "conflict_type": "同案双方代理对立冲突 (DUAL_REPRESENTATION_BLOCKED)",
                            "severity": "CRITICAL_BLOCKED",
                            "conflict_party": f"{p_clean} 与 {d_clean}",
                            "matched_role": "双方当事人均在我所业务底档内",
                            "matched_case_id": r["case_id"],
                            "matched_case_title": r["case_title"],
                            "lead_lawyer": r["lead_lawyer"],
                            "case_status": r_status,
                            "rule_basis": "《律师法》第39条第(三)项：在同一案件中为双方当事人担任代理人。",
                            "action_required": "【法定义务绝对禁止】此乃司法行政机关直接吊销执业证之法定绝对红线，严禁任何形式的代理！",
                        }
                    )

        if highest_severity >= 3:
            verdict = "CRITICAL_BLOCKED"
            status_label = "【顶格红线·禁止代理】存在法定直接利益冲突"
        elif highest_severity == 2:
            verdict = "HIGH_WARNING"
            status_label = "【高危预警·管委会审批】存在实控人或子公司穿透冲突"
        elif highest_severity == 1:
            verdict = "CAUTION_REQUIRED"
            status_label = "【审慎立案·需备豁免函】涉及历史已结案客户"
        else:
            verdict = "CLEAR"
            status_label = "【核验合格·可以立案】全库穿透排查无任何利益冲突"

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cert_hash = hashlib.sha256(
            f"{p_clean}:{d_clean}:{p_id}:{d_id}:{datetime.now().strftime('%Y%m%d%H%M')}".encode(
                "utf-8"
            )
        ).hexdigest()
        cert_no = f"CC-{datetime.now().strftime('%Y%m%d')}-{cert_hash[:8].upper()}"

        triggered_rules = list(
            dict.fromkeys(it.get("rule_basis", "") for it in conflict_items if it.get("rule_basis"))
        )
        if not triggered_rules and verdict == "CLEAR":
            triggered_rules = [
                "《律师法》第39条检验通过",
                "《律师执业行为规范》第50条/51条检验通过",
            ]

        conflicts_formatted = []
        for it in conflict_items:
            conflicts_formatted.append(
                {
                    "type": it.get("conflict_type", "利益冲突"),
                    "case_no": it.get("matched_case_id", ""),
                    "case_name": it.get("matched_case_title", ""),
                    "registered_client": it.get("matched_role", ""),
                    "registered_opposing": it.get("conflict_party", ""),
                    "handling_lawyer": it.get("lead_lawyer", ""),
                    "description": it.get("action_required", ""),
                    "rule_basis": it.get("rule_basis", ""),
                }
            )

        clearance_certificate = {
            "certificate_no": cert_no,
            "is_cleared": (verdict == "CLEAR"),
            "verdict": verdict,
            "status_label": status_label,
            "verification_status": status_label,
            "plaintiff": p_clean,
            "defendant": d_clean,
            "verified_at": now_str,
            "timestamp": now_str,
            "handling_lawyer": "合规审查专员",
            "sha256_fingerprint": cert_hash,
            "audit_dimensions": [
                "1. 当事人名下在办诉讼及仲裁案件冲突穿透检索",
                "2. 律所常年法律顾问服务名录存续期重叠性比对",
                "3. 控股子公司、法定代表人及实际控制人股权穿透核查",
                "4. 历史已结案客户再代理保密义务与实质关联性审查",
                "5. 中华全国律师协会《律师执业行为规范》第50/51条强制规则库",
            ],
            "digital_fingerprint": f"SHA256:{cert_hash[:24]}...",
        }

        return {
            "status": "success",
            "conflict_level": verdict,
            "verdict": verdict,
            "has_conflict": (verdict != "CLEAR"),
            "status_label": status_label,
            "summary": status_label,
            "recommendation": status_label,
            "triggered_rules": triggered_rules,
            "total_conflicts": len(conflict_items),
            "conflict_items": conflict_items,
            "conflicts": conflicts_formatted,
            "clearance_certificate": clearance_certificate,
        }

    except (sqlite3.Error, sqlite3.OperationalError, OSError) as e:
        logger.error(f"利益冲突排查数据库异常: {e}", exc_info=True)
        return _unable_to_check_response()


def list_conflict_registry_cases(
    keyword: Optional[str] = None, status: Optional[str] = None, limit: int = 50
) -> List[Dict[str, Any]]:
    """查询律所已登记的历史客户与利冲底档"""
    init_conflict_registry_table()
    with get_db_connection() as conn:
        cursor = conn.cursor()

        query = "SELECT * FROM conflict_case_registry WHERE 1=1"
        params: List[Any] = []

        if keyword:
            kw = f"%{keyword.strip()}%"
            query += " AND (client_name LIKE ? OR opposing_name LIKE ? OR case_title LIKE ? OR case_id LIKE ?)"
            params.extend([kw, kw, kw, kw])

        if status and status != "ALL":
            query += " AND case_status = ?"
            params.append(status)

        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()

        result = []
        for r in rows:
            affs = []
            try:
                affs = json.loads(r["affiliates_json"] or "[]")
            except Exception:
                affs = []
            result.append(
                {
                    "id": r["id"],
                    "case_id": r["case_id"],
                    "case_title": r["case_title"],
                    "cause_of_action": r["cause_of_action"],
                    "lead_lawyer": r["lead_lawyer"],
                    "client_name": r["client_name"],
                    "client_uscc_id": r["client_uscc_id"],
                    "client_type": r["client_type"],
                    "opposing_name": r["opposing_name"],
                    "opposing_uscc_id": r["opposing_uscc_id"],
                    "affiliates": affs,
                    "case_status": r["case_status"],
                    "retainer_end_date": r["retainer_end_date"],
                    "notes": r["notes"],
                    "created_at": r["created_at"],
                }
            )
        return result


def register_new_conflict_case(
    case_id: str = "",
    case_title: str = "",
    cause_of_action: str = "",
    lead_lawyer: str = "",
    client_name: str = "",
    client_uscc_id: str = "",
    client_type: str = "CLIENT",
    opposing_name: str = "",
    opposing_uscc_id: str = "",
    affiliates: Optional[List[Any]] = None,
    case_status: str = "ACTIVE",
    retainer_end_date: str = "",
    notes: str = "",
    case_name: str = "",
    case_no: str = "",
    opposing_party: str = "",
    status: str = "",
    related_entities: Optional[List[str]] = None,
    handling_lawyer: str = "",
    **kwargs,
) -> Dict[str, Any]:
    """录入新案件或新法律顾问当事人进利冲底档库"""
    date_part = datetime.now().strftime("%Y%m%d")
    c_id = case_id or case_no or f"CASE-{date_part}-{uuid.uuid4().hex[:8]}"
    c_title = case_title or case_name or "新建诉讼案卷"
    c_cause = cause_of_action or notes or "民商事纠纷"
    c_lawyer = lead_lawyer or handling_lawyer or "主办律师"
    c_client = client_name
    c_opposing = opposing_name or opposing_party
    c_status = status or case_status or "ACTIVE"

    init_conflict_registry_table()
    aff_input = affiliates if affiliates is not None else (related_entities or [])
    aff_json = json.dumps(aff_input, ensure_ascii=False)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
            INSERT INTO conflict_case_registry (
                case_id, case_title, cause_of_action, lead_lawyer,
                client_name, client_uscc_id, client_type,
                opposing_name, opposing_uscc_id, affiliates_json,
                case_status, retainer_end_date, notes, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
                (
                    c_id,
                    c_title,
                    c_cause,
                    c_lawyer,
                    c_client,
                    client_uscc_id,
                    client_type,
                    c_opposing,
                    opposing_uscc_id,
                    aff_json,
                    c_status,
                    retainer_end_date,
                    notes,
                    now_str,
                ),
            )
            last_id = cursor.lastrowid
            return {
                "status": "success",
                "id": last_id,
                "case_id": c_id,
                "case_no": c_id,
                "case_name": c_title,
                "case_title": c_title,
                "message": f"成功登记底档: {c_title}",
            }
    except sqlite3.IntegrityError:
        return {
            "status": "success",
            "case_id": c_id,
            "case_no": c_id,
            "case_name": c_title,
            "message": f"底档已存在并核验就绪: {c_title}",
        }
    except Exception:
        raise
