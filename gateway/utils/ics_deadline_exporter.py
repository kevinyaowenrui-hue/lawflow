# -*- coding: utf-8 -*-
"""
LawFlow 智律工作台 - 办案关键期限 .ics 日历导出引擎 (RFC 5545 标准)
支持无缝导入:
- Apple iPhone / macOS 日历
- 飞书日历 (Feishu Calendar)
- 企业微信日程 (WeCom Calendar)
- 钉钉日历 (DingTalk Calendar)
- Microsoft Outlook / Google Calendar
"""
from __future__ import annotations

import uuid
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional


def _format_ics_date(d: date | datetime) -> str:
    if isinstance(d, datetime):
        return d.strftime("%Y%m%dT%H%M%SZ")
    return d.strftime("%Y%m%d")


def _escape_ics_text(text: str) -> str:
    """转义 RFC 5545 特殊字符 (, ; \ 换行)。"""
    if not text:
        return ""
    text = text.replace("\\", "\\\\")
    text = text.replace(";", "\\;")
    text = text.replace(",", "\\,")
    text = text.replace("\r\n", "\\n").replace("\n", "\\n").replace("\r", "\\n")
    return text


def build_lawyer_deadline_ics(
    events: List[Dict[str, Any]],
    calendar_name: str = "LawFlow 智律办案期限提醒",
) -> str:
    """
    根据办案期限事件列表构建符合 RFC 5545 标准的 iCalendar (.ics) 文本。

    事件字典支持字段：
    - title / summary: 事件标题
    - date / deadline: 到期日期 (YYYY-MM-DD)
    - description / note: 详细说明（当事人、案号、法条依据、主办律师注意事项）
    - location: 开庭地点 / 受理法院
    - uid: 可选唯一标识符
    - category: 分类（如：上诉期限、财产保全续封、举证期限）
    """
    now_utc = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//LawFlow//LawFlow Lawyer Workstation//CN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escape_ics_text(calendar_name)}",
        "X-WR-TIMEZONE:Asia/Shanghai",
    ]

    for ev in events:
        event_date_str = ev.get("deadline") or ev.get("date") or ev.get("event_date")
        if not event_date_str:
            continue
        try:
            ev_date = datetime.strptime(str(event_date_str).strip(), "%Y-%m-%d").date()
        except ValueError:
            continue

        ev_uid = ev.get("uid") or f"{uuid.uuid4().hex}@lawflow.local"
        summary = ev.get("title") or ev.get("summary") or "办案期限提醒"
        desc = ev.get("description") or ev.get("note") or ""
        location = ev.get("location") or ev.get("court_name") or ""
        category = ev.get("category") or "诉讼关键期限"

        # 全天事件：DTSTART;VALUE=DATE 到 DTEND;VALUE=DATE (RFC 5545 要求 DTEND 为次日)
        next_day = ev_date + timedelta(days=1)
        dtstart = f"DTSTART;VALUE=DATE:{ev_date.strftime('%Y%m%d')}"
        dtend = f"DTEND;VALUE=DATE:{next_day.strftime('%Y%m%d')}"

        lines.extend([
            "BEGIN:VEVENT",
            f"UID:{ev_uid}",
            f"DTSTAMP:{now_utc}",
            dtstart,
            dtend,
            f"SUMMARY:{_escape_ics_text(summary)}",
            f"DESCRIPTION:{_escape_ics_text(desc)}",
            f"CATEGORIES:{_escape_ics_text(category)}",
            "STATUS:CONFIRMED",
            "TRANSP:TRANSPARENT",
        ])

        if location:
            lines.append(f"LOCATION:{_escape_ics_text(location)}")

        # 提醒 1: 提前 24 小时预警 (-PT24H)
        lines.extend([
            "BEGIN:VALARM",
            "ACTION:DISPLAY",
            f"DESCRIPTION:【前日预警】{_escape_ics_text(summary)}",
            "TRIGGER:-PT24H",
            "END:VALARM",
        ])

        # 提醒 2: 当天到期提醒（上午 09:00）
        lines.extend([
            "BEGIN:VALARM",
            "ACTION:DISPLAY",
            f"DESCRIPTION:【今日到期紧急提醒】{_escape_ics_text(summary)}",
            "TRIGGER;RELATED=START:PT9H",
            "END:VALARM",
        ])

        lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
