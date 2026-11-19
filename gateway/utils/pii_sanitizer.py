"""
LawFlow 智律工作台 - 本地 PII 隐私脱敏与还原网关 (Bi-directional PII Sanitization Gateway)
功能：
1. 在向外部或云端大模型发送请求前，在本地将当事人敏感信息（身份证号、手机号、银行卡号、邮箱、统一信用代码、当事人姓名与企业名）转换为安全占位符；
2. 大模型返回推理结果后，在本地通过双向映射字典无损还原真实实体；
3. 保障诉讼核心机密（涉及《个人信息保护法》与律师执业保密义务）零云端泄露。
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Dict, List, Optional, Tuple


class PIISanitizer:
    """本地双向敏感信息脱敏与还原器"""

    # 18位二代身份证（支持带X）及15位一代身份证
    ID_CARD_PATTERN = re.compile(
        r"(?<!\d)(?:[1-9]\d{5}(?:18|19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]|[1-9]\d{7}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3})(?!\d)"
    )

    # 11位中国大陆手机号（13-19开头）
    PHONE_PATTERN = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")

    # 16-19位银行卡/结算账户
    BANK_CARD_PATTERN = re.compile(r"(?<!\d)(?:62|60|51|52|53|54|55|40|41|42|43|44|45|49|95)\d{14,17}(?!\d)")

    # 电子邮箱
    EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")

    # 18位统一社会信用代码
    USCC_PATTERN = re.compile(r"(?<![A-Za-z0-9])[1-9ANY][1-9]\d{6}[0-9A-HJ-NPQRTUWXY]{10}(?![A-Za-z0-9])")

    # 高置信中文地址：省/市/区可选 + 路/街等 + 可选门牌
    ADDRESS_PATTERN = re.compile(
        r"(?:"
        r"(?:[\u4e00-\u9fff]{2,}(?:省|自治区|特别行政区))?"
        r"(?:[\u4e00-\u9fff]{1,12}(?:市|州|地区|盟))?"
        r"(?:[\u4e00-\u9fff]{1,12}(?:区|县|旗|市))?"
        r"(?:[\u4e00-\u9fff]{1,20}(?:乡|镇|街道|办事处))?"
        r"[\u4e00-\u9fff0-9]{1,24}(?:路|街|道|巷|弄|大街|大道)"
        r"(?:\d+号(?:之\d+)?)?"
        r"(?:[\u4e00-\u9fff\d]{0,12}(?:栋|幢|单元|室|层))?"
        r")"
    )

    # 称谓/身份词 + 姓名（2-4 个汉字，避免过度匹配）
    ROLE_NAME_PATTERN = re.compile(
        r"(?:"
        r"原告|被告|第三人|上诉人|被上诉人|申请人|被申请人|再审申请人|再审被申请人|"
        r"委托代理人|法定代理人|法定代表人|负责人|保证人|出借人|借款人|承租人|出租人|"
        r"当事人|证人|鉴定人"
        r")([\u4e00-\u9fff]{2,4})(?=[\s，。、；：,.，）\)】\]】]|$)"
    )

    ORG_HINTS = ("公司", "厂", "行", "院", "中心", "有限", "合伙", "事务所", "委员会", "银行")

    def __init__(self):
        pass

    def _classify_entity(self, value: str, explicit_type: Optional[str] = None) -> Tuple[str, str]:
        """返回 (entity_type, label)。entity_type: PERSON/ORG/ADDRESS。"""
        t = (explicit_type or "").strip().upper()
        if t in ("PERSON", "ORG", "ADDRESS"):
            label = {"PERSON": "自然人", "ORG": "公司主体", "ADDRESS": "住所"}[t]
            return t, label
        if t in ("ADDRESS", "ADDR"):
            return "ADDRESS", "住所"
        if any(k in value for k in self.ORG_HINTS):
            return "ORG", "公司主体"
        if "路" in value or "街" in value or "号" in value or "区" in value:
            if len(value) >= 6 and any(k in value for k in ("路", "街", "号", "室")):
                return "ADDRESS", "住所"
        return "PERSON", "自然人"

    def mask(
        self,
        text: str,
        custom_entities: Optional[List[Dict[str, str]]] = None,
        mask_phones: bool = True,
        mask_id_cards: bool = True,
        mask_bank_cards: bool = True,
        mask_emails: bool = True,
        mask_uscc: bool = True,
        mask_addresses: bool = True,
        mask_role_names: bool = True,
    ) -> Tuple[str, Dict[str, str], Dict[str, Any]]:
        """
        对输入文本进行敏感信息占位替换，返回 (脱敏文本, 映射字典, 统计信息)
        mapping 结构：{ "[身份证号_1]": "110101199003072345", ... }
        """
        if not text:
            return "", {}, {"total_masked": 0, "categories": {}}

        masked_text = text
        mapping: Dict[str, str] = {}
        counter: Dict[str, int] = {
            "id_card": 0,
            "phone": 0,
            "bank_card": 0,
            "email": 0,
            "uscc": 0,
            "address": 0,
            "role_name": 0,
            "custom": 0,
        }
        seen_value_to_placeholder: Dict[str, str] = {}

        def _register(val: str, category_key: str, label_prefix: str) -> str:
            if val not in seen_value_to_placeholder:
                counter[category_key] += 1
                ph = f"[{label_prefix}_{counter[category_key]}]"
                seen_value_to_placeholder[val] = ph
                mapping[ph] = val
            return seen_value_to_placeholder[val]

        # 1. 优先处理外部传入的自定义当事人/企业实体
        if custom_entities:
            # 长值优先，避免短名截断长地址
            sorted_entities = sorted(
                custom_entities,
                key=lambda item: len((item.get("value") or item.get("name") or "").strip()),
                reverse=True,
            )
            for item in sorted_entities:
                raw_val = (item.get("value") or item.get("name") or "").strip()
                if not raw_val or len(raw_val) < 2:
                    continue
                etype = item.get("type") or item.get("entity_type")
                _, default_label = self._classify_entity(raw_val, etype)
                label = (item.get("label") or item.get("category") or default_label).strip()
                if raw_val not in seen_value_to_placeholder:
                    counter["custom"] += 1
                    placeholder = f"[{label}_{counter['custom']}]"
                    seen_value_to_placeholder[raw_val] = placeholder
                    mapping[placeholder] = raw_val
                else:
                    placeholder = seen_value_to_placeholder[raw_val]
                masked_text = masked_text.replace(raw_val, placeholder)

        # 2. 身份证号脱敏
        if mask_id_cards:
            for match in self.ID_CARD_PATTERN.finditer(masked_text):
                _register(match.group(0), "id_card", "身份证号")
            for val, ph in list(seen_value_to_placeholder.items()):
                if ph.startswith("[身份证号_"):
                    masked_text = masked_text.replace(val, ph)

        # 3. 银行卡号脱敏
        if mask_bank_cards:
            for match in self.BANK_CARD_PATTERN.finditer(masked_text):
                _register(match.group(0), "bank_card", "银行账号")
            for val, ph in list(seen_value_to_placeholder.items()):
                if ph.startswith("[银行账号_"):
                    masked_text = masked_text.replace(val, ph)

        # 4. 统一社会信用代码脱敏
        if mask_uscc:
            for match in self.USCC_PATTERN.finditer(masked_text):
                _register(match.group(0), "uscc", "社会信用代码")
            for val, ph in list(seen_value_to_placeholder.items()):
                if ph.startswith("[社会信用代码_"):
                    masked_text = masked_text.replace(val, ph)

        # 5. 手机号脱敏
        if mask_phones:
            for match in self.PHONE_PATTERN.finditer(masked_text):
                _register(match.group(0), "phone", "联系电话")
            for val, ph in list(seen_value_to_placeholder.items()):
                if ph.startswith("[联系电话_"):
                    masked_text = masked_text.replace(val, ph)

        # 6. 邮箱脱敏
        if mask_emails:
            for match in self.EMAIL_PATTERN.finditer(masked_text):
                _register(match.group(0), "email", "电子邮箱")
            for val, ph in list(seen_value_to_placeholder.items()):
                if ph.startswith("[电子邮箱_"):
                    masked_text = masked_text.replace(val, ph)

        # 7. 高置信中文地址（避免对已占位符区域二次处理）
        if mask_addresses:
            for match in self.ADDRESS_PATTERN.finditer(masked_text):
                val = match.group(0).strip()
                if len(val) < 6:
                    continue
                # 必须含路/街类 + 号，或 区/县 + 路/街，降低误伤
                has_road = any(k in val for k in ("路", "街", "道", "巷", "弄", "大街", "大道"))
                has_num = "号" in val
                has_admin = any(k in val for k in ("省", "市", "区", "县", "旗"))
                if not (has_road and (has_num or has_admin)):
                    continue
                if val.startswith("[") and val.endswith("]"):
                    continue
                _register(val, "address", "住所")
            for val, ph in list(seen_value_to_placeholder.items()):
                if ph.startswith("[住所_"):
                    masked_text = masked_text.replace(val, ph)

        # 8. 「称谓 + 姓名」高置信片段：仅替换姓名部分
        if mask_role_names:
            replacements: List[Tuple[int, int, str]] = []
            for match in self.ROLE_NAME_PATTERN.finditer(masked_text):
                name = match.group(1)
                if len(name) < 2:
                    continue
                # 跳过明显非姓名的词
                if name in ("人民法院", "仲裁委", "身份证", "营业执"):
                    continue
                ph = _register(name, "role_name", "自然人")
                # group(1) 相对 match 起点的偏移
                start = match.start(1)
                end = match.end(1)
                replacements.append((start, end, ph))
            # 从后往前替换，避免偏移错乱
            for start, end, ph in sorted(replacements, key=lambda x: x[0], reverse=True):
                masked_text = masked_text[:start] + ph + masked_text[end:]

        total_masked = sum(counter.values())
        stats = {
            "total_masked": total_masked,
            "has_pii": total_masked > 0,
            "categories": {k: v for k, v in counter.items() if v > 0},
        }

        return masked_text, mapping, stats

    def unmask(self, text: str, mapping: Dict[str, str]) -> str:
        """将文本中的所有占位符还原为原始真实信息"""
        if not text or not mapping:
            return text

        restored_text = text
        sorted_placeholders = sorted(mapping.keys(), key=len, reverse=True)
        for ph in sorted_placeholders:
            raw_val = mapping[ph]
            restored_text = restored_text.replace(ph, raw_val)

        return restored_text

    def scan_pii(self, text: str) -> List[Dict[str, Any]]:
        """扫描文本中包含的敏感个人信息实体并输出位置与脱敏预览"""
        results: List[Dict[str, Any]] = []
        if not text:
            return results

        for m in self.ID_CARD_PATTERN.finditer(text):
            val = m.group(0)
            results.append({
                "type": "ID_CARD",
                "label": "身份证号码",
                "start": m.start(),
                "end": m.end(),
                "masked_preview": f"{val[:6]}********{val[-4:]}",
            })

        for m in self.PHONE_PATTERN.finditer(text):
            val = m.group(0)
            results.append({
                "type": "PHONE",
                "label": "移动电话号码",
                "start": m.start(),
                "end": m.end(),
                "masked_preview": f"{val[:3]}****{val[-4:]}",
            })

        for m in self.BANK_CARD_PATTERN.finditer(text):
            val = m.group(0)
            results.append({
                "type": "BANK_CARD",
                "label": "银行卡/结算账户",
                "start": m.start(),
                "end": m.end(),
                "masked_preview": f"{val[:4]}********{val[-4:]}",
            })

        for m in self.EMAIL_PATTERN.finditer(text):
            val = m.group(0)
            results.append({
                "type": "EMAIL",
                "label": "电子邮箱",
                "start": m.start(),
                "end": m.end(),
                "masked_preview": val,
            })

        for m in self.ADDRESS_PATTERN.finditer(text):
            val = m.group(0).strip()
            if len(val) < 6:
                continue
            has_road = any(k in val for k in ("路", "街", "道", "巷", "弄", "大街", "大道"))
            has_num = "号" in val
            has_admin = any(k in val for k in ("省", "市", "区", "县", "旗"))
            if not (has_road and (has_num or has_admin)):
                continue
            results.append({
                "type": "ADDRESS",
                "label": "中文住所地址",
                "start": m.start(),
                "end": m.end(),
                "masked_preview": val[:4] + "****" + val[-2:] if len(val) > 6 else "****",
            })

        for m in self.ROLE_NAME_PATTERN.finditer(text):
            name = m.group(1)
            results.append({
                "type": "PERSON",
                "label": "称谓后姓名",
                "start": m.start(1),
                "end": m.end(1),
                "masked_preview": name[0] + "*" * (len(name) - 1),
            })

        return results

    @classmethod
    def mask_text(
        cls,
        text: str,
        known_parties: Optional[List[str]] = None,
        custom_entities: Optional[List[Dict[str, str]]] = None,
    ) -> Tuple[str, Dict[str, str]]:
        """便捷静态调用：返回 (masked_text, mapping)"""
        entities = list(custom_entities or [])
        if known_parties:
            for p in known_parties:
                cat = "公司主体" if any(k in p for k in ["公司", "厂", "行", "院", "中心", "有限", "合伙"]) else "自然人"
                entities.append({"value": p, "label": cat})
        masked, mapping, _ = pii_sanitizer.mask(text, custom_entities=entities)
        return masked, mapping

    @classmethod
    def unmask_text(cls, text: str, mapping: Dict[str, str]) -> str:
        """便捷静态调用：无损还原文本"""
        return pii_sanitizer.unmask(text, mapping)


def build_entities_from_parties(parties: Optional[List[Any]]) -> List[Dict[str, str]]:
    """
    从当事人列表构建 custom_entities。
    支持 dict / 带属性对象；字段：name/value、address、legal_rep、agent/代理人、
    org_name、party_type 等。类型 PERSON/ORG/ADDRESS。
    """
    entities: List[Dict[str, str]] = []
    seen: set = set()

    def _add(value: Optional[str], etype: Optional[str] = None, label: Optional[str] = None) -> None:
        raw = (value or "").strip()
        if not raw or len(raw) < 2 or raw in seen:
            return
        seen.add(raw)
        item: Dict[str, str] = {"value": raw}
        if etype:
            item["type"] = etype
        if label:
            item["label"] = label
        else:
            _, lbl = pii_sanitizer._classify_entity(raw, etype)
            item["label"] = lbl
            if not etype:
                item["type"] = pii_sanitizer._classify_entity(raw, None)[0]
        entities.append(item)

    if not parties:
        return entities

    for party in parties:
        if party is None:
            continue
        if isinstance(party, dict):
            data = party
            getter = data.get
        else:
            data = {}
            getter = lambda k, default=None: getattr(party, k, default)  # noqa: E731

        name = getter("name") or getter("value") or getter("party_name")
        party_type = (getter("party_type") or getter("type") or "").strip().lower()
        if party_type in ("legal", "org", "company", "法人", "企业"):
            _add(name, "ORG", "公司主体")
        else:
            _add(name, "PERSON", "自然人")

        _add(getter("address") or getter("住所") or getter("domicile"), "ADDRESS", "住所")
        _add(getter("legal_rep") or getter("法定代表人") or getter("legal_representative"), "PERSON", "法定代表人")
        _add(getter("agent") or getter("代理人") or getter("attorney") or getter("委托代理人"), "PERSON", "代理人")
        _add(getter("org_name") or getter("company_name"), "ORG", "公司主体")
        # 对方当事人别名
        _add(getter("opponent_name") or getter("counterparty"), None, None)

    return entities


def build_entities_from_matter(matter_id: str) -> List[Dict[str, str]]:
    """从案件空间当事人、对方当事人、代理人、法定代表人、住所生成实体列表。"""
    if not matter_id:
        return []
    try:
        from gateway.utils.matter_vault_db import get_matter_by_id
    except Exception:
        return []

    matter = get_matter_by_id(matter_id)
    if not matter:
        return []

    parties: List[Any] = []
    p_info = matter.get("plaintiff_info") or {}
    d_info = matter.get("defendant_info") or {}
    if isinstance(p_info, dict) and p_info:
        parties.append(p_info)
    elif matter.get("plaintiff_name"):
        parties.append({"name": matter["plaintiff_name"]})
    if isinstance(d_info, dict) and d_info:
        parties.append(d_info)
    elif matter.get("defendant_name"):
        parties.append({"name": matter["defendant_name"]})

    # 图谱中的主体节点
    graphs = matter.get("graphs") or {}
    entity_graph = graphs.get("entity_graph") or {}
    for node in entity_graph.get("nodes") or []:
        if isinstance(node, dict) and node.get("name"):
            ntype = node.get("type") or node.get("role") or ""
            if "企业" in str(ntype) or "公司" in str(ntype) or node.get("type") == "company":
                parties.append({"name": node["name"], "party_type": "legal"})
            else:
                parties.append({"name": node["name"], "party_type": "natural"})

    return build_entities_from_parties(parties)


# 只有这些标记能确定是病历材料。没有标记就不拦截，也不能写成已经拦住。
_MEDICAL_RECORD_MARKERS = (
    "病历",
    "出院小结",
    "出院记录",
    "入院记录",
    "门诊病历",
    "住院病案",
    "病案号",
    "诊断证明",
    "病程记录",
    "医嘱",
    "现病史",
    "既往史",
    "检验报告",
    "病理报告",
    "影像报告",
)
_MINOR_WORDS = ("未成年人", "未成年子女", "未成年", "未满十八", "未满18", "未满１８")
_MINOR_AGE = re.compile(r"(?<!\d)(?:1[0-7]|[1-9])\s*周岁")
_LABELED_BIRTH = re.compile(
    r"(?:出生(?:日期|年月)?|生于)\s*[:：]?\s*"
    r"((?:19|20)\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日?"
)
_LABELED_BIRTH_ISO = re.compile(
    r"(?:出生(?:日期|年月)?|生于)\s*[:：]?\s*"
    r"((?:19|20)\d{2})[-/.](\d{1,2})[-/.](\d{1,2})"
)
_SEGMENT_SPLIT = re.compile(r"(\n+|[。！？；])")
NETWORK_WITHHELD_MARK = "[本地留存未外发]"


def _age_is_minor(year: int, month: int, day: int, today: Optional[date] = None) -> Optional[bool]:
    """出生日期能解析时返回是否未满 18 周岁。解析不了返回 None，不当成已经识别。"""
    try:
        born = date(int(year), int(month), int(day))
    except (TypeError, ValueError):
        return None
    today = today or date.today()
    if born > today or born.year < 1900:
        return None
    age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    return age < 18


def id_card_is_minor(id_card: str, today: Optional[date] = None) -> Optional[bool]:
    """从身份证号里的出生日期判断是否未成年。日期不合法时返回 None。"""
    text = (id_card or "").strip().upper()
    if len(text) == 18 and text[:17].isdigit():
        year, month, day = int(text[6:10]), int(text[10:12]), int(text[12:14])
    elif len(text) == 15 and text.isdigit():
        year, month, day = 1900 + int(text[6:8]), int(text[8:10]), int(text[10:12])
    else:
        return None
    return _age_is_minor(year, month, day, today)


def _labeled_birth_is_minor(segment: str) -> Optional[bool]:
    """写明的出生日期。没有写明，或写了但解析不了，返回 None。"""
    found = False
    minor = False
    for pattern in (_LABELED_BIRTH, _LABELED_BIRTH_ISO):
        for match in pattern.finditer(segment):
            found = True
            flag = _age_is_minor(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            if flag is True:
                minor = True
    if minor:
        return True
    if found:
        return False
    return None


def _segment_withhold_reason(segment: str) -> str:
    medical = any(marker in segment for marker in _MEDICAL_RECORD_MARKERS)
    minor = any(word in segment for word in _MINOR_WORDS) or bool(_MINOR_AGE.search(segment))
    if not minor:
        for match in PIISanitizer.ID_CARD_PATTERN.finditer(segment):
            if id_card_is_minor(match.group(0)) is True:
                minor = True
                break
    if _labeled_birth_is_minor(segment) is True:
        minor = True
    if medical and minor:
        return "both"
    if medical:
        return "medical"
    if minor:
        return "minor"
    return ""


def withhold_network_sensitive(text: str) -> Tuple[str, Dict[str, Any]]:
    """外发前只拿掉能识别的未成年人信息和病历内容。

    识别不了的原文保持不动，返回说明里也不会写成已经拦住。
    """
    report: Dict[str, Any] = {
        "minor_withheld": False,
        "medical_withheld": False,
        "segments_withheld": 0,
        "blocked_unidentified": False,
        "note": "只留存已识别的未成年人信息或病历内容，识别不了的没有拦截。",
    }
    if not text:
        return "", report
    pieces = _SEGMENT_SPLIT.split(text)
    kept: List[str] = []
    for piece in pieces:
        if not piece or piece in "。！？；" or piece.startswith("\n"):
            kept.append(piece)
            continue
        reason = _segment_withhold_reason(piece)
        if not reason:
            kept.append(piece)
            continue
        report["segments_withheld"] += 1
        if reason in ("minor", "both"):
            report["minor_withheld"] = True
        if reason in ("medical", "both"):
            report["medical_withheld"] = True
        kept.append(NETWORK_WITHHELD_MARK)
    return "".join(kept), report


# 全局单例
pii_sanitizer = PIISanitizer()
