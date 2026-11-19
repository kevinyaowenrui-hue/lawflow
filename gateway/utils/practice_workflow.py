# -*- coding: utf-8 -*-
"""执业审查缺口：案由目录、管辖路径、并列请求、利冲闸门、结案闸门、今日期限。"""
from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Optional

DOCUMENT_PRESETS = (
    "民间借贷纠纷",
    "买卖合同纠纷",
    "劳动人事争议",
    "离婚纠纷",
    "通用民事纠纷",
)
PLACEHOLDER_CAUSES = {
    "",
    "请选择",
    "请选择文书类型",
    "请选择民事案由",
    "未选择案由",
    "案由待律师选择",
}
BLOCKING_CONFLICT = {"MANUAL_REVIEW", "WAIVABLE_WITH_CONSENT", "UNABLE_TO_CHECK", "PROHIBITED"}
PARTY_ROLES = ("共同原告", "共同被告", "第三人", "反诉原告", "反诉被告")
CLAIM_TRACKS = ("civil_court", "labor_arbitration", "commercial_arbitration", "enforcement", "non_litigation")
PROCEDURAL_DEADLINE_KINDS = {
    "appeal",
    "labor_award_sue",
    "labor_award_revoke",
    "arbitration_set_aside",
}
FILING_STATUSES = ("未准备", "已准备", "已线下提交", "补正中")

# 民事案件案由规定中的常用案由。不在目录里的可以手写，但不会自动套成民间借贷。
CAUSE_CATALOG: List[Dict[str, str]] = [
    {"group": "合同", "cause": "买卖合同纠纷", "document_preset": "买卖合同纠纷", "track": "civil_court"},
    {"group": "合同", "cause": "民间借贷纠纷", "document_preset": "民间借贷纠纷", "track": "civil_court"},
    {"group": "合同", "cause": "借款合同纠纷", "document_preset": "民间借贷纠纷", "track": "civil_court"},
    {"group": "合同", "cause": "金融借款合同纠纷", "document_preset": "通用民事纠纷", "track": "civil_court"},
    {"group": "合同", "cause": "保证合同纠纷", "document_preset": "通用民事纠纷", "track": "civil_court"},
    {"group": "合同", "cause": "抵押合同纠纷", "document_preset": "通用民事纠纷", "track": "civil_court"},
    {"group": "合同", "cause": "租赁合同纠纷", "document_preset": "通用民事纠纷", "track": "civil_court"},
    {"group": "合同", "cause": "房屋租赁合同纠纷", "document_preset": "通用民事纠纷", "track": "civil_court"},
    {"group": "合同", "cause": "建设工程施工合同纠纷", "document_preset": "通用民事纠纷", "track": "civil_court"},
    {"group": "合同", "cause": "承揽合同纠纷", "document_preset": "通用民事纠纷", "track": "civil_court"},
    {"group": "合同", "cause": "服务合同纠纷", "document_preset": "通用民事纠纷", "track": "civil_court"},
    {"group": "合同", "cause": "委托合同纠纷", "document_preset": "通用民事纠纷", "track": "civil_court"},
    {"group": "合同", "cause": "物业服务合同纠纷", "document_preset": "通用民事纠纷", "track": "civil_court"},
    {"group": "合同", "cause": "技术服务合同纠纷", "document_preset": "通用民事纠纷", "track": "civil_court"},
    {"group": "合同", "cause": "特许经营合同纠纷", "document_preset": "通用民事纠纷", "track": "civil_court"},
    {"group": "公司", "cause": "股权转让纠纷", "document_preset": "通用民事纠纷", "track": "civil_court"},
    {"group": "公司", "cause": "公司决议纠纷", "document_preset": "通用民事纠纷", "track": "civil_court"},
    {"group": "公司", "cause": "股东知情权纠纷", "document_preset": "通用民事纠纷", "track": "civil_court"},
    {"group": "公司", "cause": "损害公司利益责任纠纷", "document_preset": "通用民事纠纷", "track": "civil_court"},
    {"group": "劳动", "cause": "劳动争议", "document_preset": "劳动人事争议", "track": "labor_arbitration"},
    {"group": "劳动", "cause": "劳动合同纠纷", "document_preset": "劳动人事争议", "track": "labor_arbitration"},
    {"group": "劳动", "cause": "追索劳动报酬纠纷", "document_preset": "劳动人事争议", "track": "labor_arbitration"},
    {"group": "劳动", "cause": "经济补偿金纠纷", "document_preset": "劳动人事争议", "track": "labor_arbitration"},
    {"group": "劳动", "cause": "确认劳动关系纠纷", "document_preset": "劳动人事争议", "track": "labor_arbitration"},
    {"group": "劳动", "cause": "工伤保险待遇纠纷", "document_preset": "劳动人事争议", "track": "labor_arbitration"},
    {"group": "侵权", "cause": "侵权责任纠纷", "document_preset": "通用民事纠纷", "track": "civil_court"},
    {"group": "侵权", "cause": "名誉权纠纷", "document_preset": "通用民事纠纷", "track": "civil_court"},
    {"group": "侵权", "cause": "隐私权纠纷", "document_preset": "通用民事纠纷", "track": "civil_court"},
    {"group": "侵权", "cause": "姓名权纠纷", "document_preset": "通用民事纠纷", "track": "civil_court"},
    {"group": "侵权", "cause": "肖像权纠纷", "document_preset": "通用民事纠纷", "track": "civil_court"},
    {"group": "侵权", "cause": "财产损害赔偿纠纷", "document_preset": "通用民事纠纷", "track": "civil_court"},
    {"group": "侵权", "cause": "机动车交通事故责任纠纷", "document_preset": "通用民事纠纷", "track": "civil_court"},
    {"group": "侵权", "cause": "提供劳务者受害责任纠纷", "document_preset": "通用民事纠纷", "track": "civil_court"},
    {"group": "侵权", "cause": "产品责任纠纷", "document_preset": "通用民事纠纷", "track": "civil_court"},
    {"group": "婚姻家庭", "cause": "离婚纠纷", "document_preset": "离婚纠纷", "track": "civil_court"},
    {"group": "婚姻家庭", "cause": "继承纠纷", "document_preset": "通用民事纠纷", "track": "civil_court"},
    {"group": "其他民事", "cause": "通用民事纠纷", "document_preset": "通用民事纠纷", "track": "civil_court"},
]
_CATALOG_BY_CAUSE = {item["cause"]: item for item in CAUSE_CATALOG}

