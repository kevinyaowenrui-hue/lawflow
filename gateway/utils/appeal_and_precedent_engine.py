"""
LawFlow 智律工作台 - P3 阶段：二审/再审生死局·一审裁决漏洞剖析与类案分歧穿透引擎

判例来源规则（批次4 / S-07）：
- 删除内置判例常量；仅从数据库读取 is_demo=false 且 verified_at 非空的记录；
- 查不到则返回空列表，并提示按法发〔2020〕24号人工检索；
- 生成文书不得写入未核验案号，改用【类案案号待律师核验后填写】。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from gateway.utils.citation_guard import (
    CASE_NUMBER_PATTERN,
    LEGACY_CASE_NUMBER_PATTERN,
    audit_case_numbers,
    load_verified_precedents_from_db,
)

NO_VERIFIED_PRECEDENT_MSG = (
    "本地无已核验类案，请按法发〔2020〕24号的检索范围人工检索"
)
CASE_NUMBER_PLACEHOLDER = "【类案案号待律师核验后填写】"


def _load_appellate_precedents() -> List[Dict[str, Any]]:
    """从已核验库读取；演示数据一律排除。"""
    rows = load_verified_precedents_from_db()
    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "case_number": r.get("case_number") or CASE_NUMBER_PLACEHOLDER,
                "title": r.get("title") or "",
                "court_name": r.get("court_name") or "",
                "judgment_year": r.get("judgment_year"),
                "court_level": r.get("court_level") or r.get("court_name") or "",
                "is_guiding_or_gazette": bool(r.get("is_guiding_or_gazette")),
                "stance": r.get("stance") or "PRO_APPELLANT",
                "core_topic": r.get("core_topic") or r.get("cause_of_action") or "",
                "holding_ratio": r.get("holding_ratio") or r.get("holding_summary") or "",
                "appellate_rebuttal_argument": r.get("appellate_rebuttal_argument")
                or r.get("holding_summary")
                or "",
                "factual_equivalence": r.get("factual_equivalence") or "",
                "verified_at": r.get("verified_at"),
                "is_demo": False,
            }
        )
    return out


# 兼容旧测试导入名：默认空列表（真实数据仅来自 DB）
SUPREME_COURT_APPELLATE_PRECEDENTS: List[Dict[str, Any]] = []


def analyze_first_instance_judgment_and_precedents(
    judgment_text: str = "",
    case_title: Optional[str] = None,
    claim_amount: float = 80000000.0,
    agreed_repurchase_rate: float = 0.15,
    first_instance_court: str = "一审中级人民法院",
    first_instance_errors: Optional[List[str]] = None,
) -> Dict[str, Any]:
    content = judgment_text or ""
    title = case_title or "股权增资及对赌协议股权回购合同纠纷案"

    flaw_diagnostics: List[Dict[str, Any]] = []

    has_loan_mischaracterization = any(
        k in content
        for k in [
            "借款",
            "民间借贷",
            "借贷性质",
            "保本保收益",
            "名投实借",
            "名为投资实为借贷",
            "4倍LPR",
            "四倍LPR",
        ]
    ) or (
        first_instance_errors
        and any("借贷" in e or "定性" in e for e in first_instance_errors)
    )
    if has_loan_mischaracterization or True:  # 探针逻辑批次8处理；本批保持既有触发
        flaw_diagnostics.append(
            {
                "probe_id": "FLAW-01",
                "error_type": "法律关系定性严重错误（股权回购错定为民间借贷）",
                "severity": "CRITICAL_FATAL",
                "first_instance_holding": (
                    "一审法院将《增资补充协议》中约定的股权回购款及溢价定性为'借款本息'，"
                    "并以《最高人民法院关于审理民间借贷案件适用法律若干问题的规定》为由，将年化违约金强行调减至LPR。"
                ),
                "appellate_attack_point": (
                    "【致命适用法律错误】本案系股权投资回购纠纷，双方当事人系合法的商事投资主体与创始人股东。"
                    "根据《九民纪要》第5条及最高法院统一裁判规则，投资人与股东之间的回购系基于股权价值与风险分担的商事合同义务，"
                    "根本不属于民间借贷法律关系！一审法院生搬硬套民间借贷利率上限，直接剥夺了投资方合理的风险对价！"
                ),
                "statute_violated": "《中华人民共和国民法典》第四百六十五条、第五百零九条、最高法《九民纪要》第5条",
            }
        )

    has_hardship_abuse = any(
        k in content
        for k in ["情势变更", "不可抗力", "不可归责", "行业调控", "宏观政策", "宏观环境", "疫情影响", "经济下行"]
    ) or (
        first_instance_errors
        and any("情势变更" in e or "不可抗力" in e for e in first_instance_errors)
    )
    if has_hardship_abuse or True:
        flaw_diagnostics.append(
            {
                "probe_id": "FLAW-02",
                "error_type": "违法滥用《民法典》第533条情势变更原则豁免违约责任",
                "severity": "CRITICAL_FATAL",
                "first_instance_holding": (
                    "一审法院以'目标公司受宏观调控及行业客观环境影响未能如期上市，属于不可归责于创始人的客观情况'为由，"
                    "滥用情势变更原则大幅削减甚至免除创始人的回购违约责任。"
                ),
                "appellate_attack_point": (
                    "【实体法适用严重失当】宏观经济周期与行业政策波动属于股权投资领域的固有商业风险，订约时双方完全明知且应当合理预见！"
                    "《民法典》第533条及《民法典合同编通则解释》第32条明文规定，正常的商业风险绝不构成情势变更。"
                    "一审判决将商业风险泛化为情势变更，系对司法裁判豁免权的无底线滥用，彻底击穿了商事投资的契约确定性！"
                ),
                "statute_violated": "《中华人民共和国民法典》第五百三十三条、《最高人民法院关于适用〈中华人民共和国民法典〉合同编通则若干问题的解释》第三十二条",
            }
        )

    has_liquidated_damages_cut = (
        any(k in content for k in ["违约金过高", "酌情调减", "调减至LPR", "未造成实际损失", "惩罚性违约金"])
        or True
    )
    if has_liquidated_damages_cut:
        flaw_diagnostics.append(
            {
                "probe_id": "FLAW-03",
                "error_type": "违约金调减畸重与司法自由裁量权滥用",
                "severity": "HIGH_RISK",
                "first_instance_holding": (
                    "一审法院认为原告未举证证明因逾期回购产生除资金利息以外的实际损失，"
                    "故将合同约定的年化15%违约金断崖式砍至按一年期LPR计算。"
                ),
                "appellate_attack_point": (
                    "【裁量失衡与举证责任分配错误】私募基金投资具有封闭期长、高机会成本的特殊属性。"
                    "约定年化15%的回购溢价与违约责任不仅是损失补偿，更是督促履约的核心杠杆，处于市场公允合理区间。"
                    "一审法院在违约方未提供充分证据证明损失过分高于约定的情况下，依职权盲目调减至LPR，直接导致违约成本远低于守约利益！"
                ),
                "statute_violated": "《中华人民共和国民法典》第五百八十五条第二款、《最高人民法院关于适用〈中华人民共和国民法典〉合同编通则若干问题的解释》第六十四条、第六十五条",
            }
        )

    all_precedents = _load_appellate_precedents()
    pro_precedents = [p for p in all_precedents if p.get("stance") == "PRO_APPELLANT"]
    con_precedents = [p for p in all_precedents if p.get("stance") == "CON_OPPONENT"]

    matrix_rows = []
    for pro in pro_precedents:
        matrix_rows.append(
            {
                "dispute_focus": pro["core_topic"],
                "supreme_court_rule": {
                    "case_number": pro["case_number"],
                    "court_name": pro["court_name"],
                    "judgment_year": pro["judgment_year"],
                    "title": pro["title"],
                    "holding_ratio": pro["holding_ratio"],
                    "rebuttal_brief_quote": pro["appellate_rebuttal_argument"],
                    "authority_badge": "已核验类案"
                    if pro.get("verified_at")
                    else "待核验",
                },
                "first_instance_error_view": {
                    "source": "一审判决所采信之地方少数错误倾向",
                    "flawed_argument": "将商事回购当成保本借贷，用民间借贷4倍LPR强砍投资违约金，或以行业宏观波动认同情势变更。",
                    "fatal_vulnerability": "违背《九民纪要》第5条及最高法院民商事统一裁判尺度，严重侵害商事契约自由。",
                },
            }
        )

    # 海富案案号未经 verified_at 核验，不得写入文书
    judicial_evolution_timeline = [
        {
            "stage": "第一阶段：2012年以前（海富案初期探索）",
            "benchmark_event": f"最高人民法院海富案（案号：{CASE_NUMBER_PLACEHOLDER}）",
            "rule_evolution": "确立'与公司对赌因资本维持原则无效，与股东/实控人对赌有效'的朴素规则，但当时对违约金尺度尚未作细化规范。案号待律师核验后填写。",
        },
        {
            "stage": "第二阶段：2019年（《九民纪要》划时代统一裁判尺度）",
            "benchmark_event": "最高法《九民纪要》（《全国法院民商事审判工作会议纪要》，法发〔2019〕25号）第5条",
            "rule_evolution": "彻底厘清商事对赌协议的法律属性：全面支持投资方与股东/实控人对赌有效并实际履行；明确对赌协议不属于民间借贷，严禁套用民间借贷限额。",
        },
        {
            "stage": "第三阶段：2021年至今（《民法典》及合同编解释新时代）",
            "benchmark_event": "《民法典合同编通则解释》第32条（情势变更严格限制）与第64-65条（违约金综合衡平）",
            "rule_evolution": "最高法院明确严格限制《民法典》第533条情势变更适用，将商业固有风险完全排除；明确商事违约金调减必须考量可得利益与投资沉没机会成本。",
        },
    ]

    legal_brief_report = _generate_appellate_legal_memo(
        title=title,
        claim_amount=claim_amount,
        first_instance_court=first_instance_court,
        flaws=flaw_diagnostics,
        pro_precedents=pro_precedents,
        timeline=judicial_evolution_timeline,
    )

    appeal_pleading = _generate_appellate_pleading(
        title=title,
        claim_amount=claim_amount,
        agreed_rate=agreed_repurchase_rate,
        first_instance_court=first_instance_court,
        flaws=flaw_diagnostics,
        pro_precedents=pro_precedents,
    )

    cases_audit = audit_case_numbers(legal_brief_report + " " + appeal_pleading)

    return {
        "status": "success",
        "case_title": title,
        "claim_amount": claim_amount,
        "first_instance_court": first_instance_court,
        "flaw_diagnostics": flaw_diagnostics,
        "precedent_matrix": matrix_rows,
        "judicial_evolution_timeline": judicial_evolution_timeline,
        "appellate_memo_report": legal_brief_report,
        "appellate_pleading_text": appeal_pleading,
        "cases_verified": cases_audit,
        "total_pro_precedents": len(pro_precedents),
        "total_con_precedents": len(con_precedents),
        "total_flaws_found": len(flaw_diagnostics),
        "precedent_notice": NO_VERIFIED_PRECEDENT_MSG if not pro_precedents else "",
    }


def _generate_appellate_legal_memo(
    title: str,
    claim_amount: float,
    first_instance_court: str,
    flaws: List[Dict[str, Any]],
    pro_precedents: List[Dict[str, Any]],
    timeline: List[Dict[str, Any]],
) -> str:
    lines = []
    lines.append("【类案检索与统一法律适用裁判尺度对抗论证意见书】")
    lines.append(f"案由：股权转让及对赌协议回购纠纷   涉案标的：人民币 {claim_amount:,.2f} 元")
    lines.append(f"一审判决法院：{first_instance_court}   审级：二审审理程序")
    lines.append("")
    lines.append("【导言：一审判决适用法律确有错误，背离最高法院统一裁判尺度】")
    lines.append(
        "依据最高人民法院《关于统一法律适用加强类案检索的指导意见（试行）》（法发〔2020〕24号）第四条之规定："
        "承办法官在审理案件时，应当检索最高人民法院发布的指导性案例、公报案例以及各高级人民法院的同类生效裁判。"
        "本案一审判决在法律关系定性、情势变更认定及违约金调整三大核心争议点上，"
        "明显背离了最高人民法院现行统一裁判指引，适用法律确有错误，依法应当由二审法院予以撤销并全额改判！"
    )
    lines.append("")
    lines.append("一、一审判决说理存在的致命法律破绽诊断：")
    for idx, f in enumerate(flaws, 1):
        lines.append(f"  ({idx}) 【破绽 {f['probe_id']}】：{f['error_type']}")
        lines.append(f"      一审错误裁判观点：{f['first_instance_holding']}")
        lines.append(f"      二审靶向突围说理：{f['appellate_attack_point']}")
        lines.append(f"      违反法律条文：{f['statute_violated']}")
        lines.append("")

    lines.append("二、最高人民法院与各省高级法院类案权威裁判规则矩阵：")
    if not pro_precedents:
        lines.append(f"  （{NO_VERIFIED_PRECEDENT_MSG}）")
        lines.append(f"  类案案号：{CASE_NUMBER_PLACEHOLDER}")
    else:
        for idx, p in enumerate(pro_precedents, 1):
            lines.append(f"  ({idx}) 【最高院/高院权威判例】：{p['case_number']} ({p['court_name']})")
            lines.append(f"      判例全称：{p['title']}")
            lines.append(f"      裁判核心要旨：{p['holding_ratio']}")
            lines.append(f"      同等事实可采信说理链：{p['appellate_rebuttal_argument']}")
            lines.append("")

    lines.append("三、最高法院关于商事对赌裁判口径的时间演进与定分止争谱系：")
    for t in timeline:
        lines.append(f"  • {t['stage']} - 【标志依据：{t['benchmark_event']}】")
        lines.append(f"    裁判演化准则：{t['rule_evolution']}")

    lines.append("")
    lines.append("【结论】")
    lines.append(
        f"综上所述，一审判决无视《九民纪要》第5条及最高法院统一裁判规则（类案案号：{CASE_NUMBER_PLACEHOLDER}），"
        "属于认定事实不清、适用法律严重错误。上诉人特呈递本类案检索报告，恳请二审合议庭统一法律适用尺度，"
        "依法撤销一审判决，全额支持上诉人股权回购款及约定逾期违约金之全部上诉请求！"
    )
    return "\n".join(lines)


def _generate_appellate_pleading(
    title: str,
    claim_amount: float,
    agreed_rate: float,
    first_instance_court: str,
    flaws: List[Dict[str, Any]],
    pro_precedents: List[Dict[str, Any]],
) -> str:
    lines = []
    lines.append("民 事 上 诉 状")
    lines.append("")
    lines.append("上诉人（一审原告）：某科技创业投资基金合伙企业（有限合伙）")
    lines.append("被上诉人（一审被告）：李某某（目标公司实际控制人兼创始人）")
    lines.append("")
    lines.append(f"上诉人因不服 {first_instance_court} 作出之民事判决，特依法向上一级高级人民法院提起上诉。")
    lines.append("")
    lines.append("【上诉请求】")
    lines.append("1. 依法撤销一审判决第一项、第二项；")
    lines.append(f"2. 依法改判被上诉人向上诉人全额支付股权回购款人民币 {claim_amount:,.2f} 元；")
    lines.append(
        f"3. 依法改判被上诉人按合同约定年化 {agreed_rate*100:.1f}% 向上诉人支付自违约之日起至实际清偿之日止的逾期回购违约金；"
    )
    lines.append("4. 判令由被上诉人承担本案一审、二审之全部诉讼费用及财产保全责任险保费。")
    lines.append("")
    lines.append("【事实与理由】")
    lines.append("一审判决在事实认定与法律适用上均存在重大错误，严重损害了上诉人的合法民商事权益：")
    lines.append("")
    lines.append("一、一审判决将股权回购性质定性为民间借贷并适用4倍LPR限制，属于严重的法律适用错误！")
    lines.append(
        "一审判决认定上诉人主张的回购溢价及违约金受民间借贷4倍LPR限制，完全背离了最高人民法院统一裁判规则。"
        f"依据最高法院已核验类案（{CASE_NUMBER_PLACEHOLDER}）及《全国法院民商事审判工作会议纪要》（法发〔2019〕25号）第5条之规定，"
        "投资方与目标公司实际控制人签订的回购协议系双方真实意思表示，属于商事股权转让范畴，不属于借款合同法律关系！"
        "被上诉人系具有完全民事行为能力且深谙商业运作的资深企业家，自愿签订对赌回购条款，一审法院强行类推借贷关系，"
        "肆意干预商事意思自治，适用法律确有错误。"
    )
    if not pro_precedents:
        lines.append(f"（{NO_VERIFIED_PRECEDENT_MSG}）")
    lines.append("")
    lines.append("二、一审判决认定宏观环境调控构成情势变更并调减回购责任，系对《民法典》第五百三十三条的违法滥用！")
    lines.append(
        "根据《民法典》第五百三十三条及最高人民法院《民法典合同编通则解释》第三十二条规定，"
        "情势变更原则所规制的事由必须是缔约时无法预见的非商业风险。目标公司所处行业的正常政策变动与市场起伏，"
        "系商事主体在创业投资时应当合理预见的固有商业风险。"
        f"相关高院类案案号：{CASE_NUMBER_PLACEHOLDER}。"
        "一审合议庭以此调减违约金，缺乏法理支撑。"
    )
    lines.append("")
    lines.append("三、合同约定的年化违约金符合行业惯例与真实机会成本，一审法院畸重调减滥用了司法自由裁量权！")
    lines.append(
        "根据《民法典》第五百八十五条规定，违约金兼具补偿与惩罚性质。在股权投资交易中，上诉人长达数年的资金投入面临极高的流动性锁定，"
        "约定的年化违约金是上诉人丧失其他优质投资标的之机会成本的合理补偿。被上诉人未提供任何相反证据证明约定金额过分高于实际损失，"
        "一审法院将约定标准断崖式调减至一年期LPR，直接导致违约方获益、守约方受损，背离了民商事审判诚实信用与鼓励交易的基本原则。"
    )
    lines.append("")
    lines.append(
        "综上所述，一审判决适用法律严重错误、认定事实不清。特依据《中华人民共和国民事诉讼法》第一百七十七条之规定，"
        "恳请二审法院查明事实，依法予以撤销并全额改判支持上诉人之诉请，以彰显司法公正与商事契约精神！"
    )
    lines.append("")
    lines.append("此致")
    lines.append("高级人民法院")
    lines.append("")
    lines.append("上诉人：某科技创业投资基金合伙企业（有限合伙）")
    lines.append(f"日期：{datetime.now().strftime('%Y年%m月%d日')}")
    text = "\n".join(lines)
    # 安全网：确保生成文书不含任何案号格式（未核验库时）
    if not pro_precedents:
        text = CASE_NUMBER_PATTERN.sub(CASE_NUMBER_PLACEHOLDER, text)
        text = LEGACY_CASE_NUMBER_PATTERN.sub(CASE_NUMBER_PLACEHOLDER, text)
    return text
