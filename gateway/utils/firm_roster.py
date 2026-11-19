# -*- coding: utf-8 -*-
"""本所律师名册：承办律师、执业证、事务所和近亲属。供接案利冲与立案文书共用。"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

_FAKE_IDENTITIES = {
    "王律师",
    "13900008888",
    "11101201510123456",
    "北京市京师律师事务所",
}

NOT_RECORDED_TEXT = (
    "本所人员未录入，此项未检查。本所人员及近亲属利益冲突：本项未检查。"
    "不能单独当作接案结论。"
)


def _conn():
    from gateway.utils.conflict_checker import get_db_connection

    return get_db_connection()


# 姓名分隔：空白，以及中点、间隔号、项目符号。全角标点先转半角后再剔除。
_NAME_SEPARATORS = re.compile(r"[\s·・•･∙⋅‧]+")
_IGNORED_CREDENTIALS = {
    "",
    "未录入",
    "未填写",
    "无",
    "暂无",
    "待填写",
    "不详",
    "未知",
    "无证件",
    "-",
    "—",
    "NONE",
    "N/A",
    "NA",
}


def _to_halfwidth(text: str) -> str:
    chars = []
    for ch in text:
        code = ord(ch)
        if code == 0x3000:
            chars.append(" ")
        elif 0xFF01 <= code <= 0xFF5E:
            chars.append(chr(code - 0xFEE0))
        else:
            chars.append(ch)
    return "".join(chars)


def normalize_person_name(value: Any) -> str:
    """比对前的姓名：去首尾空白、全角转半角、去掉中间空格和·・•。"""
    text = _to_halfwidth(str(value or "")).strip()
    return _NAME_SEPARATORS.sub("", text).casefold()


def normalize_credential(value: Any) -> str:
    """执业证号、身份证号：全角转半角，去掉空白和间隔号。空值和占位不算证件号。"""
    text = _to_halfwidth(str(value or "")).strip()
    text = _NAME_SEPARATORS.sub("", text).upper()
    if text in _IGNORED_CREDENTIALS or len(text) < 6:
        return ""
    return text


def names_are_similar(left: str, right: str) -> bool:
    """规范化后仍不相等，但一个姓名包含另一个，或等长且只差一个字。

    两个字的姓名只差一个字时不提示，避免同姓（张三/张四）大量误报。
    单字姓名被包含也不提示。
    """
    if not left or not right or left == right:
        return False
    shorter, longer = (left, right) if len(left) <= len(right) else (right, left)
    if shorter in longer:
        return len(shorter) >= 2
    if len(left) == len(right) and len(left) >= 3:
        return sum(a != b for a, b in zip(left, right)) == 1
    return False


def _norm(value: Any) -> str:
    return normalize_person_name(value)


def ensure_firm_roster_table() -> None:
    with _conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS firm_roster (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lawyer_name TEXT NOT NULL,
                license_no TEXT NOT NULL DEFAULT '',
                id_no TEXT NOT NULL DEFAULT '',
                law_firm TEXT NOT NULL DEFAULT '',
                phone TEXT NOT NULL DEFAULT '',
                relatives_json TEXT NOT NULL DEFAULT '[]',
                is_default INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(firm_roster)")}
        if "id_no" not in columns:
            conn.execute("ALTER TABLE firm_roster ADD COLUMN id_no TEXT NOT NULL DEFAULT ''")


def _row_to_lawyer(row) -> Dict[str, Any]:
    try:
        relatives = json.loads(row["relatives_json"] or "[]")
    except json.JSONDecodeError:
        relatives = []
    if not isinstance(relatives, list):
        relatives = []
    clean_relatives = []
    for item in relatives:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        rel_id = str(item.get("id_no") or item.get("id_number") or item.get("id_card") or "").strip()
        if rel_id in _FAKE_IDENTITIES:
            rel_id = ""
        clean_relatives.append({
            "name": name,
            "relation": str(item.get("relation") or "近亲属").strip() or "近亲属",
            "id_no": rel_id,
        })
    return {
        "id": row["id"],
        "lawyer_name": row["lawyer_name"],
        "license_no": row["license_no"] or "",
        "id_no": (row["id_no"] if "id_no" in row.keys() else "") or "",
        "law_firm": row["law_firm"] or "",
        "phone": row["phone"] or "",
        "relatives": clean_relatives,
        "is_default": bool(row["is_default"]),
    }


def list_lawyers() -> List[Dict[str, Any]]:
    ensure_firm_roster_table()
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM firm_roster ORDER BY is_default DESC, id ASC"
        ).fetchall()
    return [_row_to_lawyer(row) for row in rows]


def _reject_fake(field: str, value: str) -> None:
    if value in _FAKE_IDENTITIES:
        raise ValueError(f"{field}不能使用示例身份「{value}」。请填写本所真实资料，没有就留空。")


def save_lawyer(data: Dict[str, Any]) -> Dict[str, Any]:
    ensure_firm_roster_table()
    name = str(data.get("lawyer_name") or "").strip()
    if not name:
        raise ValueError("请填写律师姓名")
    _reject_fake("律师姓名", name)
    license_no = str(data.get("license_no") or "").strip()
    id_no = str(data.get("id_no") or data.get("id_number") or "").strip()
    law_firm = str(data.get("law_firm") or "").strip()
    phone = str(data.get("phone") or "").strip()
    _reject_fake("执业证号", license_no)
    _reject_fake("身份证号", id_no)
    _reject_fake("联系电话", phone)
    relatives_in = data.get("relatives")
    is_default = bool(data.get("is_default"))
    key = _norm(name)
    with _conn() as conn:
        existing = None
        for row in conn.execute("SELECT * FROM firm_roster").fetchall():
            if _norm(row["lawyer_name"]) == key:
                existing = row
                break
        if relatives_in is None and existing is not None:
            relatives_json = existing["relatives_json"] or "[]"
        else:
            relatives = []
            for item in relatives_in or []:
                if not isinstance(item, dict):
                    continue
                rel_name = str(item.get("name") or "").strip()
                if not rel_name or rel_name in _FAKE_IDENTITIES:
                    continue
                rel_id = str(item.get("id_no") or item.get("id_number") or item.get("id_card") or "").strip()
                if rel_id in _FAKE_IDENTITIES:
                    rel_id = ""
                relatives.append({
                    "name": rel_name,
                    "relation": str(item.get("relation") or "近亲属").strip() or "近亲属",
                    "id_no": rel_id,
                })
            relatives_json = json.dumps(relatives, ensure_ascii=False)
        if is_default:
            conn.execute("UPDATE firm_roster SET is_default = 0")
        if existing is None:
            if not is_default:
                count = conn.execute("SELECT COUNT(*) AS n FROM firm_roster").fetchone()["n"]
                is_default = count == 0
            conn.execute(
                """
                INSERT INTO firm_roster
                    (lawyer_name, license_no, id_no, law_firm, phone, relatives_json, is_default)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (name, license_no, id_no, law_firm, phone, relatives_json, 1 if is_default else 0),
            )
        else:
            conn.execute(
                """
                UPDATE firm_roster
                   SET lawyer_name = ?, license_no = ?, id_no = ?, law_firm = ?, phone = ?,
                       relatives_json = ?, is_default = ?
                 WHERE id = ?
                """,
                (
                    name,
                    license_no,
                    id_no,
                    law_firm,
                    phone,
                    relatives_json,
                    1 if is_default else 0,
                    existing["id"],
                ),
            )
    saved = next(item for item in list_lawyers() if _norm(item["lawyer_name"]) == key)
    return saved