ARBITRATION_MATERIALS = (
    "仲裁申请书",
    "仲裁协议或仲裁条款",
    "身份证明",
    "授权委托书",
    "证据目录",
    "证据材料",
    "当地仲裁委额外材料",
)

LABOR_BURDEN_ITEMS = [
    "与争议事项有关、由用人单位掌握管理的证据，用人单位应当提供；不提供的承担不利后果。工资支付凭证、考勤记录、社保缴纳记录属于这一类。依据《劳动争议调解仲裁法》第六条。",
    "用人单位解除劳动合同的，解除理由、规章制度的民主程序和公示，由用人单位举证。不要按普通民事「谁主张谁举证」把解除合法性丢给劳动者。",
    "劳动者主张加班费的，先就加班事实举证；劳动者有证据证明用人单位掌握考勤等加班证据而用人单位不提供的，由用人单位承担不利后果。",
    "劳动关系存续期间拖欠劳动报酬的仲裁时效，不适用一年的一般规定。不要把这条请求算成民事诉讼三年。",
]
CIVIL_BURDEN_ITEMS = [
    "民事诉讼由主张事实的一方提供证据。对方不认可的事实，不能只因为对方没交证据就当成已经证明。",
    "这份质证按真实性、合法性、关联性写。不要把劳动争议里用人单位掌握证据的规则套到普通民事请求上。",
]


def _clean(value: Any) -> str:
    return str(value or "").strip()


def catalog_entry(cause: str) -> Optional[Dict[str, str]]:
    return _CATALOG_BY_CAUSE.get(_clean(cause))


def document_preset_for_cause(cause: str) -> Optional[str]:
    text = _clean(cause)
    if text in PLACEHOLDER_CAUSES or text.startswith("请选择"):
        return None
    entry = catalog_entry(text)
    if entry:
        return entry["document_preset"]
    if text in DOCUMENT_PRESETS:
        return text
    if "劳动" in text:
        return "劳动人事争议"
    if "借贷" in text or text.startswith("借款"):
        return "民间借贷纠纷"
    if "买卖" in text:
        return "买卖合同纠纷"
    if "离婚" in text:
        return "离婚纠纷"
    return None


