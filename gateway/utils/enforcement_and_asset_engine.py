"""
LawFlow 智律工作台 - P4 阶段：执行终本破局·财产线索穿透与追加被执行人对抗引擎
(Enforcement Breakthrough, Asset Penetration & Debtor Piercing Engine)

针对执行终本案件（执行标的过亿、账面仅余数百元、实控人金蝉脱壳转移财产）的核心实务法理：
1. 探针 1：新《公司法》第47条/第88条 & 最高院《追加当事人规定》第17-19条【出资未届满转让穿透探针】
   - 认缴期限不得超5年；转让未届出资股权，受让人未按期足额缴纳，原股东承担补充责任；
   - 涉嫌找偏远山区无清偿能力老人（职业背债人）0元接盘恶意逃废债，直接穿透追加原股东在未出资范围内承担责任。
2. 探针 2：《公司法》第23条第三款 & 最高院《追加当事人规定》第20条【一人公司/关联空壳公私资金混同探针】
   - 一人公司财产独立举证责任倒置；
   - 穿行审计公转私、微信支付宝大额个人代收代付、关联空壳承接业务流水，直接追加实控人个人连带清偿。
3. 探针 3：《民法典》第538-539条【协议假离婚恶意无偿转移财产撤销探针】
   - 负债成立在先，执行保全前夕协议离婚净身出户，将数千万房产理财无偿赠与前妻，恶意串通逃避执行；
   - 锁定无偿性与时间戳矛盾，依法行使债权人撤销权，追回两套豪宅作为执行责任财产。
4. 探针 4：《民事诉讼法》第238条 & 《执行异议复议规定》第28/31条【案外人倒签融资租赁虚假异议破壁探针】
   - 查封数控机床遭遇案外人持倒签租赁合同异议；
   - 从实际交付管领权、真实对价银行流水缺位、发票开具时序矛盾三重粉碎其虚假异议，提起执行异议之诉继续执行。
5. 一键生成符合最高人民法院执行审查标准的《追加被执行人申请书》与《执行异议之诉起诉状》并原生导出 Word。
"""

import os
import re
from datetime import datetime, date
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

from gateway.utils.citation_guard import audit_case_numbers, audit_citations_in_text


# ==============================================================================
# 1. 穿透式执行线索侦测与破局引擎
# ==============================================================================

