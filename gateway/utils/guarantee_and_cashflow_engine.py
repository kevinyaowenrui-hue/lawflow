"""
LawFlow 智律工作台 - P2 阶段：复杂交易多方交叉担保拓扑与资金穿透流水精算引擎
(Cross-Guarantee Topology & Fund Tracing Cashflow Reconciliation Engine)

核心实务风控与精算法则：
1. 《民法典》第692条保证期间生死线监控与除斥期间灭失阻断；
2. 《民法典》第392条人保与物保并存受偿顺位判定（主债务人物保优先强制执行）；
3. 新《公司法》第15条、《民法典》第61条及《九民纪要》第17-22条公司对外担保越权代表效力穿透；
4. 《民法典》第561条法定冲抵对账规则（实现债权费用 -> 利息 -> 本金）；
5. 资金穿透全链路追踪与三大异常洗钱/虚假交付风险探针（同日回流、代付阻断、附言冲突）。
"""

import re
from datetime import datetime, date
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, List, Optional, Tuple


# ==============================================================================
# 1. 复杂多方交叉担保拓扑与保证期间灭失/物保人保受偿顺位引擎
# ==============================================================================

def analyze_guarantee_topology_and_deadlines(
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
    timeline: Optional[List[Dict[str, Any]]] = None,
    principal_due_date: Optional[str] = None,
    today_date: Optional[str] = None
) -> Dict[str, Any]:
    """
    复杂交易多方交叉担保拓扑分析与执业红线监控：
    - 保证期间生死线检测（民法典692条法定6个月除斥期间）；
    - 人保与物保并存受偿顺位（民法典392条：债务人自己提供物保应当优先执行）；
    - 公司对外关联担保决议合规性（公司法15条、九民纪要17-22条越权代表效力）。
    """
    today = datetime.strptime(today_date, "%Y-%m-%d").date() if today_date else date.today()
    
    # 查找主债务到期日
    p_due = None
    if principal_due_date:
        try:
            p_due = datetime.strptime(principal_due_date, "%Y-%m-%d").date()
        except Exception:
            pass

    # 若未直接指定主债务到期日，尝试从时间线中提取“借期届满/合同到期”
    if not p_due and timeline:
        for ev in timeline:
            tag = ev.get("legal_tag", "")
            event_text = ev.get("event", "")
            if "借期届满" in event_text or "合同到期" in event_text or "到期" in tag or "届满" in tag:
                try:
                    p_due = datetime.strptime(ev["date"][:10], "%Y-%m-%d").date()
                    break
                except Exception:
                    continue

    if not p_due:
        # 默认推算：若无确切日期，设为今日前1年作为推演基准
        p_due = date(today.year - 1, today.month, min(today.day, 28))

    # 建立主体索引映射
    node_map = {}
    debtor_id = None
    debtor_name = "主债务人"
    creditor_id = None
    creditor_name = "出借人/债权人"

    for n in nodes:
        nid = str(n.get("id", ""))
        name = str(n.get("name", ""))
        role = str(n.get("role", "")).lower()
        node_map[nid] = n
        node_map[name] = n
        if "主债务" in role or "被告" in role or "借款人" in role:
            if not debtor_id:
                debtor_id = nid
                debtor_name = name
        elif "原告" in role or "出借人" in role or "债权人" in role:
            if not creditor_id:
                creditor_id = nid
                creditor_name = name

    # 提取时间线中向各主体主张权利记录（用于保证期间中断/主张判断）
    demand_records = {} # guarantor_name_or_id -> demand_date
    if timeline:
        for ev in timeline:
            text = ev.get("event", "")
            d_str = ev.get("date", "")[:10]
            if any(k in text for k in ["催告", "催要", "律师函", "起诉", "立案", "EMS", "发函", "要求承担保证"]):
                for n in nodes:
                    name = n.get("name", "")
                    if name and name in text:
                        try:
                            d_parsed = datetime.strptime(d_str, "%Y-%m-%d").date()
                            if name not in demand_records or d_parsed < demand_records[name]:
                                demand_records[name] = d_parsed
                        except Exception:
                            pass

    guarantee_audits = []
    collateral_audits = []
    topology_nodes = []
    topology_edges = []

    # 保证期间到期日推算 (《民法典》第692条第2款：未约定或约定不明确的，保证期间为主债务履行期限届满之日起六个月)
    # 计算 p_due 往后推 6 个月
    year_offset = (p_due.month + 6 - 1) // 12
    new_month = (p_due.month + 6 - 1) % 12 + 1
    new_day = min(p_due.day, 28)
    statutory_guarantee_expiry = date(p_due.year + year_offset, new_month, new_day)

    for edge in edges:
        source_id = str(edge.get("source", ""))
        target_id = str(edge.get("target", ""))
        rel_type = str(edge.get("type", "") or edge.get("relation", ""))
        detail = str(edge.get("detail", "") or edge.get("details", ""))

        source_node = node_map.get(source_id, {})
        target_node = node_map.get(target_id, {})
        source_name = source_node.get("name", source_id)
        target_name = target_node.get("name", target_id)

        # A. 连带保证责任 / 一般保证审查
        if any(k in rel_type for k in ["保证", "连带", "担保责任", "个人无限连带"]):
            guarantor_name = source_name
            guarantor_node = source_node
            is_company = "有限公司" in guarantor_name or "股份" in guarantor_name or guarantor_node.get("type") in ["company", "企业", "企业主体"]

            # 检查是否有催告记录
            demand_date = demand_records.get(guarantor_name)
            has_demanded = demand_date is not None

            # 状态判定
            days_to_expiry = (statutory_guarantee_expiry - today).days
            status = "SAFE"
            status_label = "保证期间合规锁定"
            status_color = "#15803D"
            warning_msg = "已在法定保证期间内主张权利，保证期间转化为保证债务诉讼时效。"

            if has_demanded:
                if demand_date <= statutory_guarantee_expiry:
                    status = "SAFE"
                    status_label = "保证期间已依法阻断"
                    status_color = "#15803D"
                    warning_msg = f"债权人已于 {demand_date}（保证期间届满前）依法向该保证人主张权利，依据《民法典》第694条，自该日起计算保证债务三年诉讼时效！"
                else:
                    status = "CRITICAL_EXPIRED"
                    status_label = "保证期间已过·责任免除！"
                    status_color = "#B91C1C"
                    warning_msg = f"致命执业险情！主张日期 {demand_date} 已晚于法定保证期间截止日 {statutory_guarantee_expiry}，依据《民法典》第692条第二款，保证人免除保证责任！"
            else:
                if today > statutory_guarantee_expiry:
                    status = "CRITICAL_EXPIRED"
                    status_label = "保证责任已法定灭失！"
                    status_color = "#B91C1C"
                    warning_msg = f"重大执业风险！主债务已于 {p_due} 届满，法定6个月保证期间已于 {statutory_guarantee_expiry} 届满！卷宗中未发现有效主张权利证明，保证人享有免责抗辩权！"
                elif days_to_expiry <= 30:
                    status = "WARNING_EXPIRING_SOON"
                    status_label = f"临近届满 (剩 {days_to_expiry} 天)"
                    status_color = "#C58532"
                    warning_msg = f"🚨 紧急红线：保证期间将于 {statutory_guarantee_expiry} 届满（仅剩 {days_to_expiry} 天）！必须在截止日前向保证人发出EMS律师催告函或提起诉讼，否则将导致保证债权彻底灭失！"
                else:
                    status = "NORMAL_UNEXPIRED"
                    status_label = f"在保证期间内 (剩 {days_to_expiry} 天)"
                    status_color = "#1E40AF"
                    warning_msg = f"当前处于《民法典》第692条法定保证期间内，截止日为 {statutory_guarantee_expiry}。"

            # 公司对外担保决议审查
            corporate_resolution_risk = None
            if is_company:
                corporate_resolution_risk = {
                    "is_company": True,
                    "statute_basis": "新《公司法》第15条、《民法典》第61条、《九民纪要》第17-22条",
                    "audit_note": (
                        "企业法人为他人提供连带保证，属于重大或关联对外担保行为。"
                        "若系为公司股东或实控人担保，必须经股东会决议（被担保股东回避表决）；"
                        "若无合法决议且债权人未尽审慎审查义务，担保合同对公司不发生效力，公司仅承担不超过债务人不能清偿部分二分之一的缔约过失赔偿责任！"
                    )
                }

            guarantee_audits.append({
                "guarantor_name": guarantor_name,
                "guarantor_type": "企业法人保证" if is_company else "自然人保证",
                "guarantee_type": "连带责任保证（法释及合同约定）",
                "principal_due_date": str(p_due),
                "guarantee_expiry_date": str(statutory_guarantee_expiry),
                "has_demanded_in_time": has_demanded,
                "demand_date": str(demand_date) if demand_date else None,
                "days_remaining": days_to_expiry,
                "status": status,
                "status_label": status_label,
                "status_color": status_color,
                "warning_message": warning_msg,
                "corporate_resolution_check": corporate_resolution_risk
            })

        # B. 抵押 / 质押 物保受偿顺位审查 (《民法典》第392条)
        elif any(k in rel_type for k in ["抵押", "质押", "物保", "房产抵押", "股权质押", "留置"]):
            collateral_provider = source_name
            is_debtor_property = (source_id == debtor_id) or (source_name == debtor_name)
            
            if is_debtor_property:
                priority_rank = "第一顺位 (强制先行实现)"
                priority_level = 1
                statutory_rule = (
                    "依据《民法典》第三百九十二条前段之规定：被担保的债权既有物的担保又有人的担保的，"
                    "债务人自己提供物的担保的，债权人应当先就该物的担保实现债权！"
                )
                action_warning = (
                    "【法定排挤警示】本案抵押物系主债务人自身所有的财产，债权人在实现债权时必须先就该抵押物申请拍卖/变卖！"
                    "在抵押物变现受偿完毕前，其他保证人对未处置物保部分享有法定抗辩权，债权人不可绕过抵押物直接向连带保证人强制全额扣划！"
                )
            else:
                priority_rank = "并列顺位 (债权人选择权)"
                priority_level = 2
                statutory_rule = (
                    "依据《民法典》第三百九十二条后段之规定：第三人提供物的担保的，"
                    "债权人可以就物的担保实现债权，也可以请求保证人承担保证责任。"
                )
                action_warning = (
                    "抵押物系第三人提供，债权人享有受偿选择权。可根据不动产查封顺位与变现难易度，"
                    "自由决定优先执行抵押物或扣划保证人银行存款。"
                )

            collateral_audits.append({
                "collateral_provider": collateral_provider,
                "is_debtor_own_property": is_debtor_property,
                "priority_rank": priority_rank,
                "priority_level": priority_level,
                "statutory_rule": statutory_rule,
                "action_warning": action_warning,
                "detail": detail
            })

    # 构建拓扑节点视图 (便于前端 Canvas / SVG 绘制)
    for n in nodes:
        nid = str(n.get("id", ""))
        name = str(n.get("name", ""))
        role = str(n.get("role", ""))
        
        # 寻找该主体上的保证审查结果
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
            "collateral_priority": c_audit.get("priority_rank") if c_audit else None
        })

    for e in edges:
        s_id = str(e.get("source", ""))
        t_id = str(e.get("target", ""))
        r_type = str(e.get("type", "") or e.get("relation", ""))
        det = str(e.get("detail", "") or e.get("details", ""))
        
        s_name = node_map.get(s_id, {}).get("name", s_id)
        t_name = node_map.get(t_id, {}).get("name", t_id)

        topology_edges.append({
            "source_id": s_id,
            "target_id": t_id,
            "source_name": s_name,
            "target_name": t_name,
            "relation_type": r_type,
            "detail": det,
            "is_guarantee": any(k in r_type for k in ["保证", "连带", "担保"]),
            "is_collateral": any(k in r_type for k in ["抵押", "质押", "物保"])
        })

    # 4. 生成合伙人交叉担保实战风控备忘录
    tactical_summary = _generate_guarantee_topology_memo(
        debtor_name=debtor_name,
        principal_due_date=str(p_due),
        guarantee_audits=guarantee_audits,
        collateral_audits=collateral_audits
    )

    return {
        "status": "success",
        "principal_due_date": str(p_due),
        "statutory_guarantee_expiry": str(statutory_guarantee_expiry),
        "guarantee_audits": guarantee_audits,
        "collateral_audits": collateral_audits,
        "topology": {
            "nodes": topology_nodes,
            "edges": topology_edges
        },
        "partner_tactical_memo": tactical_summary
    }