def delete_lawyer(lawyer_id: int) -> bool:
    ensure_firm_roster_table()
    with _conn() as conn:
        cur = conn.execute("DELETE FROM firm_roster WHERE id = ?", (lawyer_id,))
        return cur.rowcount > 0


def default_counsel() -> Optional[Dict[str, Any]]:
    rows = list_lawyers()
    if not rows:
        return None
    marked = [row for row in rows if row["is_default"]]
    if len(marked) == 1:
        return marked[0]
    if len(rows) == 1:
        return rows[0]
    return None


def counsel_for_documents(
    lawyer_name: Any = "",
    law_firm: Any = "",
    lawyer_license: Any = "",
    lawyer_phone: Any = "",
) -> Dict[str, str]:
    """文书字段：请求里已经填写的保留；空着的才从名册默认承办律师补上。"""
    def _usable(value: Any) -> str:
        text = str(value or "").strip()
        if text in _FAKE_IDENTITIES:
            return ""
        return text

    name = _usable(lawyer_name)
    firm = _usable(law_firm)
    license_no = _usable(lawyer_license)
    phone = _usable(lawyer_phone)
    picked = default_counsel()
    if picked:
        if not name:
            name = _usable(picked["lawyer_name"])
        if not firm:
            firm = _usable(picked["law_firm"])
        if not license_no:
            license_no = _usable(picked["license_no"])
        if not phone:
            phone = _usable(picked["phone"])
    return {
        "lawyer_name": name,
        "law_firm": firm,
        "lawyer_license": license_no,
        "lawyer_phone": phone,
    }


