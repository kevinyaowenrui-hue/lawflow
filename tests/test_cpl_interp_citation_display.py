# -*- coding: utf-8 -*-
"""民诉法解释检索展示：旧《民事诉讼法》条号对照 2023 年文本。"""
from __future__ import annotations

import json
from pathlib import Path

from gateway.utils.cpl_interp_citation_display import (
    WARNING,
    present_civil_procedure_interp_citations,
)
from gateway.utils.statute_db import _annotate_result

ROOT = Path(__file__).resolve().parents[1]
INTERP_PATH = ROOT / "data" / "legal" / "corpus" / "civil_procedure_interp.json"


def _article_containing(phrase: str) -> dict:
    data = json.loads(INTERP_PATH.read_text(encoding="utf-8"))
    for art in data["articles"]:
        if phrase in (art.get("content") or ""):
            return art
    raise AssertionError(f"解释库中没有含「{phrase}」的条文")


def test_interp_article_276_display_warns_and_points_to_286():
    """解释条文含「民事诉讼法第二百七十六条」时，展示结果带旧条号警示，并指出现行上诉期是第286条。"""
    art = _article_containing("民事诉讼法第二百七十六条")
    original = art["content"]
    assert "第二百八十六条" not in original

    shown = present_civil_procedure_interp_citations(original)
    note = shown["display_note"]
    assert WARNING in note
    assert "现行上诉期条文是第286条" in note

    cite = next(item for item in shown["citations"] if item["old_article_no"] == 276)
    assert cite["current_article_no"] == 286
    assert cite["copyable_as_current_authority"] is False
    assert shown["copyable_as_current_authority"] is False
    assert "不能直接作为现行依据写入代理词" in note

    domestic = next(item for item in shown["citations"] if item["old_article_no"] == 171)
    assert domestic["aligned"] is True
    assert domestic["current_article_no"] == 171

    displayed = _annotate_result(
        {
            "law_id": "civil_procedure_interp",
            "content": original,
            "hierarchy": 2,
            "verification_status": "OFFICIAL_SOURCE",
            "key_terms": [],
        }
    )
    assert displayed["content"] == original
    assert WARNING in displayed["cpl_citation_display_note"]
    assert "现行上诉期条文是第286条" in displayed["cpl_citation_display_note"]
    assert displayed["cpl_copyable_as_current_authority"] is False


def test_auction_cite_254_points_to_current_article_258_and_is_not_copyable():
    """拍卖所引旧第254条对上2023年文本第258条，不能当成现行依据抄进代理词。"""
    text = (
        "依照民事诉讼法第二百五十四条规定，人民法院在执行中需要拍卖被执行人财产的，"
        "可以由人民法院自行组织拍卖，也可以交由具备相应资质的拍卖机构拍卖。"
    )
    shown = present_civil_procedure_interp_citations(text)
    cite = shown["citations"][0]
    assert cite["old_article_no"] == 254
    assert cite["aligned"] is False
    assert cite["current_article_no"] == 258
    assert cite["copyable_as_current_authority"] is False
    assert "现行拍卖条文是第258条" in shown["display_note"]
    assert WARNING in shown["display_note"]
