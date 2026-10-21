"""
LawFlow 智律工作台 - 大模型生成法条后验本地库比对熔断器
核心职责：从文书中提取法条/案号，与本地 SQLite 法典库及统一法律数据比对。
状态语义：LOCAL_MATCH（绿）/ 黄色待核验 / 红色废止或捏造。禁止输出「零幻觉」「验真通过」等背书字样。
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import sqlite3
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple

from gateway.core.db import connect
from gateway.core.paths import get_laws_db_path
from gateway.utils.legal_data import (
    LAW_ALIAS_TO_CANONICAL,
    build_case_number_patterns,
    get_abrogated_by_normalized,
    get_official_max_article as _get_max_info,
    known_law_canonical_names,
    load_precedents_demo,
    normalize_law_name,
)
from gateway.utils.legal_texts import CIVIL_CODE_TIME_EFFECT_ART1_PARA2

logger = logging.getLogger("lawflow.citation_guard")

CONTENT_SIMILARITY_THRESHOLD = 0.6

# 律师确认的合同法→民法典自动替换映射（仅 incident_date >= 2021-01-01 时使用）
CONTRACT_LAW_TO_CIVIL_CODE = {
    114: (585, "第五百八十五条"),
    107: (577, "第五百七十七条"),
    12: (470, "第四百七十条"),
}

PRIVATE_LENDING_OLD_RATE_HINTS = ("年利率24%", "36%", "两线三区", "年化24%")

CIVIL_CODE_EFFECTIVE = "2021-01-01"


def _db_path_str() -> str:
    return str(get_laws_db_path())


class _DBPathProxy:
    def __str__(self) -> str:
        return _db_path_str()

    def __fspath__(self) -> str:
        return _db_path_str()


DB_PATH = _DBPathProxy()

# 兼容旧导入名：别名表只读视图
LAW_ALIAS_MAP = {k: v for k, v in LAW_ALIAS_TO_CANONICAL.items()}

CN_NUM_MAP = {
    "零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
    "百": 100, "千": 1000, "万": 10000,
}


def cn_to_int(cn_str: str) -> Optional[int]:
    if not cn_str:
        return None
    cn_str = cn_str.replace("第", "").replace("条", "").replace("款", "").replace("项", "").strip()
    if cn_str.isdigit():
        return int(cn_str)
    total = 0
    temp = 0
    for char in cn_str:
        if char in CN_NUM_MAP:
            val = CN_NUM_MAP[char]
            if val >= 10:
                if temp == 0:
                    temp = 1
                total += temp * val
                temp = 0
            else:
                temp = val
        else:
            return None
    total += temp
    return total if total > 0 else None


def int_to_cn_article(num: int) -> str:
    units = ["", "十", "百", "千"]
    digits = ["零", "一", "二", "三", "四", "五", "六", "七", "八", "九"]
    if num <= 0:
        return f"第{num}条"
    if num < 10:
        return f"第{digits[num]}条"
    if num < 20:
        return f"第十{digits[num % 10] if num % 10 != 0 else ''}条"
    s = str(num)
    res = ""
    n = len(s)
    for i, ch in enumerate(s):
        d = int(ch)
        if d != 0:
            res += digits[d] + units[n - 1 - i]
        else:
            if not res.endswith("零"):
                res += "零"
    res = res.rstrip("零")
    return f"第{res}条"


def get_official_max_article(law_name: str, incident_date: Optional[str] = None) -> Optional[int]:
    """兼容旧接口：返回法定总条数上限整数；子串匹配已删除，仅规范名精确相等。"""
    info = _get_max_info(law_name, incident_date=incident_date)
    return info["max_articles"] if info else None


CASE_NUMBER_PATTERN, LEGACY_CASE_NUMBER_PATTERN = build_case_number_patterns()


def _ensure_laws_db() -> bool:
    """确保法典库已初始化（测试临时目录或首次启动）。"""
    try:
        from gateway.utils.statute_db import init_statute_database

        init_statute_database()
        return os.path.exists(_db_path_str())
    except Exception as e:
        logger.warning("初始化法典库失败: %s", e)
        return os.path.exists(_db_path_str())


def ensure_court_precedents_table(conn: sqlite3.Connection):
    cursor = conn.cursor()
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS court_precedents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        case_number TEXT UNIQUE NOT NULL,
        title TEXT NOT NULL,
        court_name TEXT NOT NULL,
        judgment_year INTEGER,
        cause_of_action TEXT,
        holding_summary TEXT,
        source TEXT DEFAULT '演示判例种子',
        is_demo INTEGER DEFAULT 1
    );
    """
    )
    # 兼容旧库缺 is_demo 列
    try:
        cursor.execute("SELECT is_demo FROM court_precedents LIMIT 1")
    except sqlite3.OperationalError:
        try:
            cursor.execute("ALTER TABLE court_precedents ADD COLUMN is_demo INTEGER DEFAULT 1")
        except sqlite3.OperationalError:
            pass

    for p in load_precedents_demo():
        try:
            cursor.execute(
                """
            INSERT OR IGNORE INTO court_precedents
            (case_number, title, court_name, judgment_year, cause_of_action, holding_summary, is_demo)
            VALUES (?, ?, ?, ?, ?, ?, 1);
            """,
                (
                    p["case_number"],
                    p["title"],
                    p["court_name"],
                    p["judgment_year"],
                    p["cause_of_action"],
                    p["holding_summary"],
                ),
            )
        except sqlite3.OperationalError:
            cursor.execute(
                """
            INSERT OR IGNORE INTO court_precedents
            (case_number, title, court_name, judgment_year, cause_of_action, holding_summary)
            VALUES (?, ?, ?, ?, ?, ?);
            """,
                (
                    p["case_number"],
                    p["title"],
                    p["court_name"],
                    p["judgment_year"],
                    p["cause_of_action"],
                    p["holding_summary"],
                ),
            )
    conn.commit()


