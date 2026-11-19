"""

LawFlow 智律工作台 - 接案利益冲突穿透排查引擎 (Conflict of Interest Check Engine)

规则定性（律师 L-I20）：

- PROHIBITED：不得代理（如同一案件中为双方当事人担任代理人）

- WAIVABLE_WITH_CONSENT：告知并经委托人同意后可以代理（如律所与委托人存在法律服务关系、本所律师担任该委托人对方当事人的代理人）

- CAUTION：关联主体需人工判断

面向结果的《律师法》只写2017年修正文本第三十九条（利益冲突）和第三十八条（保密）。全国律协规范项次未核对前不得标为已核实，未命中也不签发验讫证书。

"""



from __future__ import annotations



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



_VALID_STATUSES = {"ACTIVE", "CLOSED", "RETAINER"}



# 冲突等级优先级（数值越大越严）：五级体系

_LEVEL_RANK = {

    "CLEAR": 0,

    "WAIVABLE_WITH_CONSENT": 1,

    "MANUAL_REVIEW": 2,

    "CAUTION": 2,  # 兼容旧代码引用

    "PROHIBITED": 3,

    "UNABLE_TO_CHECK": 4,

}



_CONSENT_NOTE = "须向各相关委托人书面告知利益冲突的事实和可能的后果，取得各方签署的知情同意书后方可接受委托；接受后，承办律师之间须对各自委托人的信息保密。"



_RULE_LAWYER_LAW = "《律师法》（2017年修正文本）第三十九条"

_RULE_LAWYER_CONFIDENTIALITY = "《律师法》（2017年修正文本）第三十八条"

_RULE_CONDUCT_PENDING = "全国律协《律师执业行为规范》利益冲突条款（项次待核对）"

_RULE_CONFLICT_BASIS = f"{_RULE_LAWYER_LAW}；{_RULE_CONDUCT_PENDING}"

_RULE_CONFIDENTIALITY_BASIS = f"{_RULE_LAWYER_CONFIDENTIALITY}；{_RULE_CONDUCT_PENDING}"

_NOT_CHECKED_ITEMS = (

    "刑事案件被害人代理与辩护",

    "分所及品牌关联所",

    "本所人员近亲属以外的其他任职",

)

_NOT_CHECKED_NOTE = "本次未检查：" + "、".join(_NOT_CHECKED_ITEMS) + "。"



# AC-8 必须显示的提示语

_PROMPT_GENERAL = (

    "本结果仅基于本所系统内已登记的数据自动比对，可能因数据不全、名称不一致而遗漏冲突。"

    "最终是否接受委托，以律师事务所利益冲突审查的决定为准（《律师执业管理办法》第二十六条）。本结果不构成法律意见。"

)

_PROMPT_PROHIBITED = "命中不可豁免的利益冲突：{reason}。依据：{basis}。不得接受委托；已接受的，应当终止委托关系。当事人同意不能豁免本情形。"

_PROMPT_WAIVABLE = "命中可豁免的利益冲突：{reason}。须向各相关委托人书面告知利益冲突的事实和可能的后果，取得各方签署的知情同意书后方可接受委托；接受后，承办律师之间须对各自委托人的信息保密。"

_PROMPT_MANUAL = "系统无法自动判断{reason}。人工确认前，请按禁止代理处理。"

_PROMPT_UNABLE = "底档存在无法识别的数据{reason}，本次检查不完整，不能作为可以接案的依据。"

_PROMPT_PERSONNEL = "本所人员及近亲属利益冲突：本项未检查"



def _normalize_same_matter(val: Any) -> Optional[str]:

    if val is None:

        return None

    if isinstance(val, bool):

        return "YES" if val else "NO"

    s = str(val).strip().upper()

    if s in ("是", "YES", "TRUE", "1", "同案", "同一案件"):

        return "YES"

    if s in ("否", "NO", "FALSE", "0", "非同案", "不同案件"):

        return "NO"

    if s in ("不确定", "UNCERTAIN", "UNKNOWN", "待定"):

        return "UNCERTAIN"

    return None



def _parse_date(d_str: Optional[str]) -> Optional[datetime]:

    if not d_str:

        return None

    m = re.search(r"(\d{4})[-/](\d{1,2})(?:[-/](\d{1,2}))?", str(d_str))

    if m:

        year = int(m.group(1))

        month = int(m.group(2))

        day = int(m.group(3)) if m.group(3) else 1

        return datetime(year, month, day)

    return None





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



    try:

        from gateway.utils.firm_roster import ensure_firm_roster_table

        ensure_firm_roster_table()

    except Exception as roster_exc:

        logger.warning(f"本所名册表初始化失败: {roster_exc}")

    if _should_seed_demo() and not _CONFLICT_DEMO_SEEDED:

        seed_demo_conflict_cases()

        _CONFLICT_DEMO_SEEDED = True

    scrub_demo_conflict_placeholders()





init_conflict_database = init_conflict_registry_table