def _credential_set(*values: Any) -> List[str]:
    found: List[str] = []
    for value in values:
        if isinstance(value, (list, tuple)):
            found.extend(_credential_set(*value))
            continue
        token = normalize_credential(value)
        if token and token not in found:
            found.append(token)
    return found


def _hit_label(hit: Dict[str, str]) -> str:
    if hit.get("role") == "本所律师":
        who = f"本所律师{hit.get('lawyer_name') or ''}"
    else:
        who = f"{hit.get('lawyer_name') or ''}的{hit.get('relation') or '近亲属'}{hit.get('matched_name') or ''}"
    if hit.get("match_kind") == "credential":
        return f"{who}（证件号相同）"
    if hit.get("match_kind") == "similar":
        shown = str(hit.get("opposing_name") or "").strip()
        if shown:
            return f"{who}，对方填写{shown}"
    return who


def _join_labels(hits: List[Dict[str, str]]) -> str:
    labels = [_hit_label(hit) for hit in hits]
    if len(labels) <= 2:
        return "、".join(labels)
    return "、".join(labels[:2]) + f"等{len(labels)}处"


def _screen_result(
    status: str,
    hits: List[Dict[str, str]],
    check: str,
    block: str = "",
    ack: str = "",
) -> Dict[str, Any]:
    return {
        "status": status,
        "hits": hits,
        "personnel_and_relatives_check": check,
        "block_message": block,
        "ack_message": ack,
    }


