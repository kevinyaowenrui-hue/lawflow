"""
LawFlow 智律工作台 - P2 阶段：复杂交易多方交叉担保拓扑与资金穿透流水精算引擎
(Cross-Guarantee Topology & Fund Tracing Cashflow Reconciliation Engine)

核心实务风控与精算法则：
1. 《民法典》第692条保证期间监控与除斥期间灭失阻断；
2. 《民法典》第392条人保与物保并存受偿顺位判定（有约定从约定；无约定且债务人自有物保时先就物保实现）；
3. 《担保制度解释》第7、8、9、10、17条及《公司法》第15条公司对外担保效力与过错责任；
4. 《民法典》第561条法定抵充顺序（费用→利息→主债务；当事人另有约定的除外）；
5. 资金穿透全链路追踪与三大异常风险探针（同日回流、代付阻断、附言冲突）。
"""

import re
from datetime import datetime, date
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, List, Optional, Tuple

from gateway.utils.cn_legal_calc import (
    add_months_exact,
    get_private_lending_four_times_lpr_cap,
)


_ISO_DATE_RE = re.compile(r"(20\d{2}-\d{2}-\d{2})")
_CN_DATE_RE = re.compile(r"(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")


def _parse_date_from_text(text: str) -> Optional[date]:
    if not text:
        return None
    m = _ISO_DATE_RE.search(text)
    if m:
        try:
            return datetime.strptime(m.group(1), "%Y-%m-%d").date()
        except ValueError as val_err:
            logger.debug(f"日期解析失败: {val_err}")
    m2 = _CN_DATE_RE.search(text)
    if m2:
        try:
            return date(int(m2.group(1)), int(m2.group(2)), int(m2.group(3)))
        except ValueError as val_err:
            logger.debug(f"中文日期解析失败: {val_err}")
    return None


def _insufficient_data(missing_fields: List[str], message: str) -> Dict[str, Any]:
    return {
        "status": "insufficient_data",
        "missing_fields": missing_fields,
        "message": message,
        "guarantee_audits": [],
        "collateral_audits": [],
        "reconciliation_ledger": [],
        "unclassified_records": [],
    }


def _extract_principal_due_date(
    principal_due_date: Optional[str],
    timeline: Optional[List[Dict[str, Any]]],
) -> Optional[date]:
    if principal_due_date:
        try:
            return datetime.strptime(principal_due_date, "%Y-%m-%d").date()
        except ValueError as val_err:
            logger.debug(f"本金到期日解析失败: {val_err}")

    if not timeline:
        return None

    for ev in timeline:
        tag = str(ev.get("legal_tag", "") or "")
        event_text = str(ev.get("event", "") or "")
        blob = event_text + " " + tag
        if any(k in blob for k in ("借期届满", "合同到期", "到期", "届满")):
            # 优先从事件正文解析“到期 2023-12-31”
            parsed = _parse_date_from_text(event_text)
            if parsed:
                return parsed
            d_str = str(ev.get("date", "") or "")[:10]
            if d_str:
                try:
                    return datetime.strptime(d_str, "%Y-%m-%d").date()
                except Exception:
                    continue
    return None


def _infer_guarantee_mode(edge: Dict[str, Any], rel_type: str, detail: str) -> Tuple[str, bool, str]:
    """
    返回 (mode, mode_inferred, hint)。
    mode ∈ {"general","joint"}
    """
    raw = edge.get("guarantee_mode")
    if raw in ("general", "joint"):
        return raw, False, ""

    text = f"{rel_type} {detail}"
    if "一般保证" in text:
        return "general", False, ""
    if "连带" in text:
        return "joint", False, ""

    hint = (
        "合同未明确约定保证方式，依《民法典》第686条第2款按一般保证处理，请核实合同原文"
    )
    return "general", True, hint


def _is_guarantee_edge(rel_type: str, detail: str) -> bool:
    # 关系类型明确为物保时，不按人保边处理（即便 detail 提及保证人）
    if any(k in rel_type for k in ("抵押", "质押", "留置", "物保", "房产抵押", "股权质押")):
        return False
    blob = f"{rel_type} {detail}"
    return (
        "保证" in blob
        or "连带" in blob
        or "担保责任" in blob
        or "个人无限连带" in blob
    )


def _resolve_guarantee_expiry(
    p_due: date,
    edge: Dict[str, Any],
    detail: str,
) -> Tuple[date, str]:
    """
    约定届满日早于或等于主债务到期日 → 视为没有约定，按 6 个月；
    约定原文含“直至主债务本息还清时为止”等 → 视为约定不明，按 6 个月；
    其他有效约定按约定日。
    """
    statutory = add_months_exact(p_due, 6)
    agreed_text = str(
        edge.get("agreed_period_text") or edge.get("agreed_guarantee_period_text") or detail or ""
    )
    unclear_markers = (
        "直至主债务本息还清时为止",
        "至本息还清时止",
        "本息还清为止",
        "还清时为止",
    )
    if any(m in agreed_text for m in unclear_markers):
        return statutory, (
            "约定原文含类似“直至主债务本息还清时为止”的内容，依《担保制度解释》第32条"
            "视为约定不明，保证期间为主债务履行期限届满之日起六个月"
        )

    agreed_expiry_raw = edge.get("agreed_guarantee_expiry") or edge.get("agreed_expiry")
    agreed_expiry: Optional[date] = None
    if agreed_expiry_raw:
        try:
            agreed_expiry = datetime.strptime(str(agreed_expiry_raw)[:10], "%Y-%m-%d").date()
        except Exception:
            agreed_expiry = _parse_date_from_text(str(agreed_expiry_raw))

    if agreed_expiry is not None:
        if agreed_expiry <= p_due:
            return statutory, (
                "约定的保证期间早于或与主债务履行期限同时届满，依《民法典》第692条第2款"
                "视为没有约定，保证期间为主债务履行期限届满之日起六个月"
            )
        return agreed_expiry, f"按约定保证期间届满日 {agreed_expiry} 计算"

    return statutory, "未约定或约定不明确，依《民法典》第692条第2款按主债务履行期限届满之日起六个月"