def _row_is_demo(db_case) -> bool:
    keys = db_case.keys() if hasattr(db_case, "keys") else []
    if "is_demo" not in keys:
        # 列不存在：种子案号一律视为演示数据
        return True
    val = db_case["is_demo"]
    if val is None:
        return True
    return bool(val)


def audit_case_numbers(text: str, conn: Optional[sqlite3.Connection] = None) -> List[Dict[str, Any]]:
    if not text:
        return []

    def _run(active_conn: sqlite3.Connection) -> List[Dict[str, Any]]:
        ensure_court_precedents_table(active_conn)
        cursor = active_conn.cursor()
        audited_cases: List[Dict[str, Any]] = []
        seen = set()
        current_year = datetime.now().year

        matches: List[Tuple[re.Match, str]] = []
        for m in CASE_NUMBER_PATTERN.finditer(text):
            matches.append((m, "modern"))
        for m in LEGACY_CASE_NUMBER_PATTERN.finditer(text):
            # 避免与现代案号重叠
            if any(m.start() < em.end() and m.end() > em.start() for em, _ in matches):
                continue
            matches.append((m, "legacy"))

        for match, style in matches:
            raw_match = match.group(0).strip()
            year = int(match.group("year"))
            case_type = match.group("type").strip()
            no = match.group("no").strip()
            court = match.groupdict().get("court") or ""
            court = court.strip() if court else ""

            if style == "legacy":
                std_case_number = f"（{year}）{case_type}字第{no}号"
            else:
                std_case_number = f"（{year}）{court}{case_type}{no}号"

            if std_case_number in seen:
                continue
            seen.add(std_case_number)

            cursor.execute(
                "SELECT * FROM court_precedents WHERE case_number = ? OR case_number LIKE ? LIMIT 1;",
                (std_case_number, f"%{year}%{court}%{case_type}%{no}号%"),
            )
            db_case = cursor.fetchone()

            case_entry: Dict[str, Any] = {
                "raw_case_number": raw_match,
                "standard_case_number": std_case_number,
                "year": year,
                "court": court,
                "case_type": case_type,
                "serial_no": no,
                "is_hallucination": False,
                "risk_level": "MODERATE_WARNING",
                "status": "STRUCTURE_ONLY_UNVERIFIED",
                "notes": "案号格式合规，本地库未收录，需在中国裁判文书网/人民法院案例库人工核验",
                "case_title": None,
                "holding_summary": None,
                "matched_precedent": None,
            }

            if year > current_year or year < 1980:
                case_entry["is_hallucination"] = True
                case_entry["risk_level"] = "CRITICAL_BLOCKED"
                case_entry["status"] = "CASE_NUMBER_HALLUCINATION_YEAR"
                case_entry["notes"] = (
                    f"案号年份 {year} 超出合理范围 (1980-{current_year})，疑似捏造，不得引用。"
                )
            elif db_case:
                if _row_is_demo(db_case):
                    case_entry["is_hallucination"] = True
                    case_entry["risk_level"] = "CRITICAL_BLOCKED"
                    case_entry["status"] = "DEMO_DATA_BLOCKED"
                    case_entry["notes"] = "演示数据·不得引用"
                    case_entry["case_title"] = db_case["title"]
                    case_entry["holding_summary"] = db_case["holding_summary"]
                else:
                    case_entry["status"] = "LOCAL_MATCH"
                    case_entry["risk_level"] = "SAFE"
                    case_entry["notes"] = "本地库比对一致（非演示）"
                    case_entry["case_title"] = db_case["title"]
                    case_entry["holding_summary"] = db_case["holding_summary"]
                    case_entry["matched_precedent"] = {
                        "title": db_case["title"],
                        "court_name": db_case["court_name"],
                        "holding_summary": db_case["holding_summary"],
                        "judgment_year": db_case["judgment_year"],
                    }
            # else: STRUCTURE_ONLY_UNVERIFIED 已设

            audited_cases.append(case_entry)
        return audited_cases

    if conn is not None:
        return _run(conn)

    if not os.path.exists(_db_path_str()):
        if not _ensure_laws_db():
            return []
    with connect(get_laws_db_path(), row_factory=sqlite3.Row) as owned:
        return _run(owned)