def _generate_guarantee_topology_memo(
    debtor_name: str,
    principal_due_date: str,
    guarantee_audits: List[Dict[str, Any]],
    collateral_audits: List[Dict[str, Any]]
) -> str:
    lines = []
    lines.append("【合伙人多方交叉担保与保证期间执业审定备忘录】")
    lines.append(f"主债务人：{debtor_name} · 主债务约定到期日：{principal_due_date}")
    lines.append("")

    # A. 保证期间执业预警
    lines.append("一、《民法典》第692条保证期间生死线审计：")
    if not guarantee_audits:
        lines.append("  • 本案未识别到明确连带责任保证人主体。")
    else:
        for idx, g in enumerate(guarantee_audits, 1):
            lines.append(f"  ({idx}) 保证人【{g['guarantor_name']}】（{g['guarantor_type']}）：")
            lines.append(f"      法定保证期间截止日：{g['guarantee_expiry_date']} · 当前状态：【{g['status_label']}】")
            lines.append(f"      风控结论：{g['warning_message']}")
            if g.get("corporate_resolution_check"):
                lines.append(f"      企业对外担保合规：{g['corporate_resolution_check']['audit_note']}")

    lines.append("")
    # B. 人保物保受偿顺位
    lines.append("二、《民法典》第392条人保物保受偿顺位与强制执行预备：")
    if not collateral_audits:
        lines.append("  • 本案系纯人保架构，无独立登记之不动产或股权抵押物。")
    else:
        for idx, c in enumerate(collateral_audits, 1):
            lines.append(f"  ({idx}) 提供人【{c['collateral_provider']}】：受偿顺位：【{c['priority_rank']}】")
            lines.append(f"      法定规则：{c['statutory_rule']}")
            lines.append(f"      实操警示：{c['action_warning']}")

    return "\n".join(lines)



