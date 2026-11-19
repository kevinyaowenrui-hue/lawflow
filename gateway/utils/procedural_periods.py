# -*- coding: utf-8 -*-
"""答辩期、举证期限：与上诉期相同的起算和节假日顺延，并标明法定依据。"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from gateway.utils.cn_legal_calc import _load_cn_holidays_and_workdays


def roll_service_deadline(
    anchor_date: str,
    period_days: int,
    *,
    holidays: Optional[List[str]] = None,
    treat_weekend_as_holiday: bool = True,
) -> Dict[str, Any]:
    """起算日当日不计入。届满日 = 起算日 + period_days，再按休假日顺延。"""
    if period_days <= 0:
        raise ValueError("期间天数必须大于 0")
    anchor = datetime.strptime(anchor_date.strip(), "%Y-%m-%d").date()
    deadline = anchor + timedelta(days=period_days)

    if holidays is None:
        holiday_set, workdays = _load_cn_holidays_and_workdays(anchor.year)
        h_next, w_next = _load_cn_holidays_and_workdays(deadline.year)
        holiday_set |= h_next
        workdays |= w_next
        known_years = _known_holiday_years()
    else:
        holiday_set = set(holidays)
        workdays = set()
        known_years = None

    def _is_non_working(d) -> bool:
        ds = d.strftime("%Y-%m-%d")
        if ds in holiday_set:
            return True
        if ds in workdays:
            return False
        if treat_weekend_as_holiday and d.weekday() >= 5:
            return True
        return False

    extended = False
    while _is_non_working(deadline):
        deadline = deadline + timedelta(days=1)
        extended = True

    warnings: List[str] = []
    if known_years is not None:
        missing = [y for y in sorted({anchor.year, deadline.year}) if str(y) not in known_years]
        if missing:
            years = "、".join(str(y) for y in missing)
            warnings.append(
                f"【法定节假日数据缺失警告】系统节假日库尚未收录 {years} 年的国务院办公厅节假日安排。"
                "当前只按普通周六日粗算，不能识别法定休假日和调休上班日。请承办律师对照官方通知人工核实。"
            )

    return {
        "anchor_date": anchor.strftime("%Y-%m-%d"),
        "period_days": period_days,
        "raw_deadline": (anchor + timedelta(days=period_days)).strftime("%Y-%m-%d"),
        "deadline": deadline.strftime("%Y-%m-%d"),
        "extended_for_holiday_or_weekend": extended,
        "warnings": warnings,
        "holiday_rule": (
            "期间开始的当日不计算在内；届满的最后一日是法定休假日的，顺延至法定休假日后的第一日。"
            "未调休的周六、周日按非工作日顺延，国务院安排的补班日不顺延。"
            "依据《中华人民共和国民事诉讼法》（2023修正）第八十五条。"
        ),
    }


def _known_holiday_years() -> set:
    from pathlib import Path
    import json

    path = Path(__file__).resolve().parents[2] / "data" / "legal" / "holidays_cn.json"
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return set((data.get("years") or {}).keys())
    except Exception:
        return set()


def calculate_defense_answer_deadline(
    service_date: str,
    *,
    holidays: Optional[List[str]] = None,
    treat_weekend_as_holiday: bool = True,
) -> Dict[str, Any]:
    """被告收到起诉状副本之日起十五日提出答辩状。"""
    rolled = roll_service_deadline(
        service_date,
        15,
        holidays=holidays,
        treat_weekend_as_holiday=treat_weekend_as_holiday,
    )
    basis = "《中华人民共和国民事诉讼法》（2023修正）第一百二十八条"
    rolled.update({
        "kind": "defense_answer",
        "period_label": "答辩期",
        "legal_basis": basis,
        "is_court_designated": False,
        "notes": [
            "被告应当在收到起诉状副本之日起十五日内提出答辩状。",
            "起算日（收到副本当日）不计入十五日。",
            rolled["holiday_rule"],
            "本结果只按上述条文测算。公告送达、留置送达或法院另定期间的，以送达回证和法院通知为准。",
        ],
    })
    return rolled


def calculate_evidence_period(
    anchor_date: str,
    *,
    period_days: Optional[int] = None,
    mode: str = "first_ordinary_minimum",
    holidays: Optional[List[str]] = None,
    treat_weekend_as_holiday: bool = True,
) -> Dict[str, Any]:
    """
    举证期限。

    first_ordinary_minimum：一审普通程序法院指定期限不得少于十五日，这是下限，不是法院已经指定的日期。
    second_new_evidence_minimum：二审提供新证据不得少于十日，同样只是下限。
    court_designated：按承办律师录入的法院指定天数顺延，不能代替通知书上已经写明的届满日。
    notice_due_date：直接采用通知书、传票上写明的届满日，不再换算。此时 anchor_date 就是该届满日。
    """
    mode_norm = (mode or "").strip() or "first_ordinary_minimum"
    if mode_norm == "notice_due_date":
        due = datetime.strptime(anchor_date.strip(), "%Y-%m-%d").date().strftime("%Y-%m-%d")
        return {
            "anchor_date": due,
            "period_days": None,
            "raw_deadline": due,
            "deadline": due,
            "extended_for_holiday_or_weekend": False,
            "warnings": [
                "这是承办律师从法院通知、传票或举证通知上抄录的届满日，系统没有再换算，也没有改成十五日下限。"
            ],
            "holiday_rule": "通知书已经写明届满日的，以通知书为准。",
            "kind": "evidence_production",
            "mode": "notice_due_date",
            "period_label": "通知书写明的举证期限届满日",
            "legal_basis": "以法院通知写明的日期为准，不用《民事诉讼法解释》第九十九条的下限代替",
            "is_court_designated": True,
            "is_statutory_minimum_only": False,
            "notes": ["届满日按通知书原文录入，不顺延、不重算。"],
        }
    basis = "《最高人民法院关于适用〈中华人民共和国民事诉讼法〉的解释》（2022年修正）第九十九条"
    warnings_extra: List[str] = []
    if mode_norm == "first_ordinary_minimum":
        days = 15
        label = "一审普通程序举证期限下限"
        warnings_extra.append(
            "这是第一审普通程序举证期限的法定下限（不得少于十五日），不是法院已经指定的届满日。"
            "法院通知或传票写了具体日期的，以该日期为准，不要用本结果覆盖。"
        )
        designated = False
    elif mode_norm == "second_new_evidence_minimum":
        days = 10
        label = "二审新证据举证期限下限"
        warnings_extra.append(
            "这是当事人在二审提供新的证据时，法院指定举证期限不得少于十日的下限，不是法院已经指定的届满日。"
        )
        designated = False
    elif mode_norm == "court_designated":
        if period_days is None:
            raise ValueError("法院指定举证期限时必须填写天数")
        days = int(period_days)
        label = "法院指定的举证期限"
        warnings_extra.append(
            "本结果按承办律师录入的天数，从起算日的次日连算并做休假日顺延。"
            "如果法院通知已经写明届满日，直接录入该日，不要再换算。"
        )
        designated = True
    else:
        raise ValueError("mode 仅允许 first_ordinary_minimum / second_new_evidence_minimum / court_designated")

    rolled = roll_service_deadline(
        anchor_date,
        days,
        holidays=holidays,
        treat_weekend_as_holiday=treat_weekend_as_holiday,
    )
    rolled["warnings"] = warnings_extra + list(rolled.get("warnings") or [])
    rolled.update({
        "kind": "evidence_production",
        "mode": mode_norm,
        "period_label": label,
        "legal_basis": basis,
        "is_court_designated": designated,
        "is_statutory_minimum_only": not designated,
        "notes": [
            f"{label}：{days} 日。",
            rolled["holiday_rule"],
            *warnings_extra,
        ],
    })
    return rolled


def _anniversary_then_roll(anchor_date: str, months: int) -> Dict[str, Any]:
    """按月的对应日为届满日，当日不计入；对应日遇休假日再顺延。"""
    from datetime import timedelta
    from gateway.utils.cn_legal_calc import add_months_exact

    anchor = datetime.strptime(anchor_date.strip(), "%Y-%m-%d").date()
    anniversary = add_months_exact(anchor, months)
    day_before = anniversary - timedelta(days=1)
    rolled = roll_service_deadline(day_before.strftime("%Y-%m-%d"), 1)
    rolled["anchor_date"] = anchor.strftime("%Y-%m-%d")
    rolled["period_months"] = months
    return rolled


def calculate_labor_arbitration_limitation(
    start_date: str,
    *,
    employment_ongoing: bool = False,
    wage_arrears: bool = False,
    employment_end_date: Optional[str] = None,
    interruption_dates: Optional[List[str]] = None,
    today_date: Optional[str] = None,
) -> Dict[str, Any]:
    """劳动争议申请仲裁时效。《劳动争议调解仲裁法》第二十七条。"""
    basis = "《劳动争议调解仲裁法》第二十七条"
    today = datetime.strptime(today_date, "%Y-%m-%d").date() if today_date else datetime.now().date()
    if employment_ongoing and wage_arrears:
        return {
            "cause_type": "labor_arbitration_1y",
            "rule_name": "劳动关系存续期间拖欠劳动报酬",
            "legal_basis": basis + "第四款",
            "open_ended": True,
            "is_preclusive": False,
            "start_date": start_date,
            "initial_expire_date": None,
            "final_expire_date": None,
            "days_remaining": None,
            "is_expired": False,
            "status_level": "OPEN",
            "calculation_benchmark_today": today.isoformat(),
            "status_label": "劳动关系存续期间拖欠劳动报酬，不受一年仲裁时效限制",
            "risk_alert": "不要改按民事诉讼三年，也不要催当事人必须在一年内申请仲裁。劳动关系终止的，自终止之日起一年内提出。",
            "timeline_log": [],
            "effective_interruptions_count": 0,
            "warnings": [
                "本结果只覆盖劳动关系存续期间的劳动报酬争议。经济补偿、赔偿金、加班费是否同属这一款，要按请求性质另核，不要整案套用。"
            ],
            "special_notice": "劳动关系终止后，应当自劳动关系终止之日起一年内提出。",
        }
    anchor = start_date
    warnings = [
        "申请仲裁的时效期间为一年，从当事人知道或者应当知道其权利被侵害之日起计算。",
        "向对方当事人主张权利、向有关部门请求权利救济，或者对方当事人同意履行义务的，时效中断，从中断时起重新计算一年。",
    ]
    if wage_arrears and employment_end_date:
        anchor = employment_end_date
        warnings.append("劳动关系已经终止的劳动报酬争议，自终止之日起一年内提出，不再从每笔工资应当发放之日起分别计算。")
    interruptions = [item.strip() for item in (interruption_dates or []) if item and item.strip()]
    if interruptions:
        anchor = max(interruptions)
        warnings.append(f"已按最近一次中断日 {anchor} 重新计算一年。中断事由是否成立，仍要核对送达和内容。")
    rolled = _anniversary_then_roll(anchor, 12)
    expire = datetime.strptime(rolled["deadline"], "%Y-%m-%d").date()
    days_remaining = (expire - today).days
    return {
        "cause_type": "labor_arbitration_1y",
        "rule_name": "劳动争议申请仲裁时效（一年）",
        "legal_basis": basis,
        "open_ended": False,
        "is_preclusive": False,
        "start_date": anchor,
        "initial_expire_date": rolled["raw_deadline"],
        "final_expire_date": rolled["deadline"],
        "days_remaining": days_remaining,
        "is_expired": days_remaining < 0,
        "status_level": "CRITICAL_EXPIRED" if days_remaining < 0 else "SAFE_GREEN",
        "calculation_benchmark_today": today.isoformat(),
        "status_label": "仲裁时效已届满" if days_remaining < 0 else f"仲裁时效还剩 {days_remaining} 天",
        "risk_alert": "这是劳动仲裁申请时效，不是《民法典》第一百八十八条的三年民事诉讼时效。",
        "timeline_log": [],
        "effective_interruptions_count": len(interruptions),
        "warnings": warnings + list(rolled.get("warnings") or []),
        "special_notice": warnings[1],
        "extended_for_holiday_or_weekend": rolled["extended_for_holiday_or_weekend"],
    }


def calculate_labor_award_court_deadline(receipt_date: str, path: str) -> Dict[str, Any]:
    """收到劳动裁决后的起诉或撤销期限。终局与非终局不能混用。"""
    paths = {
        "worker_final_15": (
            15,
            "labor_award_sue",
            "劳动者对终局裁决起诉",
            "《劳动争议调解仲裁法》第四十八条",
            "只适用于劳动者不服终局裁决。用人单位不能按这十五日起诉。",
        ),
        "either_party_nonfinal_15": (
            15,
            "labor_award_sue",
            "当事人对非终局裁决起诉",
            "《劳动争议调解仲裁法》第五十条",
            "只适用于本法第四十七条以外的裁决。终局裁决不要选这一项。",
        ),
        "employer_revoke_30": (
            30,
            "labor_award_revoke",
            "用人单位申请撤销终局裁决",
            "《劳动争议调解仲裁法》第四十九条",
            "用人单位对终局裁决是三十日内向中级人民法院申请撤销，不是十五日内起诉。",
        ),
    }
    if path not in paths:
        raise ValueError("path 只接受 worker_final_15、either_party_nonfinal_15 或 employer_revoke_30")
    days, kind, label, basis, note = paths[path]
    rolled = roll_service_deadline(receipt_date, days)
    rolled.update({
        "kind": kind,
        "period_label": label,
        "legal_basis": basis,
        "path": path,
        "notes": [
            note,
            "收到裁决书当日不计入。届满日遇法定休假日顺延。",
            rolled["holiday_rule"],
        ],
    })
    return rolled


def calculate_arbitration_set_aside_deadline(receipt_date: str) -> Dict[str, Any]:
    """商事仲裁申请撤销裁决。现行《仲裁法》第七十二条为三个月，不是修订前的六个月。"""
    rolled = _anniversary_then_roll(receipt_date, 3)
    rolled.update({
        "kind": "arbitration_set_aside",
        "period_label": "申请撤销仲裁裁决（三个月）",
        "legal_basis": "《中华人民共和国仲裁法》（2025修订）第七十二条",
        "notes": [
            "当事人申请撤销裁决的，应当自收到裁决书之日起三个月内提出。",
            "不要按修订前《仲裁法》的六个月计算。三个月是现行条文。",
            "收到裁决书当日不计入，届满日为三个月后的对应日；对应日遇法定休假日顺延。",
        ],
        "warnings": [
            "不要按六个月计算。现行《仲裁法》第七十二条写明的是收到裁决书之日起三个月。"
        ] + list(rolled.get("warnings") or []),
    })
    return rolled