def screen_personnel(
    opposing_name: Any = "",
    opposing_id: Any = "",
    party_ids: Optional[List[Any]] = None,
) -> Dict[str, Any]:
    """对方姓名、接案当事人证件号与本所律师、近亲属比对。名册为空时写明未检查。"""
    lawyers = list_lawyers()
    if not lawyers:
        return _screen_result("NOT_RECORDED", [], NOT_RECORDED_TEXT)
    opposing = normalize_person_name(opposing_name)
    opposing_display = str(opposing_name or "").strip()
    party_credentials = _credential_set(opposing_id, party_ids or [])
    if not opposing and not party_credentials:
        return _screen_result(
            "NOT_COMPARED",
            [],
            "对方名称未填，未能与本所名册比对。补齐对方后再查。",
        )

    name_hits: List[Dict[str, str]] = []
    credential_hits: List[Dict[str, str]] = []
    similar_hits: List[Dict[str, str]] = []

    def _consider(display_name: str, role: str, lawyer_name: str, relation: str, credentials: List[Any]) -> None:
        normalized = normalize_person_name(display_name)
        creds = _credential_set(credentials)
        base = {
            "matched_name": display_name,
            "role": role,
            "lawyer_name": lawyer_name,
            "relation": relation,
            "opposing_name": opposing_display,
        }
        if opposing and normalized and opposing == normalized:
            name_hits.append({**base, "match_kind": "name"})
            return
        if party_credentials and any(token in party_credentials for token in creds):
            credential_hits.append({**base, "match_kind": "credential"})
            return
        if opposing and normalized and names_are_similar(opposing, normalized):
            similar_hits.append({**base, "match_kind": "similar"})

    for lawyer in lawyers:
        _consider(
            lawyer["lawyer_name"],
            "本所律师",
            lawyer["lawyer_name"],
            "",
            [lawyer.get("license_no") or "", lawyer.get("id_no") or ""],
        )
        for relative in lawyer["relatives"]:
            _consider(
                relative["name"],
                "近亲属",
                lawyer["lawyer_name"],
                relative.get("relation") or "近亲属",
                [relative.get("id_no") or ""],
            )

    if name_hits or credential_hits:
        same_person = name_hits + credential_hits
        joined = _join_labels(same_person)
        if name_hits and not credential_hits:
            check = (
                f"对方与本所人员或近亲属同名：{joined}。"
                "本所人员及近亲属利益冲突：已命中，未确认前不能建案。"
            )
            block = f"对方与本所律师或近亲属同名（{joined}）。未确认前不能建案。如仍接案，请勾选已书面确认。"
            ack = f"已确认对方与本所人员或近亲属同名（{joined}），请另纸留书面记录。本次不是静默建案。"
        elif credential_hits and not name_hits:
            check = (
                f"接案当事人证件号与本所人员或近亲属相同：{joined}。"
                "即使姓名不同，也按同一人处理，不能静默建案。"
                "本所人员及近亲属利益冲突：已命中，未确认前不能建案。"
            )
            block = (
                f"接案当事人证件号与本所律师或近亲属相同（{joined}）。"
                "即使姓名不同，也按同一人处理，不能静默建案。未确认前不能建案。如仍接案，请勾选已书面确认。"
            )
            ack = (
                f"已确认接案当事人证件号与本所人员或近亲属相同（{joined}），按同一人处理，请另纸留书面记录。"
                "本次不是静默建案。"
            )
        else:
            check = (
                f"对方与本所人员或近亲属为同一人：{joined}。"
                "姓名规范化后全同，或证件号相同。不能静默建案。"
                "本所人员及近亲属利益冲突：已命中，未确认前不能建案。"
            )
            block = f"对方与本所律师或近亲属为同一人（{joined}）。不能静默建案。未确认前不能建案。如仍接案，请勾选已书面确认。"
            ack = f"已确认对方与本所人员或近亲属为同一人（{joined}），请另纸留书面记录。本次不是静默建案。"
        return _screen_result("HIT", same_person, check, block, ack)

    if similar_hits:
        joined = _join_labels(similar_hits)
        check = (
            f"姓名相近，需人工核对：{joined}。"
            "未勾选书面确认前不能建案。"
            "本所人员及近亲属利益冲突：姓名相近，需人工核对。"
        )
        block = f"姓名相近，需人工核对（{joined}）。未勾选书面确认前不能建案。"
        ack = f"已书面确认姓名相近仍要建档（{joined}）。姓名相近，需人工核对。本次不是静默建案。"
        return _screen_result("SIMILAR", similar_hits, check, block, ack)

    return _screen_result(
        "CHECKED",
        [],
        (
            f"已核对本所名册（{len(lawyers)}人），未发现承办律师或近亲属与对方同名。"
            "证件号也未与本所人员或近亲属相同。"
            "本所人员及近亲属利益冲突：已检查。"
        ),
    )