def _find_effective_demand(
    timeline: Optional[List[Dict[str, Any]]],
    mode: str,
    guarantor_name: str,
    debtor_name: str,
    expiry: date,
) -> Tuple[bool, Optional[date], str]:
    """
    一般保证：保证期间内对债务人提起诉讼或申请仲裁才有效；催告/律师函/EMS 无效。
    连带责任保证：保证期间内向保证人提出请求（催告、律师函、起诉、仲裁）有效。
    文案引用《民法典》第693条要点（非原文）。
    """
    if not timeline:
        return False, None, ""

    best: Optional[date] = None
    note = ""

    for ev in timeline:
        text = str(ev.get("event", "") or "")
        tag = str(ev.get("legal_tag", "") or "")
        blob = text + " " + tag
        d_str = str(ev.get("date", "") or "")[:10]
        try:
            d_parsed = datetime.strptime(d_str, "%Y-%m-%d").date()
        except Exception:
            continue
        if d_parsed > expiry:
            continue

        if mode == "general":
            is_suit = ("起诉" in blob) or ("仲裁" in blob) or ("立案" in blob and "起诉" in blob)
            targets_debtor = (debtor_name and debtor_name in text) or (
                "债务人" in text and (not guarantor_name or guarantor_name not in text)
            ) or ("对债务人" in text)
            # 仅律师函/催告/EMS → 无效
            if any(k in blob for k in ("律师函", "催告", "催要", "EMS", "发函")) and not is_suit:
                continue
            if is_suit and targets_debtor:
                if best is None or d_parsed < best:
                    best = d_parsed
                    note = (
                        f"债权人已于 {d_parsed}（保证期间届满前）对债务人提起诉讼或申请仲裁。"
                        "要点（《民法典》第693条）：一般保证中，债权人未在保证期间内对债务人"
                        "提起诉讼或申请仲裁的，保证人不再承担保证责任；本案已依法主张，保证责任未因期间届满而免除。"
                    )
        else:
            # joint
            is_request = any(
                k in blob
                for k in ("催告", "催要", "律师函", "起诉", "仲裁", "立案", "EMS", "发函", "要求承担保证")
            )
            targets_guarantor = (guarantor_name and guarantor_name in text) or ("保证人" in text)
            if is_request and targets_guarantor:
                if best is None or d_parsed < best:
                    best = d_parsed
                    note = (
                        f"债权人已于 {d_parsed}（保证期间届满前）向保证人提出承担保证责任的请求。"
                        "要点（《民法典》第693条）：连带责任保证中，债权人未在保证期间内请求保证人"
                        "承担保证责任的，保证人不再承担保证责任；本案已依法请求，保证责任未因期间届满而免除。"
                    )

    return (best is not None), best, note


def _build_corporate_resolution_risk(
    edge: Dict[str, Any],
    creditor_at_fault: Optional[bool],
    guarantor_at_fault: Optional[bool],
) -> Dict[str, Any]:
    statute_basis = (
        "《担保制度解释》第7、8、9、10、17条；《公司法》第15条"
    )
    case_both_fault = (
        "债权人与担保人均有过错的，担保人承担的赔偿责任不应超过债务人不能清偿部分的二分之一"
        "（《担保制度解释》第17条）"
    )
    case_guarantor_only = (
        "担保人有过错而债权人无过错的，担保人对债务人不能清偿的部分承担赔偿责任"
        "（《担保制度解释》第17条）"
    )
    case_creditor_only = (
        "债权人有过错而担保人无过错的，担保人不承担赔偿责任"
        "（《担保制度解释》第17条）"
    )
    art8_note = (
        "另有无需机构决议的情形（见《担保制度解释》第8条，具体情形请律师核实）"
    )

    cf = edge.get("creditor_at_fault") if "creditor_at_fault" in edge else creditor_at_fault
    gf = edge.get("guarantor_at_fault") if "guarantor_at_fault" in edge else guarantor_at_fault

    if cf is not None and gf is not None:
        if cf and gf:
            selected = case_both_fault
        elif gf and not cf:
            selected = case_guarantor_only
        elif cf and not gf:
            selected = case_creditor_only
        else:
            selected = "双方均无过错时的责任承担，请结合《担保制度解释》第7、9、10条及案情由律师核实。"
        audit_note = (
            "公司对外担保可能涉及越权代表效力问题。"
            f"{selected}。{art8_note}。"
        )
    else:
        audit_note = (
            "公司对外担保可能涉及越权代表效力问题。越权担保无效后的赔偿责任，依《担保制度解释》第17条区分："
            f"（1）{case_both_fault}；（2）{case_guarantor_only}；（3）{case_creditor_only}。"
            f"{art8_note}。"
        )

    return {
        "is_company": True,
        "statute_basis": statute_basis,
        "audit_note": audit_note,
        "verification_status": "PENDING_HUMAN",
    }


# ==============================================================================
# 1. 复杂多方交叉担保拓扑与保证期间灭失/物保人保受偿顺位引擎
# ==============================================================================