def _extract_quoted_content(text: str, match_end: int) -> Optional[str]:
    """条号后紧随「规定：」或引号内的引述正文。"""
    tail = text[match_end : match_end + 400]
    m = re.match(r"^[之的]?规定[：:]\s*[「\"“]?(.+?)[」\"”]?(?=[。；;\n]|$)", tail)
    if m:
        return m.group(1).strip()
    m = re.match(r"^[：:，,]\s*[「\"“](.+?)[」\"”]", tail)
    if m:
        return m.group(1).strip()
    m = re.match(r"^\s*[「\"“](.+?)[」\"”]", tail)
    if m:
        return m.group(1).strip()
    return None


def _article_verification_status(art_row, cursor) -> str:
    """兼容 verification_status 列尚不存在。"""
    try:
        keys = art_row.keys()
    except Exception:
        keys = []
    if "verification_status" in keys and art_row["verification_status"]:
        return str(art_row["verification_status"])
    # 尝试从 laws 表
    try:
        cursor.execute(
            "SELECT verification_status FROM laws WHERE full_name = ? OR short_name = ? LIMIT 1",
            (art_row["full_name"], art_row["short_name"]),
        )
        row = cursor.fetchone()
        if row and "verification_status" in row.keys() and row["verification_status"]:
            return str(row["verification_status"])
    except sqlite3.OperationalError:
        pass
    return "VERIFIED"


def _law_known_in_db(cursor, canon: str) -> bool:
    cursor.execute("SELECT full_name, short_name FROM laws")
    for row in cursor.fetchall():
        if normalize_law_name(row["full_name"]) == canon or normalize_law_name(row["short_name"]) == canon:
            return True
    return False


def _is_recognized_law(canon: str, cursor) -> bool:
    if canon in known_law_canonical_names():
        return True
    if canon in get_abrogated_by_normalized():
        return True
    return _law_known_in_db(cursor, canon)