def assert_generatable_cause(cause: str) -> str:
    text = _clean(cause)
    preset = document_preset_for_cause(text)
    if not preset:
        raise ValueError(
            "这份文书没有对应模板。请从案由目录选择，或明确选民间借贷、买卖合同、劳动人事争议、离婚、通用民事之一。"
            "不会按民间借贷生成。"
        )
    return preset


def seed_claim(cause: str, forum: str = "") -> Dict[str, Any]:
    entry = catalog_entry(cause)
    track = entry["track"] if entry else ("labor_arbitration" if "劳动" in cause else "civil_court")
    pleading = {
        "labor_arbitration": "劳动仲裁请求待律师按事实填写，不预选补偿月数。",
        "commercial_arbitration": "仲裁请求待律师按仲裁协议范围填写。",
        "civil_court": "诉讼请求待律师按本条请求填写，不预选利息或连带责任。",
    }.get(track, "请求事项待律师填写。")
    return {
        "id": f"claim-{uuid.uuid4().hex[:8]}",
        "cause": cause,
        "track": track,
        "forum": forum,
        "pleading": pleading,
        "document_preset": document_preset_for_cause(cause) or "",
    }


def normalize_claims(claims: Any, fallback_cause: str = "") -> List[Dict[str, Any]]:
    if claims is None:
        return []
    if not isinstance(claims, list) or not claims:
        raise ValueError("并列请求至少要有一条，每条写明案由、程序和受理机关。")
    normalized = []
    for index, raw in enumerate(claims, 1):
        if not isinstance(raw, dict):
            raise ValueError(f"第 {index} 条请求无法识别。")
        cause = _clean(raw.get("cause"))
        if not cause or cause in PLACEHOLDER_CAUSES:
            raise ValueError(f"第 {index} 条请求没有案由。不要留空后默认成民间借贷。")
        track = _clean(raw.get("track")) or (catalog_entry(cause) or {}).get("track") or "civil_court"
        if track not in CLAIM_TRACKS:
            raise ValueError("请求程序只接受法院、劳动仲裁、商事仲裁、执行或非诉。")
        preset = _clean(raw.get("document_preset")) or document_preset_for_cause(cause) or ""
        if preset and preset not in DOCUMENT_PRESETS:
            raise ValueError("文书模板只接受民间借贷、买卖合同、劳动人事争议、离婚或通用民事。")
        if not preset and not catalog_entry(cause) and "劳动" not in cause:
            raise ValueError(
                f"「{cause}」不在案由目录里。请改选目录中的案由，或同时指定文书模板。不会自动套用民间借贷。"
            )
        forum = _clean(raw.get("forum"))
        pleading = _clean(raw.get("pleading"))[:500]
        normalized.append({
            "id": _clean(raw.get("id")) or f"claim-{uuid.uuid4().hex[:8]}",
            "cause": cause,
            "track": track,
            "forum": forum,
            "pleading": pleading,
            "document_preset": preset or document_preset_for_cause(cause) or "",
        })
    if fallback_cause and all(item["cause"] != fallback_cause for item in normalized):
        pass
    return normalized


def normalize_extra_parties(parties: Any) -> List[Dict[str, str]]:
    if parties is None:
        return []
    if not isinstance(parties, list):
        raise ValueError("追加当事人必须逐条填写。")
    normalized = []
    for index, raw in enumerate(parties, 1):
        if not isinstance(raw, dict):
            raise ValueError(f"第 {index} 个追加当事人无法识别。")
        name = _clean(raw.get("name"))
        role = _clean(raw.get("role"))
        if not name:
            raise ValueError(f"第 {index} 个追加当事人没有姓名或名称。")
        if role not in PARTY_ROLES:
            raise ValueError("追加当事人地位只接受共同原告、共同被告、第三人、反诉原告或反诉被告。")
        normalized.append({
            "name": name[:80],
            "role": role,
            "id_no": _clean(raw.get("id_no"))[:40],
            "note": _clean(raw.get("note"))[:200],
        })
    return normalized


