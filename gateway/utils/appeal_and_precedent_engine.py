"""
LawFlow 智律工作台 - P3 阶段：二审/再审·一审判决漏洞剖析与类案检索引擎

批次8：
- 删除探针无条件恒真短路；缺关键词则不输出漏洞，记入 unrecognized；
- 默认金额/当事人不再写死；演示数据仅 use_demo=true 时加载；
- 类案检索说明按法发〔2020〕24号第4条层级；上诉状按民诉法第171-173条要素。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from gateway.utils.citation_guard import (
    CASE_NUMBER_PATTERN,
    LEGACY_CASE_NUMBER_PATTERN,
    audit_case_numbers,
    load_verified_precedents_from_db,
)
from gateway.utils.text_utils import normalize_court_name

NO_VERIFIED_PRECEDENT_MSG = (
    "本地无已核验类案，请按法发〔2020〕24号的检索范围人工检索"
)
CASE_NUMBER_PLACEHOLDER = "【类案案号待律师核验后填写】"
PLACEHOLDER = "【待填写】"
DEMO_NOTICE = "演示数据·非真实案例"

RETRIEVAL_HIERARCHY = [
    "指导性案例",
    "最高人民法院发布的典型案例及裁判生效的案件",
    "本省（自治区、直辖市）高级人民法院发布的参考性案例及裁判生效的案件",
    "上一级人民法院及本院裁判生效的案件",
]


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_appeal_demo() -> Dict[str, Any]:
    path = _project_root() / "data" / "demo" / "appeal_demo.json"
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    data["is_demo"] = True
    return data


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
                "stance": r.get("stance") or "UNSTATED",
                "core_topic": r.get("core_topic") or r.get("cause_of_action") or "",
                "holding_ratio": r.get("holding_ratio") or r.get("holding_summary") or "",
                "appellate_rebuttal_argument": r.get("appellate_rebuttal_argument")
                or r.get("holding_summary")
                or "",
                "factual_equivalence": r.get("factual_equivalence") or "",
                "verified_at": r.get("verified_at"),
                "is_demo": False,
                "retrieval_tier": _infer_retrieval_tier(r),
            }
        )
    out.sort(key=lambda p: p.get("retrieval_tier", 99))
    return out


def _infer_retrieval_tier(row: Dict[str, Any]) -> int:
    if row.get("is_guiding_or_gazette"):
        return 0
    court = (row.get("court_name") or "") + (row.get("court_level") or "")
    if "最高人民" in court:
        return 1
    if "高级人民" in court:
        return 2
    return 3


# 兼容旧测试导入名：默认空列表（真实数据仅来自 DB）
SUPREME_COURT_APPELLATE_PRECEDENTS: List[Dict[str, Any]] = []


def _party_line(role: str, party: Optional[Union[Dict[str, Any], Any]]) -> str:
    if party is None:
        return f"{role}：{PLACEHOLDER}"
    if hasattr(party, "model_dump"):
        party = party.model_dump()
    if not isinstance(party, dict):
        return f"{role}：{PLACEHOLDER}"
    name = party.get("name") or PLACEHOLDER
    bits = [f"{role}：{name}"]
    if party.get("party_type") == "legal" or party.get("legal_rep"):
        if party.get("legal_rep"):
            bits.append(f"法定代表人：{party.get('legal_rep')}")
        if party.get("rep_position"):
            bits.append(f"职务：{party.get('rep_position')}")
    else:
        if party.get("gender"):
            bits.append(f"性别：{party.get('gender')}")
        if party.get("birth"):
            bits.append(f"出生日期：{party.get('birth')}")
        if party.get("ethnicity"):
            bits.append(f"民族：{party.get('ethnicity')}")
    pid = party.get("id_card_or_uscc") or party.get("id_number") or ""
    if pid:
        bits.append(f"证件号码：{pid}")
    else:
        bits.append(f"证件号码：{PLACEHOLDER}")
    addr = party.get("address") or PLACEHOLDER
    bits.append(f"住所地：{addr}")
    if party.get("phone"):
        bits.append(f"联系电话：{party.get('phone')}")
    return "，".join(bits)


def _fmt_amount(amount: Optional[float]) -> str:
    if amount is None:
        return PLACEHOLDER
    return f"{amount:,.2f}"


def analyze_first_instance_judgment_and_precedents(
    judgment_text: str = "",
    case_title: Optional[str] = None,
    claim_amount: Optional[float] = None,
    agreed_repurchase_rate: Optional[float] = None,
    first_instance_court: Optional[str] = None,
    first_instance_errors: Optional[List[str]] = None,
    use_demo: bool = False,
    appellant: Optional[Any] = None,
    appellee: Optional[Any] = None,
    first_instance_case_no: Optional[str] = None,
    cause_of_action: Optional[str] = None,
    appellate_court: Optional[str] = None,
    judgment_type: Optional[str] = None,
    service_date: Optional[str] = None,
    include_preservation_insurance: bool = False,
    appeal_deadline: Optional[str] = None,
) -> Dict[str, Any]:
    demo_notice = ""
    is_demo = False
    if use_demo:
        demo = _load_appeal_demo()
        is_demo = True
        demo_notice = DEMO_NOTICE
        judgment_text = judgment_text or demo.get("judgment_text") or ""
        case_title = case_title or demo.get("case_title")
        if claim_amount is None:
            claim_amount = demo.get("claim_amount")
        if agreed_repurchase_rate is None:
            agreed_repurchase_rate = demo.get("agreed_repurchase_rate")
        first_instance_court = first_instance_court or demo.get("first_instance_court")
        first_instance_errors = first_instance_errors or demo.get("first_instance_errors")
        appellant = appellant or demo.get("appellant")
        appellee = appellee or demo.get("appellee")
        first_instance_case_no = first_instance_case_no or demo.get("first_instance_case_no")
        cause_of_action = cause_of_action or demo.get("cause_of_action")
        judgment_type = judgment_type or demo.get("judgment_type")

    content = judgment_text or ""
    title = case_title or PLACEHOLDER
    court = first_instance_court or PLACEHOLDER

    flaw_diagnostics: List[Dict[str, Any]] = []
    unrecognized: List[str] = []

    investment_words = ("对赌", "股权回购", "增资", "回购", "保本保收益", "名为投资")
    loan_words = ("借贷", "借款", "民间借贷", "4倍LPR", "四倍LPR")
    has_loan_mischaracterization = any(
        k in content for k in ("保本保收益", "名投实借", "名为投资实为借贷")
    ) or (
        any(k in content for k in investment_words) and any(k in content for k in loan_words)
    ) or (
        first_instance_errors
        and any("借贷" in e or "定性" in e for e in first_instance_errors)
    )
    if has_loan_mischaracterization:
        flaw_diagnostics.append(
            {
                "probe_id": "FLAW-01",
                "error_type": "法律关系定性争议（股权回购被认定为民间借贷）",
                "severity": "CRITICAL_FATAL",
                "first_instance_holding": (
                    "一审裁判将投资回购款及溢价定性为借款本息，并援引民间借贷利率限制予以调减。"
                ),
                "appellate_attack_point": (
                    "本案争议焦点在于法律关系定性。若当事人真实意思为股权投资回购，"
                    "则不宜简单适用民间借贷利率上限。"
                    "《九民纪要》（法发〔2019〕25号）第五条：与目标公司订立对赌协议，没有法定无效事由的，"
                    "目标公司不能仅因约定了股权回购或者金钱补偿就主张协议无效。"
                    "投资方请求目标公司回购股权，目标公司未完成减资程序的，人民法院应当驳回；"
                    "请求金钱补偿的，公司没有利润或者利润不足的，驳回或者部分支持，以后有利润可以另行起诉。"
                    "纪要写的是当时《公司法》第三十五条、第一百四十二条、第一百六十六条。"
                    "现行《公司法》（2024年修订）中，不得抽逃出资见第五十三条，"
                    "股份有限公司不得收购本公司股份见第一百六十二条，弥补亏损并提取公积金后分配利润见第二百一十条。"
                    "有限责任公司减资回购不能只套第一百六十二条。"
                ),
                "statute_violated": "《九民纪要》（法发〔2019〕25号）第五条；《公司法》（2024年修订）第五十三条、第一百六十二条、第二百一十条",
            }
        )
    else:
        unrecognized.append("FLAW-01 未识别")

    has_hardship_abuse = any(
        k in content
        for k in ["情势变更", "不可抗力", "不可归责", "行业调控", "宏观政策", "宏观环境", "疫情影响", "经济下行"]
    ) or (
        first_instance_errors
        and any("情势变更" in e or "不可抗力" in e for e in first_instance_errors)
    )
    if has_hardship_abuse:
        flaw_diagnostics.append(
            {
                "probe_id": "FLAW-02",
                "error_type": "情势变更原则适用争议",
                "severity": "CRITICAL_FATAL",
                "first_instance_holding": (
                    "一审以宏观环境或行业客观变化为由，适用情势变更削减或免除违约责任。"
                ),
                "appellate_attack_point": (
                    "合同成立后，基础条件发生了订立时无法预见、不属于商业风险的重大变化，"
                    "继续履行对一方明显不公平的，才可以请求变更或者解除合同（《民法典》第五百三十三条）。"
                    "政策调整或者市场供求异常导致的价格涨跌，可以构成这种重大变化；"
                    "市场属性活跃、价格波动较大的大宗商品以及股票、期货等风险投资型金融产品除外"
                    "（《民法典合同编通则解释》第三十二条）。"
                    "股权投资的一般市场波动，通常属于商业风险，不能直接写成情势变更。"
                ),
                "statute_violated": "《中华人民共和国民法典》第五百三十三条",
            }
        )
    else:
        unrecognized.append("FLAW-02 未识别")

    trigger_ld = any(
        k in content
        for k in ["违约金过高", "酌情调减", "调减至LPR", "未造成实际损失", "惩罚性违约金", "酌减"]
    ) or (
        "违约金" in content and ("LPR" in content or "调减" in content or "酌" in content)
    ) or (
        first_instance_errors
        and any("违约金" in e or "调减" in e for e in first_instance_errors)
    )
    if trigger_ld:
        flaw_diagnostics.append(
            {
                "probe_id": "FLAW-03",
                "error_type": "违约金调减幅度与举证责任分配争议",
                "severity": "HIGH_RISK",
                "first_instance_holding": (
                    "一审以守约方未充分证明实际损失为由，对约定违约金予以较大幅度调减。"
                ),
                "appellate_attack_point": (
                    "依《民法典》第五百八十五条第二款，违约金调减应综合约定目的、履行情况、过错与损失等因素。"
                    + (
                        "股权投资的封闭期和机会成本可以作为损失的说明，不能用一年期贷款市场报价利率直接替换约定标准。"
                        if any(k in content for k in ("股权", "对赌", "回购", "增资", "私募", "保本保收益"))
                        else "本案文本没有写股权投资或对赌。不要把投资封闭期直接写成损失，也不要用一年期贷款市场报价利率直接替换约定标准。损失的百分之三十是过分高于的门槛，不是减完以后的金额。"
                    )
                ),
                "statute_violated": "《中华人民共和国民法典》第五百八十五条第二款",
            }
        )
    else:
        unrecognized.append("FLAW-03 未识别")

    all_precedents = _load_appellate_precedents()
    pro_precedents = [p for p in all_precedents if p.get("stance") == "PRO_APPELLANT"]
    con_precedents = [p for p in all_precedents if p.get("stance") == "CON_OPPONENT"]

    matrix_rows = []
    for pro in pro_precedents:
        matrix_rows.append(
            {
                "dispute_focus": pro["core_topic"],
                "retrieval_tier": RETRIEVAL_HIERARCHY[min(pro.get("retrieval_tier", 3), 3)],
                "supreme_court_rule": {
                    "case_number": pro["case_number"],
                    "court_name": pro["court_name"],
                    "judgment_year": pro["judgment_year"],
                    "title": pro["title"],
                    "holding_ratio": pro["holding_ratio"],
                    "rebuttal_brief_quote": pro["appellate_rebuttal_argument"],
                    "authority_badge": "已核验类案" if pro.get("verified_at") else "待核验",
                },
                "first_instance_error_view": {
                    "source": "一审判决相关认定",
                    "flawed_argument": "需对照用户提供的一审理由逐项比对。",
                    "fatal_vulnerability": "对照本案已经识别的争议评估。没有对赌或名为投资实为借贷的表述时，不要套用对赌口径。",
                },
            }
        )

    has_vam_flaw = any(f.get("probe_id") == "FLAW-01" for f in flaw_diagnostics)
    vam_timeline = [
        {
            "stage": "第一阶段：2012年以前（海富案初期探索）",
            "benchmark_event": f"最高人民法院海富案（案号：{CASE_NUMBER_PLACEHOLDER}）",
            "rule_evolution": "确立与公司对赌、与股东对赌效力区分的早期探索规则；案号待律师核验后填写。",
        },
        {
            "stage": "第二阶段：2019年（《九民纪要》统一裁判尺度）",
            "benchmark_event": "最高法《九民纪要》（《全国法院民商事审判工作会议纪要》，法发〔2019〕25号）第5条",
            "rule_evolution": (
                "《九民纪要》（法发〔2019〕25号）第五条：与目标公司对赌，没有法定无效事由的，"
                "不能仅因约定股权回购或金钱补偿就认定无效。"
                "请求回购的，目标公司未完成减资程序的，驳回诉讼请求；"
                "请求金钱补偿的，没有利润或利润不足的，驳回或部分支持。"
                "纪要所引《公司法》第三十五条、第一百四十二条、第一百六十六条是当时的条号。"
                "现行公司法（2024年修订）不得抽逃出资见第五十三条，"
                "股份有限公司回购限制见第一百六十二条，利润分配见第二百一十条。"
            ),
        },
    ]
    general_timeline = [
        {
            "stage": "《民法典》施行后的情势变更与违约金",
            "benchmark_event": "《民法典》第五百三十三条、第五百八十五条；合同编通则解释第三十二条、第六十五条",
            "rule_evolution": (
                "情势变更见《民法典》第五百三十三条：基础条件发生订立时无法预见、不属于商业风险的重大变化，"
                "继续履行明显不公平的，可以请求变更或解除。"
                "价格异常涨跌是否构成重大变化，见《民法典合同编通则解释》第三十二条；"
                "股票、期货等风险投资型金融产品除外。"
                "违约金是否过分高于损失，见合同编通则解释第六十五条，损失的百分之三十是调整门槛，不是减完以后的金额。"
            ),
        },
    ]
    if has_vam_flaw:
        judicial_evolution_timeline = vam_timeline + general_timeline
    elif flaw_diagnostics:
        judicial_evolution_timeline = general_timeline
    else:
        judicial_evolution_timeline = [
            {
                "stage": "本案没有识别对赌、情势变更或违约金调减",
                "benchmark_event": "不附对赌口径",
                "rule_evolution": "判决文本没有出现对赌、名为投资实为借贷、情势变更或违约金调减。不附对赌纪要口径，也不附该案早期对赌探索口径。",
            }
        ]

    legal_brief_report = _generate_appellate_legal_memo(
        title=title,
        claim_amount=claim_amount,
        first_instance_court=court,
        flaws=flaw_diagnostics,
        pro_precedents=pro_precedents,
        timeline=judicial_evolution_timeline,
    )

    appeal_pleading = _generate_appellate_pleading(
        title=title,
        claim_amount=claim_amount,
        agreed_rate=agreed_repurchase_rate,
        first_instance_court=court,
        flaws=flaw_diagnostics,
        pro_precedents=pro_precedents,
        appellant=appellant,
        appellee=appellee,
        first_instance_case_no=first_instance_case_no,
        cause_of_action=cause_of_action,
        appellate_court=appellate_court,
        include_preservation_insurance=include_preservation_insurance,
        appeal_deadline=appeal_deadline,
        judgment_type=judgment_type,
        service_date=service_date,
    )

    cases_audit = audit_case_numbers(legal_brief_report + " " + appeal_pleading)

    out: Dict[str, Any] = {
        "status": "success",
        "case_title": title,
        "claim_amount": claim_amount,
        "first_instance_court": court,
        "flaw_diagnostics": flaw_diagnostics,
        "unrecognized": unrecognized,
        "precedent_matrix": matrix_rows,
        "judicial_evolution_timeline": judicial_evolution_timeline,
        "appellate_memo_report": legal_brief_report,
        "appellate_pleading_text": appeal_pleading,
        "cases_verified": cases_audit,
        "total_pro_precedents": len(pro_precedents),
        "total_con_precedents": len(con_precedents),
        "total_flaws_found": len(flaw_diagnostics),
        "precedent_notice": NO_VERIFIED_PRECEDENT_MSG if not pro_precedents else "",
        "retrieval_hierarchy": RETRIEVAL_HIERARCHY,
    }
    if is_demo:
        out["is_demo"] = True
        out["demo_notice"] = demo_notice
    return out


def _generate_appellate_legal_memo(
    title: str,
    claim_amount: Optional[float],
    first_instance_court: str,
    flaws: List[Dict[str, Any]],
    pro_precedents: List[Dict[str, Any]],
    timeline: List[Dict[str, Any]],
) -> str:
    lines = []
    lines.append("【类案检索与统一法律适用裁判尺度对抗论证意见书】")
    lines.append(f"案由：{title}   涉案标的：人民币 {_fmt_amount(claim_amount)} 元")
    lines.append(f"一审判决法院：{first_instance_court}   审级：二审审理程序")
    lines.append("")
    lines.append("【导言】")
    lines.append(
        "依据最高人民法院《关于统一法律适用加强类案检索的指导意见（试行）》（法发〔2020〕24号）第四条，"
        "检索范围依次为："
    )
    for i, name in enumerate(RETRIEVAL_HIERARCHY, 1):
        lines.append(f"  ({i}) {name}")
    lines.append(
        "另需检索人民法院案例库（rmfyalk.court.gov.cn）。"
        "入库案例供办案参考，不能替代法发〔2020〕24号列出的检索范围。"
    )
    lines.append(
        (
            "本案判决文本出现对赌或名为投资实为借贷的表述，可以对照《九民纪要》第五条，但不能把纪要写成判决。"
            if any(f.get("probe_id") == "FLAW-01" for f in flaws)
            else "本案没有识别对赌争议。不要把对赌纪要第五条写进代理意见。"
        )
    )
    lines.append("")
    lines.append("一、一审判决说理诊断：")
    if not flaws:
        lines.append("  （根据现有判决文本，未识别出预设探针对应的漏洞；请补充判决书关键说理段落。）")
    for idx, f in enumerate(flaws, 1):
        lines.append(f"  ({idx}) 【破绽 {f['probe_id']}】：{f['error_type']}")
        lines.append(f"      一审裁判观点：{f['first_instance_holding']}")
        lines.append(f"      二审攻防要点：{f['appellate_attack_point']}")
        lines.append(f"      相关法律依据：{f['statute_violated']}")
        lines.append("")

    lines.append("二、类案权威裁判规则（按检索层级排序）：")
    if not pro_precedents:
        lines.append(f"  （{NO_VERIFIED_PRECEDENT_MSG}）")
        lines.append(f"  类案案号：{CASE_NUMBER_PLACEHOLDER}")
    else:
        for idx, p in enumerate(pro_precedents, 1):
            tier_name = RETRIEVAL_HIERARCHY[min(p.get("retrieval_tier", 3), 3)]
            lines.append(f"  ({idx}) 【{tier_name}】：{p['case_number']} ({p['court_name']})")
            lines.append(f"      判例全称：{p['title']}")
            lines.append(f"      裁判核心要旨：{p['holding_ratio']}")
            lines.append(f"      可采信说理：{p['appellate_rebuttal_argument']}")
            lines.append("")

    lines.append("三、相关裁判口径演进：")
    for t in timeline:
        lines.append(f"  • {t['stage']} - 【标志依据：{t['benchmark_event']}】")
        lines.append(f"    说明：{t['rule_evolution']}")

    lines.append("")
    lines.append("【结论】")
    if any(f.get("probe_id") == "FLAW-01" for f in flaws):
        lines.append(
            f"综上所述，本案出现对赌或名为投资实为借贷的表述，可以对照《九民纪要》第五条和类案检索结果（类案案号：{CASE_NUMBER_PLACEHOLDER}）审查。"
            "纪要不是判决。"
        )
    else:
        lines.append(
            f"综上所述，请只根据本案已经识别的争议和类案检索结果（类案案号：{CASE_NUMBER_PLACEHOLDER}）审查。"
            "本案没有识别对赌争议，不要套用对赌纪要第五条。"
        )
    return "\n".join(lines)


def _generate_appellate_pleading(
    title: str,
    claim_amount: Optional[float],
    agreed_rate: Optional[float],
    first_instance_court: str,
    flaws: List[Dict[str, Any]],
    pro_precedents: List[Dict[str, Any]],
    appellant: Optional[Any] = None,
    appellee: Optional[Any] = None,
    first_instance_case_no: Optional[str] = None,
    cause_of_action: Optional[str] = None,
    appellate_court: Optional[str] = None,
    include_preservation_insurance: bool = False,
    appeal_deadline: Optional[str] = None,
    judgment_type: Optional[str] = None,
    service_date: Optional[str] = None,
) -> str:
    case_no = first_instance_case_no or PLACEHOLDER
    cause = cause_of_action or PLACEHOLDER
    if appellate_court:
        dest_court = normalize_court_name(appellate_court)
    else:
        dest_court = "【待填写：原审人民法院的上一级人民法院】"

    rate_str = f"{agreed_rate * 100:.1f}%" if agreed_rate is not None else PLACEHOLDER

    lines = []
    lines.append("民 事 上 诉 状")
    lines.append("")
    lines.append(_party_line("上诉人", appellant))
    lines.append(_party_line("被上诉人", appellee))
    lines.append("一审地位未填写。上诉人可能是一审原告，也可能是一审被告。诉请方向不要按当事人称谓猜测。")
    lines.append("")
    lines.append(f"原审人民法院：{first_instance_court}")
    lines.append(f"原审案号：{case_no}")
    lines.append(f"案由：{cause}")
    if service_date:
        lines.append(f"一审裁判送达日期：{service_date}")
    if judgment_type:
        jt = "判决" if judgment_type == "judgment" else "裁定" if judgment_type == "ruling" else judgment_type
        lines.append(f"裁判种类：{jt}")
    if appeal_deadline:
        lines.append(f"上诉期截止日（测算）：{appeal_deadline}")
    lines.append("")
    lines.append(
        f"上诉人因不服 {first_instance_court} 作出之民事裁判（案号：{case_no}），"
        f"特依法提起上诉。上诉状应当通过原审人民法院提出（《民事诉讼法》第一百七十三条）。"
    )
    lines.append("")
    lines.append("【上诉请求】")
    lines.append("1. 撤销一审裁判中上诉人不服的判项；")
    if claim_amount is not None:
        amount_note = f"用户录入的争议金额为人民币 {_fmt_amount(claim_amount)} 元。"
    else:
        amount_note = "争议金额未填写。"
    lines.append(
        f"2. 依法改判。{amount_note}本页不写谁向谁付款。付款方向按上诉人在一审的地位改写。"
    )
    if agreed_rate is not None:
        lines.append(
            f"3. 逾期利息或违约金是否按约定年化 {rate_str} 纳入改判，取决于上诉人在一审是主张债权还是提出抗辩。"
            "本页不写成被上诉人应当支付该利率。"
        )
    claim_idx = 4 if agreed_rate is not None else 3
    fee_line = f"{claim_idx}. 一审、二审诉讼费用由人民法院依法确定"
    if include_preservation_insurance:
        fee_line += "。财产保全责任险保费仅在合同有约定或法律有规定时列入，无约定时一般不支持"
    fee_line += "。"
    lines.append(fee_line)
    lines.append("")
    lines.append("【事实与理由】")
    if not flaws:
        lines.append("（根据现有材料，上诉理由【待填写】；请结合一审判决书补充。）")
    else:
        lines.append("一审判决在事实认定与法律适用上存在以下争议，上诉人请求二审予以审查：")
        lines.append("")
        for idx, f in enumerate(flaws, 1):
            lines.append(f"{idx}、{f['error_type']}")
            lines.append(f["appellate_attack_point"])
            lines.append("")
        if not pro_precedents:
            lines.append(f"（{NO_VERIFIED_PRECEDENT_MSG}；类案案号：{CASE_NUMBER_PLACEHOLDER}）")
    lines.append("")
    lines.append(
        "综上所述，特依据《中华人民共和国民事诉讼法》相关规定，恳请二审法院查明事实，依法裁判。"
    )
    lines.append("")
    lines.append("此致")
    lines.append(dest_court)
    lines.append("")
    app_name = PLACEHOLDER
    if isinstance(appellant, dict) and appellant.get("name"):
        app_name = appellant["name"]
    elif hasattr(appellant, "name") and getattr(appellant, "name", None):
        app_name = appellant.name
    lines.append(f"上诉人：{app_name}")
    lines.append(f"日期：{datetime.now().strftime('%Y年%m月%d日')}")
    text = "\n".join(lines)
    if not pro_precedents:
        # 仅清洗类案叙述中的未核验案号；保留用户提供的原审案号
        protected: List[str] = []
        if first_instance_case_no:
            protected.append(first_instance_case_no)
        tmp = text
        for i, p in enumerate(protected):
            tmp = tmp.replace(p, f"__PROTECTED_CASE_{i}__")
        tmp = CASE_NUMBER_PATTERN.sub(CASE_NUMBER_PLACEHOLDER, tmp)
        tmp = LEGACY_CASE_NUMBER_PATTERN.sub(CASE_NUMBER_PLACEHOLDER, tmp)
        for i, p in enumerate(protected):
            tmp = tmp.replace(f"__PROTECTED_CASE_{i}__", p)
        text = tmp
    return text
