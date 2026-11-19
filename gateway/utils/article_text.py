# -*- coding: utf-8 -*-
"""条文正文清洗。不依赖网络或第三方库。"""
from __future__ import annotations

import re

_GLUED_HEADING = re.compile(
    r"^(?:[一二三四五六七八九十百千]+、|（[一二三四五六七八九十百千]+）)关于.+$"
)
_DIGIT_ITEM = re.compile(r"^\d+[\.、．]")


def trim_glued_section_heading(content: str) -> str:
    """去掉粘在条尾的「二、关于…」「（一）关于…」章节导语。

    海商法等条文内部的「（一）关于…」后面紧跟「1.」分项，必须保留。
    九民纪要、担保制度解释里，这类标题后面是下一编的导语，没有分项，应切掉。
    """
    lines = (content or "").splitlines()
    for i, line in enumerate(lines):
        if i == 0:
            continue
        stripped = line.strip()
        if not stripped or "。" in stripped or len(stripped) > 48:
            continue
        if not _GLUED_HEADING.match(stripped):
            continue
        rest = [x.strip() for x in lines[i + 1 :] if x.strip()]
        if any(_DIGIT_ITEM.match(x) for x in rest):
            continue
        return "\n".join(lines[:i]).strip()
    return (content or "").strip()
