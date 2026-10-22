"""
LawFlow 智律工作台 - P4 阶段：执行财产线索穿透与追加被执行人引擎

批次8：默认参数改为 None；缺事实探针返回 INSUFFICIENT_FACTS；
法律表述按律师意见 L-I14/I15/I16/I17 修正；演示数据仅 use_demo=true 加载。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from gateway.utils.citation_guard import audit_case_numbers, audit_citations_in_text

PLACEHOLDER = "【待填写】"
DEMO_NOTICE = "演示数据·非真实案例"


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_enforcement_demo() -> Dict[str, Any]:
    path = _project_root() / "data" / "demo" / "enforcement_demo.json"
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    data["is_demo"] = True
    return data


def _fmt_amount(amount: Optional[float]) -> str:
    if amount is None:
        return PLACEHOLDER
    return f"{amount:,.2f}"


def _has_evidence_phrase(evidence_note: Optional[str], *keywords: str) -> bool:
    note = evidence_note or ""
    return any(k in note for k in keywords)


def analyze_enforcement_and_asset_penetration(
    case_title: Optional[str] = None,
    claim_amount: Optional[float] = None,
    book_balance: Optional[float] = None,
    debtor_name: Optional[str] = None,
    controller_name: Optional[str] = None,
    transferee_name: Optional[str] = None,
    share_capital: Optional[float] = None,
    subscribed_share_ratio: Optional[float] = None,
    ex_wife_name: Optional[str] = None,
    divorce_date: Optional[str] = None,
    debt_origin_date: Optional[str] = None,
    real_estate_value: Optional[float] = None,
    equipment_value: Optional[float] = None,
    third_party_claimant: Optional[str] = None,
    intermingled_flows: Optional[List[Dict[str, Any]]] = None,
    use_demo: bool = False,
    is_one_person_company: Optional[bool] = None,
    equity_transfers: Optional[List[Dict[str, Any]]] = None,
    capital_flows: Optional[List[Dict[str, Any]]] = None,
    divorce_transfer: Optional[Dict[str, Any]] = None,
    third_party_objection: Optional[Dict[str, Any]] = None,
    related_company_hint: bool = False,
    related_company_note: Optional[str] = None,
    execution_case_no: Optional[str] = None,
    court_name: Optional[str] = None,
    applicant_name: Optional[str] = None,
    company_unable_to_pay: Optional[bool] = None,
) -> Dict[str, Any]:
    is_demo = False
    demo_notice = ""
    if use_demo:
        demo = _load_enforcement_demo()
        is_demo = True
        demo_notice = DEMO_NOTICE
        case_title = case_title or demo.get("case_title")
        claim_amount = claim_amount if claim_amount is not None else demo.get("claim_amount")
        book_balance = book_balance if book_balance is not None else demo.get("book_balance")
        debtor_name = debtor_name or demo.get("debtor_name")
        controller_name = controller_name or demo.get("controller_name")
        transferee_name = transferee_name or demo.get("transferee_name")
        share_capital = share_capital if share_capital is not None else demo.get("share_capital")
        subscribed_share_ratio = (
            subscribed_share_ratio
            if subscribed_share_ratio is not None
            else demo.get("subscribed_share_ratio")
        )
        is_one_person_company = (
            is_one_person_company
            if is_one_person_company is not None
            else demo.get("is_one_person_company")
        )
        equity_transfers = equity_transfers or demo.get("equity_transfers")
        capital_flows = capital_flows or demo.get("capital_flows") or demo.get("intermingled_flows")
        divorce_transfer = divorce_transfer or demo.get("divorce_transfer")
        third_party_objection = third_party_objection or demo.get("third_party_objection")
        related_company_note = related_company_note or demo.get("related_company_note")
        related_company_hint = True if related_company_note else related_company_hint
        execution_case_no = execution_case_no or demo.get("execution_case_no")
        court_name = court_name or demo.get("court_name")
        applicant_name = applicant_name or demo.get("applicant_name")
        if divorce_transfer:
            ex_wife_name = ex_wife_name or divorce_transfer.get("ex_spouse")
            divorce_date = divorce_date or divorce_transfer.get("divorce_date")
            debt_origin_date = debt_origin_date or divorce_transfer.get("debt_origin_date")
            real_estate_value = (
                real_estate_value
                if real_estate_value is not None
                else divorce_transfer.get("transferred_assets_value")
            )
        if third_party_objection:
            third_party_claimant = third_party_claimant or third_party_objection.get("claimant")
            equipment_value = (
                equipment_value
                if equipment_value is not None
                else third_party_objection.get("asset_value")
            )

    flows = capital_flows if capital_flows is not None else intermingled_flows
    title = case_title or PLACEHOLDER

    probes: List[Dict[str, Any]] = []
    recoverable_parts: List[float] = []

    # --------------------------------------------------------------------------
    # 探针 1：未届出资期限股权转让
    # --------------------------------------------------------------------------
    p1_missing = []
    if not equity_transfers:
        p1_missing.append("equity_transfers")
    if controller_name is None and not (equity_transfers and equity_transfers[0].get("transferor")):
        p1_missing.append("controller_name/transferor")
    if p1_missing:
        probes.append(
            {
                "probe_id": "ENF-01",
                "probe_name": "股东未届出资期转让股权",
                "status": "INSUFFICIENT_FACTS",
                "missing_facts": p1_missing,
                "severity": None,
            }
        )
    else:
        tr = equity_transfers[0]
        unpaid = tr.get("unpaid_capital")
        if unpaid is None and share_capital is not None and subscribed_share_ratio is not None:
            unpaid = share_capital * subscribed_share_ratio
        transferor = tr.get("transferor") or controller_name or PLACEHOLDER
        transferee = tr.get("transferee") or transferee_name or PLACEHOLDER
        evidence_note = tr.get("evidence_note") or ""
        factual = (
            f"原股东 {transferor} 向 {transferee} 转让股权；"
            f"未缴纳出资额（用户提供）：{_fmt_amount(unpaid)} 元。"
            f"{evidence_note}"
        )
        qualitative = []
        if _has_evidence_phrase(evidence_note, "职业背债人"):
            qualitative.append("职业背债人")
        if _has_evidence_phrase(evidence_note, "勾结中介"):
            qualitative.append("勾结中介")
        accel_note = ""
        if company_unable_to_pay:
            accel_note = (
                "另：公司不能清偿到期债务时，可关注新《公司法》第五十四条关于出资加速到期的规定。"
            )
        logic = (
            "可以依《追加规定》第十七条、第十九条申请追加；"
            "该情形能否在执行程序中直接追加，实务存在争议，如被驳回，"
            "可通过执行异议之诉或另诉主张（新《公司法》第八十八条）。"
            + accel_note
        )
        probes.append(
            {
                "probe_id": "ENF-01",
                "probe_name": "股东未届出资期转让股权",
                "status": "READY",
                "target_entity": transferor,
                "target_statute": (
                    "最高人民法院《关于民事执行中变更、追加当事人若干问题的规定》第十七条、第十九条；"
                    "新《公司法》第八十八条"
                ),
                "severity": "CRITICAL_PIERCING",
                "unpaid_amount": unpaid,
                "factual_findings": factual,
                "qualitative_labels": qualitative,
                "legal_breakthrough_logic": logic,
                "piercing_relief": (
                    f"可以申请追加原股东 {transferor} 为被执行人，"
                    f"在未出资 {_fmt_amount(unpaid)} 元范围内主张补充清偿责任。"
                ),
            }
        )
        if unpaid:
            recoverable_parts.append(float(unpaid))

    # --------------------------------------------------------------------------
    # 探针 2：一人公司财产独立 / 关联公司提示
    # --------------------------------------------------------------------------
    p2_missing = []
    if is_one_person_company is not True:
        p2_missing.append("is_one_person_company=true")
    if not flows:
        p2_missing.append("capital_flows")
    if not controller_name:
        p2_missing.append("controller_name")
    related_hint_text = (
        "关联公司之间的人格否认（《公司法》第二十三条第二款）不属于执行追加情形，需另行提起诉讼。"
    )
    if p2_missing:
        probe2: Dict[str, Any] = {
            "probe_id": "ENF-02",
            "probe_name": "一人公司财产独立与人格否认",
            "status": "INSUFFICIENT_FACTS",
            "missing_facts": p2_missing,
            "severity": None,
        }
        if related_company_hint or related_company_note:
            probe2["related_company_note"] = related_hint_text
            if related_company_note:
                probe2["related_company_note"] += f" 用户说明：{related_company_note}"
        probes.append(probe2)
    else:
        total_commingled = sum(float(f.get("amount") or 0) for f in flows)
        logic = (
            "依《追加规定》第二十条，一人有限责任公司的股东不能证明公司财产独立于自己的财产的，"
            "可以申请追加其为被执行人。"
        )
        probes.append(
            {
                "probe_id": "ENF-02",
                "probe_name": "一人公司财产独立与人格否认",
                "status": "READY",
                "target_entity": controller_name,
                "target_statute": (
                    "《中华人民共和国公司法》第二十三条第三款、"
                    "最高人民法院《关于民事执行中变更、追加当事人若干问题的规定》第二十条"
                ),
                "severity": "CRITICAL_PIERCING",
                "commingled_amount": total_commingled,
                "factual_findings": (
                    f"用户主张目标公司为一人有限责任公司，实控人 {controller_name}；"
                    f"提供混同流水合计 {_fmt_amount(total_commingled)} 元。"
                ),
                "legal_breakthrough_logic": logic,
                "related_company_note": related_hint_text if (related_company_hint or related_company_note) else None,
                "piercing_relief": f"可以申请追加 {controller_name} 为被执行人。",
            }
        )

    # --------------------------------------------------------------------------
    # 探针 3：撤销权（假离婚/无偿转让）
    # --------------------------------------------------------------------------
    p3_missing = []
    dt = divorce_transfer
    if not dt:
        # 兼容零散字段：需同时具备关键事实
        if not (ex_wife_name and divorce_date and debt_origin_date and real_estate_value is not None):
            p3_missing.extend(
                [
                    x
                    for x, v in [
                        ("divorce_transfer.ex_spouse", ex_wife_name),
                        ("divorce_transfer.divorce_date", divorce_date),
                        ("divorce_transfer.debt_origin_date", debt_origin_date),
                        ("divorce_transfer.transferred_assets_value", real_estate_value),
                    ]
                    if not v and v != 0
                ]
            )
            if not divorce_transfer:
                p3_missing.append("divorce_transfer")
        else:
            dt = {
                "ex_spouse": ex_wife_name,
                "divorce_date": divorce_date,
                "debt_origin_date": debt_origin_date,
                "transferred_assets_value": real_estate_value,
                "description": "",
            }
    if p3_missing:
        probes.append(
            {
                "probe_id": "ENF-03",
                "probe_name": "债权人撤销权（无偿转让财产）",
                "status": "INSUFFICIENT_FACTS",
                "missing_facts": list(dict.fromkeys(p3_missing)),
                "severity": None,
            }
        )
    else:
        assert dt is not None
        asset_val = dt.get("transferred_assets_value")
        logic = (
            "依据《民法典》第五百三十八条、第五百三十九条，债权人可就债务人无偿或以明显不合理低价"
            "转让财产等行为提起撤销权之诉。"
            "另请注意《民法典》第五百四十一条除斥期间："
            "自知道或应当知道撤销事由之日起1年，自行为发生之日起5年"
            "（律师注明原文未在线逐字核对）。"
        )
        probes.append(
            {
                "probe_id": "ENF-03",
                "probe_name": "债权人撤销权（无偿转让财产）",
                "status": "READY",
                "target_entity": f"{controller_name or PLACEHOLDER}及 {dt.get('ex_spouse') or PLACEHOLDER}",
                "target_statute": "《中华人民共和国民法典》第五百三十八条、第五百三十九条、第五百四十一条",
                "severity": "CRITICAL_PIERCING",
                "sheltered_asset_value": asset_val,
                "factual_findings": (
                    f"债务发生于 {dt.get('debt_origin_date') or PLACEHOLDER}，"
                    f"于 {dt.get('divorce_date') or PLACEHOLDER} 发生财产分割/转让；"
                    f"涉及财产价值 {_fmt_amount(asset_val)} 元。"
                    f"{dt.get('description') or ''}"
                ),
                "legal_breakthrough_logic": logic,
                "piercing_relief": f"可提起债权人撤销权之诉，主张追回价值 {_fmt_amount(asset_val)} 元之责任财产。",
            }
        )
        if asset_val:
            recoverable_parts.append(float(asset_val))

    # --------------------------------------------------------------------------
    # 探针 4：融资租赁执行异议
    # --------------------------------------------------------------------------
    p4_missing = []
    obj = third_party_objection
    if not obj:
        if not (third_party_claimant and equipment_value is not None):
            p4_missing.append("third_party_objection")
            if not third_party_claimant:
                p4_missing.append("third_party_claimant")
            if equipment_value is None:
                p4_missing.append("equipment_value")
        else:
            obj = {
                "claimant": third_party_claimant,
                "asset_value": equipment_value,
                "asset_description": "涉案动产",
                "evidence_note": "",
            }
    if p4_missing:
        probes.append(
            {
                "probe_id": "ENF-04",
                "probe_name": "案外人融资租赁执行异议",
                "status": "INSUFFICIENT_FACTS",
                "missing_facts": list(dict.fromkeys(p4_missing)),
                "severity": None,
            }
        )
    else:
        assert obj is not None
        ev = obj.get("evidence_note") or ""
        daoqian = _has_evidence_phrase(ev, "倒签")
        factual = (
            f"案外人 {obj.get('claimant') or PLACEHOLDER} 就 "
            f"{obj.get('asset_description') or '涉案财产'}（价值 {_fmt_amount(obj.get('asset_value'))} 元）"
            f"提出执行异议。{ev}"
        )
        if daoqian:
            factual += "（用户提供的证据描述含倒签相关内容。）"
        logic = (
            "融资租赁动产异议应关注《民法典》第七百四十五条"
            "（出租人对租赁物的所有权，未经登记不得对抗善意第三人；律师注明原文未在线逐字核对）"
            "及《担保制度解释》关于融资租赁的规定（具体条号 TODO(律师核实)）。"
            "融资租赁与所有权保留分属不同制度，应分别审查构成要件。"
            "申请执行人可依法提起执行异议之诉。"
        )
        probes.append(
            {
                "probe_id": "ENF-04",
                "probe_name": "案外人融资租赁执行异议",
                "status": "READY",
                "target_entity": obj.get("claimant"),
                "target_statute": (
                    "《中华人民共和国民事诉讼法》第二百三十八条；"
                    "《民法典》第七百四十五条（需律师核实原文）；"
                    "《担保制度解释》融资租赁相关规定（条号 TODO(律师核实)）"
                ),
                "severity": "CRITICAL_PIERCING",
                "equipment_value": obj.get("asset_value"),
                "factual_findings": factual,
                "legal_breakthrough_logic": logic,
                "piercing_relief": (
                    f"可提起执行异议之诉，请求对价值 {_fmt_amount(obj.get('asset_value'))} 元之财产继续执行。"
                ),
            }
        )
        if obj.get("asset_value"):
            recoverable_parts.append(float(obj["asset_value"]))

    # 关联公司提示：即使探针2不足，也在结果中给出（验收：关联公司输出含另行提起诉讼）
    if related_company_hint or related_company_note:
        for p in probes:
            if p["probe_id"] == "ENF-02" and not p.get("related_company_note"):
                p["related_company_note"] = (
                    "关联公司之间的人格否认（《公司法》第二十三条第二款）不属于执行追加情形，需另行提起诉讼。"
                )

    total_recoverable = sum(recoverable_parts) if recoverable_parts else None
    # 无任何 READY 探针时 recoverable 为 0
    if all(p.get("status") == "INSUFFICIENT_FACTS" for p in probes):
        total_recoverable = 0

    app_doc = _generate_addition_application(
        debtor_name=debtor_name,
        controller_name=controller_name,
        transferee_name=transferee_name,
        claim_amount=claim_amount,
        equity_transfers=equity_transfers,
        flows=flows,
        is_one_person_company=is_one_person_company,
        execution_case_no=execution_case_no,
        court_name=court_name,
        applicant_name=applicant_name,
        company_unable_to_pay=company_unable_to_pay,
    )
    lawsuit_obj = third_party_objection
    if not p4_missing and lawsuit_obj is None and obj is not None:
        lawsuit_obj = obj
    lawsuit_doc = _generate_execution_objection_lawsuit(
        debtor_name=debtor_name,
        third_party_objection=lawsuit_obj,
        claim_amount=claim_amount,
        execution_case_no=execution_case_no,
        court_name=court_name,
        applicant_name=applicant_name,
    )

    case_guard = audit_case_numbers(app_doc + " " + lawsuit_doc)
    citation_guard_res = audit_citations_in_text(app_doc + " " + lawsuit_doc)

    ready_n = sum(1 for p in probes if p.get("status") == "READY")
    overall = (
        f"已具备事实输入的探针 {ready_n}/4；"
        f"可主张责任财产测算合计 {_fmt_amount(total_recoverable)} 元（仅基于用户输入，非法院认定）。"
    )

    out: Dict[str, Any] = {
        "status": "success",
        "case_title": title,
        "claim_amount": claim_amount,
        "book_balance": book_balance,
        "recoverable_potential": total_recoverable,
        "probes": probes,
        "intermingled_flows": flows or [],
        "addition_application_text": app_doc,
        "objection_lawsuit_text": lawsuit_doc,
        "cases_verified": case_guard,
        "citations_verified": citation_guard_res,
        "overall_strategy": overall,
    }
    if is_demo:
        out["is_demo"] = True
        out["demo_notice"] = demo_notice
    return out


def _generate_addition_application(
    debtor_name: Optional[str],
    controller_name: Optional[str],
    transferee_name: Optional[str],
    claim_amount: Optional[float],
    equity_transfers: Optional[List[Dict[str, Any]]],
    flows: Optional[List[Dict[str, Any]]],
    is_one_person_company: Optional[bool],
    execution_case_no: Optional[str],
    court_name: Optional[str],
    applicant_name: Optional[str],
    company_unable_to_pay: Optional[bool],
) -> str:
    applicant = applicant_name or PLACEHOLDER
    debtor = debtor_name or PLACEHOLDER
    controller = controller_name or PLACEHOLDER
    case_no = execution_case_no or PLACEHOLDER
    court = court_name or PLACEHOLDER

    unpaid = None
    transferee = transferee_name or PLACEHOLDER
    evidence_note = ""
    if equity_transfers:
        tr = equity_transfers[0]
        unpaid = tr.get("unpaid_capital")
        transferee = tr.get("transferee") or transferee
        evidence_note = tr.get("evidence_note") or ""
        controller = tr.get("transferor") or controller

    lines = []
    lines.append("追 加 被 执 行 人 申 请 书")
    lines.append("")
    lines.append(f"申请执行人：{applicant}")
    lines.append(f"被执行人：{debtor}")
    lines.append(f"被申请人（原出资股东）：{controller}")
    if equity_transfers:
        lines.append(f"股权受让人：{transferee}")
    lines.append("")
    lines.append("【申请请求】")
    lines.append(f"1. 依法裁定追加被申请人【{controller}】为 {case_no} 执行案件的被执行人；")
    lines.append(
        f"2. 裁定追加被申请人【{controller}】在未缴纳出资人民币 {_fmt_amount(unpaid)} 元范围内，"
        f"对被执行人不能清偿的执行标的人民币 {_fmt_amount(claim_amount)} 元承担补充清偿责任；"
    )
    if is_one_person_company:
        lines.append(
            f"3. 依《追加规定》第二十条，申请追加被申请人【{controller}】为被执行人，"
            f"对公司债务承担相应责任。"
        )
    lines.append("")
    lines.append("【事实与理由】")
    lines.append(
        f"申请执行人与被执行人纠纷一案，生效法律文书确定的执行标的为人民币 {_fmt_amount(claim_amount)} 元。"
        f"执行案号：{case_no}。"
    )
    if equity_transfers:
        lines.append("")
        lines.append("一、未届出资期限转让股权")
        fact_extra = evidence_note
        for banned_kw in ("职业背债人", "勾结中介"):
            if banned_kw not in evidence_note:
                fact_extra = fact_extra  # 仅用户证据描述中有时才保留（已在 evidence_note）
        lines.append(
            f"被申请人 {controller} 将股权转让给 {transferee}，未缴纳出资金额 {_fmt_amount(unpaid)} 元。"
            f"{evidence_note}"
            "可以依《追加规定》第十七条、第十九条申请追加；"
            "该情形能否在执行程序中直接追加，实务存在争议，如被驳回，"
            "可通过执行异议之诉或另诉主张（新《公司法》第八十八条）。"
        )
        if company_unable_to_pay:
            lines.append(
                "在公司不能清偿到期债务时，可关注新《公司法》第五十四条关于出资加速到期的规定。"
            )
    if is_one_person_company and flows:
        lines.append("")
        lines.append("二、一人有限责任公司财产独立")
        total = sum(float(f.get("amount") or 0) for f in flows)
        lines.append(
            f"申请执行人提供公私资金往来流水合计 {_fmt_amount(total)} 元。"
            "依《追加规定》第二十条，一人有限责任公司的股东不能证明公司财产独立于自己的财产的，"
            "可以申请追加其为被执行人。"
        )
    if not equity_transfers and not (is_one_person_company and flows):
        lines.append(f"具体追加事实与证据：{PLACEHOLDER}")
    lines.append("")
    lines.append("此致")
    lines.append(court)
    lines.append("")
    lines.append(f"申请执行人：{applicant}")
    lines.append(f"日期：{datetime.now().strftime('%Y年%m月%d日')}")
    return "\n".join(lines)


def _generate_execution_objection_lawsuit(
    debtor_name: Optional[str],
    third_party_objection: Optional[Dict[str, Any]],
    claim_amount: Optional[float],
    execution_case_no: Optional[str],
    court_name: Optional[str],
    applicant_name: Optional[str],
) -> str:
    applicant = applicant_name or PLACEHOLDER
    debtor = debtor_name or PLACEHOLDER
    case_no = execution_case_no or PLACEHOLDER
    court = court_name or PLACEHOLDER
    obj = third_party_objection or {}
    claimant = obj.get("claimant") or PLACEHOLDER
    asset_desc = obj.get("asset_description") or PLACEHOLDER
    asset_val = obj.get("asset_value")
    evidence_note = obj.get("evidence_note") or ""

    lines = []
    lines.append("民 事 起 诉 状")
    lines.append("（案外人执行异议之诉·申请执行人提起）")
    lines.append("")
    lines.append(f"原告（申请执行人）：{applicant}")
    lines.append(f"被告（案外人/异议人）：{claimant}")
    lines.append(f"第三人（被执行人）：{debtor}")
    lines.append("")
    lines.append("【诉讼请求】")
    lines.append(f"1. 依法确认查封于第三人处的 {asset_desc} 属于第三人的责任财产；")
    lines.append(
        f"2. 判令对贵院在 {case_no} 执行案件中查封的涉案财产"
        f"（价值人民币 {_fmt_amount(asset_val)} 元）准予继续执行；"
    )
    lines.append("3. 判令由被告承担本案全部诉讼费用。")
    lines.append("")
    lines.append("【事实与理由】")
    lines.append(
        f"原告与第三人 {debtor} 债务纠纷一案（执行标的 {_fmt_amount(claim_amount)} 元），"
        f"贵院在执行程序中依法查封了涉案财产。被告提出执行异议。{evidence_note}"
    )
    lines.append("")
    lines.append(
        "融资租赁相关权利应依《民法典》第七百四十五条（需律师核实原文）"
        "及《担保制度解释》关于融资租赁的规定（具体条号 TODO(律师核实)）审查；"
        "融资租赁与所有权保留分属不同制度，不得混淆。"
    )
    lines.append("")
    lines.append(
        "综上所述，依据《中华人民共和国民事诉讼法》第二百三十八条之规定，"
        "特诉请贵院查明事实，判决准予继续执行涉案财产。"
    )
    lines.append("")
    lines.append("此致")
    lines.append(court)
    lines.append("")
    lines.append(f"起诉人：{applicant}")
    lines.append(f"日期：{datetime.now().strftime('%Y年%m月%d日')}")
    return "\n".join(lines)