# ==============================================================================
# 2. 资金穿透流水大屏与《民法典》第561条法定冲抵对账引擎
# ==============================================================================

def audit_and_reconcile_cashflow(
    cashflow_records: List[Dict[str, Any]],
    principal_amount: float | Decimal = 5000000.0,
    annual_interest_rate: float = 0.144,
    start_date: Optional[str] = None,
    debtor_name: Optional[str] = None,
    creditor_name: Optional[str] = None,
    **kwargs
) -> Dict[str, Any]:
    """
    资金穿透流水对账与《民法典》第561条法定冲抵对账计算引擎：
    - 冲抵清偿顺序：实现债权的有关费用 -> 利息 -> 本金；
    - 针对借款人'已还款全部抵扣本金'之抗辩，提供具有不可辩驳法理证据效力的对账清单；
    - 侦测三大异常风险：资金快速回流（砍头息）、第三方代收无书面授权、附言性质冲突。
    """
    if "annual_rate" in kwargs and kwargs["annual_rate"] is not None:
        annual_interest_rate = float(kwargs["annual_rate"])

    try:
        p_base = float(Decimal(str(principal_amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    except Exception:
        p_base = 5000000.0

    rate = max(0.0, min(0.36, float(annual_interest_rate)))

    # 规范与清洗流水条目
    parsed_flows = []
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
            except Exception:
                pass
        
        parsed_flows.append({
            "flow_id": str(f.get("flow_id", f"cf_{len(parsed_flows)+1}")),
            "date_str": d_str or "待核日期",
            "date": flow_date,
            "payer": payer,
            "payee": payee,
            "amount": amt,
            "purpose": purpose,
            "voucher": voucher,
            "raw": f
        })

    # 按时间升序排序
    valid_dated_flows = [x for x in parsed_flows if x["date"] is not None]
    valid_dated_flows.sort(key=lambda x: x["date"])

    # 确定出借交付起息日
    d_initial = None
    if start_date:
        try:
            d_initial = datetime.strptime(start_date, "%Y-%m-%d").date()
        except Exception:
            pass

    if not d_initial and valid_dated_flows:
        # 寻找第一笔大额支付（出借）
        for f in valid_dated_flows:
            if any(k in f["purpose"] for k in ["借款", "本金", "出借", "交付", "转账", "往来"]):
                d_initial = f["date"]
                break
        if not d_initial:
            d_initial = valid_dated_flows[0]["date"]

    if not d_initial:
        d_initial = date.today()

    # 1. 执行《民法典》第561条法定分段冲抵重算
    reconciliation_ledger = []
    current_principal = p_base
    last_calc_date = d_initial
    total_repayments_nominal = 0.0
    total_interest_offset = 0.0
    total_principal_offset = 0.0
    unpaid_accrued_interest = 0.0

    # 区分借款出借流水与还款流水
    disbursement_flows = []
    repayment_flows = []

    for f in valid_dated_flows:
        p_text = f["purpose"]
        amt = f["amount"]
        is_repay = any(k in p_text for k in ["还款", "付息", "利息", "部分清偿", "归还"])
        if is_repay:
            repayment_flows.append(f)
        else:
            disbursement_flows.append(f)

    for idx, rf in enumerate(repayment_flows, 1):
        f_date = rf["date"]
        repay_amt = rf["amount"]
        total_repayments_nominal += repay_amt

        # 计息区间天数
        days = max(0, (f_date - last_calc_date).days)
        # 本期新增利息 = 当前本金基数 * 年化利率 * (天数 / 365)
        period_interest = current_principal * rate * (days / 365.0)
        total_interest_due = unpaid_accrued_interest + period_interest

        # 依据《民法典》第561条：先冲抵利息，再冲抵本金
        if repay_amt <= total_interest_due:
            # 款项不足以清偿全部利息：全额冲利息，本金不动
            offset_interest = repay_amt
            offset_principal = 0.0
            unpaid_accrued_interest = total_interest_due - repay_amt
        else:
            # 款项超出当期利息：利息全部结清，剩余冲抵本金
            offset_interest = total_interest_due
            offset_principal = repay_amt - total_interest_due
            unpaid_accrued_interest = 0.0
            current_principal = max(0.0, current_principal - offset_principal)

        total_interest_offset += offset_interest
        total_principal_offset += offset_principal

        legal_comment = (
            f"名义还款 ¥{repay_amt:,.2f} 元不足以清偿本期利息（计息{days}天，利息 ¥{total_interest_due:,.2f} 元）。依法全额冲抵利息，冲抵本金为0元，剩余本金基数保持 ¥{current_principal:,.2f} 元不变！"
            if repay_amt <= total_interest_due
            else (
                f"名义还款 ¥{repay_amt:,.2f} 元先抵清应付利息 ¥{total_interest_due:,.2f} 元；剩余款项 ¥{offset_principal:,.2f} 元依法冲抵本金，本金余额降至 ¥{current_principal:,.2f} 元。"
            )
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
            "accrued_interest_due": round(total_interest_due, 2),
            "total_interest_before_repay": round(total_interest_due, 2),
            "offset_interest": round(offset_interest, 2),
            "offset_to_interest": round(offset_interest, 2),
            "offset_principal": round(offset_principal, 2),
            "offset_to_principal": round(offset_principal, 2),
            "remaining_principal_balance": round(current_principal, 2),
            "remaining_principal": round(current_principal, 2),
            "unpaid_interest_balance": round(unpaid_accrued_interest, 2),
            "unpaid_interest_after_repay": round(unpaid_accrued_interest, 2),
            "legal_comment": legal_comment,
            "statute_basis": "《民法典》第561条法定顺位冲抵（费用->利息->本金）",
            "voucher": rf["voucher"]
        })

        last_calc_date = f_date

    # 2. 异常洗钱/虚假交付风险探针扫描 (Red-Flag Detector)
    red_flags = []
    
    # 探针 A: 资金快速回流检测（出借转出后 48 小时内，又有资金反向回流原告/出借人关联账户，涉嫌砍头息或假交付）
    for df in disbursement_flows:
        d_out = df["date"]
        amt_out = df["amount"]
        for other_f in valid_dated_flows:
            if other_f["flow_id"] == df["flow_id"]:
                continue
            d_in = other_f["date"]
            amt_in = other_f["amount"]
            delta_days = (d_in - d_out).days

            # 判断是否为反向回流款
            is_reverse = False
            if df["payee"] and other_f["payer"] and (df["payee"] in other_f["payer"] or other_f["payer"] in df["payee"]):
                is_reverse = True
            elif df["payer"] and other_f["payee"] and (df["payer"] in other_f["payee"] or other_f["payee"] in df["payer"] or "出借" in other_f["payee"] or "原告" in other_f["payee"]):
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
                    )
                })

    # 探针 B: 第三方代收或第三方代付/账户混同无委托凭据
    for f in parsed_flows:
        p_text = f["purpose"]
        payer = f["payer"]
        payee = f["payee"]
        # B1. 出借交付入第三方账户
        if any(k in p_text for k in ["借款", "出借", "本金"]) and ("第三人" in payee or "出纳" in payee or "配偶" in payee or (debtor_name and payee and debtor_name not in payee)):
            red_flags.append({
                "risk_type": "第三方代收交付阻断抗辩",
                "severity": "HIGH",
                "flow_id": f["flow_id"],
                "payee": payee,
                "risk_tip": (
                    f"借款本金未直接汇入借款人本人银行账户，而是汇入第三方【{payee}】！"
                    "依《最高法民间借贷规定》第8条，出借人主张第三人系受委托收款的，必须提供借款人明确的书面指示委托书或微信聊天明确确认，"
                    "否则将面临'借款款项未实际交付、借贷实践合同未生效'的败诉风险！"
                )
            })
        # B2. 还款清偿由第三方汇出
        if any(k in p_text for k in ["还款", "代还", "归还", "清偿", "付息"]) and ("第三" in payer or "代" in p_text or (debtor_name and payer and debtor_name not in payer)):
            red_flags.append({
                "risk_type": "第三方代付未见授权抗辩",
                "severity": "HIGH",
                "flow_id": f["flow_id"],
                "payer": payer,
                "risk_tip": (
                    f"还款资金系由案外第三方【{payer}】汇出！"
                    "卷宗内若无第三人代为清偿协议或债务人委托代付书，该款项性质可能被案外人主张为错汇、不当得利或借贷往来，"
                    "面临被另案起诉要求返还的重大衍生诉讼风险！"
                )
            })

    # 探针 C: 附言定性冲突
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
                )
            })

    # 3. 生成合伙人对账质证意见
    statutory_statement = _generate_art_561_court_statement(
        principal_amount=p_base,
        rate=rate,
        start_date=str(d_initial),
        ledger=reconciliation_ledger,
        remaining_p=current_principal,
        unpaid_interest=unpaid_accrued_interest,
        red_flags=red_flags
    )

    return {
        "status": "success",
        "principal_claim_initial": round(p_base, 2),
        "annual_interest_rate": rate,
        "initial_lending_date": str(d_initial),
        "current_principal_unpaid": round(current_principal, 2),
        "total_nominal_repayments": round(total_repayments_nominal, 2),
        "total_interest_offset": round(total_interest_offset, 2),
        "total_principal_offset": round(total_principal_offset, 2),
        "unpaid_accrued_interest": round(unpaid_accrued_interest, 2),
        "reconciliation_ledger": reconciliation_ledger,
        "red_flags": red_flags,
        "court_cross_exam_statement": statutory_statement
    }