def normalize_local_filing_items(items: Any) -> List[Dict[str, str]]:
    if items is None:
        return []
    if not isinstance(items, list):
        raise ValueError("当地额外材料必须逐条登记。")
    normalized = []
    for index, raw in enumerate(items, 1):
        if not isinstance(raw, dict):
            raise ValueError(f"第 {index} 项额外材料无法识别。")
        label = _clean(raw.get("label"))
        if not label:
            raise ValueError(f"第 {index} 项额外材料没有名称。")
        status = _clean(raw.get("status")) or "未准备"
        if status not in FILING_STATUSES:
            raise ValueError("额外材料状态只能是未准备、已准备、已线下提交或补正中。系统不记录法院已经受理。")
        normalized.append({
            "label": label[:80],
            "status": status,
            "note": _clean(raw.get("note"))[:200],
        })
    return normalized


def default_arbitration_materials() -> List[Dict[str, str]]:
    return [{"label": label, "status": "未准备", "note": ""} for label in ARBITRATION_MATERIALS]


def normalize_conflict_conclusion(raw: Any) -> Dict[str, Any]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("利冲结论要写明是否可以代理，以及依据。")
    decision = _clean(raw.get("decision"))
    if decision and decision not in {"可以代理", "不代理"}:
        raise ValueError("利冲结论只接受可以代理或不代理。")
    return {
        "decision": decision,
        "text": _clean(raw.get("text"))[:500],
        "same_matter": _clean(raw.get("same_matter")) or "不确定",
        "written_consent": bool(raw.get("written_consent")),
    }


def drafting_block_reason(practice: Optional[Dict[str, Any]]) -> Optional[str]:
    data = practice or {}
    conflict = data.get("conflict") or {}
    level = _clean(conflict.get("conflict_level"))
    if level not in BLOCKING_CONFLICT:
        return None
    conclusion = data.get("conflict_conclusion") or {}
    decision = _clean(conclusion.get("decision"))
    text = _clean(conclusion.get("text"))
    if level == "PROHIBITED" or decision == "不代理":
        return "利益冲突结论是不能代理。确认改判之前，不能起草文书，也不能把材料标成已线下提交。"
    if level == "WAIVABLE_WITH_CONSENT":
        if decision != "可以代理" or not conclusion.get("written_consent") or not text:
            return "存在须各方书面同意才能代理的利益冲突。写明已取得书面同意之前，不能起草文书，也不能推进立案。"
    if level in {"MANUAL_REVIEW", "UNABLE_TO_CHECK"}:
        if decision != "可以代理" or not text:
            return "利冲还不能出接案结论。写明是否同一争议、核查了什么、是否可以代理之前，不能起草文书，也不能把材料标成已线下提交。"
    return None


def normalize_defendant_posture(raw: Any) -> Dict[str, Any]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("被告侧事项要分别填写管辖异议和反诉。")
    objection = raw.get("jurisdiction_objection") if isinstance(raw.get("jurisdiction_objection"), dict) else {}
    counter = raw.get("counterclaim") if isinstance(raw.get("counterclaim"), dict) else {}
    amount = counter.get("amount")
    if amount not in (None, ""):
        try:
            amount = round(float(amount), 2)
        except (TypeError, ValueError) as exc:
            raise ValueError("反诉金额必须是数字。") from exc
        if amount < 0:
            raise ValueError("反诉金额不能为负。")
    else:
        amount = None
    return {
        "jurisdiction_objection": {
            "prepared": bool(objection.get("prepared")),
            "basis": _clean(objection.get("basis"))[:300],
            "note": _clean(objection.get("note"))[:300],
        },
        "counterclaim": {
            "prepared": bool(counter.get("prepared")),
            "claims": _clean(counter.get("claims"))[:500],
            "amount": amount,
            "note": _clean(counter.get("note"))[:300],
        },
    }


def _has_any(text: str, words: tuple) -> bool:
    return any(word in text for word in words)


def _sale_court_track() -> Dict[str, Any]:
    return {
        "cause": "买卖合同纠纷",
        "track": "civil_court",
        "blocks_court": False,
        "reason": "买卖合同纠纷一般由被告住所地或合同履行地法院管辖。系统不替你选定哪一个。",
        "pleading": "请求支付货款。金额以核对后的数字为准。",
        "forum_options": ["被告住所地人民法院", "合同履行地人民法院"],
    }


def _loan_court_track() -> Dict[str, Any]:
    return {
        "cause": "民间借贷纠纷",
        "track": "civil_court",
        "blocks_court": False,
        "reason": "借贷请求由被告住所地或合同履行地法院管辖。先核对有没有仲裁条款。",
        "pleading": "请求返还借款。金额以核对后的数字为准。",
        "forum_options": ["被告住所地人民法院", "合同履行地人民法院"],
    }


