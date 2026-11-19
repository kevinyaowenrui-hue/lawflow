# -*- coding: utf-8 -*-
"""接案字段整理：不把占位当事人写成真实客户，并带上程序、收费和利冲结果。"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, Optional

PLACEHOLDER_PARTY_NAMES = {"委托人", "相对人", "未指定", "未填写"}
CLIENT_ROLES = {"原告", "被告", "第三人", "申请人", "被申请人"}
PROCEDURES = {
    "first_ordinary": "一审普通程序",
    "first_summary": "一审简易程序",
    "second_instance": "二审",
    "arbitration": "仲裁",
    "enforcement": "执行",
    "non_litigation": "非诉",
}
FEE_TYPES = {
    "unset": "未约定",
    "fixed": "固定收费",
    "staged": "分阶段收费",
    "risk": "风险代理",
}
FILING_CATALOG = (
    ("complaint", "起诉状"),
    ("engagement", "委托手续"),
    ("evidence_catalog", "证据目录"),
    ("service_address", "送达地址确认书"),
    ("identity", "身份证明材料"),
    ("evidence", "证据材料"),
)
FILING_STATUSES = ("未准备", "已准备", "已线下提交", "补正中")
FILING_NOTICE = "清单状态由律师自己勾选，不代表法院已经受理或立案。"
RISK_FEE_CONTRACT_NOTE = "勾选「已说明」不能代替书面风险代理合同。"
_RISK_FEE_ARTICLE_11 = (
    ("婚姻", ("婚姻", "离婚", "同居")),
    ("继承", ("继承", "遗赠", "遗产")),
    ("社会保险", ("社会保险", "社保待遇")),
    ("最低生活保障", ("最低生活保障", "低保")),
    ("赡养费", ("赡养",)),
    ("抚养费", ("抚养",)),
    ("扶养费", ("扶养",)),
    ("抚恤金", ("抚恤",)),
    ("救济金", ("救济金",)),
    ("工伤赔偿", ("工伤",)),
    ("劳动报酬", ("劳动报酬",)),
)
_RISK_FEE_ARTICLE_12 = (
    ("刑事", ("刑事",)),
    ("行政", ("行政",)),
    ("国家赔偿", ("国家赔偿",)),
    ("群体性诉讼", ("群体",)),
)


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _party_name(info: Optional[Dict[str, Any]], fallback: Any) -> str:
    if isinstance(info, dict) and _clean(info.get("name")):
        return _clean(info.get("name"))
    return _clean(fallback)


def _reject_placeholder(name: str, role_label: str) -> None:
    if name in PLACEHOLDER_PARTY_NAMES:
        raise ValueError(f"{role_label}不能使用「{name}」。请填写当事人真实姓名或企业全称。")


def _fee_position(
    fee_amount: Optional[float],
    fee_received: Optional[float],
    hourly_rate: Optional[float],
    hours_logged: Optional[float],
    fee_receivable: Optional[float],
) -> Dict[str, Any]:
    """应收、已收、未收。未收不为负；多收时标成待核对，不当成已经结清。"""
    rate = hourly_rate or 0.0
    hours = hours_logged or 0.0
    hourly_accrued = round(rate * hours, 2) if rate and hours else 0.0
    extra = ""
    if fee_receivable is not None:
        receivable = round(fee_receivable, 2)
        basis = "律师填写的应收"
    elif hourly_accrued and not fee_amount:
        receivable = hourly_accrued
        basis = "小时费率乘以已记小时"
    else:
        receivable = round(fee_amount or 0.0, 2)
        basis = "约定金额"
        if hourly_accrued and fee_amount:
            extra = "约定金额和小时费都有数，应收暂按约定金额，未把两笔相加。若按小时计收，请直接填写应收。"
    received = round(fee_received or 0.0, 2)
    raw = round(receivable - received, 2)
    if raw < 0:
        outstanding = 0.0
        overpaid = round(-raw, 2)
        settled = False
        label = f"已收多于应收 {overpaid:.2f} 元，未收按 0 显示，请核对，不要当成已经结清"
    else:
        outstanding = raw
        overpaid = 0.0
        settled = receivable > 0 and outstanding == 0
        if receivable == 0 and received == 0:
            label = "尚未约定应收"
        elif settled:
            label = "已收齐"
        else:
            label = f"未收 {outstanding:.2f} 元"
    if extra:
        label = f"{label}。{extra}"
    return {
        "fee_hourly_rate": rate,
        "fee_hours": hours,
        "fee_hourly_accrued": hourly_accrued,
        "fee_receivable": receivable,
        "fee_outstanding": outstanding,
        "fee_overpaid": overpaid,
        "fee_settled": settled,
        "fee_basis": basis,
        "fee_status_label": label,
    }


def default_filing_checklist() -> list:
    return [
        {"key": key, "label": label, "status": "未准备", "note": ""}
        for key, label in FILING_CATALOG
    ]


def normalize_filing_checklist(items: Any, existing: Any = None) -> list:
    """只接受律师勾选的四种状态。不接受「已受理」这类法院结论。"""
    catalog = {key: label for key, label in FILING_CATALOG}
    base = {item["key"]: dict(item) for item in default_filing_checklist()}
    if isinstance(existing, list):
        for raw in existing:
            if not isinstance(raw, dict):
                continue
            key = str(raw.get("key") or "").strip()
            if key not in catalog:
                continue
            status = str(raw.get("status") or "").strip()
            if status in FILING_STATUSES:
                base[key]["status"] = status
            note = str(raw.get("note") or "").strip()
            if note:
                base[key]["note"] = note[:200]
    if not items:
        return [base[key] for key, _label in FILING_CATALOG]
    if not isinstance(items, list):
        raise ValueError("立案材料清单格式不对。请逐项选择未准备、已准备、已线下提交或补正中。")
    for raw in items:
        if not isinstance(raw, dict):
            raise ValueError("立案材料清单里有无法识别的一项。")
        key = str(raw.get("key") or "").strip()
        if key not in catalog:
            raise ValueError("不认识的立案材料。请使用起诉状、委托手续、证据目录、送达地址确认书、身份证明材料或证据材料。")
        status = str(raw.get("status") or "").strip()
        if status not in FILING_STATUSES:
            raise ValueError("立案材料状态只能由律师选择：未准备、已准备、已线下提交、补正中。系统不推测法院已经受理。")
        note = str(raw.get("note") or "").strip()
        if len(note) > 200:
            raise ValueError("材料备注请控制在 200 字以内。")
        base[key]["status"] = status
        base[key]["label"] = catalog[key]
        base[key]["note"] = note
    return [base[key] for key, _label in FILING_CATALOG]


def normalize_seal_records(records: Any) -> list:
    """用印只登记文件名、份数和日期，不做审批流。"""
    if not records:
        return []
    if not isinstance(records, list):
        raise ValueError("用印登记必须是一组记录，每条包含文件名、份数和日期。")
    normalized = []
    for index, raw in enumerate(records, 1):
        if not isinstance(raw, dict):
            raise ValueError(f"第 {index} 条用印登记不是有效记录。")
        filename = str(raw.get("filename") or raw.get("file_name") or "").strip()
        if not filename:
            raise ValueError(f"第 {index} 条用印登记缺少文件名。")
        if len(filename) > 200:
            raise ValueError("用印文件名请控制在 200 字以内。")
        copies = raw.get("copies")
        try:
            copies_num = int(copies)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"第 {index} 条用印份数必须是正整数。") from exc
        if isinstance(copies, float) and not copies.is_integer():
            raise ValueError(f"第 {index} 条用印份数必须是正整数。")
        if isinstance(copies, str) and "." in copies.strip():
            raise ValueError(f"第 {index} 条用印份数必须是正整数。")
        if copies_num < 1 or copies_num > 99:
            raise ValueError(f"第 {index} 条用印份数必须是 1 到 99 的整数。")
        used_on = str(raw.get("date") or "").strip()
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", used_on):
            raise ValueError(f"第 {index} 条用印日期必须是 YYYY-MM-DD，例如 2026-11-11。")
        try:
            datetime.strptime(used_on, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError(f"第 {index} 条用印日期不是有效日期。") from exc
        normalized.append({"filename": filename, "copies": copies_num, "date": used_on})
    return normalized


def receivable_of(practice: Optional[Dict[str, Any]]) -> float:
    data = practice or {}
    if data.get("fee_receivable") is not None:
        return round(float(data.get("fee_receivable") or 0), 2)
    position = _fee_position(
        data.get("fee_amount"),
        data.get("fee_received"),
        data.get("fee_hourly_rate") if data.get("fee_hourly_rate") is not None else data.get("hourly_rate"),
        data.get("fee_hours") if data.get("fee_hours") is not None else data.get("hours_logged"),
        None,
    )
    return float(position["fee_receivable"])


def assert_invoice_within_receivable(invoiced: Optional[float], receivable: float) -> None:
    if invoiced is None:
        return
    if round(invoiced * 100) > round(float(receivable) * 100):
        raise ValueError(
            f"已开票金额不能大于应收。当前应收 {float(receivable):.2f} 元，填写的已开票 {invoiced:.2f} 元。"
        )


def _money(value: Any, label: str) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        amount = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label}必须是数字") from exc
    if amount < 0:
        raise ValueError(f"{label}不能为负数")
    return amount


def prohibited_risk_fee(cause: str) -> Optional[tuple]:
    """案由落入《律师服务收费管理办法》第十一条或第十二条时，返回（条、类型）。"""
    text = _clean(cause)
    for label, keys in _RISK_FEE_ARTICLE_11:
        if any(key in text for key in keys):
            return "第十一条", label
    for label, keys in _RISK_FEE_ARTICLE_12:
        if any(key in text for key in keys):
            return "第十二条", label
    return None


def _parse_risk_ratio(practice_in: Dict[str, Any], data: Dict[str, Any]) -> Optional[float]:
    raw = None
    for source in (practice_in, data):
        if not isinstance(source, dict):
            continue
        for key in ("risk_fee_ratio", "fee_ratio", "agreed_ratio"):
            if source.get(key) not in (None, ""):
                raw = source.get(key)
                break
        if raw not in (None, ""):
            break
    if raw is None or raw == "":
        return None
    text = str(raw).strip().replace("％", "%")
    if text.endswith("%"):
        text = text[:-1].strip()
    try:
        value = float(text)
    except (TypeError, ValueError) as exc:
        raise ValueError("风险代理约定比例必须填写数字，表示按标的额收取的百分数。") from exc
    if value <= 0 or value > 100:
        raise ValueError("风险代理约定比例按百分数填写，须大于 0 且不超过 100。")
    return value


def normalize_matter_intake(data: Dict[str, Any]) -> Dict[str, Any]:
    """整理新建/更新案件。缺当事人时允许先建草稿，但禁止占位姓名。"""
    title = _clean(data.get("title"))
    cause = _clean(data.get("cause_of_action"))
    if not title:
        raise ValueError("请填写案件名称")
    if not cause:
        raise ValueError("请填写案由")

    role = _clean(data.get("client_role")) or "原告"
    if role not in CLIENT_ROLES:
        raise ValueError("委托人诉讼地位只接受：原告、被告、第三人、申请人、被申请人")

    plaintiff_info = dict(data.get("plaintiff_info") or {})
    defendant_info = dict(data.get("defendant_info") or {})
    p_name = _party_name(plaintiff_info, data.get("plaintiff_name"))
    d_name = _party_name(defendant_info, data.get("defendant_name"))
    _reject_placeholder(p_name, "原告")
    _reject_placeholder(d_name, "被告")
    if p_name:
        plaintiff_info["name"] = p_name
    if d_name:
        defendant_info["name"] = d_name

    for src, info, key in (
        (data.get("plaintiff_phone"), plaintiff_info, "phone"),
        (data.get("plaintiff_id"), plaintiff_info, "id_no"),
        (data.get("defendant_phone"), defendant_info, "phone"),
        (data.get("defendant_id"), defendant_info, "id_no"),
    ):
        text = _clean(src)
        if text and not info.get(key):
            info[key] = text

    principal = data.get("principal_amount")
    if principal is None or principal == "":
        principal_amount = 0.0
    else:
        principal_amount = _money(principal, "标的金额") or 0.0

    practice_in = data.get("practice") if isinstance(data.get("practice"), dict) else {}
    procedure = _clean(practice_in.get("procedure") or data.get("procedure"))
    if procedure and procedure not in PROCEDURES:
        raise ValueError("程序只接受一审普通、一审简易、二审、仲裁、执行或非诉")
    fee_type = _clean(practice_in.get("fee_type") or data.get("fee_type")) or "unset"
    if fee_type not in FEE_TYPES:
        raise ValueError("收费方式只接受未约定、固定收费、分阶段收费或风险代理")
    fee_amount = _money(practice_in.get("fee_amount", data.get("fee_amount")), "约定律师费")
    fee_received = _money(practice_in.get("fee_received", data.get("fee_received")), "已到账律师费")
    hourly_rate = _money(practice_in.get("hourly_rate", data.get("hourly_rate")), "小时费率")
    hours_logged = _money(practice_in.get("hours_logged", data.get("hours_logged")), "已记小时")
    fee_receivable = _money(practice_in.get("fee_receivable", data.get("fee_receivable")), "应收")
    risk_disclosed = bool(practice_in.get("risk_disclosed", data.get("risk_disclosed")))
    risk_fee_ratio = None
    risk_fee_warning = ""
    if fee_type == "risk":
        banned = prohibited_risk_fee(cause)
        if banned:
            article, label = banned
            raise ValueError(
                f"《律师服务收费管理办法》{article}禁止对{label}案件实行风险代理。"
                f"本案案由「{cause}」属于禁止类型，不能按风险代理保存。"
                f"{RISK_FEE_CONTRACT_NOTE}"
            )
        if not risk_disclosed:
            raise ValueError(
                "风险代理必须记录已经向委托人说明收费风险。未勾选前不能按风险代理建档。"
                + RISK_FEE_CONTRACT_NOTE
            )
        risk_fee_ratio = _parse_risk_ratio(practice_in, data)
        if risk_fee_ratio is None:
            raise ValueError(
                "其他财产案件实行风险代理，必须填写约定比例。"
                + RISK_FEE_CONTRACT_NOTE
            )
        if risk_fee_ratio > 30:
            risk_fee_warning = (
                f"约定比例为标的额的 {risk_fee_ratio:g}%，已超过 30%。"
                "《律师服务收费管理办法》规定风险代理最高收费不得高于约定标的额的 30%，当地收费办法可能更严。"
            )

    same_matter = practice_in.get("is_same_matter", data.get("is_same_matter"))
    practice = {
        "procedure": procedure,
        "procedure_label": PROCEDURES.get(procedure, "未选择程序"),
        "client_role": role,
        "fee_type": fee_type,
        "fee_type_label": FEE_TYPES[fee_type],
        "fee_amount": fee_amount,
        "fee_received": fee_received,
        "fee_note": _clean(practice_in.get("fee_note") or data.get("fee_note")),
        **_fee_position(fee_amount, fee_received, hourly_rate, hours_logged, fee_receivable),
        "risk_disclosed": risk_disclosed,
        "risk_fee_ratio": risk_fee_ratio,
        "risk_fee_warning": risk_fee_warning,
        "risk_fee_contract_note": RISK_FEE_CONTRACT_NOTE if fee_type == "risk" else "",
        "is_same_matter": same_matter,
    }
    for preserved in (
        "claims",
        "extra_parties",
        "conflict_conclusion",
        "closeout",
        "local_filing_items",
        "jurisdiction",
        "defendant_posture",
        "conflict",
        "personnel_status",
        "personnel_check",
        "filing_checklist",
        "seal_records",
        "filing_notice",
        "fee_invoiced",
    ):
        if preserved in practice_in and preserved not in practice:
            practice[preserved] = practice_in[preserved]

    out = dict(data)
    out.update({
        "title": title,
        "cause_of_action": cause,
        "client_role": role,
        "plaintiff_info": plaintiff_info if p_name or plaintiff_info else {},
        "defendant_info": defendant_info if d_name or defendant_info else {},
        "plaintiff_name": p_name,
        "defendant_name": d_name,
        "principal_amount": principal_amount,
        "case_summary": _clean(data.get("case_summary") or data.get("summary")),
        "practice": practice,
    })
    return out


def conflict_parties(intake: Dict[str, Any]) -> Dict[str, str]:
    """按委托人地位确定利冲比对的客户和对方，而不是永远把原告当成委托人。"""
    role = intake.get("client_role") or "原告"
    p_name = intake.get("plaintiff_name") or ""
    d_name = intake.get("defendant_name") or ""
    p_info = intake.get("plaintiff_info") or {}
    d_info = intake.get("defendant_info") or {}
    if role in {"被告", "被申请人"}:
        return {
            "client_name": d_name,
            "opposing_name": p_name,
            "client_id": (d_info.get("id_no") or ""),
            "opposing_id": (p_info.get("id_no") or ""),
        }
    return {
        "client_name": p_name,
        "opposing_name": d_name,
        "client_id": (p_info.get("id_no") or ""),
        "opposing_id": (d_info.get("id_no") or ""),
    }