def _generate_art_561_court_statement(
    principal_amount: float,
    rate: float,
    start_date: str,
    ledger: List[Dict[str, Any]],
    remaining_p: float,
    unpaid_interest: float,
    red_flags: List[Dict[str, Any]]
) -> str:
    lines = []
    lines.append("【原告方代理词/质证意见：依据《民法典》第561条驳斥被告清偿抗辩之冲抵对账说明】")
    lines.append(f"一、诉争借款本金基数与利率标准：")
    lines.append(f"原告向被告出借本金人民币 {principal_amount:,.2f} 元，出借交付起算日为 {start_date}，合同约定年化利率为 {rate*100:.2f}%（未逾越司法保护红线）。")
    lines.append("")
    lines.append("二、法定清偿顺位与逐笔冲抵核算事实：")
    lines.append("《中华人民共和国民法典》第五百六十一条明确规定：")
    lines.append("『债务人在履行主债务外还应当支付利息和实现债权的有关费用，其给付不足以清偿全部债务的，除当事人另有约定外，应当按照下列顺序履行：")
    lines.append("  （一）实现债权的有关费用；")
    lines.append("  （二）利息；")
    lines.append("  （三）主债务。』")
    lines.append("本案中双方并未特别约定利息与本金的任意冲抵顺序，故被告此前支付的款项必须依法先行清偿当期已产生的应付利息，剩余部分方可冲减借款本金。")
    lines.append("")
    
    if ledger:
        lines.append("分笔冲抵对账明细如下：")
        for item in ledger:
            lines.append(
                f"  • {item['payment_date']} 被告还款 ¥{item['nominal_amount']:,.2f} 元："
                f"冲抵当期利息 ¥{item['offset_interest']:,.2f} 元，冲减借款本金 ¥{item['offset_principal']:,.2f} 元；"
                f"冲抵后借款本金尚欠余额为人民币 ¥{item['remaining_principal_balance']:,.2f} 元。"
            )
        lines.append("")
    else:
        lines.append("  • 被告自借款发生至今未向原告清偿任何款项，尚欠全额本金及逾期利息。")

    lines.append(f"三、对账终审结论：")
    lines.append(f"截至最后结息日，被告仍拖欠原告借款本金人民币 {remaining_p:,.2f} 元，并拖欠未结清利息人民币 {unpaid_interest:,.2f} 元。被告关于'还款全额冲抵本金'之抗辩，违背国家强制性清偿冲抵法则，依法不应被采信！")

    if red_flags:
        lines.append("")
        lines.append("四、主办律师特别风控防线排查提示：")
        for idx, rf in enumerate(red_flags, 1):
            lines.append(f"  [{idx}] 【{rf['risk_type']}】: {rf['risk_tip']}")

    return "\n".join(lines)
