"""
LawFlow 智律工作台 - 本地 PII 隐私脱敏与还原网关 (Bi-directional PII Sanitization Gateway)
功能：
1. 在向外部或云端大模型发送请求前，在本地将当事人敏感信息（身份证号、手机号、银行卡号、邮箱、统一信用代码、当事人姓名与企业名）转换为安全占位符；
2. 大模型返回推理结果后，在本地通过双向映射字典无损还原真实实体；
3. 保障诉讼核心机密（涉及《个人信息保护法》与律师执业保密义务）零云端泄露。
"""

import re
from typing import Dict, Any, List, Optional, Tuple


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

    # 18位统一社会信用代码（前两位登记管理部门+机构类别，第三至八位行政区划码，第九至十七位主体标识码，第十八位校验码）
    USCC_PATTERN = re.compile(r"(?<![A-Za-z0-9])[1-9ANY][1-9]\d{6}[0-9A-HJ-NPQRTUWXY]{10}(?![A-Za-z0-9])")

    def __init__(self):
        pass

    def mask(
        self,
        text: str,
        custom_entities: Optional[List[Dict[str, str]]] = None,
        mask_phones: bool = True,
        mask_id_cards: bool = True,
        mask_bank_cards: bool = True,
        mask_emails: bool = True,
        mask_uscc: bool = True
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
            "custom": 0
        }
        seen_value_to_placeholder: Dict[str, str] = {}

        # 1. 优先处理外部传入的自定义当事人/企业实体 (如原告、被告、企业名)
        if custom_entities:
            for item in custom_entities:
                raw_val = (item.get("value") or item.get("name") or "").strip()
                label = (item.get("label") or item.get("category") or "当事人").strip()
                if not raw_val or len(raw_val) < 2:
                    continue

                if raw_val not in seen_value_to_placeholder:
                    counter["custom"] += 1
                    placeholder = f"[{label}_{counter['custom']}]"
                    seen_value_to_placeholder[raw_val] = placeholder
                    mapping[placeholder] = raw_val
                else:
                    placeholder = seen_value_to_placeholder[raw_val]

                # 精确全词替换
                masked_text = masked_text.replace(raw_val, placeholder)

        # 2. 身份证号脱敏
        if mask_id_cards:
            for match in self.ID_CARD_PATTERN.finditer(masked_text):
                val = match.group(0)
                if val not in seen_value_to_placeholder:
                    counter["id_card"] += 1
                    ph = f"[身份证号_{counter['id_card']}]"
                    seen_value_to_placeholder[val] = ph
                    mapping[ph] = val

            for val, ph in seen_value_to_placeholder.items():
                if ph.startswith("[身份证号_"):
                    masked_text = masked_text.replace(val, ph)

        # 3. 银行卡号脱敏
        if mask_bank_cards:
            for match in self.BANK_CARD_PATTERN.finditer(masked_text):
                val = match.group(0)
                if val not in seen_value_to_placeholder:
                    counter["bank_card"] += 1
                    ph = f"[银行账号_{counter['bank_card']}]"
                    seen_value_to_placeholder[val] = ph
                    mapping[ph] = val

            for val, ph in seen_value_to_placeholder.items():
                if ph.startswith("[银行账号_"):
                    masked_text = masked_text.replace(val, ph)

        # 4. 统一社会信用代码脱敏
        if mask_uscc:
            for match in self.USCC_PATTERN.finditer(masked_text):
                val = match.group(0)
                if val not in seen_value_to_placeholder:
                    counter["uscc"] += 1
                    ph = f"[社会信用代码_{counter['uscc']}]"
                    seen_value_to_placeholder[val] = ph
                    mapping[ph] = val

            for val, ph in seen_value_to_placeholder.items():
                if ph.startswith("[社会信用代码_"):
                    masked_text = masked_text.replace(val, ph)

        # 5. 手机号脱敏
        if mask_phones:
            for match in self.PHONE_PATTERN.finditer(masked_text):
                val = match.group(0)
                if val not in seen_value_to_placeholder:
                    counter["phone"] += 1
                    ph = f"[联系电话_{counter['phone']}]"
                    seen_value_to_placeholder[val] = ph
                    mapping[ph] = val

            for val, ph in seen_value_to_placeholder.items():
                if ph.startswith("[联系电话_"):
                    masked_text = masked_text.replace(val, ph)

        # 6. 邮箱脱敏
        if mask_emails:
            for match in self.EMAIL_PATTERN.finditer(masked_text):
                val = match.group(0)
                if val not in seen_value_to_placeholder:
                    counter["email"] += 1
                    ph = f"[电子邮箱_{counter['email']}]"
                    seen_value_to_placeholder[val] = ph
                    mapping[ph] = val

            for val, ph in seen_value_to_placeholder.items():
                if ph.startswith("[电子邮箱_"):
                    masked_text = masked_text.replace(val, ph)

        total_masked = sum(counter.values())
        stats = {
            "total_masked": total_masked,
            "has_pii": total_masked > 0,
            "categories": {k: v for k, v in counter.items() if v > 0}
        }

        return masked_text, mapping, stats

    def unmask(self, text: str, mapping: Dict[str, str]) -> str:
        """
        将文本中的所有占位符还原为原始真实信息
        """
        if not text or not mapping:
            return text

        restored_text = text
        # 按占位符长度降序排序替换，防止前缀冲突
        sorted_placeholders = sorted(mapping.keys(), key=len, reverse=True)
        for ph in sorted_placeholders:
            raw_val = mapping[ph]
            restored_text = restored_text.replace(ph, raw_val)

        return restored_text

    def scan_pii(self, text: str) -> List[Dict[str, Any]]:
        """扫描文本中包含的敏感个人信息实体并输出位置与脱敏预览"""
        results = []
        if not text:
            return results

        # 身份证
        for m in self.ID_CARD_PATTERN.finditer(text):
            val = m.group(0)
            masked = f"{val[:6]}********{val[-4:]}"
            results.append({
                "type": "ID_CARD",
                "label": "身份证号码",
                "start": m.start(),
                "end": m.end(),
                "masked_preview": masked
            })

        # 手机
        for m in self.PHONE_PATTERN.finditer(text):
            val = m.group(0)
            masked = f"{val[:3]}****{val[-4:]}"
            results.append({
                "type": "PHONE",
                "label": "移动电话号码",
                "start": m.start(),
                "end": m.end(),
                "masked_preview": masked
            })

        # 银行卡
        for m in self.BANK_CARD_PATTERN.finditer(text):
            val = m.group(0)
            masked = f"{val[:4]}********{val[-4:]}"
            results.append({
                "type": "BANK_CARD",
                "label": "银行卡/结算账户",
                "start": m.start(),
                "end": m.end(),
                "masked_preview": masked
            })

        # 邮箱
        for m in self.EMAIL_PATTERN.finditer(text):
            val = m.group(0)
            results.append({
                "type": "EMAIL",
                "label": "电子邮箱",
                "start": m.start(),
                "end": m.end(),
                "masked_preview": val
            })

        return results

    @classmethod
    def mask_text(
        cls,
        text: str,
        known_parties: Optional[List[str]] = None,
        custom_entities: Optional[List[Dict[str, str]]] = None
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


# 全局单例
pii_sanitizer = PIISanitizer()