def suggest_claim_tracks(text: str) -> List[Dict[str, Any]]:
    """从一段事实里拆出应并列处理的请求。拆不开时返回空列表，不猜测案由。"""
    facts = _clean(text)
    if not facts:
        return []
    tracks: List[Dict[str, Any]] = []
    labor = _has_any(facts, ("劳动合同", "用人单位", "劳动者", "经济补偿", "劳动报酬", "违法解除", "劳动仲裁", "工伤", "确认劳动关系"))
    sale = _has_any(facts, ("买卖", "货款", "购销"))
    loan = _has_any(facts, ("借款", "借贷", "出借"))
    tort = _has_any(facts, ("侵权", "名誉", "隐私", "交通事故"))
    arbitration_words = _has_any(facts, ("仲裁委员会", "仲裁条款", "提交仲裁", "申请仲裁", "仲裁协议"))
    court_words = "人民法院" in facts or "法院起诉" in facts or "向法院" in facts
    or_both = arbitration_words and court_words and _has_any(facts, ("也可以", "或向", "亦可", "或者向"))
    if labor:
        tracks.append({
            "cause": "劳动争议",
            "track": "labor_arbitration",
            "blocks_court": True,
            "reason": "劳动争议实行仲裁前置。这条请求先向劳动人事争议仲裁委员会申请，不能直接写进民事起诉状。",
            "pleading": "劳动仲裁请求与货款、侵权请求分开写。",
            "forum_options": ["劳动人事争议仲裁委员会"],
        })
    if arbitration_words and not labor:
        if or_both:
            tracks.append({
                "cause": "买卖合同纠纷" if sale else "合同纠纷",
                "track": "civil_court",
                "blocks_court": False,
                "reason": "条款同时写了仲裁和起诉，属于或裁或审，仲裁协议可能无效。不能直接排除法院，也不能直接出仲裁申请。",
                "pleading": "先判断仲裁协议是否有效，再决定起诉或仲裁。",
                "forum_options": ["待律师判断仲裁协议效力"],
            })
        else:
            tracks.append({
                "cause": "买卖合同纠纷" if sale else ("民间借贷纠纷" if loan else "合同纠纷"),
                "track": "commercial_arbitration",
                "blocks_court": True,
                "reason": "约定了仲裁机构或仲裁协议的，法院原则上不予受理。不要生成民事起诉状，也不要做微法院四分卷。",
                "pleading": "按仲裁协议范围写仲裁请求。",
                "forum_options": ["仲裁协议选定的仲裁机构"],
            })
    elif sale and not labor:
        tracks.append(_sale_court_track())
    elif loan and not labor:
        tracks.append(_loan_court_track())
    if labor and sale:
        tracks.append(_sale_court_track())
    if labor and loan:
        tracks.append(_loan_court_track())
    if tort:
        tracks.append({
            "cause": "名誉权纠纷" if "名誉" in facts else "侵权责任纠纷",
            "track": "civil_court",
            "blocks_court": False,
            "reason": "侵权请求可以由被告住所地或侵权行为地法院管辖，和合同履行地不是同一套规则。",
            "pleading": "侵权请求与合同货款、劳动补偿分开写。",
            "forum_options": ["被告住所地人民法院", "侵权行为地人民法院"],
        })
    if _has_any(facts, ("不动产", "房屋所有权", "港口作业")):
        tracks.append({
            "cause": "不动产纠纷" if "港口" not in facts else "港口作业纠纷",
            "track": "civil_court",
            "blocks_court": False,
            "exclusive": True,
            "reason": "不动产纠纷由不动产所在地法院专属管辖；港口作业纠纷由港口所在地法院专属管辖。不要改成被告住所地。",
            "pleading": "专属管辖的请求单独列明。",
            "forum_options": ["不动产所在地人民法院" if "港口" not in facts else "港口所在地人民法院"],
        })
    if _has_any(facts, ("继承遗产", "遗产继承")):
        tracks.append({
            "cause": "继承纠纷",
            "track": "civil_court",
            "blocks_court": False,
            "exclusive": True,
            "reason": "继承遗产纠纷由被继承人死亡时住所地或者主要遗产所在地法院专属管辖。",
            "pleading": "继承请求单独列明。",
            "forum_options": ["被继承人死亡时住所地人民法院", "主要遗产所在地人民法院"],
        })
    return tracks


