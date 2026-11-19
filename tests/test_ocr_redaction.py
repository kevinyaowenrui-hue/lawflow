# -*- coding: utf-8 -*-
"""扫描件脱敏：OCR 字块坐标映射，不加载 EasyOCR 模型。"""
import re

from gateway.utils.ocr_engine import sensitive_rects_from_ocr_items

ID_RE = re.compile(
    r"(?<!\d)(?:[1-9]\d{5}(?:18|19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx])(?!\d)"
)


def test_ocr_rect_covers_only_the_id_inside_a_longer_line():
    items = [{
        "text": "身份证号110101199003072379住址",
        "x0": 0, "y0": 10, "x1": 200, "y1": 30,
    }]
    hits = sensitive_rects_from_ocr_items(items, [ID_RE], 400, 600, 200, 300)
    assert len(hits) == 1
    x0, y0, x1, y1 = hits[0]["rect"]
    assert hits[0]["text"] == "110101199003072379"
    assert x0 > 0
    assert x1 < 400
    assert y0 == 20
    assert y1 == 60


def test_ocr_joins_split_id_boxes_on_the_same_line():
    items = [
        {"text": "11010119900307", "x0": 10, "y0": 10, "x1": 80, "y1": 28},
        {"text": "2379", "x0": 82, "y0": 10, "x1": 110, "y1": 28},
    ]
    hits = sensitive_rects_from_ocr_items(items, [ID_RE], 200, 200, 200, 200)
    assert {h["text"] for h in hits} == {"110101199003072379"}
    assert len(hits) == 2


def test_ocr_does_not_join_numbers_in_distant_columns():
    items = [
        {"text": "11010119900307", "x0": 10, "y0": 10, "x1": 80, "y1": 28},
        {"text": "2379", "x0": 400, "y0": 10, "x1": 440, "y1": 28},
    ]
    hits = sensitive_rects_from_ocr_items(items, [ID_RE], 500, 200, 500, 200)
    assert hits == []
