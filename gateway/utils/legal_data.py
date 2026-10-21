"""
LawFlow 智律工作台 - 法律静态数据统一加载（data/legal、data/demo）
代码内不再维护重复字典；一律从此处或数据库读取。
"""

from __future__ import annotations

import json
import threading
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

_LOCK = threading.Lock()
_CACHE: Dict[str, Any] = {}

# 项目根目录：gateway/utils/legal_data.py → 上两级
_ROOT = Path(__file__).resolve().parents[2]
_LEGAL_DIR = _ROOT / "data" / "legal"
_DEMO_DIR = _ROOT / "data" / "demo"


def _load_json(path: Path) -> Any:
    key = str(path)
    with _LOCK:
        if key in _CACHE:
            return _CACHE[key]
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        _CACHE[key] = data
        return data


def clear_legal_data_cache() -> None:
    with _LOCK:
        _CACHE.clear()
        load_abrogated_laws.cache_clear()
        load_statute_max_articles.cache_clear()
        load_case_type_codes.cache_clear()
        load_seed_articles_bundle.cache_clear()
        load_seed_links.cache_clear()
        load_precedents_demo.cache_clear()
        load_preset_dossiers.cache_clear()
        load_private_cases_demo.cache_clear()


@lru_cache(maxsize=1)
def load_abrogated_laws() -> List[Dict[str, Any]]:
    return list(_load_json(_LEGAL_DIR / "abrogated_laws.json"))


@lru_cache(maxsize=1)
def load_statute_max_articles() -> List[Dict[str, Any]]:
    return list(_load_json(_LEGAL_DIR / "statute_max_articles.json"))


@lru_cache(maxsize=1)
def load_case_type_codes() -> Dict[str, Any]:
    return dict(_load_json(_LEGAL_DIR / "case_type_codes.json"))


@lru_cache(maxsize=1)
def load_seed_articles_bundle() -> Dict[str, Any]:
    return dict(_load_json(_LEGAL_DIR / "seed_articles.json"))


@lru_cache(maxsize=1)
def load_seed_links() -> List[Dict[str, Any]]:
    return list(_load_json(_LEGAL_DIR / "seed_links.json"))


@lru_cache(maxsize=1)
def load_precedents_demo() -> List[Dict[str, Any]]:
    return list(_load_json(_DEMO_DIR / "precedents_demo.json"))


@lru_cache(maxsize=1)
def load_preset_dossiers() -> Dict[str, Any]:
    return dict(_load_json(_DEMO_DIR / "preset_dossiers.json"))


@lru_cache(maxsize=1)
def load_private_cases_demo() -> List[Dict[str, Any]]:
    return list(_load_json(_DEMO_DIR / "private_cases_demo.json"))


# 常见法律简称 ↔ 规范短名（不含书名号、不含「中华人民共和国」前缀）
LAW_ALIAS_TO_CANONICAL: Dict[str, str] = {
    "民法典": "民法典",
    "民法": "民法典",
    "民法通则": "民法通则",
    "民法总则": "民法总则",
    "合同法": "合同法",
    "物权法": "物权法",
    "担保法": "担保法",
    "侵权责任法": "侵权责任法",
    "婚姻法": "婚姻法",
    "继承法": "继承法",
    "收养法": "收养法",
    "公司法": "公司法",
    "新公司法": "公司法",
    "刑法": "刑法",
    "民事诉讼法": "民事诉讼法",
    "民诉法": "民事诉讼法",
    "劳动合同法": "劳动合同法",
    "劳动法": "劳动法",
    "个人信息保护法": "个人信息保护法",
    "反不正当竞争法": "反不正当竞争法",
    "民间借贷规定": "民间借贷规定",
    "民间借贷司法解释": "民间借贷规定",
    "合同编解释": "合同编通则解释",
    "合同编通则解释": "合同编通则解释",
    "民诉法解释": "民诉法解释",
    "劳动争议解释一": "劳动争议解释一",
    "九民纪要": "九民纪要",
    "追加规定": "追加规定",
    "类案检索指导意见": "类案检索指导意见",
    "担保制度解释": "担保制度解释",
    "行政诉讼法": "行政诉讼法",
    "劳动争议调解仲裁法": "劳动争议调解仲裁法",
    "数据安全法": "数据安全法",
    "网络安全法": "网络安全法",
    "消费者权益保护法": "消费者权益保护法",
    "劳动人事争议仲裁办案规则": "劳动人事争议仲裁办案规则",
}


def _fullwidth_to_half(s: str) -> str:
    out = []
    for ch in s:
        code = ord(ch)
        if code == 0x3000:
            out.append(" ")
        elif 0xFF01 <= code <= 0xFF5E:
            out.append(chr(code - 0xFEE0))
        else:
            out.append(ch)
    return "".join(out)