def _find_article_row(cursor, canon: str, norm_art_no: Optional[int], art_no_cn: str):
    cursor.execute(
        """
        SELECT a.id, a.article_no_cn, a.content, a.has_proviso, l.short_name, l.full_name
        FROM articles a
        JOIN laws l ON a.law_id = l.id
        """
    )
    for row in cursor.fetchall():
        if normalize_law_name(row["full_name"]) != canon and normalize_law_name(row["short_name"]) != canon:
            continue
        if norm_art_no and (row["article_no_cn"] == art_no_cn or True):
            # 精确条号
            pass
        # re-query with int
    cursor.execute(
        """
        SELECT a.id, a.article_no_cn, a.content, a.has_proviso, l.short_name, l.full_name
               , a.article_no_int
        FROM articles a
        JOIN laws l ON a.law_id = l.id
        """
    )
    for row in cursor.fetchall():
        ln = normalize_law_name(row["full_name"])
        sn = normalize_law_name(row["short_name"])
        if ln != canon and sn != canon:
            continue
        if norm_art_no is not None and row["article_no_int"] == norm_art_no:
            return row
        if row["article_no_cn"] == art_no_cn:
            return row
    return None


def _apply_sanitize_replacements(
    text: str,
    replacements: List[Tuple[int, int, str]],
) -> str:
    """按 (start, end, new) 从后往前定点替换；同句去重相同民法典引用。"""
    if not replacements:
        return text
    replacements = sorted(replacements, key=lambda x: x[0], reverse=True)
    result = text
    for start, end, new in replacements:
        result = result[:start] + new + result[end:]

    # 同一句中重复的相同民法典条文引用去重
    def _dedupe_sentence(sent: str) -> str:
        pattern = re.compile(r"《中华人民共和国民法典》第[零一二三四五六七八九十百千万\d]+条")
        seen = set()
        out = []
        last = 0
        for m in pattern.finditer(sent):
            key = m.group(0)
            out.append(sent[last : m.start()])
            if key in seen:
                # 去掉可能残留的顿号
                if out and out[-1].endswith(("、", "及", "和", "与", "，")):
                    out[-1] = out[-1][:-1]
                elif out and out[-1].endswith("以及"):
                    out[-1] = out[-1][:-2]
            else:
                seen.add(key)
                out.append(key)
            last = m.end()
        out.append(sent[last:])
        return "".join(out)

    parts = re.split(r"(?<=[。！？\n])", result)
    return "".join(_dedupe_sentence(p) for p in parts)


def audit_citations_in_text(
    raw_text: str = "",
    auto_sanitize: bool = True,
    text: str = "",
    incident_date: Optional[str] = None,
    **kwargs,
) -> Dict[str, Any]:
    content_text = raw_text or text or kwargs.get("content", "") or ""
    incident_date = incident_date or kwargs.get("incident_date")

    if not os.path.exists(_db_path_str()):
        if not _ensure_laws_db():
            return {
                "status": "error",
                "message": "法典数据库未就绪",
                "is_safe": False,
            }

    with connect(get_laws_db_path(), row_factory=sqlite3.Row) as conn:
        return _audit_citations_core(conn, content_text, auto_sanitize, incident_date)


