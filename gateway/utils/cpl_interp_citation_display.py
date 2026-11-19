"""民诉法解释检索结果上的《民事诉讼法》条号对照。

2022 年修正的解释仍按修正前条号引用《民事诉讼法》，与仓库里的
2023 年文本不是同一套条号。这里不改解释原文，只在展示时标明对不上的引注。
条号仍与 2023 年文本同一主题的（解释所引、且 2023 年文本在同一条号上主题未变的，
截止到宣告失踪公告第 192 条），不标成旧条号。
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

from gateway.utils.citation_guard import cn_to_int

WARNING = "解释所引条号对应修正前《民事诉讼法》，现行条文请以 2023 年修正本为准"
NOT_CURRENT = "不能直接作为现行依据写入代理词。"
UNMAPPED = "2023年修正本中没有对上可抄入代理词的现行条号。"

# 2023 年文本里，解释所引第 192 条（宣告失踪、宣告死亡的公告）及以前各条，主题仍在同一条号。
_STABLE_THROUGH = 192

_LAW_HEAD = re.compile(r"(?:《\s*)?(?:中华人民共和国)?民事诉讼法(?:\s*》)?")
_ARTICLE = re.compile(r"第([一二三四五六七八九十百零〇]+)条")
_PARAGRAPH = re.compile(r"第[一二三四五六七八九十百零〇]+款")
_SEPARATOR = re.compile(r"[、，及和以及\s]+")

# 只收录已用 2023 年文本核对过的对应。对不上且没有这条规则的，不猜现行条号。
# must 必须原样出现在指定的 2023 年条文里，否则不给现行条号。
_RULES: Tuple[Dict[str, Any], ...] = (
    {"old": 201, "current": 205, "must": "申请司法确认"},
    {"old": 203, "current": 207, "must": "担保物权人"},
    {"old": 205, "current": 209, "must": "认为需要再审的"},
    {"old": 206, "current": 210, "must": "当事人一方人数众多"},
    {"old": 207, "current": 211, "must": "人民法院应当再审"},
    {"old": 208, "current": 212, "must": "调解协议的内容违反法律的，可以申请再审"},
    {"old": 211, "current": 215, "must": "三个月内审查"},
    {"old": 212, "current": 216, "must": "六个月内提出"},
    {"old": 213, "current": 217, "must": "中止原判决"},
    {"old": 215, "current": 219, "must": "提出检察建议"},
    {"old": 216, "current": 220, "must": "再审判决、裁定有明显错误"},
    {"old": 225, "current": 229, "must": "公示催告"},
    {"old": 226, "current": 230, "must": "发出公告"},
    {"old": 227, "current": 230, "must": "通知支付人停止支付"},
    {"old": 228, "current": 232, "must": "终结公示催告程序"},
    {"old": 230, "current": 234, "must": "判决公告之日起一年内"},
    {"old": 234, "current": 238, "must": "案外人对执行标的提出书面异议"},
    {"old": 238, "current": 242, "must": "暂缓执行"},
    {"old": 239, "current": 243, "must": "作为被执行人的法人或者其他组织"},
    {"old": 240, "current": 244, "must": "责令取得财产的人返还"},
    {"old": 244, "avoid": ("涉外",), "current": 248, "must": "裁定不予执行"},
    {"old": 245, "current": 249, "must": "公证债权文书"},
    {"old": 246, "current": 250, "must": "申请执行的期间为二年"},
    {"old": 252, "current": 256, "must": "查封、扣押财产时"},
    {"old": 254, "current": 258, "must": "应当拍卖被查封、扣押的财产", "note": "现行拍卖条文是第258条。"},
    {"old": 256, "current": 260, "must": "指定交付的财物或者票证"},
    {"old": 258, "current": 262, "must": "财产权证照转移手续"},
    {"old": 260, "current": 264, "must": "迟延履行金"},
    {"old": 261, "current": 265, "must": "随时请求人民法院执行"},
    {"old": 271, "current": 275, "must": "公证机关证明"},
    {"old": 273, "current": 279, "must": "下列民事案件，由人民法院专属管辖"},
    {"old": 274, "current": 283, "must": "公告送达，自发出公告之日起，经过六十日"},
    {"old": 276, "current": 286, "must": "三十日内提起上诉", "note": "现行上诉期条文是第286条。"},
    {"old": 279, "current": 289, "must": "涉外仲裁机构应当将当事人的申请"},
    {"old": 281, "current": 291, "must": "涉外仲裁机构作出的裁决"},
    {"old": 290, "current": 304, "must": "领域外作出的发生法律效力的仲裁裁决"},
)


def _corpus_path() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "legal" / "corpus" / "civil_procedure_2023.json"


@lru_cache(maxsize=1)
def load_civil_procedure_2023_articles() -> Dict[int, str]:
    """读取仓库里的 2023 年《民事诉讼法》正文，按条号索引。"""
    path = _corpus_path()
    data = json.loads(path.read_text(encoding="utf-8"))
    articles: Dict[int, str] = {}
    for art in data.get("articles") or []:
        number = art.get("article_no_int")
        if isinstance(number, int):
            articles[number] = art.get("content") or ""
    return articles


def _iter_citations(text: str) -> Iterator[Tuple[int, int, int, str]]:
    """Yield (start, end, article_no, quoted) for each 民事诉讼法第×条，含顿号续写的条号。"""
    for head in _LAW_HEAD.finditer(text):
        pos = head.end()
        first = True
        while pos < len(text):
            if not first:
                paragraph = _PARAGRAPH.match(text, pos)
                if paragraph:
                    pos = paragraph.end()
                separator = _SEPARATOR.match(text, pos)
                if not separator:
                    break
                pos = separator.end()
            match = _ARTICLE.match(text, pos)
            if not match:
                break
            number = cn_to_int(match.group(1))
            if not number:
                break
            yield match.start(), match.end(), number, text[match.start() : match.end()]
            pos = match.end()
            first = False


def _sentence_window(text: str, start: int, end: int) -> str:
    left = text.rfind("。", 0, start)
    right = text.find("。", end)
    if right == -1:
        right = len(text)
    return text[left + 1 : right]


def _map_current(old: int, window: str, articles: Dict[int, str]) -> Tuple[Optional[int], str]:
    for rule in _RULES:
        if rule["old"] != old:
            continue
        avoid = rule.get("avoid") or ()
        if any(token in window for token in avoid):
            continue
        needles = rule.get("needles") or ()
        if needles and not any(token in window for token in needles):
            continue
        body = articles.get(rule["current"]) or ""
        if rule["must"] not in body:
            continue
        note = rule.get("note") or f"现行对应条文是第{rule['current']}条。"
        return rule["current"], note
    return None, ""


def present_civil_procedure_interp_citations(content: str) -> Dict[str, Any]:
    """给一条解释正文配展示用对照。不改传入的原文。"""
    articles = load_civil_procedure_2023_articles()
    text = content or ""
    citations: List[Dict[str, Any]] = []
    for start, end, old, quoted in _iter_citations(text):
        window = _sentence_window(text, start, end)
        full_quote = "民事诉讼法" + quoted
        if old <= _STABLE_THROUGH and old in articles:
            citations.append(
                {
                    "quoted": full_quote,
                    "old_article_no": old,
                    "aligned": True,
                    "current_article_no": old,
                    "note": f"与2023年修正本第{old}条相符。",
                    "copyable_as_current_authority": True,
                }
            )
            continue
        current, note = _map_current(old, window, articles)
        citations.append(
            {
                "quoted": full_quote,
                "old_article_no": old,
                "aligned": False,
                "current_article_no": current,
                "note": note,
                "copyable_as_current_authority": False,
            }
        )

    stale = [item for item in citations if not item["aligned"]]
    if not stale:
        return {
            "citations": citations,
            "cpl_citation_warning": "",
            "display_note": "",
            "copyable_as_current_authority": True,
        }

    lines = [WARNING]
    seen = set()
    for item in stale:
        current = item["current_article_no"]
        key = (item["old_article_no"], current, item["note"])
        if key in seen:
            continue
        seen.add(key)
        if current:
            lines.append(f"「{item['quoted']}」{NOT_CURRENT}{item['note']}")
        else:
            lines.append(f"「{item['quoted']}」{NOT_CURRENT}{UNMAPPED}")
    aligned_seen = set()
    for item in citations:
        if not item["aligned"] or item["old_article_no"] in aligned_seen:
            continue
        aligned_seen.add(item["old_article_no"])
        lines.append(f"「{item['quoted']}」{item['note']}")

    return {
        "citations": citations,
        "cpl_citation_warning": WARNING,
        "display_note": "\n".join(lines),
        "copyable_as_current_authority": False,
    }


def attach_interp_cpl_citation_display(item: Dict[str, Any]) -> Dict[str, Any]:
    """检索/详情结果上附加对照。解释原文 content 保持不动。"""
    law_id = str(item.get("law_id") or "")
    name = f"{item.get('short_name') or ''}{item.get('full_name') or ''}{item.get('law_full_name') or ''}"
    if law_id != "civil_procedure_interp" and "民诉法解释" not in name and "民事诉讼法〉的解释" not in name and "民事诉讼法》的解释" not in name:
        return item
    review = present_civil_procedure_interp_citations(item.get("content") or "")
    if not review["citations"]:
        return item
    item["cpl_citation_warning"] = review["cpl_citation_warning"]
    item["cpl_citation_display_note"] = review["display_note"]
    item["cpl_citations"] = review["citations"]
    item["cpl_copyable_as_current_authority"] = review["copyable_as_current_authority"]
    return item