def normalize_law_name(name: str) -> str:
    """去书名号、去「中华人民共和国」前缀、去空白、全半角统一、查别名表，返回规范短名。"""
    if not name:
        return ""
    s = _fullwidth_to_half(str(name)).strip()
    s = s.replace("《", "").replace("》", "").replace("〈", "").replace("〉", "")
    s = "".join(s.split())
    if s.startswith("中华人民共和国"):
        s = s[len("中华人民共和国") :]
    # 全称变体常见尾巴
    for prefix in ("最高人民法院关于", "最高人民检察院、公安部关于"):
        if s.startswith(prefix):
            break
    # 民间借贷全称 → 规范短名
    if "民间借贷案件适用法律若干问题的规定" in s:
        return "民间借贷规定"
    if "合同编通则若干问题的解释" in s or "合同编通则解释" in s:
        return "合同编通则解释"
    if "全国法院民商事审判工作会议纪要" in s:
        return "九民纪要"
    if "适用〈中华人民共和国民事诉讼法〉的解释" in s or "适用《中华人民共和国民事诉讼法》的解释" in s:
        return "民诉法解释"
    if s in LAW_ALIAS_TO_CANONICAL:
        return LAW_ALIAS_TO_CANONICAL[s]
    # 带括号的公司法等
    base = s.split("(")[0].split("（")[0]
    if base in LAW_ALIAS_TO_CANONICAL:
        return LAW_ALIAS_TO_CANONICAL[base]
    return s


def get_abrogated_by_normalized() -> Dict[str, Dict[str, Any]]:
    """规范名 → 废止记录（精确相等用）。"""
    out: Dict[str, Dict[str, Any]] = {}
    for row in load_abrogated_laws():
        keys = set()
        keys.add(normalize_law_name(row.get("name", "")))
        keys.add(normalize_law_name(row.get("full_name", "")))
        for al in row.get("aliases") or []:
            keys.add(normalize_law_name(al))
        for k in keys:
            if k and k != "TODO(律师核实)":
                out[k] = row
    return out


def get_official_max_article(
    law_name: str, incident_date: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    返回选中版本信息: {max_articles, verified, effective_from, source, law_name}
    优先按 incident_date 选版本，否则取 effective_from 最新且可解析的版本。
    """
    canon = normalize_law_name(law_name)
    if not canon:
        return None

    matched = None
    for entry in load_statute_max_articles():
        ename = normalize_law_name(entry.get("law_name", ""))
        if ename == canon:
            matched = entry
            break
        # 也允许用未剥前缀的全称精确相等（已在 normalize 内处理）
    if not matched:
        return None

    versions = list(matched.get("versions") or [])
    if not versions:
        return None

    def _parse_date(d: Optional[str]) -> Optional[str]:
        if not d or str(d).startswith("TODO"):
            return None
        return str(d)[:10]

    if incident_date:
        inc = incident_date[:10]
        eligible = []
        for v in versions:
            ef = _parse_date(v.get("effective_from"))
            if ef is None or ef <= inc:
                eligible.append(v)
        if eligible:
            eligible.sort(key=lambda v: _parse_date(v.get("effective_from")) or "0000-01-01")
            chosen = eligible[-1]
        else:
            # 无适用版本则取最早
            versions_sorted = sorted(
                versions, key=lambda v: _parse_date(v.get("effective_from")) or "9999-12-31"
            )
            chosen = versions_sorted[0]
    else:
        # 无 incident_date：取最新可解析版本；若全是 TODO，取列表最后一项
        dated = [v for v in versions if _parse_date(v.get("effective_from"))]
        if dated:
            dated.sort(key=lambda v: _parse_date(v.get("effective_from")) or "")
            chosen = dated[-1]
        else:
            chosen = versions[-1]

    return {
        "law_name": matched["law_name"],
        "max_articles": int(chosen["max_articles"]),
        "verified": bool(chosen.get("verified")),
        "effective_from": chosen.get("effective_from"),
        "source": chosen.get("source"),
    }


def known_law_canonical_names() -> set:
    """别名表 + 法定条数表 + 废止表中的全部规范名。"""
    names = set(LAW_ALIAS_TO_CANONICAL.values())
    names.update(LAW_ALIAS_TO_CANONICAL.keys())
    for entry in load_statute_max_articles():
        names.add(normalize_law_name(entry.get("law_name", "")))
    for row in load_abrogated_laws():
        names.add(normalize_law_name(row.get("name", "")))
        names.add(normalize_law_name(row.get("full_name", "")))
        for al in row.get("aliases") or []:
            names.add(normalize_law_name(al))
    names.discard("")
    names.discard("TODO(律师核实)")
    return names


def build_case_number_patterns():
    """根据代字表构建现行案号与旧式案号正则。"""
    import re

    data = load_case_type_codes()
    codes = list(data.get("codes") or [])
    # 长代字优先
    codes_sorted = sorted(set(codes), key=len, reverse=True)
    type_alt = "|".join(re.escape(c) for c in codes_sorted)
    modern = re.compile(
        rf"[(（\[【](?P<year>(?:19|20)\d{{2}})[)）\]】]\s*"
        rf"(?P<court>[\u4e00-\u9fa5]{{0,10}}\d{{0,4}})\s*"
        rf"(?P<type>(?:{type_alt}))\s*"
        rf"(?P<no>\d+)\s*号"
    )
    # 旧式：（2012）民提字第11号
    legacy = re.compile(
        r"[(（\[【](?P<year>(?:19|20)\d{2})[)）\]】]\s*"
        r"(?P<type>[\u4e00-\u9fa5]{1,8})\s*字第\s*(?P<no>\d+)\s*号"
    )
    return modern, legacy