def recommend_jurisdiction(facts: str, cause: str = "", procedure: str = "") -> Dict[str, Any]:
    text = " ".join(part for part in (_clean(cause), _clean(facts), _clean(procedure)) if part)
    tracks = suggest_claim_tracks(text)
    if procedure == "arbitration" and not any(item["track"] == "commercial_arbitration" for item in tracks):
        tracks.insert(0, {
            "cause": cause or "合同纠纷",
            "track": "commercial_arbitration",
            "blocks_court": True,
            "reason": "案件程序已经选了仲裁。不要再生成微法院起诉状。",
            "pleading": "按仲裁协议写申请事项。",
            "forum_options": ["仲裁协议选定的仲裁机构"],
        })
    if cause and not tracks:
        entry = catalog_entry(cause)
        if entry and entry["track"] == "labor_arbitration":
            tracks = suggest_claim_tracks("劳动争议 " + cause)
        elif entry:
            tracks = [{
                "cause": cause,
                "track": entry["track"],
                "blocks_court": False,
                "reason": "目录中的这条案由走法院。合同纠纷在被告住所地和合同履行地之间选择；侵权纠纷在被告住所地和侵权行为地之间选择。",
                "pleading": "诉讼请求按这条案由单独填写。",
                "forum_options": ["被告住所地人民法院", "合同履行地或侵权行为地人民法院"],
            }]
    return {
        "tracks": tracks,
        "must_split": len(tracks) > 1,
        "confirmed_forum": "",
        "override_reason": "",
        "note": "管辖结论要律师确认。系统只列出路径，不把机构名称写死。",
    }


def court_generation_block(practice: Optional[Dict[str, Any]], cause: str) -> Optional[str]:
    data = practice or {}
    jurisdiction = data.get("jurisdiction") or {}
    forum = _clean(jurisdiction.get("confirmed_forum"))
    if not forum:
        return "还没有确认受理机关。先判断劳动仲裁前置、仲裁条款、专属管辖，写明仲裁委员会或法院之后再生成文书。"
    preset = document_preset_for_cause(cause)
    tracks = jurisdiction.get("tracks") or []
    blocks_arbitration = [item for item in tracks if item.get("blocks_court") and item.get("track") == "commercial_arbitration"]
    if blocks_arbitration and preset != "劳动人事争议" and "仲裁" not in forum and not _clean(jurisdiction.get("override_reason")):
        return blocks_arbitration[0].get("reason") or "仲裁协议排除法院管辖。写明仲裁协议无效的理由之前，不能生成起诉状。"
    if preset == "劳动人事争议" and "仲裁" not in forum:
        return "劳动请求应送劳动人事争议仲裁委员会。现在确认的受理机关不是仲裁委员会。"
    if preset != "劳动人事争议" and any(item.get("track") == "labor_arbitration" for item in tracks) and "劳动" in (cause or ""):
        return "这条是劳动请求，不能按民事起诉状生成。"
    return None


def causes_allowed_for_matter(matter: Dict[str, Any]) -> List[str]:
    names = []
    cause = _clean(matter.get("cause_of_action"))
    if cause:
        names.append(cause)
    practice = matter.get("practice") or {}
    for item in practice.get("claims") or []:
        if isinstance(item, dict) and _clean(item.get("cause")):
            names.append(_clean(item["cause"]))
        preset = _clean(item.get("document_preset")) if isinstance(item, dict) else ""
        if preset:
            names.append(preset)
    if cause:
        preset = document_preset_for_cause(cause)
        if preset:
            names.append(preset)
    return names


def cause_matches_matter(cause: str, matter: Dict[str, Any]) -> bool:
    text = _clean(cause)
    allowed = causes_allowed_for_matter(matter)
    if not allowed:
        return True
    return any(text == name or text in name or name in text for name in allowed)


def _parse_day(value: str) -> date:
    return datetime.strptime(value[:10], "%Y-%m-%d").date()


