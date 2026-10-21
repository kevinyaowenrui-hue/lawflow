"""
LawFlow 智律工作台 - 文书文本规范化工具
"""
from __future__ import annotations

import re
from typing import Optional


def normalize_court_name(name: Optional[str]) -> str:
    """
    规范化受诉法院全称：
    - 去除首尾空白；
    - 末尾已是「人民法院」或「法院」的不再追加；
    - 否则补「人民法院」。
    """
    if name is None:
        return "【待填写】人民法院"
    s = str(name).strip()
    if not s:
        return "【待填写】人民法院"
    if s.endswith("人民法院") or s.endswith("法院"):
        return s
    return f"{s}人民法院"


def normalize_arbitration_committee(name: Optional[str], region_hint: Optional[str] = None) -> str:
    """
    规范化劳动人事争议仲裁委员会全称。
    用户未填含「仲裁委员会」的全称时，用「{地区}劳动人事争议仲裁委员会」。
    禁止输出「人民法院劳动人事争议仲裁委员会」。
    """
    raw = (name or "").strip()
    # 去掉误拼的「人民法院」
    raw = raw.replace("人民法院", "")
    if "仲裁委员会" in raw:
        return raw
    base = raw or (region_hint or "").strip().replace("人民法院", "").replace("法院", "")
    if not base:
        base = "××"
    # 若已以「劳动人事争议」结尾则只补「仲裁委员会」
    if base.endswith("劳动人事争议"):
        return f"{base}仲裁委员会"
    if "劳动人事争议仲裁" in base:
        return base if base.endswith("委员会") else f"{base}委员会"
    return f"{base}劳动人事争议仲裁委员会"


def extract_agreed_annual_rate(text: str) -> Optional[float]:
    """从案情笔记中提取约定年利率（百分数）。"""
    if not text:
        return None
    patterns = [
        r"年(?:化)?利率\s*[为是]??\s*(\d+(?:\.\d+)?)\s*%",
        r"约定(?:年)?利率\s*[为是]??\s*(\d+(?:\.\d+)?)\s*%",
        r"按\s*年利率\s*(\d+(?:\.\d+)?)\s*%",
        r"利率\s*[为是]\s*(\d+(?:\.\d+)?)\s*%",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                continue
    return None


def extract_first_date_iso(text: str) -> Optional[str]:
    """从文本中提取第一个日期并规范为 YYYY-MM-DD。"""
    if not text:
        return None
    date_pattern = re.compile(r"(\d{4}[年\-\/\.]\d{1,2}[月\-\/\.]\d{1,2}日?)")
    found = date_pattern.findall(text)
    if not found:
        return None
    raw_d = found[0]
    norm_d = (
        raw_d.replace("年", "-")
        .replace("月", "-")
        .replace("日", "")
        .replace(".", "-")
        .replace("/", "-")
    )
    parts = norm_d.split("-")
    if len(parts) != 3:
        return None
    try:
        return f"{int(parts[0]):04d}-{int(parts[1]):02d}-{int(parts[2]):02d}"
    except Exception:
        return None


def format_date_cn(iso_date: str) -> str:
    """YYYY-MM-DD → YYYY年M月D日"""
    try:
        y, m, d = iso_date.split("-")
        return f"{int(y)}年{int(m)}月{int(d)}日"
    except Exception:
        return iso_date