def scrub_demo_conflict_placeholders() -> None:

    """已写入的演示底档不再把占位符显示成待律师核实。"""

    try:

        with get_db_connection() as conn:

            cursor = conn.cursor()

            cursor.execute(

                """

                UPDATE conflict_case_registry

                SET case_id = REPLACE(case_id, 'TODO(律师核实)-', ''),

                    client_uscc_id = REPLACE(IFNULL(client_uscc_id, ''), 'TODO(律师核实)', '未录入'),

                    opposing_uscc_id = REPLACE(IFNULL(opposing_uscc_id, ''), 'TODO(律师核实)', '未录入'),

                    affiliates_json = REPLACE(IFNULL(affiliates_json, ''), 'TODO(律师核实)', '未录入'),

                    notes = REPLACE(IFNULL(notes, ''), '细节 TODO(律师核实)。', '证件号、统一社会信用代码都没有录入。')

                WHERE case_title LIKE '%【演示】%'

                  AND (

                    case_id LIKE '%TODO(律师核实)%'

                    OR IFNULL(client_uscc_id, '') LIKE '%TODO(律师核实)%'

                    OR IFNULL(opposing_uscc_id, '') LIKE '%TODO(律师核实)%'

                    OR IFNULL(affiliates_json, '') LIKE '%TODO(律师核实)%'

                    OR IFNULL(notes, '') LIKE '%TODO(律师核实)%'

                  )

                """

            )

    except (sqlite3.Error, OSError) as e:

        logger.warning(f"清理演示利冲占位符失败: {e}")





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

                "DEMO-008",

                "【演示】北京宏达商贸有限公司常年法律顾问服务案",

                "常年法律顾问",

                "陈合伙人",

                "北京宏达商贸有限公司",

                "未录入",

                "RETAINER_CLIENT",

                "无指定特定相对人",

                "",

                json.dumps(

                    [

                        {

                            "name": "张三",

                            "relation": "法定代表人/实际控制人",

                            "id_card": "未录入",

                        },

                        {

                            "name": "北京宏达供应链管理有限公司",

                            "relation": "全资子公司",

                            "uscc": "未录入",

                        },

                    ],

                    ensure_ascii=False,

                ),

                "RETAINER",

                "2027-12-31",

                "【演示】存续期常年顾问客户示意底档。证件号、统一社会信用代码都没有录入。",

                "2023-01-01 09:00:00",

            ),

            (

                "DEMO-105",

                "【演示】智科云服诉华腾物流技术开发合同纠纷案",

                "技术开发合同纠纷",

                "王大状",

                "智科云服信息技术（北京）有限公司",

                "未录入",

                "LITIGATION_CLIENT",

                "华腾物流网络技术有限公司",

                "未录入",

                json.dumps(

                    [

                        {"name": "华腾云仓（天津）网络有限公司", "relation": "控股子公司"},

                        {"name": "赵华腾", "relation": "被告实控人"},

                    ],

                    ensure_ascii=False,

                ),

                "ACTIVE",

                "",

                "【演示】在办技术合同案件示意底档。证件号、统一社会信用代码都没有录入。",

                "2023-09-01 14:00:00",

            ),

            (

                "DEMO-072",

                "【演示】中建天成建设工程集团诉宏远实业施工合同纠纷案",

                "建设工程施工合同纠纷",

                "李合伙人",

                "中建天成建设工程集团有限公司",

                "未录入",

                "LITIGATION_CLIENT",

                "北京宏远实业开发有限公司",

                "未录入",

                json.dumps(

                    [{"name": "王宏远", "relation": "宏远实业法定代表人"}],

                    ensure_ascii=False,

                ),

                "CLOSED",

                "",

                "【演示】已结案施工合同示意底档。证件号、统一社会信用代码都没有录入。",

                "2022-05-10 10:30:00",

            ),

            (

                "DEMO-019",

                "【演示】李四诉张三民间借贷纠纷案",

                "民间借贷纠纷",

                "王大状",

                "李四",

                "未录入",

                "LITIGATION_CLIENT",

                "张三",

                "未录入",

                json.dumps(

                    [{"name": "王五", "relation": "指示付款第三方账户/宏达出纳"}],

                    ensure_ascii=False,

                ),

                "ACTIVE",

                "",

                "【演示】在办民间借贷示意底档。证件号、统一社会信用代码都没有录入。",

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

    _CONFLICT_DEMO_SEEDED = True

    return n





def clean_name(name: Optional[str]) -> str:

    if not name:

        return ""

    n = re.sub(r"[\(（].*?[\)）]", "", name).strip()

    return n





def _name_match(a: str, b: str) -> bool:

    if not a or not b:

        return False

    return a == b or a in b or b in a





def _unable_to_check_response() -> Dict[str, Any]:

    return {

        "status": "error",

        "conflict_level": "UNABLE_TO_CHECK",

        "verdict": "UNABLE_TO_CHECK",

        "has_conflict": None,

        "requires_consent": False,

        "consent_note": "",

        "status_label": "无法完成利益冲突排查，请稍后重试或人工排查",

        "summary": "无法完成利益冲突排查，请稍后重试或人工排查",

        "recommendation": "无法完成利益冲突排查，请稍后重试或人工排查",

        "message": "无法完成利益冲突排查，请稍后重试或人工排查",

        "not_checked": list(_NOT_CHECKED_ITEMS),

        "not_checked_note": _NOT_CHECKED_NOTE,

        "triggered_rules": [],

        "total_conflicts": 0,

        "conflict_items": [],

        "conflicts": [],

    }





def _make_item(

    *,

    conflict_type: str,

    level: str,

    conflict_party: str,

    matched_role: str,

    record: Any,

    action_required: str,

) -> Dict[str, Any]:

    return {

        "conflict_type": conflict_type,

        "severity": level,

        "conflict_level": level,

        "conflict_party": conflict_party,

        "matched_role": matched_role,

        "matched_case_id": record["case_id"],

        "matched_case_title": record["case_title"],

        "lead_lawyer": record["lead_lawyer"],

        "case_status": record["case_status"],

        "rule_basis": _RULE_CONFLICT_BASIS,

        "rule_verified": False,

        "action_required": action_required,

        "requires_consent": level == "WAIVABLE_WITH_CONSENT",

        "consent_note": _CONSENT_NOTE if level == "WAIVABLE_WITH_CONSENT" else "",

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

    is_same_matter: Optional[str] = None,

    allow_retainer_consent: bool = False,

    merge_branch_offices: bool = True,

    require_all_parties_consent: bool = True,

    check_date: Optional[str] = None,

    subsequent_stage: Optional[bool] = None,

    exclude_case_id: Optional[str] = None,

    **kwargs,

) -> Dict[str, Any]:

    """

    LawFlow 律所级利益冲突穿透排查（依据 LF-017 AC-1～AC-16 与 T-012）：

    五级定性体系：

    1. PROHIBITED：禁止代理（不可豁免）

    2. WAIVABLE_WITH_CONSENT：经各方书面同意可代理

    3. MANUAL_REVIEW：需人工判断（确认前按禁止处理，不能出具接案结论）

    4. UNABLE_TO_CHECK：无法检查（数据缺失或底档状态异常）

    5. CLEAR：未发现冲突

    """

    p_raw = plaintiff_name or client_name

    d_raw = defendant_name or opposing_party

    p_id_raw = plaintiff_id or client_id_or_code

    d_id_raw = defendant_id or opposing_id_or_code



    p_clean = clean_name(p_raw)

    d_clean = clean_name(d_raw)

    p_id = (p_id_raw or "").strip()

    d_id = (d_id_raw or "").strip()



    same_matter_param = (

        is_same_matter

        if is_same_matter is not None

        else kwargs.get("same_matter", kwargs.get("is_same_case"))

    )

    same_matter_norm = _normalize_same_matter(same_matter_param)



    is_subsequent = (

        bool(subsequent_stage)

        or bool(kwargs.get("is_subsequent_stage"))

        or any(kw in (case_subject or "") for kw in ("二审", "再审", "执行", "破产衍生", "执行异议"))

    )



    now_dt = _parse_date(check_date) or datetime.now()



    conflict_items: List[Dict[str, Any]] = []

    highest_rank = 0



    plaintiff_client_hits: List[Any] = []

    defendant_client_hits: List[Any] = []



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



            has_unable_record = False

            unable_reasons = []



            comparable_count = 0

            for row in records:
                r = dict(row)

                if exclude_case_id and str(r.get("case_id") or "") == str(exclude_case_id).strip():

                    continue

                if _registry_record_comparable(r):

                    comparable_count += 1

                r_client = clean_name(r["client_name"])

                r_opposing = clean_name(r["opposing_name"])

                r_status = (r["case_status"] or "").strip().upper()

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



                # 四向交叉比对

                p_matches_client = _name_match(p_clean, r_client) or (bool(p_id) and p_id == r_client_id)

                p_matches_opposing = _name_match(p_clean, r_opposing) or (bool(p_id) and p_id == r_opposing_id)

                d_matches_client = _name_match(d_clean, r_client) or (bool(d_id) and d_id == r_client_id)

                d_matches_opposing = _name_match(d_clean, r_opposing) or (bool(d_id) and d_id == r_opposing_id)



                is_defendant_affiliate = any(

                    _name_match(d_clean, an) for an in aff_names

                ) or any(d_id and d_id == ai for ai in aff_ids)



                hit_any = p_matches_client or p_matches_opposing or d_matches_client or d_matches_opposing or is_defendant_affiliate



                if not hit_any:

                    continue



                if p_matches_client:

                    plaintiff_client_hits.append(r)

                if d_matches_client:

                    defendant_client_hits.append(r)



                # AC-5: 遇到异常记录输出「无法检查」

                if r_status not in _VALID_STATUSES:

                    has_unable_record = True

                    rec_id = r["case_id"] or str(r["id"])

                    reason_msg = f"〔记录编号: {rec_id}，状态: '{r['case_status']}'〕"

                    unable_reasons.append(reason_msg)

                    conflict_items.append({

                        "conflict_type": "底档数据异常无法排查 (DATA_ANOMALY)",

                        "severity": "UNABLE_TO_CHECK",

                        "conflict_level": "UNABLE_TO_CHECK",

                        "conflict_party": f"{p_clean} / {d_clean}",

                        "matched_role": f"命中底档异常记录【{r['case_title']}】",

                        "matched_case_id": r["case_id"],

                        "matched_case_title": r["case_title"],

                        "lead_lawyer": r["lead_lawyer"],

                        "case_status": r["case_status"],

                        "rule_basis": "《律师事务所管理办法》第四十六条第二款",

                        "rule_verified": False,

                        "action_required": f"底档存在无法识别的数据{reason_msg}，本次检查不完整，不能作为可以接案的依据。",

                        "requires_consent": False,

                        "consent_note": "",

                    })

                    continue



                # 1. 拟委托人在在办案件中为对方当事人 (p matches opposing, status == ACTIVE)

                if p_matches_opposing and r_status == "ACTIVE":

                    if d_matches_client:

                        if same_matter_norm == "YES":

                            # TC1: 在办案件对方委托同一案件 -> PROHIBITED

                            conflict_items.append({

                                "conflict_type": "在办案件对方委托同一案件冲突 (ACTIVE_OPPOSING_SAME_MATTER)",

                                "severity": "PROHIBITED",

                                "conflict_level": "PROHIBITED",

                                "conflict_party": f"{p_clean} 与 {d_clean}",

                                "matched_role": f"拟委托人系在办案【{r['case_title']}】对方当事人",

                                "matched_case_id": r["case_id"],

                                "matched_case_title": r["case_title"],

                                "lead_lawyer": r["lead_lawyer"],

                                "case_status": r["case_status"],

                                "rule_basis": _RULE_CONFLICT_BASIS,

                                "rule_verified": False,

                                "action_required": f"【不得代理】命中不可豁免的利益冲突：拟委托人系在办案件【{r['case_title']}】之对方当事人，且为同一案件。依据《律师法》及行业规范，不得接受委托；已接受的，应当终止委托关系。当事人同意不能豁免本情形。",

                                "requires_consent": False,

                                "consent_note": "",

                            })

                        elif same_matter_norm == "NO":

                            # TC3: 委托非同一案件其他法律业务 -> WAIVABLE_WITH_CONSENT

                            conflict_items.append({

                                "conflict_type": "在办案件对方委托其他非同一案件业务 (ACTIVE_OPPOSING_OTHER_MATTER)",

                                "severity": "WAIVABLE_WITH_CONSENT",

                                "conflict_level": "WAIVABLE_WITH_CONSENT",

                                "conflict_party": f"{p_clean} 与 {d_clean}",

                                "matched_role": f"拟委托人系在办案【{r['case_title']}】对方当事人",

                                "matched_case_id": r["case_id"],

                                "matched_case_title": r["case_title"],

                                "lead_lawyer": r["lead_lawyer"],

                                "case_status": r["case_status"],

                                "rule_basis": _RULE_CONFLICT_BASIS,

                                "rule_verified": False,

                                "action_required": f"【须告知并经同意】命中可豁免的利益冲突：拟委托人系在办案件对方当事人，拟委托非同一案件。须向各相关委托人（在办案件委托人及拟委托人）书面告知利益冲突的事实和可能的后果，取得各方签署的知情同意书后方可接受委托；承办律师之间须对各自委托人的信息保密。",

                                "requires_consent": True,

                                "consent_note": _CONSENT_NOTE,

                            })

                        else:

                            # TC2: 是否同一案件未填或不确定 -> MANUAL_REVIEW

                            conflict_items.append({

                                "conflict_type": "在办案件对方委托案件同一性未确认 (ACTIVE_OPPOSING_UNCERTAIN_MATTER)",

                                "severity": "MANUAL_REVIEW",

                                "conflict_level": "MANUAL_REVIEW",

                                "conflict_party": f"{p_clean} 与 {d_clean}",

                                "matched_role": f"拟委托人系在办案【{r['case_title']}】对方当事人",

                                "matched_case_id": r["case_id"],

                                "matched_case_title": r["case_title"],

                                "lead_lawyer": r["lead_lawyer"],

                                "case_status": r["case_status"],

                                "rule_basis": _RULE_CONFLICT_BASIS,

                                "rule_verified": False,

                                "action_required": "【需人工判断】系统无法自动判断是否同一案件。人工确认前，请按禁止代理处理，不能出具接案结论。",

                                "requires_consent": False,

                                "consent_note": "",

                            })

                    else:

                        # d 不是底档委托人 (例如起诉丁公司)

                        if same_matter_norm == "NO":

                            conflict_items.append({

                                "conflict_type": "在办案件对方委托其他独立法律事务 (ACTIVE_OPPOSING_UNRELATED_MATTER)",

                                "severity": "WAIVABLE_WITH_CONSENT",

                                "conflict_level": "WAIVABLE_WITH_CONSENT",

                                "conflict_party": p_clean,

                                "matched_role": f"拟委托人系在办案【{r['case_title']}】对方当事人",

                                "matched_case_id": r["case_id"],

                                "matched_case_title": r["case_title"],

                                "lead_lawyer": r["lead_lawyer"],

                                "case_status": r["case_status"],

                                "rule_basis": _RULE_CONFLICT_BASIS,

                                "rule_verified": False,

                                "action_required": f"【须告知并经同意】命中可豁免利益冲突：拟委托人系我所在办案件【{r['case_title']}】之对方当事人。须向各相关委托人书面告知并取得签署知情同意书。",

                                "requires_consent": True,

                                "consent_note": _CONSENT_NOTE,

                            })

                        elif same_matter_norm == "YES":

                            conflict_items.append({

                                "conflict_type": "在办案件对方委托同源法律事务 (ACTIVE_OPPOSING_SAME_FACTS)",

                                "severity": "PROHIBITED",

                                "conflict_level": "PROHIBITED",

                                "conflict_party": p_clean,

                                "matched_role": f"拟委托人系在办案【{r['case_title']}】对方当事人",

                                "matched_case_id": r["case_id"],

                                "matched_case_title": r["case_title"],

                                "lead_lawyer": r["lead_lawyer"],

                                "case_status": r["case_status"],

                                "rule_basis": _RULE_CONFLICT_BASIS,

                                "rule_verified": False,

                                "action_required": "【不得代理】拟委托事项与在办案件基于同一法律事实或争议，不得接受委托。",

                                "requires_consent": False,

                                "consent_note": "",

                            })

                        else:

                            conflict_items.append({

                                "conflict_type": "在办案件对方委托事务关联性待定 (ACTIVE_OPPOSING_FACTS_UNCERTAIN)",

                                "severity": "MANUAL_REVIEW",

                                "conflict_level": "MANUAL_REVIEW",

                                "conflict_party": p_clean,

                                "matched_role": f"拟委托人系在办案【{r['case_title']}】对方当事人",

                                "matched_case_id": r["case_id"],

                                "matched_case_title": r["case_title"],

                                "lead_lawyer": r["lead_lawyer"],

                                "case_status": r["case_status"],

                                "rule_basis": _RULE_CONFLICT_BASIS,

                                "rule_verified": False,

                                "action_required": "【需人工判断】系统无法自动判断是否基于同一法律事实或争议。人工确认前，请按禁止代理处理。",

                                "requires_consent": False,

                                "consent_note": "",

                            })



                # 2. 拟对方 (d) 是本所常年法律顾问单位 (RETAINER)

                elif d_matches_client and r_status == "RETAINER":

                    if not allow_retainer_consent:

                        # TC4: 默认禁止代理

                        conflict_items.append({

                            "conflict_type": "常年法律顾问相对人直接冲突 (RETAINER_OPPOSING_PROHIBITED)",

                            "severity": "PROHIBITED",

                            "conflict_level": "PROHIBITED",

                            "conflict_party": d_clean,

                            "matched_role": "现为我所常年法律顾问单位",

                            "matched_case_id": r["case_id"],

                            "matched_case_title": r["case_title"],

                            "lead_lawyer": r["lead_lawyer"],

                            "case_status": r["case_status"],

                            "rule_basis": _RULE_CONFLICT_BASIS,

                            "rule_verified": False,

                            "action_required": f"【不得代理】命中不可豁免的利益冲突：拟相对方【{r['client_name']}】系我所存续期常年法律顾问单位。不得接受委托；已接受的，应当终止委托关系。",

                            "requires_consent": False,

                            "consent_note": "",

                        })

                    else:

                        conflict_items.append({

                            "conflict_type": "常年法律顾问相对人利益冲突 (RETAINER_OPPOSING_CONSENT)",

                            "severity": "WAIVABLE_WITH_CONSENT",

                            "conflict_level": "WAIVABLE_WITH_CONSENT",

                            "conflict_party": d_clean,

                            "matched_role": "现为我所常年法律顾问单位",

                            "matched_case_id": r["case_id"],

                            "matched_case_title": r["case_title"],

                            "lead_lawyer": r["lead_lawyer"],

                            "case_status": r["case_status"],

                            "rule_basis": _RULE_CONFLICT_BASIS,

                            "rule_verified": False,

                            "action_required": f"【须告知并经同意】拟相对方【{r['client_name']}】系我所常年法律顾问单位。须向各相关委托人书面告知利益冲突并取得书面知情同意书。",

                            "requires_consent": True,

                            "consent_note": _CONSENT_NOTE,

                        })



                # 3. 拟对方 (d) 是本所在办诉讼客户 (ACTIVE)

                elif d_matches_client and r_status == "ACTIVE" and not p_matches_opposing:

                    if same_matter_norm == "YES":

                        conflict_items.append({

                            "conflict_type": "拟起诉在办客户同一案件冲突 (DIRECT_CLIENT_OPPOSING_SAME)",

                            "severity": "PROHIBITED",

                            "conflict_level": "PROHIBITED",

                            "conflict_party": d_clean,

                            "matched_role": "现为我所在办诉讼客户",

                            "matched_case_id": r["case_id"],

                            "matched_case_title": r["case_title"],

                            "lead_lawyer": r["lead_lawyer"],

                            "case_status": r["case_status"],

                            "rule_basis": _RULE_CONFLICT_BASIS,

                            "rule_verified": False,

                            "action_required": f"【不得代理】拟相对方【{r['client_name']}】系我所在办客户，且涉及同一争议。不得接受委托。",

                            "requires_consent": False,

                            "consent_note": "",

                        })

                    elif same_matter_norm == "NO":

                        conflict_items.append({

                            "conflict_type": "拟起诉在办客户非同一案件冲突 (DIRECT_CLIENT_OPPOSING_OTHER)",

                            "severity": "WAIVABLE_WITH_CONSENT",

                            "conflict_level": "WAIVABLE_WITH_CONSENT",

                            "conflict_party": d_clean,

                            "matched_role": "现为我所在办诉讼客户",

                            "matched_case_id": r["case_id"],

                            "matched_case_title": r["case_title"],

                            "lead_lawyer": r["lead_lawyer"],

                            "case_status": r["case_status"],

                            "rule_basis": _RULE_CONFLICT_BASIS,

                            "rule_verified": False,

                            "action_required": f"【须告知并经同意】拟相对方【{r['client_name']}】系我所在办客户。须向各相关委托人书面告知并取得书面同意后方可代理。",

                            "requires_consent": True,

                            "consent_note": _CONSENT_NOTE,

                        })

                    else:

                        conflict_items.append({

                            "conflict_type": "拟起诉在办客户同一性未确认 (DIRECT_CLIENT_OPPOSING_UNCERTAIN)",

                            "severity": "MANUAL_REVIEW",

                            "conflict_level": "MANUAL_REVIEW",

                            "conflict_party": d_clean,

                            "matched_role": "现为我所在办诉讼客户",

                            "matched_case_id": r["case_id"],

                            "matched_case_title": r["case_title"],

                            "lead_lawyer": r["lead_lawyer"],

                            "case_status": r["case_status"],

                            "rule_basis": _RULE_CONFLICT_BASIS,

                            "rule_verified": False,

                            "action_required": "【需人工判断】拟相对方为我所在办客户，系统无法自动判断是否同一案件。人工确认前，请按禁止代理处理。",

                            "requires_consent": False,

                            "consent_note": "",

                        })



                # 4. 已结案件 (CLOSED)

                elif (p_matches_opposing or d_matches_client) and r_status == "CLOSED":

                    closed_date_str = r.get("retainer_end_date") or r.get("notes") or r.get("created_at") or ""

                    closed_dt = _parse_date(closed_date_str)

                    elapsed_days = (now_dt - closed_dt).days if closed_dt else 999



                    if is_subsequent or (same_matter_norm == "YES" and is_subsequent):

                        # TC5: 已结案件后续审理或执行阶段接受原对方当事人委托 -> PROHIBITED

                        conflict_items.append({

                            "conflict_type": "已结案件同一案件后续阶段再代理冲突 (CLOSED_SUBSEQUENT_STAGE_PROHIBITED)",

                            "severity": "PROHIBITED",

                            "conflict_level": "PROHIBITED",

                            "conflict_party": f"{p_clean} 与 {d_clean}",

                            "matched_role": f"曾为我所已结案件【{r['case_title']}】对方当事人",

                            "matched_case_id": r["case_id"],

                            "matched_case_title": r["case_title"],

                            "lead_lawyer": r["lead_lawyer"],

                            "case_status": r["case_status"],

                            "rule_basis": _RULE_CONFLICT_BASIS,

                            "rule_verified": False,

                            "action_required": "【不得代理】同一案件已结案后续阶段（二审/再审/执行）接受原对方当事人委托。依据行业规范，不受结案时间限制，不得接受委托；当事人同意不能豁免本情形。",

                            "requires_consent": False,

                            "consent_note": "",

                        })

                    elif elapsed_days <= 365 and same_matter_norm == "YES":

                        # TC6: 终止后1年内，就同一法律事务接受原对方委托 -> WAIVABLE_WITH_CONSENT

                        conflict_items.append({

                            "conflict_type": "已结案件一年内同一法律事务再代理冲突 (CLOSED_WITHIN_1YR_SAME_MATTER)",

                            "severity": "WAIVABLE_WITH_CONSENT",

                            "conflict_level": "WAIVABLE_WITH_CONSENT",

                            "conflict_party": f"{p_clean} 与 {d_clean}",

                            "matched_role": f"曾为我所已结案件【{r['case_title']}】对方当事人",

                            "matched_case_id": r["case_id"],

                            "matched_case_title": r["case_title"],

                            "lead_lawyer": r["lead_lawyer"],

                            "case_status": r["case_status"],

                            "rule_basis": _RULE_CONFLICT_BASIS,

                            "rule_verified": False,

                            "action_required": "【须告知并经同意】原委托关系终止后一年内就同一法律事务接受原对方委托。须向各相关委托人书面告知利益冲突并取得知情同意书，承办律师之间负有信息保密义务。",

                            "requires_consent": True,

                            "consent_note": _CONSENT_NOTE,

                        })

                    else:

                        # TC7: 超过1年或无关争议 -> MANUAL_REVIEW

                        conflict_items.append({

                            "conflict_type": "已结案件客户保密义务与关联性审查 (CLOSED_CONFIDENTIALITY_REVIEW)",

                            "severity": "MANUAL_REVIEW",

                            "conflict_level": "MANUAL_REVIEW",

                            "conflict_party": f"{p_clean} 与 {d_clean}",

                            "matched_role": f"曾为我所已结案件【{r['case_title']}】之当事人",

                            "matched_case_id": r["case_id"],

                            "matched_case_title": r["case_title"],

                            "lead_lawyer": r["lead_lawyer"],

                            "case_status": r["case_status"],

                            "rule_basis": _RULE_CONFIDENTIALITY_BASIS,

                            "rule_verified": False,

                            "action_required": "【需人工判断】系统无法自动判断保密信息相关性。律师对原委托人的保密义务不随结案终止，须核查原案获取的保密信息是否与新案相关。人工确认前，请按禁止代理处理。",

                            "requires_consent": False,

                            "consent_note": "",

                        })



                # 5. 穿透式关联主体 (is_defendant_affiliate)

                elif is_defendant_affiliate and r_status in ["ACTIVE", "RETAINER"]:

                    if not d_matches_client:

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

                        conflict_items.append({

                            "conflict_type": "穿透式关联主体利益冲突 (PIERCING_AFFILIATE_CONFLICT)",

                            "severity": "MANUAL_REVIEW",

                            "conflict_level": "MANUAL_REVIEW",

                            "conflict_party": d_clean,

                            "matched_role": f"系我所顾问/在办客户【{r['client_name']}】之关联方 ({matched_aff.get('relation', '关联实控主体')})",

                            "matched_case_id": r["case_id"],

                            "matched_case_title": r["case_title"],

                            "lead_lawyer": r["lead_lawyer"],

                            "case_status": r["case_status"],

                            "rule_basis": _RULE_CONFLICT_BASIS,

                            "rule_verified": False,

                            "action_required": "【需人工判断】拟起诉主体系我所现存客户之关联方，请律所按内部程序人工审查后再决定是否承接。",

                            "requires_consent": False,

                            "consent_note": "",

                        })



            # AC-6: 同案双方代理判断：只有在同一案件中代理双方，才禁止

            # 双方当事人若分别在我所不同底档中为客户，非同一案件不再一律禁止

            if plaintiff_client_hits and defendant_client_hits:

                if same_matter_norm == "YES":

                    hit = defendant_client_hits[0]

                    conflict_items.append({

                        "conflict_type": "同一案件双方代理禁止冲突 (DUAL_REPRESENTATION_BLOCKED)",

                        "severity": "PROHIBITED",

                        "conflict_level": "PROHIBITED",

                        "conflict_party": f"{p_clean} 与 {d_clean}",

                        "matched_role": "双方当事人均在我所业务底档内且为同一案件",

                        "matched_case_id": hit["case_id"],

                        "matched_case_title": hit["case_title"],

                        "lead_lawyer": hit["lead_lawyer"],

                        "case_status": hit["case_status"],

                        "rule_basis": _RULE_CONFLICT_BASIS,

                        "rule_verified": False,

                        "action_required": "【不得代理】同一案件中为双方当事人担任代理人，严禁承接；已接受的应当终止委托关系。",

                        "requires_consent": False,

                        "consent_note": "",

                    })

                elif same_matter_norm is None or same_matter_norm == "UNCERTAIN":

                    hit = defendant_client_hits[0]

                    conflict_items.append({

                        "conflict_type": "双方均为客户同一性未确认 (DUAL_CLIENTS_UNCERTAIN_MATTER)",

                        "severity": "MANUAL_REVIEW",

                        "conflict_level": "MANUAL_REVIEW",

                        "conflict_party": f"{p_clean} 与 {d_clean}",

                        "matched_role": "双方当事人均在我所客户名册中",

                        "matched_case_id": hit["case_id"],

                        "matched_case_title": hit["case_title"],

                        "lead_lawyer": hit["lead_lawyer"],

                        "case_status": hit["case_status"],

                        "rule_basis": _RULE_CONFLICT_BASIS,

                        "rule_verified": False,

                        "action_required": "【需人工判断】双方当事人均曾委托本所，系统无法自动判断是否同一案件。人工确认前，请按禁止代理处理。",

                        "requires_consent": False,

                        "consent_note": "",

                    })

                elif same_matter_norm == "NO":

                    hit = defendant_client_hits[0]

                    conflict_items.append({

                        "conflict_type": "双方客户非同一案件业务冲突 (DUAL_CLIENTS_DIFFERENT_MATTER)",

                        "severity": "WAIVABLE_WITH_CONSENT",

                        "conflict_level": "WAIVABLE_WITH_CONSENT",

                        "conflict_party": f"{p_clean} 与 {d_clean}",

                        "matched_role": "双方当事人在不同案件中分别曾为我所客户",

                        "matched_case_id": hit["case_id"],

                        "matched_case_title": hit["case_title"],

                        "lead_lawyer": hit["lead_lawyer"],

                        "case_status": hit["case_status"],

                        "rule_basis": _RULE_CONFLICT_BASIS,

                        "rule_verified": False,

                        "action_required": "【须告知并经同意】双方当事人在不同案件中为我所客户。经各方书面知情同意后可以代理。",

                        "requires_consent": True,

                        "consent_note": _CONSENT_NOTE,

                    })



        # 计算最高冲突等级

        for it in conflict_items:

            lvl = it.get("conflict_level", "CLEAR")

            highest_rank = max(highest_rank, _LEVEL_RANK.get(lvl, 0))



        if has_unable_record:

            verdict = "UNABLE_TO_CHECK"

            status_label = "【无法检查】底档数据异常或无法识别，本次检查不完整"

            recommendation = _PROMPT_UNABLE.format(reason="".join(unable_reasons))

        elif highest_rank >= _LEVEL_RANK["PROHIBITED"]:

            verdict = "PROHIBITED"

            status_label = "【不得代理】存在不可豁免的法定利益冲突"

            reasons_txt = "；".join([it["conflict_type"] for it in conflict_items if it.get("conflict_level") == "PROHIBITED"])

            rules_txt = "、".join(dict.fromkeys([it.get("rule_basis", "") for it in conflict_items if it.get("conflict_level") == "PROHIBITED"]))

            recommendation = _PROMPT_PROHIBITED.format(reason=reasons_txt, basis=rules_txt)

        elif highest_rank >= _LEVEL_RANK["MANUAL_REVIEW"]:

            verdict = "MANUAL_REVIEW"

            status_label = "【需人工判断】存在利益冲突线索，人工确认前按禁止处理"

            reasons_txt = "〔是否同一案件 / 关联关系 / 保密信息相关性〕"

            recommendation = _PROMPT_MANUAL.format(reason=reasons_txt)

        elif highest_rank >= _LEVEL_RANK["WAIVABLE_WITH_CONSENT"]:

            verdict = "WAIVABLE_WITH_CONSENT"

            status_label = "【须告知并经同意】存在可豁免利益冲突，须取得各方书面同意"

            reasons_txt = "；".join([it["conflict_type"] for it in conflict_items if it.get("conflict_level") == "WAIVABLE_WITH_CONSENT"])

            recommendation = _PROMPT_WAIVABLE.format(reason=reasons_txt)

        else:

            verdict = "CLEAR"

            if comparable_count <= 0:

                status_label = "未比对到已登记记录"

                recommendation = "未比对到已登记记录"

            else:

                status_label = f"在已登记的 {comparable_count} 条记录中未发现冲突"

                recommendation = status_label



        requires_consent = (verdict == "WAIVABLE_WITH_CONSENT")



        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cert_no = ""


        triggered_rules = list(

            dict.fromkeys(it.get("rule_basis", "") for it in conflict_items if it.get("rule_basis"))

        )

        if not triggered_rules and verdict == "CLEAR":

            triggered_rules = [

                _RULE_LAWYER_LAW,

                _RULE_CONDUCT_PENDING,

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

                    "rule_verified": it.get("rule_verified", False),

                    "conflict_level": it.get("conflict_level", ""),

                    "requires_consent": it.get("requires_consent", False),

                    "consent_note": it.get("consent_note", ""),

                }

            )



        try:

            from gateway.utils.firm_roster import screen_personnel

            personnel_line = screen_personnel(d_raw, d_id, party_ids=[p_id, d_id]).get("personnel_and_relatives_check") or _PROMPT_PERSONNEL

        except Exception as personnel_exc:

            logger.warning(f"本所名册比对失败，按未录入处理: {personnel_exc}")

            personnel_line = "本所人员未录入，此项未检查。本所人员及近亲属利益冲突：本项未检查。"

        clearance_certificate = {

            "certificate_no": cert_no,

            "is_cleared": False,

            "verdict": verdict,

            "status_label": status_label,

            "verification_status": status_label,

            "plaintiff": p_clean,

            "defendant": d_clean,

            "verified_at": "",

            "timestamp": now_str,

            "handling_lawyer": "",

            "sha256_fingerprint": "",

            "audit_dimensions": [

                "1. 当事人名下在办诉讼及仲裁案件冲突穿透检索",

                "2. 律所常年法律顾问服务名录存续期重叠性比对",

                "3. 控股子公司、法定代表人及实际控制人股权穿透核查",

                "4. 历史已结案客户再代理保密义务与实质关联性审查",

                f"5. {_RULE_LAWYER_LAW}；{_RULE_CONDUCT_PENDING}",

                f"6. {personnel_line}",

                f"7. {_NOT_CHECKED_NOTE}",

            ],

            "digital_fingerprint": "",

        }



        return {

            "status": "success",

            "conflict_level": verdict,

            "verdict": verdict,

            "has_conflict": None if verdict == "CLEAR" and comparable_count <= 0 else (verdict != "CLEAR"),

            "requires_consent": requires_consent,

            "consent_note": _CONSENT_NOTE if requires_consent else "",

            "status_label": status_label,

            "summary": status_label,

            "recommendation": recommendation,

            "general_prompt": _PROMPT_GENERAL + _NOT_CHECKED_NOTE,

            "personnel_and_relatives_check": personnel_line,

            "not_checked": list(_NOT_CHECKED_ITEMS),

            "not_checked_note": _NOT_CHECKED_NOTE,

            "registered_record_count": comparable_count,

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

    c_status = (status or case_status or "ACTIVE").strip().upper()

    if c_status not in _VALID_STATUSES:

        raise ValueError(f"case_status 必须为 ACTIVE / CLOSED / RETAINER 之一，非法值: '{c_status}'")



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




def _registry_record_comparable(record: Dict[str, Any]) -> bool:
    """有姓名或证件号才算可以比对的底档记录。占位证件号不算。"""
    client = clean_name(record.get("client_name"))
    opposing = clean_name(record.get("opposing_name"))
    ignored = {"", "未录入", "未填写", "无", "暂无", "不详", "未知", "NONE", "N/A", "NA", "-", "—"}
    client_id = str(record.get("client_uscc_id") or "").strip()
    opposing_id = str(record.get("opposing_uscc_id") or "").strip()
    if client_id in ignored:
        client_id = ""
    if opposing_id in ignored:
        opposing_id = ""
    return bool(client or opposing or client_id or opposing_id)


def upsert_matter_conflict_registry(matter: Dict[str, Any]) -> Dict[str, Any]:
    """把案件当事人写入 conflict_case_registry。同一 matter_id 覆盖原行。"""
    from gateway.utils.matter_intake import conflict_parties

    matter_id = str(matter.get("matter_id") or "").strip()
    if not matter_id:
        raise ValueError("matter_id 为空，不能写入利冲底档")
    parties = conflict_parties(matter)
    status = str(matter.get("status") or "active").strip().lower()
    case_status = "CLOSED" if status == "archived" else "ACTIVE"
    title = str(matter.get("title") or "").strip() or "未命名案件"
    cause = str(matter.get("cause_of_action") or "").strip() or "未填写案由"
    practice = matter.get("practice") if isinstance(matter.get("practice"), dict) else {}
    lawyer = str(
        practice.get("lead_lawyer") or practice.get("handling_lawyer") or "主办律师"
    ).strip() or "主办律师"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    init_conflict_registry_table()
    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO conflict_case_registry (
                case_id, case_title, cause_of_action, lead_lawyer,
                client_name, client_uscc_id, client_type,
                opposing_name, opposing_uscc_id, affiliates_json,
                case_status, retainer_end_date, notes, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(case_id) DO UPDATE SET
                case_title = excluded.case_title,
                cause_of_action = excluded.cause_of_action,
                lead_lawyer = excluded.lead_lawyer,
                client_name = excluded.client_name,
                client_uscc_id = excluded.client_uscc_id,
                client_type = excluded.client_type,
                opposing_name = excluded.opposing_name,
                opposing_uscc_id = excluded.opposing_uscc_id,
                case_status = excluded.case_status,
                notes = excluded.notes
            """,
            (
                matter_id,
                title,
                cause,
                lawyer,
                str(parties.get("client_name") or "").strip(),
                str(parties.get("client_id") or "").strip(),
                "LITIGATION_CLIENT",
                str(parties.get("opposing_name") or "").strip(),
                str(parties.get("opposing_id") or "").strip(),
                "[]",
                case_status,
                "",
                f"由案件空间 {matter_id} 同步，供后续委托比对。",
                now_str,
            ),
        )
    return {
        "case_id": matter_id,
        "client_name": str(parties.get("client_name") or "").strip(),
        "opposing_name": str(parties.get("opposing_name") or "").strip(),
    }


_REGISTRY_CREDENTIAL_KEYS = {
    "id_no",
    "id_card",
    "idcard",
    "id_number",
    "identity_no",
    "uscc",
    "credit_code",
    "unified_social_credit_code",
    "phone",
    "mobile",
    "tel",
    "email",
}


def clear_conflict_registry_credentials(case_id: str) -> Dict[str, Any]:
    """抹去底档里的证件号，保留当事人姓名。"""
    init_conflict_registry_table()
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT client_name, opposing_name, affiliates_json FROM conflict_case_registry WHERE case_id = ?",
            (case_id,),
        )
        row = cur.fetchone()
        if not row:
            return {
                "found": False,
                "keeps_names": False,
                "note": "利冲底档没有本案记录，因此没有当事人姓名可保留。",
            }
        client_name = str(row["client_name"] or "").strip()
        opposing_name = str(row["opposing_name"] or "").strip()
        try:
            affs = json.loads(row["affiliates_json"] or "[]")
        except (json.JSONDecodeError, TypeError):
            affs = []
        cleaned = []
        if isinstance(affs, list):
            for item in affs:
                if isinstance(item, dict):
                    cleaned.append({
                        key: value
                        for key, value in item.items()
                        if str(key).strip().lower() not in _REGISTRY_CREDENTIAL_KEYS
                    })
                else:
                    cleaned.append(item)
        cur.execute(
            """
            UPDATE conflict_case_registry
            SET client_uscc_id = '', opposing_uscc_id = '', affiliates_json = ?
            WHERE case_id = ?
            """,
            (json.dumps(cleaned, ensure_ascii=False), case_id),
        )
    names = [name for name in (client_name, opposing_name) if name]
    if names:
        return {
            "found": True,
            "keeps_names": True,
            "note": f"利冲底档仍保留当事人姓名（{'、'.join(names)}），底档中的证件号已抹去。",
        }
    return {
        "found": True,
        "keeps_names": False,
        "note": "利冲底档有本案记录，但没有当事人姓名。",
    }