def closeout_blockers(
    practice: Optional[Dict[str, Any]],
    deadlines: Optional[List[Dict[str, Any]]] = None,
    today: Optional[date] = None,
) -> List[str]:
    data = practice or {}
    closeout = data.get("closeout") or {}
    blockers: List[str] = []
    if not _clean(closeout.get("judgment_result")):
        blockers.append("未填写裁判或处理结果")
    if not closeout.get("appeal_window_cleared"):
        blockers.append("未确认上诉、起诉或申请撤销期限已经届满或已经处理")
    if not closeout.get("originals_returned"):
        blockers.append("未确认原件已经退还")
    outstanding = float(data.get("fee_outstanding") or 0)
    if outstanding > 0:
        if not closeout.get("fees_settled") or not _clean(closeout.get("fees_note")):
            blockers.append(f"律师费未收 {outstanding:.2f} 元。写明已经结清、减免或另案收取之后才能归档")
    elif not closeout.get("fees_settled"):
        blockers.append("未确认律师费已经结清或没有应收")
    closed_on = _clean(closeout.get("conflict_closed_on"))
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", closed_on):
        blockers.append("未填写利冲底档结案日")
    else:
        try:
            datetime.strptime(closed_on, "%Y-%m-%d")
        except ValueError:
            blockers.append("利冲底档结案日不是有效日期")
    open_items = open_procedural_deadlines(deadlines or [], today)
    if open_items and not closeout.get("appeal_window_cleared"):
        labels = "、".join(item["due_date"][:10] for item in open_items)
        blockers.append(f"还有未到期的上诉、起诉或撤销期限：{labels}")
    return blockers


def normalize_closeout(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("结案前要确认裁判结果、期限、原件、律师费和利冲结案日。")
    return {
        "judgment_result": _clean(raw.get("judgment_result"))[:500],
        "appeal_window_cleared": bool(raw.get("appeal_window_cleared")),
        "originals_returned": bool(raw.get("originals_returned")),
        "fees_settled": bool(raw.get("fees_settled")),
        "fees_note": _clean(raw.get("fees_note"))[:300],
        "conflict_closed_on": _clean(raw.get("conflict_closed_on")),
    }


def open_procedural_deadlines(deadlines: List[Dict[str, Any]], today: Optional[date] = None) -> List[Dict[str, Any]]:
    current = today or date.today()
    found = []
    for item in deadlines:
        if item.get("done"):
            continue
        if item.get("kind") not in PROCEDURAL_DEADLINE_KINDS:
            continue
        due = _clean(item.get("due_date"))
        if len(due) < 10:
            continue
        try:
            due_day = _parse_day(due)
        except ValueError:
            continue
        if due_day >= current:
            found.append(item)
    return found


def build_deadline_board(deadlines: List[Dict[str, Any]], today: Optional[date] = None) -> Dict[str, Any]:
    current = today or date.today()
    rows = []
    for item in deadlines:
        if item.get("done"):
            continue
        due = _clean(item.get("due_date"))
        if len(due) < 10:
            continue
        try:
            due_day = _parse_day(due)
        except ValueError:
            continue
        days_left = (due_day - current).days
        rows.append({
            "matter_id": item.get("matter_id") or "",
            "matter_title": item.get("matter_title") or "未命名案件",
            "kind": item.get("kind") or "custom",
            "due_date": due[:10],
            "days_left": days_left,
            "urgent": days_left <= 7,
            "source": item.get("source") or "",
            "note": item.get("note") or "",
            "origin_label": item.get("origin_label") or "",
        })
    rows.sort(key=lambda row: (not row["urgent"], row["days_left"], row["matter_title"]))
    groups: List[Dict[str, Any]] = []
    index: Dict[str, int] = {}
    for row in rows:
        key = row["matter_id"] or row["matter_title"]
        if key not in index:
            index[key] = len(groups)
            groups.append({
                "matter_id": row["matter_id"],
                "matter_title": row["matter_title"],
                "urgent": False,
                "items": [],
            })
        group = groups[index[key]]
        group["items"].append(row)
        if row["urgent"]:
            group["urgent"] = True
    groups.sort(key=lambda group: (not group["urgent"], min(item["days_left"] for item in group["items"])))
    return {
        "today": current.isoformat(),
        "urgent_count": sum(1 for row in rows if row["urgent"]),
        "total": len(rows),
        "groups": groups,
    }


def evidence_burden(track: str = "", cause: str = "") -> Dict[str, Any]:
    labor = track == "labor" or "劳动" in (cause or "")
    if labor:
        return {
            "mode": "labor_employer",
            "title": "劳动争议举证",
            "items": list(LABOR_BURDEN_ITEMS),
        }
    return {
        "mode": "civil_claimant",
        "title": "民事诉讼举证",
        "items": list(CIVIL_BURDEN_ITEMS),
    }