def _audit_citations_core(conn, content_text, auto_sanitize, incident_date=None):
    cursor = conn.cursor()
    abrogated_map = get_abrogated_by_normalized()

    primary_pattern = re.compile(
        r"《(?P<law>[^》]+)》(?P<art_prefix>第)?(?P<art>[零一二三四五六七八九十百千万\d]+)条"
        r"(?:第(?P<para>[零一二三四五六七八九十\d]+)款)?"
        r"(?:第(?P<item>[零一二三四五六七八九十\d]+)项)?"
    )
    chained_pattern = re.compile(
        r"(?P<sep>[、，及和与或]|以及)\s*"
        r"(?P<art_full>(?P<art_prefix>第)?(?P<art>[零一二三四五六七八九十百千万\d]+)条"
        r"(?:第(?P<para>[零一二三四五六七八九十\d]+)款)?"
        r"(?:第(?P<item>[零一二三四五六七八九十\d]+)项)?)"
    )

    extracted_items = []
    for m in primary_pattern.finditer(content_text):
        law_name_raw = m.group("law").strip()
        extracted_items.append(
            {
                "full_match_str": m.group(0),
                "replace_target": m.group(0),
                "span": (m.start(), m.end()),
                "law_name_raw": law_name_raw,
                "art_raw": m.group("art").strip(),
                "para_raw": m.group("para"),
                "item_raw": m.group("item"),
                "match_end": m.end(),
            }
        )
        end = m.end()
        while end < len(content_text):
            sub = content_text[end : end + 60]
            chain_m = chained_pattern.match(sub)
            if chain_m:
                art_full = chain_m.group("art_full")
                extracted_items.append(
                    {
                        "full_match_str": f"《{law_name_raw}》{art_full}",
                        "replace_target": art_full,
                        "span": (end + chain_m.start("art_full"), end + chain_m.end("art_full")),
                        "law_name_raw": law_name_raw,
                        "art_raw": chain_m.group("art").strip(),
                        "para_raw": chain_m.group("para"),
                        "item_raw": chain_m.group("item"),
                        "match_end": end + chain_m.end(),
                    }
                )
                end += chain_m.end()
            else:
                break

    audited_citations = []
    sanitize_ops: List[Tuple[int, int, str]] = []
    hallucination_count = 0
    abrogated_count = 0
    valid_count = 0
    unverified_count = 0
    yellow_count = 0
    red_count = 0
    warnings: List[str] = []

    # 民间借贷旧口径黄色提示
    for hint in PRIVATE_LENDING_OLD_RATE_HINTS:
        if hint in content_text:
            warnings.append(
                "可能引用了2020年修正前的民间借贷利率口径，请核实"
            )
            yellow_count += 1
            break

    seen_citations = set()
    allow_auto_replace = False
    if incident_date and incident_date[:10] >= CIVIL_CODE_EFFECTIVE:
        allow_auto_replace = True

    for item in extracted_items:
        full_match_str = item["full_match_str"]
        law_name_raw = item["law_name_raw"]
        art_raw = item["art_raw"]
        span = item["span"]

        norm_art_no = cn_to_int(art_raw)
        art_no_cn = int_to_cn_article(norm_art_no) if norm_art_no else f"第{art_raw}条"
        canon = normalize_law_name(law_name_raw)

        unique_key = f"{canon}_{art_no_cn}"
        if unique_key in seen_citations:
            continue
        seen_citations.add(unique_key)

        citation_entry: Dict[str, Any] = {
            "raw_citation": full_match_str,
            "citation_text": full_match_str,
            "law_name": canon,
            "original_law_name": law_name_raw,
            "article_no": norm_art_no,
            "article_no_cn": art_no_cn,
            "para_no": item.get("para_raw"),
            "item_no": item.get("item_raw"),
            "status": "UNINDEXED_UNVERIFIABLE",
            "audit_status": "UNINDEXED_UNVERIFIABLE",
            "risk_level": "MODERATE_WARNING",
            "notes": "",
            "replacement_suggestion": None,
            "suggested_replacement": None,
        }

        # A. 废止
        if canon in abrogated_map:
            ab_info = abrogated_map[canon]
            abrogated_count += 1
            red_count += 1
            citation_entry["status"] = "ABROGATED_BLOCKED"
            citation_entry["audit_status"] = "ABROGATED_BLOCKED"
            citation_entry["risk_level"] = "CRITICAL_BLOCKED"
            tip = ab_info.get("risk_tip") or ""
            citation_entry["notes"] = (
                f"《{canon}》已于 {ab_info.get('abrogated_date')} 废止。"
                f"{tip} 依据：{ab_info.get('basis') or 'TODO(律师核实)'}"
            )
            citation_entry["risk_tip"] = citation_entry["notes"]
            citation_entry["replacement_suggestion"] = f"建议替换援引：{ab_info.get('replaced_by')}"
            citation_entry["suggested_replacement"] = ab_info.get("replaced_by")

            if auto_sanitize:
                if not incident_date or incident_date[:10] < CIVIL_CODE_EFFECTIVE:
                    citation_entry["sanitize_note"] = (
                        "未提供法律事实发生日期，或日期早于2021-01-01，未自动替换。"
                        f"依时间效力规定第一条第二款：{CIVIL_CODE_TIME_EFFECT_ART1_PARA2}"
                    )
                    warnings.append(citation_entry["sanitize_note"])
                elif allow_auto_replace and "合同" in canon:
                    if norm_art_no in CONTRACT_LAW_TO_CIVIL_CODE:
                        _, cn = CONTRACT_LAW_TO_CIVIL_CODE[norm_art_no]
                        sanitized_replacement = f"《中华人民共和国民法典》{cn}"
                        sanitize_ops.append((span[0], span[1], sanitized_replacement))
                        citation_entry["sanitized_to"] = sanitized_replacement
                        citation_entry["suggested_replacement"] = sanitized_replacement
                    else:
                        citation_entry["sanitize_note"] = "请人工确定民法典对应条文"
                        warnings.append(citation_entry["sanitize_note"])
                else:
                    citation_entry["sanitize_note"] = "请人工确定民法典对应条文"
                    warnings.append(citation_entry["sanitize_note"])

            audited_citations.append(citation_entry)
            continue

        # B. 未识别法律名称
        if not _is_recognized_law(canon, cursor):
            yellow_count += 1
            unverified_count += 1
            citation_entry["status"] = "UNRECOGNIZED_LAW"
            citation_entry["audit_status"] = "UNRECOGNIZED_LAW"
            citation_entry["risk_level"] = "HIGH_WARNING"
            citation_entry["notes"] = "未识别的法律名称，无法核验"
            citation_entry["risk_tip"] = citation_entry["notes"]
            audited_citations.append(citation_entry)
            continue

        # C. 条号越界（仅 verified=True 的上限可判红）
        max_info = _get_max_info(canon, incident_date=incident_date)
        if (
            max_info
            and max_info.get("verified")
            and norm_art_no
            and norm_art_no > max_info["max_articles"]
        ):
            hallucination_count += 1
            red_count += 1
            citation_entry["status"] = "HALLUCINATION_EXCEEDED"
            citation_entry["audit_status"] = "HALLUCINATION_EXCEEDED"
            citation_entry["risk_level"] = "CRITICAL_BLOCKED"
            citation_entry["notes"] = (
                f"【虚构条号】《{canon}》法定共 {max_info['max_articles']} 条，"
                f"第 {norm_art_no} 条超出上限。"
            )
            citation_entry["risk_tip"] = citation_entry["notes"]
            if auto_sanitize:
                sanitize_ops.append(
                    (span[0], span[1], f"【拦截捏造法条: {full_match_str}】")
                )
            audited_citations.append(citation_entry)
            continue
        elif (
            max_info
            and not max_info.get("verified")
            and norm_art_no
            and norm_art_no > max_info["max_articles"]
        ):
            yellow_count += 1
            unverified_count += 1
            citation_entry["status"] = "UNINDEXED_UNVERIFIABLE"
            citation_entry["audit_status"] = "UNINDEXED_UNVERIFIABLE"
            citation_entry["risk_level"] = "MODERATE_WARNING"
            citation_entry["notes"] = (
                f"条号可能越界（法定条数 {max_info['max_articles']} 尚未律师核实），"
                "请对照官方文本人工核对"
            )
            citation_entry["risk_tip"] = citation_entry["notes"]
            audited_citations.append(citation_entry)
            continue

        # D. 本地库条文
        art_row = _find_article_row(cursor, canon, norm_art_no, art_no_cn)
        if art_row:
            vstatus = _article_verification_status(art_row, cursor)
            quoted = _extract_quoted_content(content_text, item["match_end"])
            content_mismatch = False
            if quoted:
                ratio = SequenceMatcher(None, quoted, art_row["content"] or "").ratio()
                if ratio < CONTENT_SIMILARITY_THRESHOLD:
                    content_mismatch = True

            if content_mismatch:
                red_count += 1
                citation_entry["status"] = "CONTENT_MISMATCH"
                citation_entry["audit_status"] = "CONTENT_MISMATCH"
                citation_entry["risk_level"] = "CRITICAL_BLOCKED"
                citation_entry["notes"] = "引述正文与本地库比对不一致"
                citation_entry["official_content"] = art_row["content"]
                citation_entry["article_content"] = art_row["content"]
            elif vstatus == "VERIFIED":
                valid_count += 1
                citation_entry["status"] = "LOCAL_MATCH"
                citation_entry["audit_status"] = "LOCAL_MATCH"
                citation_entry["risk_level"] = "SAFE"
                citation_entry["notes"] = "本地库比对一致（已收录并核对）"
                citation_entry["official_content"] = art_row["content"]
                citation_entry["article_content"] = art_row["content"]
                citation_entry["statute_full_name"] = art_row["full_name"]
                citation_entry["has_proviso"] = bool(art_row["has_proviso"])
            else:
                yellow_count += 1
                unverified_count += 1
                citation_entry["status"] = "PENDING_VERIFICATION"
                citation_entry["audit_status"] = "PENDING_VERIFICATION"
                citation_entry["risk_level"] = "MODERATE_WARNING"
                citation_entry["notes"] = f"本地库已收录但 verification_status={vstatus}，待核验"
                citation_entry["official_content"] = art_row["content"]
                citation_entry["article_content"] = art_row["content"]
            citation_entry["risk_tip"] = citation_entry["notes"]
        else:
            yellow_count += 1
            unverified_count += 1
            citation_entry["status"] = "UNINDEXED_UNVERIFIABLE"
            citation_entry["audit_status"] = "UNINDEXED_UNVERIFIABLE"
            citation_entry["risk_level"] = "MODERATE_WARNING"
            citation_entry["notes"] = "未收录·无法核验，请对照官方文本人工核对"
            citation_entry["risk_tip"] = citation_entry["notes"]

        audited_citations.append(citation_entry)

    sanitized_text = content_text
    if auto_sanitize and sanitize_ops:
        sanitized_text = _apply_sanitize_replacements(content_text, sanitize_ops)

    audited_case_numbers = audit_case_numbers(content_text, conn)
    case_hallucination_count = sum(1 for c in audited_case_numbers if c.get("is_hallucination"))
    case_unverified = sum(
        1
        for c in audited_case_numbers
        if c.get("status") == "STRUCTURE_ONLY_UNVERIFIED"
    )
    case_verified_local = sum(
        1 for c in audited_case_numbers if c.get("status") == "LOCAL_MATCH"
    )
    case_total = len(audited_case_numbers)

    if case_hallucination_count:
        hallucination_count += case_hallucination_count
        red_count += case_hallucination_count
    if case_unverified:
        yellow_count += case_unverified
        unverified_count += case_unverified

    total = len(audited_citations)
    has_abrogated = abrogated_count > 0
    has_hallucinations = hallucination_count > 0
    is_safe = red_count == 0 and yellow_count == 0
    compliance_rate = f"{(valid_count / total * 100):.1f}%" if total > 0 else "100.0%"

    all_citations_local = total > 0 and all(
        c.get("status") == "LOCAL_MATCH" for c in audited_citations
    )
    no_case_pending = case_unverified == 0 and case_hallucination_count == 0

    if total == 0 and case_total == 0 and not warnings:
        overall_status = "NO_CITATIONS"
        badge_label = "⚪ 文中未引用特定法条与案号"
        badge_color = "gray"
    elif all_citations_local and (case_total == 0 or (case_verified_local == case_total and no_case_pending)) and yellow_count == 0 and red_count == 0:
        overall_status = "LOCAL_MATCH_PASSED"
        badge_label = f"✓ 本地库比对一致（{valid_count} 条已收录并核对）"
        badge_color = "green"
    elif red_count > 0 and (abrogated_count > 0 or has_hallucinations):
        if has_hallucinations and abrogated_count == 0:
            overall_status = "HALLUCINATION_BLOCKED"
            badge_label = f"⛔ 捕捉到 {hallucination_count} 处虚构法条或案号"
            badge_color = "red"
        elif abrogated_count > 0 and not has_hallucinations:
            overall_status = "ABROGATED_INTERCEPTED"
            badge_label = f"⚠ 拦截到 {abrogated_count} 处废止法规"
            badge_color = "amber"
        else:
            overall_status = "HALLUCINATION_BLOCKED"
            badge_label = f"⛔ 废止与虚构问题共 {red_count} 处"
            badge_color = "red"
    elif yellow_count > 0 or unverified_count > 0 or warnings:
        overall_status = "PARTIALLY_VERIFIED"
        badge_label = f"⚠ 部分待核验（本地库比对 {valid_count}/{total}）"
        badge_color = "amber"
    else:
        overall_status = "PARTIALLY_VERIFIED"
        badge_label = f"⚠ 部分待核验（本地库比对 {valid_count}/{total}）"
        badge_color = "amber"

    # 仅有案号待核验、无法条
    if total == 0 and case_total > 0:
        if case_hallucination_count:
            overall_status = "HALLUCINATION_BLOCKED"
            badge_label = f"⛔ 案号问题 {case_hallucination_count} 处"
            badge_color = "red"
        else:
            overall_status = "PARTIALLY_VERIFIED"
            badge_label = "⚠ 案号格式合规，本地库未完成比对"
            badge_color = "amber"

    audit_hash = hashlib.sha256(
        f"{content_text[:80]}:{total}:{datetime.now().strftime('%Y%m%d%H')}".encode("utf-8")
    ).hexdigest()
    audit_report = (
        f"共审查 {total} 处法条引注与 {case_total} 处司法案号："
        f"{valid_count} 处本地库比对一致，{unverified_count} 处待核验，"
        f"{abrogated_count} 处废止拦截，{hallucination_count} 处虚构条号/案号。"
    )

    return {
        "status": "success",
        "is_safe": is_safe,
        "is_safe_to_submit": is_safe,
        "has_abrogated_laws": has_abrogated,
        "has_hallucinations": has_hallucinations,
        "compliance_rate": compliance_rate,
        "overall_status": overall_status,
        "audit_report": audit_report,
        "warnings": warnings,
        "incident_date": incident_date,
        "badge": {
            "label": badge_label,
            "color": badge_color,
            "is_safe": is_safe,
        },
        "stats": {
            "total_citations": total,
            "verified_valid": valid_count,
            "verified_count": valid_count,
            "unverified_count": unverified_count,
            "abrogated_intercepted": abrogated_count,
            "abrogated_count": abrogated_count,
            "hallucination_blocked": hallucination_count,
            "hallucinated_count": hallucination_count,
            "local_match_score": int((valid_count / total * 100)) if total > 0 else 100,
            "case_numbers_total": case_total,
            "case_numbers_verified": case_verified_local,
            "case_numbers_hallucinated": case_hallucination_count,
            "case_numbers_unverified": case_unverified,
        },
        "audit_cert": {
            "audit_id": f"CG-{datetime.now().strftime('%Y%m%d')}-{audit_hash[:8].upper()}",
            "verifier": "LawFlow 智律工作台本地库比对网关",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "hash": f"SHA256:{audit_hash[:20]}...",
        },
        "citations": audited_citations,
        "items": audited_citations,
        "case_citations": audited_case_numbers,
        "case_numbers": audited_case_numbers,
        "sanitized_text": sanitized_text if auto_sanitize else content_text,
    }