def analyze_guarantee_topology_and_deadlines(
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
    timeline: Optional[List[Dict[str, Any]]] = None,
    principal_due_date: Optional[str] = None,
    today_date: Optional[str] = None,
    creditor_at_fault: Optional[bool] = None,
    guarantor_at_fault: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    复杂交易多方交叉担保拓扑分析与执业红线监控：
    - 保证期间检测（民法典692条法定6个月；有有效约定从约定）；
    - 人保与物保并存受偿顺位（民法典392条：有约定从约定）；
    - 公司对外担保（《担保制度解释》第7-10、17条等）。
    """
    today = datetime.strptime(today_date, "%Y-%m-%d").date() if today_date else date.today()

    p_due = _extract_principal_due_date(principal_due_date, timeline)
    if not p_due:
        return _insufficient_data(
            missing_fields=["principal_due_date"],
            message="缺少主债务履行期限届满日，无法计算保证期间",
        )

    node_map: Dict[str, Any] = {}
    debtor_id = None
    debtor_name = "主债务人"
    creditor_id = None
    creditor_name = "出借人/债权人"

    for n in nodes:
        nid = str(n.get("id", ""))
        name = str(n.get("name", ""))
        role = str(n.get("role", "")).lower()
        node_map[nid] = n
        if name:
            node_map[name] = n
        if "主债务" in role or "被告" in role or "借款人" in role:
            if not debtor_id:
                debtor_id = nid
                debtor_name = name
        elif "原告" in role or "出借人" in role or "债权人" in role:
            if not creditor_id:
                creditor_id = nid
                creditor_name = name

    guarantee_audits: List[Dict[str, Any]] = []
    collateral_audits: List[Dict[str, Any]] = []
    topology_nodes: List[Dict[str, Any]] = []
    topology_edges: List[Dict[str, Any]] = []

    statutory_guarantee_expiry = add_months_exact(p_due, 6)

    for edge in edges:
        source_id = str(edge.get("source", ""))
        target_id = str(edge.get("target", ""))
        rel_type = str(edge.get("type", "") or edge.get("relation", "") or "")
        detail = str(edge.get("detail", "") or edge.get("details", "") or "")

        source_node = node_map.get(source_id, {})
        target_node = node_map.get(target_id, {})
        source_name = source_node.get("name", source_id) if isinstance(source_node, dict) else source_id
        target_name = target_node.get("name", target_id) if isinstance(target_node, dict) else target_id

        # A. 保证审查
        if _is_guarantee_edge(rel_type, detail):
            guarantor_name = source_name
            guarantor_node = source_node if isinstance(source_node, dict) else {}
            is_company = (
                "有限公司" in str(guarantor_name)
                or "股份" in str(guarantor_name)
                or guarantor_node.get("type") in ["company", "企业", "企业主体"]
            )

            mode, mode_inferred, mode_hint = _infer_guarantee_mode(edge, rel_type, detail)
            guarantee_type = "连带责任保证" if mode == "joint" else "一般保证"
            if mode_inferred:
                guarantee_type = f"一般保证（依《民法典》第686条第2款推定）"
            elif mode == "joint":
                guarantee_type = "连带责任保证"
            else:
                guarantee_type = "一般保证"

            expiry, period_basis = _resolve_guarantee_expiry(p_due, edge, detail)
            has_demanded, demand_date, demand_note = _find_effective_demand(
                timeline, mode, guarantor_name, debtor_name, expiry
            )

            days_to_expiry = (expiry - today).days
            status = "NORMAL_UNEXPIRED"
            status_label = f"在保证期间内 (剩 {days_to_expiry} 天)"
            status_color = "#1E40AF"
            warning_msg = f"当前处于保证期间内，截止日为 {expiry}。{period_basis}"

            if has_demanded and demand_date is not None:
                status = "SAFE"
                status_label = "保证期间已依法阻断"
                status_color = "#15803D"
                warning_msg = demand_note
            else:
                if today > expiry:
                    status = "CRITICAL_EXPIRED"
                    status_color = "#B91C1C"
                    # 若期间外曾有主张，标注“已过·责任免除”；完全无主张则“法定灭失”
                    late_claim = False
                    if timeline:
                        for ev in timeline:
                            t = str(ev.get("event", "") or "")
                            if guarantor_name and guarantor_name in t and any(
                                k in t for k in ("催告", "律师函", "起诉", "仲裁", "EMS", "发函")
                            ):
                                late_claim = True
                                break
                    if late_claim:
                        status_label = "保证期间已过·责任免除！"
                    else:
                        status_label = "保证责任已法定灭失！"
                    if mode == "general":
                        warning_msg = (
                            f"重大执业风险！主债务已于 {p_due} 届满，保证期间已于 {expiry} 届满！"
                            "卷宗中未发现保证期间内对债务人提起诉讼或申请仲裁的记录。"
                            "要点（《民法典》第693条）：一般保证中，债权人未在保证期间内对债务人提起诉讼或申请仲裁的，"
                            "保证人不再承担保证责任。催告、律师函、EMS 不构成一般保证下的有效主张。"
                        )
                    else:
                        late_note = ""
                        if late_claim:
                            late_note = (
                                f"主张日期晚于法定保证期间截止日 {expiry}，依据《民法典》第692条第二款，"
                                "保证人免除保证责任！"
                            )
                        warning_msg = (
                            f"致命执业险情！保证期间截止日 {expiry} 已届满，卷宗中未发现保证期间内向该保证人提出请求的有效记录。"
                            "要点（《民法典》第693条）：连带责任保证中，债权人未在保证期间内请求保证人承担保证责任的，"
                            f"保证人不再承担保证责任。{late_note}"
                        )
                elif days_to_expiry <= 30:
                    status = "WARNING_EXPIRING_SOON"
                    status_label = f"临近届满 (剩 {days_to_expiry} 天)"
                    status_color = "#C58532"
                    if mode == "general":
                        warning_msg = (
                            f"紧急红线：保证期间将于 {expiry} 届满（仅剩 {days_to_expiry} 天）！"
                            "一般保证须在截止日前对债务人提起诉讼或申请仲裁，仅发律师函不足以保全保证债权。"
                        )
                    else:
                        warning_msg = (
                            f"紧急红线：保证期间将于 {expiry} 届满（仅剩 {days_to_expiry} 天）！"
                            "须在截止日前向保证人提出请求（催告、律师函、起诉或仲裁），否则保证债权可能灭失。"
                        )
                else:
                    status = "NORMAL_UNEXPIRED"
                    status_label = f"在保证期间内 (剩 {days_to_expiry} 天)"
                    status_color = "#1E40AF"
                    warning_msg = f"当前处于保证期间内，截止日为 {expiry}。依据：{period_basis}"

            if mode_hint:
                warning_msg = mode_hint + " " + warning_msg

            corporate_resolution_risk = None
            if is_company:
                corporate_resolution_risk = _build_corporate_resolution_risk(
                    edge, creditor_at_fault, guarantor_at_fault
                )

            guarantee_audits.append({
                "guarantor_name": guarantor_name,
                "guarantor_type": "企业法人保证" if is_company else "自然人保证",
                "guarantee_type": guarantee_type,
                "guarantee_mode": mode,
                "mode_inferred": mode_inferred,
                "principal_due_date": str(p_due),
                "guarantee_expiry_date": str(expiry),
                "period_basis": period_basis,
                "has_demanded_in_time": has_demanded,
                "demand_date": str(demand_date) if demand_date else None,
                "days_remaining": days_to_expiry,
                "status": status,
                "status_label": status_label,
                "status_color": status_color,
                "warning_message": warning_msg,
                "corporate_resolution_check": corporate_resolution_risk,
            })

        # B. 抵押 / 质押 物保受偿顺位审查 (《民法典》第392条)
        elif any(k in rel_type for k in ["抵押", "质押", "物保", "房产抵押", "股权质押", "留置"]):
            collateral_provider = source_name
            is_debtor_property = (source_id == debtor_id) or (source_name == debtor_name)

            has_order_agreement = edge.get("has_enforcement_order_agreement")
            if has_order_agreement is None:
                has_order_agreement = ("约定" in detail and "实现顺序" in detail) or (
                    "实现顺序" in detail
                ) or ("约定实现" in detail)

            if has_order_agreement:
                priority_rank = "按约定顺位"
                priority_level = 0
                statutory_rule = "按照约定实现债权（《民法典》第392条）"
                action_warning = (
                    "本案就人保与物保并存的实现顺序已有约定，应按照约定实现债权（《民法典》第392条）。"
                )
            elif is_debtor_property:
                priority_rank = "第一顺位 (债务人物保优先)"
                priority_level = 1
                statutory_rule = (
                    "无约定或约定不明确，且债务人自己提供物的担保的，"
                    "债权人应当先就该物的担保实现债权；保证人可以在债务人物保范围内主张免责抗辩"
                    "（《民法典》第392条）"
                )
                action_warning = (
                    "本案抵押物系主债务人自身财产，且无关于实现顺序的明确约定时，"
                    "债权人应当先就该物的担保实现债权；保证人可以在债务人物保范围内主张免责抗辩"
                    "（《民法典》第392条）。"
                )
            else:
                priority_rank = "并列顺位 (债权人选择权)"
                priority_level = 2
                statutory_rule = (
                    "第三人提供物的担保的，债权人可以就物的担保实现债权，也可以请求保证人承担保证责任"
                    "（《民法典》第392条）。"
                )
                action_warning = (
                    "抵押物系第三人提供，债权人享有受偿选择权，可根据查封顺位与变现难易度决定执行路径。"
                )

            collateral_audits.append({
                "collateral_provider": collateral_provider,
                "is_debtor_own_property": is_debtor_property,
                "has_enforcement_order_agreement": bool(has_order_agreement),
                "priority_rank": priority_rank,
                "priority_level": priority_level,
                "statutory_rule": statutory_rule,
                "action_warning": action_warning,
                "detail": detail,
            })

    for n in nodes:
        nid = str(n.get("id", ""))
        name = str(n.get("name", ""))
        role = str(n.get("role", ""))
        g_audit = next((g for g in guarantee_audits if g["guarantor_name"] == name), None)
        c_audit = next((c for c in collateral_audits if c["collateral_provider"] == name), None)
        topology_nodes.append({
            "id": nid,
            "name": name,
            "role": role,
            "type": n.get("type", "entity"),
            "guarantee_status": g_audit.get("status") if g_audit else None,
            "guarantee_badge": g_audit.get("status_label") if g_audit else None,
            "is_debtor_own_collateral": c_audit.get("is_debtor_own_property") if c_audit else False,
            "collateral_priority": c_audit.get("priority_rank") if c_audit else None,
        })

    for e in edges:
        s_id = str(e.get("source", ""))
        t_id = str(e.get("target", ""))
        r_type = str(e.get("type", "") or e.get("relation", "") or "")
        det = str(e.get("detail", "") or e.get("details", "") or "")
        s_name = node_map.get(s_id, {}).get("name", s_id) if isinstance(node_map.get(s_id), dict) else s_id
        t_name = node_map.get(t_id, {}).get("name", t_id) if isinstance(node_map.get(t_id), dict) else t_id
        topology_edges.append({
            "source_id": s_id,
            "target_id": t_id,
            "source_name": s_name,
            "target_name": t_name,
            "relation_type": r_type,
            "detail": det,
            "is_guarantee": _is_guarantee_edge(r_type, det),
            "is_collateral": any(k in r_type for k in ["抵押", "质押", "物保"]),
        })

    tactical_summary = _generate_guarantee_topology_memo(
        debtor_name=debtor_name,
        principal_due_date=str(p_due),
        guarantee_audits=guarantee_audits,
        collateral_audits=collateral_audits,
    )

    return {
        "status": "success",
        "principal_due_date": str(p_due),
        "statutory_guarantee_expiry": str(statutory_guarantee_expiry),
        "guarantee_audits": guarantee_audits,
        "collateral_audits": collateral_audits,
        "topology": {
            "nodes": topology_nodes,
            "edges": topology_edges,
        },
        "partner_tactical_memo": tactical_summary,
    }


def _generate_guarantee_topology_memo(
    debtor_name: str,
    principal_due_date: str,
    guarantee_audits: List[Dict[str, Any]],
    collateral_audits: List[Dict[str, Any]],
) -> str:
    lines = []
    lines.append("【合伙人多方交叉担保与保证期间执业审定备忘录】")
    lines.append(f"主债务人：{debtor_name} · 主债务约定到期日：{principal_due_date}")
    lines.append("")
    lines.append("一、《民法典》第692条保证期间审计：")
    if not guarantee_audits:
        lines.append("  • 本案未识别到明确保证人主体。")
    else:
        for idx, g in enumerate(guarantee_audits, 1):
            lines.append(f"  ({idx}) 保证人【{g['guarantor_name']}】（{g['guarantor_type']}）：")
            lines.append(
                f"      保证方式：{g['guarantee_type']} · 保证期间截止日：{g['guarantee_expiry_date']} · 当前状态：【{g['status_label']}】"
            )
            lines.append(f"      期间依据：{g.get('period_basis', '')}")
            lines.append(f"      风控结论：{g['warning_message']}")
            if g.get("corporate_resolution_check"):
                lines.append(f"      企业对外担保合规：{g['corporate_resolution_check']['audit_note']}")

    lines.append("")
    lines.append("二、《民法典》第392条人保物保受偿顺位：")
    if not collateral_audits:
        lines.append("  • 本案系纯人保架构，无独立登记之物保。")
    else:
        for idx, c in enumerate(collateral_audits, 1):
            lines.append(f"  ({idx}) 提供人【{c['collateral_provider']}】：受偿顺位：【{c['priority_rank']}】")
            lines.append(f"      法定规则：{c['statutory_rule']}")
            lines.append(f"      实操提示：{c['action_warning']}")

    return "\n".join(lines)


# ==============================================================================
# 2. 资金穿透流水大屏与《民法典》第561条法定抵充对账引擎
# ==============================================================================

_REPAY_KEYS = ("还款", "付息", "利息", "部分清偿", "归还", "清偿")
_DISBURSE_KEYS = ("借款", "本金出借", "出借", "交付", "放款", "贷款发放")


def _classify_flow_purpose(purpose: str) -> str:
    p = purpose or ""
    if any(k in p for k in _REPAY_KEYS):
        return "repayment"
    if any(k in p for k in _DISBURSE_KEYS):
        return "disbursement"
    # 单独“本金”且伴随借款语义
    if "本金" in p and any(k in p for k in ("借款", "出借", "放款", "交付")):
        return "disbursement"
    return "unclassified"


def audit_and_reconcile_cashflow(
    cashflow_records: List[Dict[str, Any]],
    principal_amount: Optional[float | Decimal] = None,
    annual_interest_rate: Optional[float] = None,
    start_date: Optional[str] = None,
    debtor_name: Optional[str] = None,
    creditor_name: Optional[str] = None,
    both_natural_persons: Optional[bool] = None,
    lender_is_natural_person: Optional[bool] = None,
    borrower_is_natural_person: Optional[bool] = None,
    contract_date: Optional[str] = None,
    filing_date: Optional[str] = None,
    fees: float | Decimal = 0.0,
    agreed_offset_order: Optional[List[str]] = None,
    **kwargs,
) -> Dict[str, Any]:
    """
    资金穿透流水对账与《民法典》第561条法定抵充对账计算引擎：
    - 抵充顺序：实现债权的有关费用 → 利息 → 本金（当事人另有约定的除外）；
    - 利率上限：合同成立时一年期 LPR 四倍（《民间借贷规定》第25条）；
    - 侦测三大异常风险：资金快速回流、第三方代收无书面授权、附言性质冲突。
    """
    if "annual_rate" in kwargs and kwargs["annual_rate"] is not None:
        annual_interest_rate = float(kwargs["annual_rate"])

    if principal_amount is None:
        raise ValueError("principal_amount 为必填参数")
    if annual_interest_rate is None:
        raise ValueError("annual_interest_rate 为必填参数（可用 annual_rate 别名）")

    if both_natural_persons is None:
        if lender_is_natural_person is not None and borrower_is_natural_person is not None:
            both_natural_persons = bool(lender_is_natural_person and borrower_is_natural_person)
        elif "party_type" in kwargs:
            both_natural_persons = str(kwargs.get("party_type") or "").lower() in (
                "natural",
                "natural_person",
                "双方均为自然人",
                "自然人",
            )
        else:
            both_natural_persons = False

    try:
        p_base = float(Decimal(str(principal_amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    except Exception as exc:
        raise ValueError("principal_amount 无法解析为金额") from exc

    agreed_rate = float(annual_interest_rate)
    if agreed_rate < 0:
        raise ValueError("annual_interest_rate 不能为负数")

    # 规范与清洗流水条目
    parsed_flows = []
    unclassified_records: List[Dict[str, Any]] = []
    for f in cashflow_records:
        d_str = str(f.get("date", "")).strip()[:10]
        amt = float(f.get("amount", 0.0))
        payer = str(f.get("payer", "") or f.get("from_party", ""))
        payee = str(f.get("payee", "") or f.get("to_party", ""))
        purpose = str(f.get("purpose", "") or f.get("channel", "") or f.get("note", ""))
        voucher = str(f.get("voucher", "") or "银行网银流水回单")

        flow_date = None
        if d_str:
            try:
                flow_date = datetime.strptime(d_str, "%Y-%m-%d").date()
            except ValueError as val_err:
                logger.debug(f"流水日期解析失败: {val_err}")

        kind = _classify_flow_purpose(purpose)
        item = {
            "flow_id": str(f.get("flow_id", f"cf_{len(parsed_flows)+1}")),
            "date_str": d_str or "待核日期",
            "date": flow_date,
            "payer": payer,
            "payee": payee,
            "amount": amt,
            "purpose": purpose,
            "voucher": voucher,
            "kind": kind,
            "raw": f,
        }
        parsed_flows.append(item)
        if kind == "unclassified":
            unclassified_records.append({
                "flow_id": item["flow_id"],
                "date": item["date_str"],
                "amount": amt,
                "payer": payer,
                "payee": payee,
                "purpose": purpose,
                "message": "以下流水未能识别性质，请人工分类后再对账",
            })

    valid_dated_flows = [x for x in parsed_flows if x["date"] is not None]
    valid_dated_flows.sort(key=lambda x: x["date"])

    d_initial = None
    if start_date:
        try:
            d_initial = datetime.strptime(start_date, "%Y-%m-%d").date()
        except ValueError as val_err:
            logger.debug(f"初始日期解析失败: {val_err}")

    if not d_initial and valid_dated_flows:
        for f in valid_dated_flows:
            if f["kind"] == "disbursement":
                d_initial = f["date"]
                break

    if not d_initial:
        return _insufficient_data(
            missing_fields=["start_date"],
            message="缺少起息日/放款日，无法进行流水对账",
        )

    contract_date_str = contract_date or str(d_initial)
    rate_note = ""
    try:
        cap_info = get_private_lending_four_times_lpr_cap(
            contract_date=contract_date_str,
            filing_date=filing_date,
        )
        cap_decimal = float(cap_info["cap_rate_decimal"])
        cap_percent = float(cap_info["cap_rate_percent"])
        agreed_percent = round(agreed_rate * 100.0, 4) if agreed_rate <= 1 else round(agreed_rate, 4)
        # 入参统一按小数年利率（0.144）；若误传百分数（>1）则按百分数理解
        if agreed_rate > 1:
            agreed_decimal = agreed_rate / 100.0
            agreed_percent = round(agreed_rate, 4)
        else:
            agreed_decimal = agreed_rate
            agreed_percent = round(agreed_rate * 100.0, 4)

        if agreed_decimal > cap_decimal + 1e-12:
            rate = cap_decimal
            rate_note = (
                f"约定年利率 {agreed_percent:g}% 超过合同成立时一年期 LPR 四倍（{cap_percent:g}%），"
                f"超过部分依《民间借贷规定》第25条不予支持，按 {cap_percent:g}% 计算"
            )
        else:
            rate = agreed_decimal
            rate_note = (
                f"约定年利率 {agreed_percent:g}% 未超过合同成立时一年期 LPR 四倍（{cap_percent:g}%），"
                f"按约定利率 {agreed_percent:g}% 计算"
            )
    except ValueError as exc:
        # 合同早于 2020-08-20 且缺 filing_date：仍按约定利率计算并提示
        rate = agreed_rate if agreed_rate <= 1 else agreed_rate / 100.0
        rate_note = f"利率上限核验受限：{exc}"

    unpaid_fees = float(Decimal(str(fees or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

    # 抵充顺序
    default_order = ["fees", "interest", "principal"]
    order = list(agreed_offset_order) if agreed_offset_order else default_order
    # 归一化
    norm_map = {
        "费用": "fees",
        "fees": "fees",
        "fee": "fees",
        "利息": "interest",
        "interest": "interest",
        "本金": "principal",
        "主债务": "principal",
        "principal": "principal",
    }
    order = [norm_map.get(str(x), str(x)) for x in order]
    using_agreed_order = bool(agreed_offset_order)

    reconciliation_ledger = []
    current_principal = p_base
    last_calc_date = d_initial
    total_repayments_nominal = 0.0
    total_interest_offset = 0.0
    total_principal_offset = 0.0
    total_fees_offset = 0.0
    unpaid_accrued_interest = 0.0

    disbursement_flows = [f for f in valid_dated_flows if f["kind"] == "disbursement"]
    repayment_flows = [f for f in valid_dated_flows if f["kind"] == "repayment"]

    for idx, rf in enumerate(repayment_flows, 1):
        f_date = rf["date"]
        repay_amt = rf["amount"]
        total_repayments_nominal += repay_amt

        days = max(0, (f_date - last_calc_date).days)
        period_interest = current_principal * rate * (days / 365.0)
        interest_before = unpaid_accrued_interest + period_interest
        interest_left = interest_before

        remaining = repay_amt
        offset_fees = 0.0
        offset_interest = 0.0
        offset_principal = 0.0

        for slot in order:
            if remaining <= 0:
                break
            if slot == "fees" and unpaid_fees > 0:
                take = min(remaining, unpaid_fees)
                offset_fees += take
                unpaid_fees -= take
                remaining -= take
            elif slot == "interest" and interest_left > 0:
                take = min(remaining, interest_left)
                offset_interest += take
                interest_left -= take
                remaining -= take
            elif slot == "principal" and current_principal > 0:
                take = min(remaining, current_principal)
                offset_principal += take
                current_principal = max(0.0, current_principal - take)
                remaining -= take

        unpaid_accrued_interest = max(0.0, interest_left)
        total_interest_offset += offset_interest
        total_principal_offset += offset_principal
        total_fees_offset += offset_fees

        if using_agreed_order:
            basis = "当事人约定的抵充顺序（《民法典》第561条但书：当事人另有约定的除外）"
        else:
            basis = "《民法典》第561条法定抵充顺序（费用→利息→主债务；当事人另有约定的除外）"

        if repay_amt <= interest_before and offset_fees == 0 and offset_principal == 0:
            legal_comment = (
                f"名义还款 ¥{repay_amt:,.2f} 元不足以清偿本期利息（计息{days}天，利息 ¥{interest_before:,.2f} 元）。"
                f"依法全额冲抵利息，冲抵本金为0元，剩余本金基数保持 ¥{current_principal:,.2f} 元不变！"
            )
        else:
            legal_comment = (
                f"名义还款 ¥{repay_amt:,.2f} 元：冲抵费用 ¥{offset_fees:,.2f} 元、"
                f"利息 ¥{offset_interest:,.2f} 元、本金 ¥{offset_principal:,.2f} 元；"
                f"剩余本金 ¥{current_principal:,.2f} 元，未结利息 ¥{unpaid_accrued_interest:,.2f} 元。"
            )

        reconciliation_ledger.append({
            "step": idx,
            "step_num": idx,
            "payment_date": str(f_date),
            "repayment_date": str(f_date),
            "days_accrued": days,
            "payer": rf["payer"],
            "payee": rf["payee"],
            "nominal_amount": round(repay_amt, 2),
            "repay_amount": round(repay_amt, 2),
            "interest_period": f"{last_calc_date} 至 {f_date} ({days} 天)",
            "accrued_interest_due": round(interest_before, 2),
            "total_interest_before_repay": round(interest_before, 2),
            "offset_fees": round(offset_fees, 2),
            "offset_to_fees": round(offset_fees, 2),
            "offset_interest": round(offset_interest, 2),
            "offset_to_interest": round(offset_interest, 2),
            "offset_principal": round(offset_principal, 2),
            "offset_to_principal": round(offset_principal, 2),
            "remaining_principal_balance": round(current_principal, 2),
            "remaining_principal": round(current_principal, 2),
            "unpaid_interest_balance": round(unpaid_accrued_interest, 2),
            "unpaid_interest_after_repay": round(unpaid_accrued_interest, 2),
            "remaining_fees": round(unpaid_fees, 2),
            "legal_comment": legal_comment,
            "statute_basis": basis,
            "voucher": rf["voucher"],
        })

        last_calc_date = f_date

    red_flags: List[Dict[str, Any]] = []

    for df in disbursement_flows:
        d_out = df["date"]
        amt_out = df["amount"]
        for other_f in valid_dated_flows:
            if other_f["flow_id"] == df["flow_id"]:
                continue
            d_in = other_f["date"]
            amt_in = other_f["amount"]
            delta_days = (d_in - d_out).days

            is_reverse = False
            if df["payee"] and other_f["payer"] and (df["payee"] in other_f["payer"] or other_f["payer"] in df["payee"]):
                is_reverse = True
            elif df["payer"] and other_f["payee"] and (
                df["payer"] in other_f["payee"]
                or other_f["payee"] in df["payer"]
                or "出借" in other_f["payee"]
                or "原告" in other_f["payee"]
            ):
                is_reverse = True
            elif any(k in other_f["purpose"] for k in ["还款", "付息", "顾问", "服务费", "保证金", "手续费", "返还", "回扣", "管理费"]):
                is_reverse = True

            if is_reverse and 0 <= delta_days <= 2 and amt_in < amt_out:
                red_flags.append({
                    "risk_type": "同日快速回流（疑似砍头息或虚构交付）",
                    "severity": "CRITICAL",
                    "flow_out": f"{df['date_str']} 出借 ¥{amt_out:,.2f}",
                    "flow_in": f"{other_f['date_str']} 极速回款 ¥{amt_in:,.2f}",
                    "gap_days": delta_days,
                    "risk_tip": (
                        f"出借后仅 {delta_days} 天内即有 ¥{amt_in:,.2f} 资金反向回流出借方（备注：{other_f['purpose']}）！"
                        "法庭质证中极易被被告抗辩主张'出借人预扣砍头息'或'双方并无真实借贷合意'，"
                        "依照《民法典》第670条，借款利息不得预先扣除，预先扣除的应当按照实际交付金额计算本金利息！"
                    ),
                })

    for f in parsed_flows:
        p_text = f["purpose"]
        payer = f["payer"]
        payee = f["payee"]
        if any(k in p_text for k in ["借款", "出借", "本金"]) and (
            "第三人" in payee or "出纳" in payee or "配偶" in payee
            or (debtor_name and payee and debtor_name not in payee)
        ):
            tip = (
                f"借款本金未直接汇入借款人本人银行账户，而是汇入第三方【{payee}】！"
                "出借人主张第三人系受委托收款的，必须提供借款人明确的书面指示委托书或微信聊天明确确认，"
                "否则可能面临借款款项未实际交付之举证困境。"
            )
            if both_natural_persons:
                tip += (
                    "双方均为自然人时，依据《民法典》第六百七十九条，自然人之间的借款合同自贷款人提供借款时成立；"
                    "若未能证明已向借款人提供借款，合同可能尚未成立生效。"
                )
            red_flags.append({
                "risk_type": "第三方代收交付阻断抗辩",
                "severity": "HIGH",
                "flow_id": f["flow_id"],
                "payee": payee,
                "risk_tip": tip,
            })
        if any(k in p_text for k in ["还款", "代还", "归还", "清偿", "付息"]) and (
            "第三" in payer or "代" in p_text or (debtor_name and payer and debtor_name not in payer)
        ):
            red_flags.append({
                "risk_type": "第三方代付未见授权抗辩",
                "severity": "HIGH",
                "flow_id": f["flow_id"],
                "payer": payer,
                "risk_tip": (
                    f"还款资金系由案外第三方【{payer}】汇出！"
                    "卷宗内若无第三人代为清偿协议或债务人委托代付书，该款项性质可能被案外人主张为错汇、不当得利或借贷往来，"
                    "面临被另案起诉要求返还的重大衍生诉讼风险！"
                ),
            })

    for f in parsed_flows:
        p_text = f["purpose"]
        if any(k in p_text for k in ["货款", "定金", "技术服务费", "工程款", "分红"]):
            red_flags.append({
                "risk_type": "银行附言与借款性质冲突",
                "severity": "MEDIUM",
                "flow_id": f["flow_id"],
                "purpose": p_text,
                "risk_tip": (
                    f"银行电子回单附言为『{p_text}』，而非借款备注！"
                    "对方可能以买卖合同或承揽合同进行抗辩，原告必须提前补充提供证据排除其他基础交易关系存在。"
                ),
            })

    statutory_statement = _generate_art_561_court_statement(
        principal_amount=p_base,
        rate=rate,
        start_date=str(d_initial),
        ledger=reconciliation_ledger,
        remaining_p=current_principal,
        unpaid_interest=unpaid_accrued_interest,
        red_flags=red_flags,
        rate_note=rate_note,
        using_agreed_order=using_agreed_order,
        unclassified_records=unclassified_records,
    )

    result = {
        "status": "success",
        "principal_claim_initial": round(p_base, 2),
        "annual_interest_rate": rate,
        "agreed_annual_interest_rate": agreed_rate if agreed_rate <= 1 else agreed_rate / 100.0,
        "rate_note": rate_note,
        "initial_lending_date": str(d_initial),
        "contract_date": contract_date_str,
        "current_principal_unpaid": round(current_principal, 2),
        "total_nominal_repayments": round(total_repayments_nominal, 2),
        "total_interest_offset": round(total_interest_offset, 2),
        "total_principal_offset": round(total_principal_offset, 2),
        "total_fees_offset": round(total_fees_offset, 2),
        "unpaid_accrued_interest": round(unpaid_accrued_interest, 2),
        "remaining_fees": round(unpaid_fees, 2),
        "reconciliation_ledger": reconciliation_ledger,
        "unclassified_records": unclassified_records,
        "unclassified_hint": (
            "以下流水未能识别性质，请人工分类后再对账" if unclassified_records else None
        ),
        "red_flags": red_flags,
        "court_cross_exam_statement": statutory_statement,
    }
    return result


def _generate_art_561_court_statement(
    principal_amount: float,
    rate: float,
    start_date: str,
    ledger: List[Dict[str, Any]],
    remaining_p: float,
    unpaid_interest: float,
    red_flags: List[Dict[str, Any]],
    rate_note: str = "",
    using_agreed_order: bool = False,
    unclassified_records: Optional[List[Dict[str, Any]]] = None,
) -> str:
    lines = []
    lines.append("【原告方代理词/质证意见：依据《民法典》第561条驳斥被告清偿抗辩之抵充对账说明】")
    lines.append("一、诉争借款本金基数与利率标准：")
    rate_line = (
        f"原告向被告出借本金人民币 {principal_amount:,.2f} 元，出借交付起算日为 {start_date}，"
        f"执行年化利率为 {rate*100:.2f}%。"
    )
    if rate_note:
        rate_line += rate_note
    lines.append(rate_line)
    lines.append("")
    lines.append("二、法定抵充顺序与逐笔冲抵核算事实：")
    lines.append("《中华人民共和国民法典》第五百六十一条确立法定抵充顺序（当事人另有约定的除外）：")
    lines.append("  （一）实现债权的有关费用；")
    lines.append("  （二）利息；")
    lines.append("  （三）主债务。")
    if using_agreed_order:
        lines.append("本案双方就抵充顺序另有约定，故按约定顺序抵充。")
    else:
        lines.append(
            "本案中双方并未特别约定利息与本金的任意冲抵顺序，故适用法定抵充顺序"
            "（费用→利息→主债务）。"
        )
    lines.append("")

    if ledger:
        lines.append("分笔冲抵对账明细如下：")
        for item in ledger:
            lines.append(
                f"  • {item['payment_date']} 被告还款 ¥{item['nominal_amount']:,.2f} 元："
                f"冲抵费用 ¥{item.get('offset_fees', 0):,.2f} 元、"
                f"冲抵当期利息 ¥{item['offset_interest']:,.2f} 元，冲减借款本金 ¥{item['offset_principal']:,.2f} 元；"
                f"冲抵后借款本金尚欠余额为人民币 ¥{item['remaining_principal_balance']:,.2f} 元。"
            )
        lines.append("")
    else:
        lines.append("  • 被告自借款发生至今未向原告清偿任何款项，尚欠全额本金及逾期利息。")

    lines.append("三、对账终审结论：")
    lines.append(
        f"截至最后结息日，被告仍拖欠原告借款本金人民币 {remaining_p:,.2f} 元，"
        f"并拖欠未结清利息人民币 {unpaid_interest:,.2f} 元。"
        "被告关于'还款全额冲抵本金'之抗辩，违背法定抵充顺序（当事人另有约定的除外），依法不应被采信！"
    )

    if unclassified_records:
        lines.append("")
        lines.append("四、未识别性质流水提示：")
        lines.append("以下流水未能识别性质，请人工分类后再对账：")
        for ur in unclassified_records:
            lines.append(
                f"  • {ur.get('date')} ¥{ur.get('amount'):,.2f} 附言『{ur.get('purpose')}』"
            )

    if red_flags:
        lines.append("")
        section = "五" if unclassified_records else "四"
        lines.append(f"{section}、主办律师特别风控防线排查提示：")
        for idx, rf in enumerate(red_flags, 1):
            lines.append(f"  [{idx}] 【{rf['risk_type']}】: {rf['risk_tip']}")

    return "\n".join(lines)