def analyze_enforcement_and_asset_penetration(
    case_title: Optional[str] = None,
    claim_amount: float = 120000000.0,
    book_balance: float = 342.18,
    debtor_name: str = "北京华腾智达科技有限公司",
    controller_name: str = "张某某",
    transferee_name: str = "赵某某（72岁偏远山区无清偿能力五保人员）",
    share_capital: float = 50000000.0,
    subscribed_share_ratio: float = 0.99,
    ex_wife_name: str = "刘某某",
    divorce_date: str = "2023-06-18",
    debt_origin_date: str = "2022-10-15",
    real_estate_value: float = 45000000.0,
    equipment_value: float = 25000000.0,
    third_party_claimant: str = "某融资租赁（天津）有限公司",
    intermingled_flows: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    执行终本破局·财产线索穿透与追加被执行人综合分析引擎
    """
    title = case_title or "1.2亿元终本借贷及担保执行款财产线索穿透案"
    unpaid_capital = share_capital * subscribed_share_ratio

    # --------------------------------------------------------------------------
    # 探针 1：新《公司法》第47/88条 & 最高院追加规定第17-19条【出资未届满转让穿透探针】
    # --------------------------------------------------------------------------
    probe_1_capital_transfer = {
        "probe_id": "ENF-01",
        "probe_name": "股东未届出资期转让股权与职业背债人穿透",
        "target_entity": controller_name,
        "target_statute": "新《公司法》第47条、第88条第一款、最高人民法院《关于民事执行中变更、追加当事人若干问题的规定》第17条、第19条",
        "severity": "CRITICAL_PIERCING",
        "unpaid_amount": unpaid_capital,
        "factual_findings": (
            f"目标公司注册资本人民币 {share_capital:,.2f} 元，实控人 {controller_name} 认缴 {subscribed_share_ratio*100:.1f}%（计 {unpaid_capital:,.2f} 元）。"
            f"在公司债务到期不能清偿且认缴期限届满前夕，{controller_name} 勾结中介以 0 元对价将股权转让给 {transferee_name}。"
            f"受让人年逾古稀且为偏远地区低保户，无任何实缴出资能力，系典型的'职业背债人'。"
        ),
        "legal_breakthrough_logic": (
            "【直接追加原股东承担补充责任】依据新《公司法》第88条第一款明文规定：股东转让未届出资期限股权的，受让人未按期足额缴纳出资，"
            "转让人对受让人未按期缴纳的出资承担补充责任！结合最高院《追加规定》第19条，原股东在明知公司存在巨额负债情况下恶意转让未实缴股权，"
            "出资义务依法加速到期，执行法院可直接裁定追加原股东张某某为被执行人，在未出资的 4950 万元范围内直接清偿债务！"
        ),
        "piercing_relief": f"追加原股东 {controller_name} 为被执行人，承担补足出资及补充清偿责任人民币 {unpaid_capital:,.2f} 元。"
    }

    # --------------------------------------------------------------------------
    # 探针 2：《公司法》第23条第三款 & 追加规定第20条【一人公司/关联空壳公私资金混同】
    # --------------------------------------------------------------------------
    flows = intermingled_flows or [
        {"flow_id": "F-01", "date": "2023-01-15", "amount": 3500000.0, "source": debtor_name, "target": f"{controller_name}个人微信", "summary": "往来款/差旅备用金"},
        {"flow_id": "F-02", "date": "2023-03-22", "amount": 5800000.0, "source": debtor_name, "target": f"{controller_name}个人招行卡", "summary": "项目咨询费无发票"},
        {"flow_id": "F-03", "date": "2023-05-10", "amount": 8200000.0, "source": debtor_name, "target": "北京嘉和盛世贸易有限公司（小舅子名下）", "summary": "预付采购款后无货物流水"}
    ]
    total_commingled = sum(f["amount"] for f in flows)

    probe_2_commingling = {
        "probe_id": "ENF-02",
        "probe_name": "一人公司人格混同与公私资金穿行混用",
        "target_entity": f"{controller_name}及关联小舅子空壳公司",
        "target_statute": "《中华人民共和国公司法》第二十三条第三款、最高人民法院《关于民事执行中变更、追加当事人若干问题的规定》第二十条",
        "severity": "CRITICAL_PIERCING",
        "commingled_amount": total_commingled,
        "factual_findings": (
            f"目标公司为一人有限责任公司，实控人 {controller_name} 长期将公司公款通过'备用金'、'咨询费'直接转入个人微信及个人私户，"
            f"累计发现无真实商业交易凭证的公私互转资金人民币 {total_commingled:,.2f} 元；"
            f"同时将其主营业务、核心上下游客户无偿剥离至其亲属名下贸易公司，导致被执行人公司被完全掏空。"
        ),
        "legal_breakthrough_logic": (
            "【举证责任倒置与人格否认直接连带】依据最高人民法院《追加规定》第二十条，一人有限责任公司财产不足以清偿生效法律文书确定债务的，"
            "只要申请执行人证明其存在公私账户互转、账目不清之事实，举证责任立即发生法定倒置——必须由股东证明公司财产独立于自己的财产！"
            "股东不能提供经专业审计无瑕疵之独立财务账册的，人民法院应当直接裁定追加其为被执行人，对公司全部 1.2 亿元债务承担无限连带清偿责任！"
        ),
        "piercing_relief": f"直接追加实控人 {controller_name} 为被执行人，对 1.2 亿元全部债务承担无限连带清偿责任。"
    }

    # --------------------------------------------------------------------------
    # 探针 3：《民法典》第538-539条【协议假离婚恶意无偿转移财产撤销探针】
    # --------------------------------------------------------------------------
    probe_3_divorce_transfer = {
        "probe_id": "ENF-03",
        "probe_name": "恶意协议假离婚无偿转移财产债权人撤销权",
        "target_entity": f"{controller_name}及其前妻 {ex_wife_name}",
        "target_statute": "《中华人民共和国民法典》第五百三十八条、第五百三十九条、最高人民法院关于适用《民法典》婚姻家庭编的解释（一）",
        "severity": "CRITICAL_PIERCING",
        "sheltered_asset_value": real_estate_value,
        "factual_findings": (
            f"涉案巨额债务发生于 {debt_origin_date}，债权人提起诉讼并拟保全财产期间，"
            f"{controller_name} 于 {divorce_date} 火速与配偶 {ex_wife_name} 协议离婚，"
            f"约定将市值约人民币 {real_estate_value:,.2f} 元的两套核心城市别墅、全部银行理财与车辆无偿归女方所有，"
            f"{controller_name} 本人净身出户且单独承担全部对外债务，导致执行陷入无财产可供执行的'终本'局面。"
        ),
        "legal_breakthrough_logic": (
            "【撤销无偿财产分割协议，追回豪宅执行】债务人在负担巨额对外债务后，通过协议离婚无偿将名下巨额财产让与配偶，"
            "属于典型的无偿转让财产行为，直接损害了申请执行人的到期合法债权。"
            "依据《民法典》第538条，债权人无需证明前妻具有主观恶意，只要客观上造成债权无法受偿，即可依法向法院提起债权人撤销权之诉，"
            "撤销该无偿分割条款，将价值 4500 万元的别墅房产重新确认为被执行人责任财产并申请查封执行！"
        ),
        "piercing_relief": f"提起债权人撤销权之诉，依法撤销《离婚财产分割协议》，追回价值 {real_estate_value:,.2f} 元豪宅恢复执行。"
    }

    # --------------------------------------------------------------------------
    # 探针 4：《民事诉讼法》第238条 & 《执行异议复议规定》第28/31条【案外人倒签融资租赁虚假异议破壁探针】
    # --------------------------------------------------------------------------
    probe_4_sham_lease = {
        "probe_id": "ENF-04",
        "probe_name": "案外人倒签融资租赁虚假执行异议破壁",
        "target_entity": third_party_claimant,
        "target_statute": "《中华人民共和国民事诉讼法》第二百三十八条、最高人民法院《关于人民法院办理执行异议和复议案件若干问题的规定》第二十八条、第三十一条",
        "severity": "CRITICAL_PIERCING",
        "equipment_value": equipment_value,
        "factual_findings": (
            f"执行局查封被执行人存放在厂房的价值人民币 {equipment_value:,.2f} 元精密数控机床后，"
            f"案外人 {third_party_claimant} 提出执行异议，提交一份倒签日期的《售后回租合同》，"
            f"主张其享有所有权并申请解除查封。但经现场与财务核查：涉案设备始终由被执行人实际占有、使用并列为固定资产折旧，"
            f"且案外人未提供完整 2500 万真实回购放款回单，增值税发票时点与合同倒签日期存在重大时序断裂。"
        ),
        "legal_breakthrough_logic": (
            "【提请执行异议之诉阻断解封，坚决拍卖变价】依据《民事诉讼法》第238条及融资租赁司法解释，"
            "真正的售后回租必须具备真实所有权让与及买受交付要件。案外人倒签合同、无真实对价给付闭环、无占有改定公示，"
            "其所谓'所有权保留'依法不能对抗申请执行人的强制执行效力。"
            "申请执行人依法在异议裁定后15日内提起《执行异议之诉》，请求法院确认涉案设备为被执行人责任财产并继续执行拍卖！"
        ),
        "piercing_relief": f"提起执行异议之诉，阻断解封并依法拍卖变价涉案 {equipment_value:,.2f} 元数控机床。"
    }

    probes = [
        probe_1_capital_transfer,
        probe_2_commingling,
        probe_3_divorce_transfer,
        probe_4_sham_lease
    ]

    total_recoverable_potential = unpaid_capital + real_estate_value + equipment_value

    # 生成《追加被执行人申请书》
    app_doc = _generate_addition_application(
        debtor_name=debtor_name,
        controller_name=controller_name,
        transferee_name=transferee_name,
        claim_amount=claim_amount,
        unpaid_capital=unpaid_capital,
        flows=flows
    )

    # 生成《执行异议之诉起诉状》
    lawsuit_doc = _generate_execution_objection_lawsuit(
        debtor_name=debtor_name,
        third_party_claimant=third_party_claimant,
        equipment_value=equipment_value,
        claim_amount=claim_amount
    )

    # 案号及法条后验验真
    case_guard = audit_case_numbers(app_doc + " " + lawsuit_doc)
    citation_guard_res = audit_citations_in_text(app_doc + " " + lawsuit_doc)

    return {
        "status": "success",
        "case_title": title,
        "claim_amount": claim_amount,
        "book_balance": book_balance,
        "recoverable_potential": total_recoverable_potential,
        "probes": probes,
        "intermingled_flows": flows,
        "addition_application_text": app_doc,
        "objection_lawsuit_text": lawsuit_doc,
        "cases_verified": case_guard,
        "citations_verified": citation_guard_res,
        "overall_strategy": (
            f"通过【四大穿透探针组合拳】：追加原股东实控人出资未实缴补充责任 {unpaid_capital/10000:.0f} 万元 + "
            f"追加一人公司财产混同连带清偿责任 + 撤销假离婚无偿分割追回豪宅 {real_estate_value/10000:.0f} 万元 + "
            f"执行异议之诉击穿虚假租赁保留机床 {equipment_value/10000:.0f} 万元，"
            f"穿透锁定可执行责任财产共计人民币 {total_recoverable_potential:,.2f} 元，彻底粉碎终本困局！"
        )
    }


def _generate_addition_application(
    debtor_name: str,
    controller_name: str,
    transferee_name: str,
    claim_amount: float,
    unpaid_capital: float,
    flows: List[Dict[str, Any]]
) -> str:
    """生成符合最高院标准的《追加被执行人申请书》"""
    lines = []
    lines.append("追 加 被 执 行 人 申 请 书")
    lines.append("")
    lines.append("申请执行人：某大型金融投资发展控股集团有限公司")
    lines.append(f"被执行人：{debtor_name}")
    lines.append(f"被申请人一（原出资股东）：{controller_name}，男，住北京市朝阳区建国路88号")
    lines.append(f"被申请人二（受让人）：{transferee_name}")
    lines.append("")
    lines.append("【申请请求】")
    lines.append(f"1. 依法裁定追加被申请人一【{controller_name}】为（2024）京01执889号执行案件的被执行人；")
    lines.append(f"2. 判令被申请人一【{controller_name}】在未缴纳出资人民币 {unpaid_capital:,.2f} 元范围内，对被执行人不能清偿的执行标的人民币 {claim_amount:,.2f} 元及利息承担补充清偿责任；")
    lines.append(f"3. 判令被申请人一【{controller_name}】因一人有限责任公司财产混同，对被执行人的全部债务承担无限连带清偿责任。")
    lines.append("")
    lines.append("【事实与理由】")
    lines.append("申请执行人与被执行人合同纠纷一案，已经生效民事判决书确定被执行人应向申请执行人偿付人民币1.2亿元及逾期利息。")
    lines.append("因被执行人未按期履行，申请执行人向贵院申请强制执行，案号为（2024）京01执889号。执行中，贵院裁定终结本次执行程序。")
    lines.append("经申请执行人深度调查核实，被执行人存在严重恶意逃避执行、掏空公司资产之违法行为，依法应予追加被申请人为被执行人：")
    lines.append("")
    lines.append("一、被申请人一作为原股东，在未届出资期限即恶意转让未缴出资股权，依法应当追加并承担出资补充清偿责任！")
    lines.append(
        f"被执行人注册资本5000万元，被申请人一 {controller_name} 认缴99%（4950万元），实缴出资为0元。"
        f"在公司债务形成后且出资期限未届满前，{controller_name} 伙同他人以0元对价将股权转让给偏远山区且无清偿能力的低保老人 {transferee_name}。"
        "依据新《中华人民共和国公司法》第四十七条、第八十八条第一款以及最高人民法院《关于民事执行中变更、追加当事人若干问题的规定》第十七条、第十九条规定，"
        "转让人对受让人未按期缴纳的出资承担补充责任。原股东利用'职业背债人'恶意逃废出资义务，依法应在未出资的4950万元范围内承担补充执行责任！"
    )
    lines.append("")
    lines.append("二、被执行人系一人有限责任公司，被申请人一长期公私财产高度混同，依法应承担举证责任倒置并承担无限连带责任！")
    lines.append(
        f"银行交易流水显示，被执行人账户多次在无真实交易背景情况下，以'备用金'、'差旅费'名义向被申请人一 {controller_name} 个人微信及银行卡"
        f"大额转账数千万元（如2023年单笔达820万元），形成严重的资产混同与利益输送。"
        "依据《中华人民共和国公司法》第二十三条第三款及最高人民法院《追加规定》第二十条规定，"
        "一人有限责任公司财产不足以清偿生效法律文书确定的债务，股东不能证明公司财产独立于自己的财产的，应当对公司债务承担连带责任。"
        f"被申请人一无法证明公司财产完全独立，贵院应直接裁定追加其为被执行人，对全部执行标的人民币 {claim_amount:,.2f} 元承担连带清偿责任！"
    )
    lines.append("")
    lines.append("此致")
    lines.append("北京市第一中级人民法院")
    lines.append("")
    lines.append("申请执行人：某大型金融投资发展控股集团有限公司")
    lines.append(f"日期：{datetime.now().strftime('%Y年%m月%d日')}")
    return "\n".join(lines)


def _generate_execution_objection_lawsuit(
    debtor_name: str,
    third_party_claimant: str,
    equipment_value: float,
    claim_amount: float
) -> str:
    """生成符合最高院标准的《执行异议之诉起诉状》"""
    lines = []
    lines.append("民 事 起 诉 状")
    lines.append("（案外人执行异议之诉·申请执行人提起）")
    lines.append("")
    lines.append("原告（申请执行人）：某大型金融投资发展控股集团有限公司")
    lines.append(f"被告（案外人/异议人）：{third_party_claimant}")
    lines.append(f"第三人（被执行人）：{debtor_name}")
    lines.append("")
    lines.append("【诉讼请求】")
    lines.append(f"1. 依法确认登记/查封于第三人 {debtor_name} 生产车间的精密数控机床设备属于第三人的责任财产；")
    lines.append(f"2. 判令对贵院在（2024）京01执889号执行案件中查封的涉案精密数控机床设备（评估价值人民币 {equipment_value:,.2f} 元）准予继续执行；")
    lines.append(f"3. 判令由被告承担本案全部诉讼费用。")
    lines.append("")
    lines.append("【事实与理由】")
    lines.append(
        f"原告与第三人 {debtor_name} 债务纠纷一案，贵院在执行程序中依法查封了第三人厂区内实际占有管领的涉案数控机床设备。"
        f"被告 {third_party_claimant} 提出执行异议，提交一份倒签日期的《售后回租融资租赁合同》，声称享有所有权，贵院执行局意图中止执行。"
        "原告认为，被告提出的执行异议纯属恶意串通倒签合同，缺乏事实与法律依据，特依法提起执行异议之诉："
    )
    lines.append("")
    lines.append("一、涉案数控机床自采购至今一直在第三人生产现场占有、使用与管领，被告从未实际受领交付！")
    lines.append(
        "根据《中华人民共和国民法典》第七百三十五条及融资租赁司法解释，融资租赁合同必须以真实买卖标的物所有权转移为前提。"
        "现场勘验与出入库台账证明，该设备从出厂即由第三人独立管领使用，被告从未派员交接或占有改定，不具备所有权对抗要件。"
    )
    lines.append("")
    lines.append("二、被告未能举证证明支付真实对价的银行清算凭证，增值税发票开具时序存在重大倒签伪造瑕疵！")
    lines.append(
        f"涉案合同虽倒签在两年前，但被告提供的银行流水中根本不存在向第三人支付 {equipment_value:,.2f} 元设备回购对价的有效凭证，"
        "且纳税申报发票时序发生于债务逾期之后。该行为系典型的虚假融资租赁，目的是协助被执行人转移财产、对抗人民法院生效判决的执行。"
    )
    lines.append("")
    lines.append("综上所述，依据《中华人民共和国民事诉讼法》第二百三十八条之规定，特诉请贵院查明事实，判决准予继续执行涉案设备！")
    lines.append("")
    lines.append("此致")
    lines.append("北京市第一中级人民法院")
    lines.append("")
    lines.append("起诉人：某大型金融投资发展控股集团有限公司")
    lines.append(f"日期：{datetime.now().strftime('%Y年%m月%d日')}")
    return "\n".join(lines)