def verify_single_case_number(case_number: str) -> Dict[str, Any]:
    results = audit_case_numbers(case_number)
    if results:
        return results[0]
    return {
        "raw_case_number": case_number,
        "standard_case_number": case_number,
        "status": "INVALID_FORMAT",
        "is_hallucination": True,
        "risk_level": "CRITICAL_BLOCKED",
        "notes": "不符合中国各级人民法院裁判文书案号编订标准",
    }


def verify_single_citation(law_name: str, article_num: int, original_citation: str = "") -> Dict[str, Any]:
    if not os.path.exists(_db_path_str()):
        return {"status": "error", "message": "法典数据库未就绪"}

    cleaned_law = law_name.strip("《》")
    art_no_cn = int_to_cn_article(article_num)
    probe = f"《{cleaned_law}》{art_no_cn}"
    report = audit_citations_in_text(raw_text=probe, auto_sanitize=False)
    if report.get("citations"):
        c = report["citations"][0]
        return {
            "law_name": c.get("law_name"),
            "statute_full_name": c.get("statute_full_name") or c.get("law_name"),
            "article_num": article_num,
            "article_no_cn": art_no_cn,
            "article_content": c.get("article_content"),
            "has_proviso": c.get("has_proviso"),
            "audit_status": c.get("audit_status"),
            "is_valid": c.get("status") == "LOCAL_MATCH",
            "risk_tip": c.get("notes"),
            "replacement_suggestion": c.get("replacement_suggestion"),
        }
    return {
        "law_name": normalize_law_name(cleaned_law),
        "article_num": article_num,
        "article_no_cn": art_no_cn,
        "audit_status": "UNRECOGNIZED_LAW",
        "is_valid": False,
        "risk_tip": "未识别的法律名称，无法核验",
    }
