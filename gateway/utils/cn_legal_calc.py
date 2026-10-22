"""
LawFlow 智律工作台 - 中国法律实务精确数学与规则计算引擎
【阶段一】核心功能：
1. 人民币大写转换：基于 cn2an 实现精确到分的人民币法院标准大写（如：人民币壹拾贰万叁仟元整）
2. 18位二代居民身份证解析与法定退休年龄判断（GB 11643-1999、最高法劳动争议司法解释一第32条）
3. 18位统一社会信用代码校验与解析 (GB 32100-2015)
4. 《诉讼费用交纳办法》财产与非财产案件受理费、保全费分段精算
5. 央行 LPR 历期分段计息算法与写入起诉状的《利息计算明细说明》自动生成
6. 《劳动合同法》第47/87条劳动争议经济补偿金 (N / N+1) 与违法解除赔偿金 (2N) 精算
"""

import calendar
import json
import logging
from datetime import datetime, date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, List, Optional, Tuple

try:
    import cn2an
except ImportError:
    cn2an = None

logger = logging.getLogger("lawflow.cn_legal_calc")

# 央行贷款基准利率（1 年期）——律师审查结论 L-I8；适用起点日期 TODO(律师核实)
PBOC_BENCHMARK_1Y_RATE = 4.35
PBOC_BENCHMARK_BASIS = "中国人民银行同期同类贷款基准利率（1年期 4.35%）（律师审查结论 L-I8）"
# TODO(律师核实): 该基准利率适用起点日期未核实，期间早于起点时仅提示人工核对


# ==============================================================================
# 1. 人民币金额转大写 (基于 cn2an + 司法公文标准)
# ==============================================================================
def rmb_to_capital(amount: float | Decimal | str) -> str:
    """
    将金额数值转换为符合中国法院裁判文书标准的规范中文大写金额。
    如: 123000.00 -> 人民币壹拾贰万叁仟元整
        10500.50  -> 人民币壹万零伍佰元伍角整
        0.58      -> 人民币伍角捌分
    """
    try:
        dec = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except Exception as e:
        raise ValueError(f"无效的金额数值: {amount}") from e

    if dec == 0:
        return "人民币零元整"

    is_negative = dec < 0
    abs_dec = abs(dec)

    if cn2an is not None:
        try:
            # 使用 cn2an 的 rmb 模式
            capital = cn2an.an2cn(float(abs_dec), mode="rmb")
            # 规范后缀：若以'角'结尾，追加'整'；若包含'分'则不追加
            if capital.endswith("角"):
                capital += "整"
            elif not capital.endswith("分") and not capital.endswith("整"):
                capital += "整"
            prefix = "人民币负" if is_negative else "人民币"
            return prefix + capital
        except Exception as conv_err:
            logger.debug(f"cn2an 大写金额转换失败，启动原生算法: {conv_err}")

    # 原生算法兜底
    digits = "零壹贰叁肆伍陆柒捌玖"
    units_int = ["", "拾", "佰", "仟"]
    big_units = ["", "万", "亿", "兆"]
    units_dec = ["角", "分"]

    str_val = f"{abs_dec:.2f}"
    int_part, dec_part = str_val.split(".")

    res_int = ""
    if int(int_part) > 0:
        groups = []
        rev_int = int_part[::-1]
        for i in range(0, len(rev_int), 4):
            groups.append(rev_int[i:i + 4][::-1])
        groups = groups[::-1]

        for i, group in enumerate(groups):
            g_len = len(group)
            g_str = ""
            zero_flag = False
            for j, ch in enumerate(group):
                n = int(ch)
                unit = units_int[g_len - j - 1]
                if n != 0:
                    if zero_flag:
                        g_str += "零"
                        zero_flag = False
                    g_str += digits[n] + unit
                else:
                    if j < g_len - 1 and int(group[j + 1:]) > 0:
                        zero_flag = True
            if g_str:
                big_unit_idx = len(groups) - i - 1
                g_str += big_units[big_unit_idx]
            res_int += g_str
        res_int += "元"

    jiao = int(dec_part[0])
    fen = int(dec_part[1])
    res_dec = ""
    if jiao == 0 and fen == 0:
        res_dec = "整"
    else:
        if jiao != 0:
            res_dec += digits[jiao] + units_dec[0]
        elif res_int:
            res_dec += "零"
        if fen != 0:
            res_dec += digits[fen] + units_dec[1]
        else:
            res_dec += "整"

    prefix = "人民币负" if is_negative else "人民币"
    return prefix + (res_int if res_int else "") + res_dec


# ==============================================================================
# 2. 18位二代居民身份证解析与法定退休年龄判断 (GB 11643-1999)
# ==============================================================================
PROVINCE_CODES = {
    "11": "北京市", "12": "天津市", "13": "河北省", "14": "山西省", "15": "内蒙古自治区",
    "21": "辽宁省", "22": "吉林省", "23": "黑龙江省",
    "31": "上海市", "32": "江苏省", "33": "浙江省", "34": "安徽省", "35": "福建省", "36": "江西省", "37": "山东省",
    "41": "河南省", "42": "湖北省", "43": "湖南省", "44": "广东省", "45": "广西壮族自治区", "46": "海南省",
    "50": "重庆市", "51": "四川省", "52": "贵州省", "53": "云南省", "54": "西藏自治区",
    "61": "陕西省", "62": "甘肃省", "63": "青海省", "64": "宁夏回族自治区", "65": "新疆维吾尔自治区",
    "71": "台湾省", "81": "香港特别行政区", "82": "澳门特别行政区"
}

def validate_and_parse_idcard(id_card: str, is_cadre: bool = False) -> Dict[str, Any]:
    """
    严格校验中国18位居民身份证号码（ISO 7064:1983.MOD 11-2）并提取要素。
    特别增加：【法定退休年龄判断】（用于劳动争议中确认是否属于劳动关系或转为劳务关系）
    """
    id_card = id_card.strip().upper()
    if len(id_card) != 18:
        return {
            "valid": False,
            "id_card": id_card,
            "error_message": f"身份证号码长度必须为18位，当前为{len(id_card)}位"
        }

    prov_code = id_card[:2]
    province = PROVINCE_CODES.get(prov_code, "未知行政区划")
    if province == "未知行政区划":
        return {
            "valid": False,
            "id_card": id_card,
            "error_message": f"前两位地区码 '{prov_code}' 不属于我国规范行政区划"
        }

    birth_str = id_card[6:14]
    try:
        birth_date = datetime.strptime(birth_str, "%Y%m%d").date()
    except ValueError:
        return {
            "valid": False,
            "id_card": id_card,
            "error_message": f"出生日期片段 '{birth_str}' 不是合法的公历日期"
        }

    today = date.today()
    if birth_date > today or birth_date.year < 1900:
        return {
            "valid": False,
            "id_card": id_card,
            "error_message": f"出生日期 {birth_date} 超出合理范围"
        }

    # 年龄计算
    age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))

    # ISO 7064:1983.MOD 11-2 校验码验证
    weights = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
    check_codes = "10X98765432"

    try:
        sum_val = sum(int(id_card[i]) * weights[i] for i in range(17))
        expected_check = check_codes[sum_val % 11]
    except ValueError:
        return {
            "valid": False,
            "id_card": id_card,
            "error_message": "身份证前17位必须全为数字"
        }

    gender_digit = int(id_card[16]) if id_card[16].isdigit() else 0
    gender = "男" if gender_digit % 2 != 0 else "女"

    # ==========================================================================
    # 法定退休年龄精准核定：实装《全国人民代表大会常务委员会关于实施渐进式延迟法定退休年龄的决定》
    # （2024年9月13日第十四届全国人大常委会第十一次会议通过，自2025年1月1日起施行）
    # 规则：
    # 1. 男职工（原60周岁）：每4个月延迟1个月，逐步延迟至63周岁（最高延36个月）；
    # 2. 原55周岁退休女职工（女管理/技术/干部岗）：每4个月延迟1个月，逐步延迟至58周岁（最高延36个月）；
    # 3. 原50周岁退休女职工（普通女工人）：每2个月延迟1个月，逐步延迟至55周岁（最高延60个月）。
    # ==========================================================================
    orig_retire_age = 60 if gender == "男" else (55 if is_cadre else 50)
    max_delay = 36 if (gender == "男" or is_cadre) else 60
    interval = 4 if (gender == "男" or is_cadre) else 2
    target_max_age = orig_retire_age + (max_delay // 12)

    orig_retire_year = birth_date.year + orig_retire_age
    orig_retire_month = birth_date.month

    if (orig_retire_year, orig_retire_month) < (2025, 1):
        # 2025年1月1日前已达到原法定退休年龄
        delay_months = 0
        statutory_retire_year = orig_retire_year
        statutory_retire_month = orig_retire_month
    else:
        # 2025年1月1日及之后退休，执行渐进式延迟
        diff_months = (orig_retire_year - 2025) * 12 + orig_retire_month - 1
        delay_months = min(max_delay, (diff_months // interval) + 1)
        total_months_calc = orig_retire_year * 12 + orig_retire_month - 1 + delay_months
        statutory_retire_year = total_months_calc // 12
        statutory_retire_month = total_months_calc % 12 + 1

    # 判定在当前核算日期是否已实际达到改革后法定退休年龄
    is_retired = (today.year, today.month) >= (statutory_retire_year, statutory_retire_month)
    statutory_retire_date_str = f"{statutory_retire_year}年{statutory_retire_month:02d}月"
    effective_retire_age_str = f"{orig_retire_age}周岁" if delay_months == 0 else f"{orig_retire_age}岁零{delay_months}个月"

    if is_retired:
        retirement_note = (
            f"该当事人现年 {age} 周岁。依据《全国人大常委会关于实施渐进式延迟法定退休年龄的决定》（2025年1月1日起施行），"
            f"其原法定退休年龄为 {orig_retire_age} 周岁，经依法测算延迟 {delay_months} 个月，"
            f"改革后法定退休时间为 {statutory_retire_date_str}（即满 {effective_retire_age_str}），现已届满法定退休年龄。"
            "依据最高法劳动争议司法解释一第32条，用人单位招用已达法定退休年龄并享受养老待遇人员按劳务关系处理；"
            "主张《劳动合同法》第47条/第87条经济补偿或违法解除赔偿金通常不予支持。"
        )
    else:
        months_left = (statutory_retire_year - today.year) * 12 + (statutory_retire_month - today.month)
        years_left = months_left // 12
        rem_m_left = months_left % 12
        countdown_str = f"{years_left}年{rem_m_left}个月" if years_left > 0 else f"{rem_m_left}个月"
        retirement_note = (
            f"该当事人现年 {age} 周岁。依据《全国人大常委会关于实施渐进式延迟法定退休年龄的决定》（2025年1月1日起施行），"
            f"其原法定退休年龄为 {orig_retire_age} 周岁，依法延迟 {delay_months} 个月，"
            f"法定退休时间为 {statutory_retire_date_str}（满 {effective_retire_age_str}），距离法定退休尚有 {countdown_str}。"
            "该当事人仍属于适龄劳动者，具备完全劳动权利能力与劳动争议仲裁/诉讼主体资格。"
        )

    actual_check = id_card[17]
    check_match = (actual_check == expected_check)

    return {
        "valid": check_match,
        "id_card": id_card,
        "province": province,
        "birth_date": birth_date.strftime("%Y-%m-%d"),
        "age": age,
        "gender": gender,
        "is_retired": is_retired,
        "orig_retire_age": orig_retire_age,
        "delay_months": delay_months,
        "statutory_retire_date": statutory_retire_date_str,
        "standard_retire_age": orig_retire_age,
        "effective_retire_age_str": effective_retire_age_str,
        "retirement_note": retirement_note,
        "expected_check": expected_check,
        "actual_check": actual_check,
        "check_digit_match": check_match,
        "error_message": None if check_match else f"校验码不匹配: 实际为'{actual_check}', 理论应为'{expected_check}'"
    }


# ==============================================================================
# 3. 18位统一社会信用代码校验与解析 (GB 32100-2015)
# ==============================================================================
USCC_CHARS = "0123456789ABCDEFGHJKLMNPQRTUWXY"
USCC_WEIGHTS = [1, 3, 9, 27, 19, 26, 16, 17, 20, 29, 25, 13, 8, 24, 10, 30, 28]

USCC_DEPARTMENTS = {
    "1": "机构编制",
    "5": "民政",
    "9": "市场监督管理 (工商)",
    "Y": "其他"
}

def validate_and_parse_uscc(uscc: str) -> Dict[str, Any]:
    """
    根据《法人和其他组织统一社会信用代码编码规则》(GB 32100-2015) 校验与解析企业组织机构代码。
    """
    code = uscc.strip().upper()
    if len(code) != 18:
        return {
            "valid": False,
            "uscc": code,
            "error_message": f"统一社会信用代码长度必须为18位，当前为{len(code)}位"
        }

    dept_code = code[0]
    dept_name = USCC_DEPARTMENTS.get(dept_code, "其他登记管理机关")

    # 校验前17位字符集
    for ch in code:
        if ch not in USCC_CHARS:
            return {
                "valid": False,
                "uscc": code,
                "error_message": f"包含非法字符 '{ch}'（代码中不允许包含字母 I, O, Z, S, V）"
            }

    try:
        sum_val = sum(USCC_CHARS.index(code[i]) * USCC_WEIGHTS[i] for i in range(17))
        rem = sum_val % 31
        check_val = 31 - rem if rem != 0 else 0
        if check_val == 31:
            check_val = 0
        expected_check = USCC_CHARS[check_val]
    except Exception as e:
        return {"valid": False, "uscc": code, "error_message": f"校验计算错误: {e}"}

    actual_check = code[17]
    valid = actual_check == expected_check

    prov_code = code[2:4]
    province = PROVINCE_CODES.get(prov_code, "全国/未知辖区")

    return {
        "valid": valid,
        "uscc": code,
        "department": dept_name,
        "province": province,
        "org_code": code[8:17],
        "expected_check": expected_check,
        "actual_check": actual_check,
        "error_message": None if valid else f"校验位不匹配: 实际为'{actual_check}', 理论应为'{expected_check}'"
    }


# ==============================================================================
# 4. 《诉讼费用交纳办法》财产与非财产案件受理费、保全费分段精算
# ==============================================================================
def calculate_court_fees(
    claim_amount: float | Decimal,
    case_type: str = "property",
    is_summary_procedure: bool = False,
    divorce_base_fee: float | Decimal = 100,
) -> Dict[str, Any]:
    """
    根据《诉讼费用交纳办法》（国务院令第481号）第十三条精确计算诉讼费用。
    """
    amount = Decimal(str(claim_amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if amount < 0:
        raise ValueError("诉讼标的额不能为负数")

    div_base = Decimal(str(divorce_base_fee)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if div_base < Decimal("50") or div_base > Decimal("300"):
        raise ValueError(f"离婚案件基础规费应在 50 至 300 元之间，当前为 {divorce_base_fee}")

    breakdown = []
    standard_fee = Decimal("0")

    # 归一化案件类型（前端可能传中文）
    ct = (case_type or "property").strip().lower()
    if ct in ("财产案件", "property", "财产"):
        ct = "property"
    elif ct in ("劳动", "labor", "劳动人事争议"):
        ct = "labor"
    elif ct in ("离婚", "divorce"):
        ct = "divorce"

    if case_type == "labor" or ct == "labor":
        standard_fee = Decimal("10.00")
        breakdown.append({"tier": "劳动人事争议案件固定收费", "rate": "法定10元/件", "fee": 10.00})
    elif case_type == "divorce" or ct == "divorce":
        base_fee = div_base
        rate_desc = f"每件 50—300 元，由各地确定，本次按 {float(base_fee):g} 元计算，以当地标准为准（《诉讼费用交纳办法》第十三条）"
        if amount <= Decimal("200000"):
            standard_fee = base_fee
            breakdown.append({"tier": "不超过20万元财产分割", "rate": rate_desc, "fee": float(base_fee)})
        else:
            excess = amount - Decimal("200000")
            excess_fee = (excess * Decimal("0.005")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            standard_fee = base_fee + excess_fee
            breakdown.append({"tier": "基础规费(20万以内)", "rate": rate_desc, "fee": float(base_fee)})
            breakdown.append({"tier": f"超过20万部分({excess:.2f}元)", "rate": "0.5%", "fee": float(excess_fee)})
    else:
        if amount <= 0:
            raise ValueError("财产案件标的额须大于 0")
        tiers = [
            (Decimal("0"), Decimal("10000"), None, Decimal("50")),
            (Decimal("10000"), Decimal("100000"), Decimal("0.025"), None),
            (Decimal("100000"), Decimal("200000"), Decimal("0.02"), None),
            (Decimal("200000"), Decimal("500000"), Decimal("0.015"), None),
            (Decimal("500000"), Decimal("1000000"), Decimal("0.01"), None),
            (Decimal("1000000"), Decimal("2000000"), Decimal("0.009"), None),
            (Decimal("2000000"), Decimal("5000000"), Decimal("0.008"), None),
            (Decimal("5000000"), Decimal("10000000"), Decimal("0.007"), None),
            (Decimal("10000000"), Decimal("20000000"), Decimal("0.006"), None),
            (Decimal("20000000"), Decimal("Infinity"), Decimal("0.005"), None),
        ]
        if amount <= Decimal("10000"):
            standard_fee = Decimal("50.00")
            breakdown.append({"tier": "不超过1万元", "rate": "50元固定", "fee": 50.00})
        else:
            standard_fee = Decimal("50.00")
            breakdown.append({"tier": "不超过1万元", "rate": "50元固定", "fee": 50.00})
            for low, high, rate, fixed in tiers[1:]:
                if amount > low:
                    taxable = min(amount, high) - low
                    seg_fee = (taxable * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                    standard_fee += seg_fee
                    breakdown.append({
                        "tier": f"{int(low/10000)}万 - {('无上限' if high == Decimal('Infinity') else str(int(high/10000))+'万')}",
                        "taxable_amount": float(taxable),
                        "rate": f"{float(rate)*100}%",
                        "fee": float(seg_fee)
                    })
                else:
                    break

    actual_fee = (standard_fee / 2).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if is_summary_procedure else standard_fee

    # 保全申请费（第十四条第二项）封顶5000元
    preservation_fee = Decimal("0")
    if amount > 0:
        if amount <= Decimal("1000"):
            preservation_fee = Decimal("30.00")
        elif amount <= Decimal("100000"):
            preservation_fee = Decimal("30.00") + ((amount - Decimal("1000")) * Decimal("0.01")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        else:
            p_fee = Decimal("30.00") + (Decimal("99000") * Decimal("0.01")) + ((amount - Decimal("100000")) * Decimal("0.005")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            preservation_fee = min(p_fee, Decimal("5000.00"))

    return {
        "claim_amount": float(amount),
        "case_type": case_type,
        "is_summary_procedure": is_summary_procedure,
        "standard_fee": float(standard_fee),
        "court_fee": float(actual_fee),
        "actual_fee": float(actual_fee),
        "preservation_fee": float(preservation_fee),
        "tier_breakdown": breakdown,
        "rmb_capital": rmb_to_capital(actual_fee)
    }


# ==============================================================================
# 5. 央行 LPR 历期分段计息算法与起诉状《利息计算明细说明》生成
# ==============================================================================

def _lookup_lpr_on_date(sorted_lpr: List[Tuple[str, float, float]], on_date: date, term: str = "1Y") -> Optional[float]:
    term_u = term.strip().upper()
    for dt_str, r1, r5 in reversed(sorted_lpr):
        pub_dt = datetime.strptime(dt_str, "%Y-%m-%d").date()
        if pub_dt <= on_date:
            return r1 if term_u == "1Y" else r5
    return None


def add_months_exact(d: date, months: int) -> date:
    """
    按《民法典》第202条按月计算期间：到期月对应日为期间最后一日；
    没有对应日的，以到期月的月末日为最后一日。
    months 可为负数。
    """
    new_year = d.year + (d.month + months - 1) // 12
    new_month = (d.month + months - 1) % 12 + 1
    max_day = calendar.monthrange(new_year, new_month)[1]
    new_day = min(d.day, max_day)
    return date(new_year, new_month, new_day)


def get_private_lending_four_times_lpr_cap(
    contract_date: str,
    filing_date: Optional[str] = None,
) -> Dict[str, Any]:
    """
    民间借贷约定利率司法保护上限（一年期 LPR×4）。
    合同成立于 2020-08-20 及之后：上限=合同成立时一年期 LPR×4；
    合同成立于 2020-08-20 之前：后段上限需起诉日 LPR×4（须提供 filing_date）。
    返回百分数口径（如 12.4 表示 12.4%）。
    """
    from gateway.utils.legal_data import load_lpr_history

    sorted_lpr = load_lpr_history()
    ref_contract_date = datetime.strptime(contract_date, "%Y-%m-%d").date()
    d_pivot = date(2020, 8, 20)

    contract_lpr = _lookup_lpr_on_date(sorted_lpr, ref_contract_date, "1Y")
    if contract_lpr is None:
        contract_lpr = 3.85

    if ref_contract_date < d_pivot:
        if not filing_date:
            raise ValueError("合同成立于2020-08-20之前，须提供起诉日期 filing_date")
        d_filing = datetime.strptime(filing_date, "%Y-%m-%d").date()
        filing_lpr = _lookup_lpr_on_date(sorted_lpr, d_filing, "1Y")
        if filing_lpr is None:
            raise ValueError("无法确定起诉日对应的一年期 LPR")
        cap_rate_percent = round(filing_lpr * 4, 4)
        basis = "起诉时LPR×4"
        lpr_base = filing_lpr
    else:
        cap_rate_percent = round(contract_lpr * 4, 4)
        basis = "合同成立时LPR×4"
        lpr_base = contract_lpr

    return {
        "cap_rate_percent": cap_rate_percent,
        "cap_rate_decimal": round(cap_rate_percent / 100.0, 6),
        "lpr_base_percent": lpr_base,
        "basis": basis,
        "contract_date": contract_date,
        "filing_date": filing_date,
    }


def check_lpr_data_freshness(today: Optional[date] = None) -> List[str]:
    """启动/调用时检查 LPR 表是否可能过期。"""
    from gateway.utils.legal_data import load_lpr_history_meta

    warnings: List[str] = []
    meta = load_lpr_history_meta()
    data_as_of = datetime.strptime(meta["data_as_of"], "%Y-%m-%d").date()
    d_today = today or date.today()
    if (d_today - data_as_of).days > 31:
        msg = "LPR 数据可能已过期，请更新 data/legal/lpr_history.json"
        warnings.append(msg)
        logger.warning(msg)
    return warnings


def calculate_lpr_interest(
    principal: float | Decimal,
    start_date: str,
    end_date: str,
    multiplier: float = 1.0,
    term: str = "1Y",
    fixed_annual_rate: Optional[float] = None,
    rule_mode: str = "commercial_floating",  # commercial_floating / private_lending_cap / sales_fixed_lpr_markup
    contract_date: Optional[str] = None,
    filing_date: Optional[str] = None,
    markup_ratio: Optional[float] = None,
    today_date: Optional[str] = None,
) -> Dict[str, Any]:
    """
    分段计算自起始日起至截止日期的逾期利息 / 资金占用损失。
    模式：
    1. commercial_floating（默认）：商事同期 LPR 浮动；2019-08-20 前用央行贷款基准利率 4.35%。
    2. private_lending_cap：民间借贷司法保护上限（法释〔2020〕17号第31条第2款）。
    3. sales_fixed_lpr_markup：买卖合同未约定逾期违约金时，起算日一年期 LPR×(1+markup_ratio) 固定计息。
    """
    from gateway.utils.legal_data import load_lpr_history, load_lpr_history_meta

    term_norm = (term or "").strip().upper()
    if term_norm not in ("1Y", "5Y"):
        raise ValueError('term 仅允许 "1Y" 或 "5Y"')
    term = term_norm

    if fixed_annual_rate is not None and 0 < float(fixed_annual_rate) < 1:
        raise ValueError("疑似填写了小数，请输入百分数（例如 0.24 应写为 24）")

    d_start = datetime.strptime(start_date, "%Y-%m-%d").date()
    d_end = datetime.strptime(end_date, "%Y-%m-%d").date()
    d_today = datetime.strptime(today_date, "%Y-%m-%d").date() if today_date else date.today()

    if d_end < d_start:
        raise ValueError("计息截止日期不能早于起始日期")

    total_days = (d_end - d_start).days
    p_dec = Decimal(str(principal)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    sorted_lpr = load_lpr_history()
    meta = load_lpr_history_meta()
    data_as_of = datetime.strptime(meta["data_as_of"], "%Y-%m-%d").date()

    warnings: List[str] = []
    warnings.extend(check_lpr_data_freshness(d_today))
    if d_end > data_as_of:
        warnings.append("计息止日超出 LPR 数据截止日，后段按最后一期利率计算")

    periods: List[Dict[str, Any]] = []
    total_interest = Decimal("0.00")
    rate_desc = ""

    # ==========================================================================
    # 模式 A：固定年化利率（非民间借贷上限模式）
    # ==========================================================================
    if fixed_annual_rate is not None and rule_mode not in ("private_lending_cap", "sales_fixed_lpr_markup"):
        rate_dec = Decimal(str(fixed_annual_rate)) / Decimal("100")
        interest = (p_dec * rate_dec * Decimal(total_days) / Decimal("365")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        total_interest = interest
        periods.append({
            "segment_start": start_date,
            "segment_end": end_date,
            "days": total_days,
            "annual_rate": float(fixed_annual_rate),
            "interest": float(interest)
        })
        rate_desc = f"双方约定的固定年利率 {fixed_annual_rate}%"

    # ==========================================================================
    # 模式 sales_fixed_lpr_markup：买卖合同固定 LPR 加计（《买卖合同解释》第18条第4款，需律师核实原文）
    # ==========================================================================
    elif rule_mode == "sales_fixed_lpr_markup":
        if markup_ratio is None:
            raise ValueError("sales_fixed_lpr_markup 模式须提供 markup_ratio（0.3–0.5）")
        mr = float(markup_ratio)
        if mr < 0.3 or mr > 0.5:
            raise ValueError("markup_ratio 须在 0.3–0.5 之间")
        base_lpr = _lookup_lpr_on_date(sorted_lpr, d_start, "1Y")
        if base_lpr is None:
            raise ValueError("无法确定违约行为发生日的一年期 LPR，请核对起息日与 LPR 表")
        applied = round(base_lpr * (1.0 + mr), 4)
        rate_dec = Decimal(str(applied)) / Decimal("100")
        interest = (p_dec * rate_dec * Decimal(total_days) / Decimal("365")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        total_interest = interest
        periods.append({
            "segment_start": start_date,
            "segment_end": end_date,
            "days": total_days,
            "base_lpr": base_lpr,
            "markup_ratio": mr,
            "applied_annual_rate": applied,
            "interest": float(interest),
            "rate_basis": "《买卖合同解释》（2020修正）第十八条第四款（需律师核实原文）",
        })
        rate_desc = (
            f"违约行为发生日一年期 LPR {base_lpr}% 加计 {mr * 100:.0f}%（固定基数，不随后续 LPR 浮动）；"
            f"依据《买卖合同解释》（2020修正）第十八条第四款（需律师核实原文）。"
            f"仅适用于合同未约定逾期付款违约金的情形，有约定的从约定"
        )
        warnings.append("仅适用于合同未约定逾期付款违约金的情形，有约定的从约定")

    # ==========================================================================
    # 模式 B：民间借贷司法保护上限（法释〔2020〕17号第31条第2款）
    # 摘录："……对于自2020年8月20日到借款返还之日的利息部分，适用起诉时本规定的利率保护标准计算。"
    # 来源：court.gov.cn 249051
    # ==========================================================================
    elif rule_mode == "private_lending_cap" or (contract_date is not None and rule_mode != "commercial_floating"):
        ref_contract_date = datetime.strptime(contract_date, "%Y-%m-%d").date() if contract_date else d_start
        d_pivot = date(2020, 8, 20)
        rate_pre_2020 = 24.0

        contract_lpr = _lookup_lpr_on_date(sorted_lpr, ref_contract_date, "1Y")
        if contract_lpr is None:
            contract_lpr = 3.85  # LPR 改革前合同兜底：参照 2020-04-20 一期 3.85%

        if ref_contract_date < d_pivot:
            if not filing_date:
                raise ValueError("合同成立于2020-08-20之前，须提供起诉日期 filing_date")
            d_filing = datetime.strptime(filing_date, "%Y-%m-%d").date()
            filing_lpr = _lookup_lpr_on_date(sorted_lpr, d_filing, "1Y")
            if filing_lpr is None:
                raise ValueError("无法确定起诉日对应的一年期 LPR")
            cap_rate_post = round(filing_lpr * 4, 4)
            post_cap_basis = "起诉时LPR×4"
            post_lpr_base = filing_lpr
        else:
            cap_rate_post = round(contract_lpr * 4, 4)
            post_cap_basis = "合同成立时LPR×4"
            post_lpr_base = contract_lpr

        user_agreed_rate = fixed_annual_rate if fixed_annual_rate is not None else cap_rate_post

        split_dates = [d_start]
        if d_start < d_pivot < d_end:
            split_dates.append(d_pivot)
        split_dates.append(d_end)

        for i in range(len(split_dates) - 1):
            s_dt = split_dates[i]
            e_dt = split_dates[i + 1]
            s_days = (e_dt - s_dt).days
            if s_days <= 0:
                continue

            if e_dt <= d_pivot:
                applicable_cap = rate_pre_2020
                seg_label = "2020-08-20前（适用原司法解释24%上限）"
                cap_basis = "2020-08-20前24%上限"
                lpr_base = None
            else:
                applicable_cap = cap_rate_post
                seg_label = f"2020-08-20后（适用{post_cap_basis} {cap_rate_post}% 上限）"
                cap_basis = post_cap_basis
                lpr_base = post_lpr_base

            effective_rate = min(user_agreed_rate, applicable_cap)
            r_dec = Decimal(str(effective_rate)) / Decimal("100")
            seg_int = (p_dec * r_dec * Decimal(s_days) / Decimal("365")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            total_interest += seg_int

            periods.append({
                "segment_start": s_dt.strftime("%Y-%m-%d"),
                "segment_end": e_dt.strftime("%Y-%m-%d"),
                "days": s_days,
                "regime": seg_label,
                "contract_lpr_base": contract_lpr,
                "lpr_base_for_cap": lpr_base,
                "statutory_cap_rate": applicable_cap,
                "cap_basis": cap_basis,
                "applied_annual_rate": effective_rate,
                "is_rate_capped": user_agreed_rate > applicable_cap,
                "interest": float(seg_int)
            })

        rate_desc = (
            f"民间借贷法定利率保护上限标准（法释〔2020〕17号第31条第2款；"
            f"后段上限依据 {post_cap_basis} = {post_lpr_base}%×4 = {cap_rate_post}%）"
        )

    # ==========================================================================
    # 模式 C：商事违约同期 LPR 浮动分段计息（默认）
    # ==========================================================================
    else:
        lpr_reform = date(2019, 8, 20)
        breakpoints = []
        if d_start < lpr_reform < d_end:
            breakpoints.append(lpr_reform)
        for dt_str, r1, r5 in sorted_lpr:
            dt = datetime.strptime(dt_str, "%Y-%m-%d").date()
            if d_start < dt < d_end and dt not in breakpoints:
                breakpoints.append(dt)
        breakpoints.sort()
        all_points = [d_start] + breakpoints + [d_end]

        for i in range(len(all_points) - 1):
            seg_start = all_points[i]
            seg_end = all_points[i + 1]
            seg_days = (seg_end - seg_start).days
            if seg_days <= 0:
                continue

            if seg_end <= lpr_reform or (seg_start < lpr_reform and seg_end <= lpr_reform):
                # 2019-08-20 前：央行贷款基准利率
                active_rate = PBOC_BENCHMARK_1Y_RATE
                rate_basis = PBOC_BENCHMARK_BASIS
                # TODO(律师核实): 基准利率适用起点日期未核实
                warnings.append(
                    "本段早于 LPR 改革日；若期间早于中国人民银行同期同类贷款基准利率适用起点（起点日期 TODO(律师核实)），请人工核对"
                )
                actual_rate = active_rate * multiplier
                rate_dec = Decimal(str(actual_rate)) / Decimal("100")
                seg_interest = (p_dec * rate_dec * Decimal(seg_days) / Decimal("365")).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                total_interest += seg_interest
                periods.append({
                    "segment_start": seg_start.strftime("%Y-%m-%d"),
                    "segment_end": seg_end.strftime("%Y-%m-%d"),
                    "days": seg_days,
                    "base_lpr": active_rate,
                    "rate_basis": rate_basis,
                    "multiplier": multiplier,
                    "applied_annual_rate": round(actual_rate, 4),
                    "interest": float(seg_interest)
                })
                continue

            active_rate = _lookup_lpr_on_date(sorted_lpr, seg_start, term)
            if active_rate is None:
                # 仍早于首期 LPR：用基准利率
                active_rate = PBOC_BENCHMARK_1Y_RATE
                rate_basis = PBOC_BENCHMARK_BASIS
            else:
                rate_basis = "全国银行间同业拆借中心公布的贷款市场报价利率（LPR）"

            actual_rate = active_rate * multiplier
            rate_dec = Decimal(str(actual_rate)) / Decimal("100")
            seg_interest = (p_dec * rate_dec * Decimal(seg_days) / Decimal("365")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            total_interest += seg_interest
            periods.append({
                "segment_start": seg_start.strftime("%Y-%m-%d"),
                "segment_end": seg_end.strftime("%Y-%m-%d"),
                "days": seg_days,
                "base_lpr": active_rate,
                "rate_basis": rate_basis,
                "multiplier": multiplier,
                "applied_annual_rate": round(actual_rate, 4),
                "interest": float(seg_interest)
            })
        rate_desc = f"同期全国银行间同业拆借中心公布的一年期贷款市场报价利率（LPR）的 {multiplier} 倍（2019-08-20前适用央行贷款基准利率）"

    # 去重 warnings
    warnings = list(dict.fromkeys(warnings))

    total_amount = p_dec + total_interest

    complaint_lines = [
        f"【利息计算明细说明】",
        f"以拖欠款项本金人民币 {p_dec:,.2f} 元为基数，自 {start_date} 起至 {end_date} 止，按照{rate_desc}标准分段计算逾期违约利息。",
        f"计息期间累计逾期 {total_days} 天，共计产生利息人民币 {total_interest:,.2f} 元（大写：{rmb_to_capital(total_interest)}），本息合计人民币 {total_amount:,.2f} 元（大写：{rmb_to_capital(total_amount)}）。",
        f"分段计息具体明细如下："
    ]
    for idx, p in enumerate(periods, 1):
        if "regime" in p:
            complaint_lines.append(
                f"  ({idx}) {p['segment_start']} 至 {p['segment_end']}（共 {p['days']} 天）：{p['regime']}，执行年化 {p['applied_annual_rate']}%，该段利息为人民币 {p['interest']:,.2f} 元；"
            )
        elif "applied_annual_rate" in p and "base_lpr" in p:
            basis_note = p.get("rate_basis") or "LPR"
            if p.get("markup_ratio") is not None:
                complaint_lines.append(
                    f"  ({idx}) {p['segment_start']} 至 {p['segment_end']}（共 {p['days']} 天）：起算日 LPR {p['base_lpr']}% × (1+{p['markup_ratio']}) = 执行年化 {p['applied_annual_rate']}%（{basis_note}），该段利息为人民币 {p['interest']:,.2f} 元；"
                )
            else:
                complaint_lines.append(
                    f"  ({idx}) {p['segment_start']} 至 {p['segment_end']}（共 {p['days']} 天）：基准 {p['base_lpr']}% × {p['multiplier']}倍 = 执行年化 {p['applied_annual_rate']}%（{basis_note}），该段利息为人民币 {p['interest']:,.2f} 元；"
                )
        else:
            complaint_lines.append(
                f"  ({idx}) {p['segment_start']} 至 {p['segment_end']}（共 {p['days']} 天）：执行年化 {p['annual_rate']}%，该段利息为人民币 {p['interest']:,.2f} 元；"
            )
    complaint_statement = "\n".join(complaint_lines)

    return {
        "principal": float(p_dec),
        "start_date": start_date,
        "end_date": end_date,
        "total_days": total_days,
        "multiplier": multiplier,
        "term": term,
        "rule_mode": rule_mode,
        "total_interest": float(total_interest),
        "total_amount": float(total_amount),
        "interest_capital": rmb_to_capital(total_interest),
        "total_amount_capital": rmb_to_capital(total_amount),
        "complaint_statement": complaint_statement,
        "segments": periods,
        "warnings": warnings,
        "lpr_data_as_of": meta["data_as_of"],
    }


# ==============================================================================
# 6. 《劳动合同法》第47/87条经济补偿金与赔偿金精算

VALID_TERMINATION_REASONS = {
    "expiry_termination",
    "employer_dismissal_with_notice",
    "mutual_agreement",
    "employee_resign_employer_fault",
    "unlawful_dismissal",
}


def _load_labor_pre2008_rules() -> dict:
    import json
    from pathlib import Path
    p = Path(__file__).resolve().parents[2] / "data" / "legal" / "labor_pre2008_rules.json"
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

# ==============================================================================
def calculate_labor_compensation(
    monthly_salary: float | Decimal,
    hire_date: str,
    termination_date: str,
    local_avg_salary: Optional[float | Decimal] = None,
    prior_30days_notice: bool = False,
    termination_reason: Optional[str] = None
) -> Dict[str, Any]:
    """
    根据《劳动合同法》第47条、第87条核算劳动争议补偿金与赔偿金。
    输出：
      - N（经济补偿）
      - N+1（含未提前30天代通知金）
      - 2N（违法解除赔偿金）
    三档精确金额及社平3倍封顶核算明细。
    """
    if termination_reason is not None and termination_reason not in VALID_TERMINATION_REASONS:
        raise ValueError(f"未知的解除事由: {termination_reason}")

    d_hire = datetime.strptime(hire_date, "%Y-%m-%d").date()
    d_term = datetime.strptime(termination_date, "%Y-%m-%d").date()

    if d_term < d_hire:
        raise ValueError("解除劳动合同日期不能早于入职日期")

    labor_warnings: List[str] = []

    salary_dec = Decimal(str(monthly_salary)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    years = d_term.year - d_hire.year
    months = d_term.month - d_hire.month
    days = d_term.day - d_hire.day

    if days < 0:
        import calendar
        prev_month = d_term.month - 1 if d_term.month > 1 else 12
        prev_year = d_term.year if d_term.month > 1 else d_term.year - 1
        days_in_prev_month = calendar.monthrange(prev_year, prev_month)[1]
        days += days_in_prev_month
        months -= 1
    if months < 0:
        years -= 1
        months += 12

    # ==========================================================================
    # 《劳动合同法》第四十七条第一款标准工龄折算规则：
    # 1. 满一年支付一个月工资；
    # 2. 六个月以上不满一年的（6个月0天至11个月29天），按一年计算；
    # 3. 不满六个月的（1天至5个月29天），按半个月计算；
    # 严禁将不满6个月中超过15天零头进位为1个月（实务纠偏）
    # ==========================================================================
    compensation_months = Decimal(str(years))
    if months >= 6:
        compensation_months += Decimal("1.0")
    elif months > 0 or days > 0:
        compensation_months += Decimal("0.5")

    # 社平三倍与年限封顶判断（全段合并核算模式）
    is_capped = False
    capped_salary = salary_dec
    cap_reason = "劳动者月薪未超过当地社会平均工资三倍，按实际月平均工资标准计算且工龄不设12年封顶。"

    if local_avg_salary is not None:
        avg_dec = Decimal(str(local_avg_salary)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        three_times_avg = avg_dec * Decimal("3")
        if salary_dec > three_times_avg:
            is_capped = True
            capped_salary = three_times_avg
            orig_months = compensation_months
            compensation_months = min(compensation_months, Decimal("12.0"))
            cap_reason = (
                f"劳动者月薪({salary_dec:,.2f}元)高于当地社平三倍({three_times_avg:,.2f}元)，"
                f"依《劳动合同法》第47条第二款，月计发基数封顶为 {three_times_avg:,.2f} 元，"
                f"补偿年限按最高12年封顶（原折算工龄 {orig_months} 个月）。"
            )

    # 1. 基础经济补偿 N
    amount_n = (capped_salary * compensation_months).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # 2. 代通知金 +1（依据《劳动合同法实施条例》第二十条，按上月实发工资标准，不受3倍封顶限制）
    notice_pay = salary_dec
    amount_n_plus_1 = amount_n + notice_pay

    # 3. 违法解除赔偿金 2N (第87条 依照第47条规定的经济补偿标准的二倍支付)
    amount_2n = (amount_n * Decimal("2")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    tenure_desc = f"{years}年{months}个月{days if days >= 0 else 0}天"

    # ==========================================================================
    # 2008年1月1日《劳动合同法》施行前后分段核算（《劳动合同法》第九十七条第三款）
    # 若入职时间在2008-01-01之前，实战中对高薪员工必须提供“分段计算”防穿仓对照：
    # - 2008年前工龄：依劳部发〔1994〕481号，月工资按实发计算，无全国统一社平三倍及12年封顶；
    # - 2008年后工龄：依《劳动合同法》第四十七条第二款，高薪者受社平三倍与最高12年封顶。
    # ==========================================================================
    segment_2008_info = None
    if d_hire < date(2008, 1, 1) and d_term >= date(2008, 1, 1):
        labor_warnings.append("2008 年前工龄按劳部发〔1994〕481号计算，以当地口径为准（需律师核实）")
        rules_cfg = _load_labor_pre2008_rules()
        reason_rules = (rules_cfg.get("rules") or {}).get(termination_reason or "")

        # 2008年前工龄（至2007-12-31）
        d_cut = date(2007, 12, 31)
        y_pre = d_cut.year - d_hire.year
        m_pre = d_cut.month - d_hire.month
        d_pre = d_cut.day - d_hire.day
        if d_pre < 0:
            m_pre -= 1
        if m_pre < 0:
            y_pre -= 1
            m_pre += 12

        # 依据 481 号与规则库判定
        if reason_rules and reason_rules.get("pays_compensation") is False:
            comp_m_pre = Decimal("0")
        else:
            # 满一年按一个月，不满一年按一年
            comp_m_pre = Decimal(str(y_pre))
            if m_pre > 0 or d_pre > 0:
                comp_m_pre += Decimal("1.0")

        if not termination_reason or (reason_rules and reason_rules.get("max_months_cap") is None):
            labor_warnings.append("该情形 2008 年前口径待律师核实")

        amt_pre = (salary_dec * comp_m_pre).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # 2008年后工龄（2008-01-01起至解除日）
        y_post = d_term.year - 2008
        m_post = d_term.month - 1
        d_post = d_term.day - 1
        if d_post < 0:
            m_post -= 1
        if m_post < 0:
            y_post -= 1
            m_post += 12
        comp_m_post = Decimal(str(y_post))
        if m_post >= 6:
            comp_m_post += Decimal("1.0")
        elif m_post > 0 or d_post > 0:
            comp_m_post += Decimal("0.5")

        if is_capped:
            comp_m_post = min(comp_m_post, Decimal("12.0"))
            amt_post = (capped_salary * comp_m_post).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        else:
            amt_post = (salary_dec * comp_m_post).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        total_segmented_n = amt_pre + amt_post
        segment_2008_info = {
            "is_applicable": True,
            "statute_basis": "《劳动合同法》第九十七条第三款及原劳部发〔1994〕481号",
            "pre_2008_tenure": f"{y_pre}年{m_pre}个月",
            "pre_2008_compensation_months": float(comp_m_pre),
            "pre_2008_salary_basis": float(salary_dec),
            "pre_2008_amount": float(amt_pre),
            "post_2008_tenure": f"{y_post}年{m_post}个月",
            "post_2008_compensation_months": float(comp_m_post),
            "post_2008_salary_basis": float(capped_salary if is_capped else salary_dec),
            "post_2008_amount": float(amt_post),
            "total_segmented_n": float(total_segmented_n),
            "total_segmented_2n": float(total_segmented_n * Decimal("2")),
            "note": "跨2008年分段精算：2008年前工龄按劳部发〔1994〕481号计算，以当地口径为准（需律师核实）；2008年后工作年限适用三倍社平及12年双封顶。",
            "warnings": list(dict.fromkeys(labor_warnings))
        }

    return {
        "monthly_salary": float(salary_dec),
        "hire_date": hire_date,
        "termination_date": termination_date,
        "tenure_str": tenure_desc,
        "compensation_months": float(compensation_months),
        "is_capped": is_capped,
        "capped_salary_used": float(capped_salary),
        "cap_reason": cap_reason,
        "tiers": {
            "N": {
                "label": "法定经济补偿金 (N)",
                "legal_basis": "《劳动合同法》第四十七条第一款",
                "amount": float(amount_n),
                "rmb_capital": rmb_to_capital(amount_n),
                "formula": f"{capped_salary:,.2f}元 × {compensation_months}个月"
            },
            "N+1": {
                "label": "未提前30天书面通知补偿 (N+1)",
                "legal_basis": "《劳动合同法》第四十条、第四十七条",
                "amount": float(amount_n_plus_1),
                "rmb_capital": rmb_to_capital(amount_n_plus_1),
                "notice_pay": float(notice_pay),
                "formula": f"经济补偿N({amount_n:,.2f}元) + 1个月代通知金({notice_pay:,.2f}元)"
            },
            "2N": {
                "label": "违法解除劳动合同赔偿金 (2N)",
                "legal_basis": "《劳动合同法》第八十七条",
                "amount": float(amount_2n),
                "rmb_capital": rmb_to_capital(amount_2n),
                "formula": f"经济补偿N({amount_n:,.2f}元) × 2倍"
            }
        },
        "segment_2008": segment_2008_info,
        "warnings": list(dict.fromkeys(labor_warnings))
    }


# ==============================================================================
# 7. 诉讼时效与除斥期间精确核算器 (《民法典》第188、194、195、199条)
# ==============================================================================
def calculate_statute_of_limitations(
    start_date: str,
    cause_type: str = "general_3y",
    interruption_events: Optional[List[Dict[str, str]]] = None,
    suspension_events: Optional[List[Dict[str, str]]] = None,
    today_date: Optional[str] = None,
    act_date: Optional[str] = None,
    damage_date: Optional[str] = None,
    holidays: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    精确核算民事诉讼时效与除斥期间：
    - 普通民事诉讼时效：3年（《民法典》第188条）
    - 国际货物买卖/技术进出口合同争议：4年（《民法典》第594条）
    - 最长权利保护期：自权利受损之日起20年（《民法典》第188条第二款）
    - 撤销权除斥期间：1年/90日（《民法典》第152条，不适用中止中断）；自行为发生日起最长5年
    - 建设工程优先受偿权除斥期间：18个月（《建工解释一》第41条，法释〔2020〕25号）
    - 一般保证保证期间（除斥期间6个月，必须起诉主债务人，《民法典》第693条）
    - 连带保证保证期间（除斥期间6个月，必须向保证人主张权利，《民法典》第693条）
    
    支持多轮时效中断事件自动推演（催告、自认还款、仲裁、诉讼），以及最后6个月法定事由时效中止（《民法典》第194条）。
    """
    d_start = datetime.strptime(start_date, "%Y-%m-%d").date()
    d_today = datetime.strptime(today_date, "%Y-%m-%d").date() if today_date else date.today()
    warnings: List[str] = []

    # 基础期限定义（月数 / 日数）
    PERIOD_RULES = {
        "general_3y": {"name": "普通民事诉讼时效（3年）", "basis": "《民法典》第一百八十八条第一款", "years": 3, "months": 36, "is_preclusive": False},
        "intl_trade_4y": {"name": "国际货物买卖/技术进出口争议（4年）", "basis": "《民法典》第五百九十四条", "years": 4, "months": 48, "is_preclusive": False},
        "guarantee_general_6m": {
            "name": "一般保证期间（法定除斥期间6个月）",
            "basis": "《民法典》第六百九十二条第二款、第六百九十三条第一款",
            "years": 0.5,
            "months": 6,
            "is_preclusive": True,
            "special_notice": "【执业穿仓红线】债权人必须在主债务届满之日起6个月内对主债务人提起诉讼或申请仲裁！仅发律师函催告无效！未在6个月内起诉主债务人的，保证人免责！"
        },
        "guarantee_joint_6m": {
            "name": "连带责任保证期间（法定除斥期间6个月）",
            "basis": "《民法典》第六百九十二条第二款、第六百九十三条第二款",
            "years": 0.5,
            "months": 6,
            "is_preclusive": True,
            "special_notice": "【执业穿仓红线】债权人必须在主债务届满之日起6个月内向保证人提出承担保证责任请求！自请求之日起，对保证人的3年诉讼时效单独起算。"
        },
        "cancel_right_1y": {
            "name": "欺诈/显失公平撤销权（1年）",
            "basis": "《民法典》第一百五十二条（律师注明：原文未在线逐字核对）",
            "years": 1,
            "months": 12,
            "is_preclusive": True,
            "is_cancel_right": True,
        },
        "cancel_mistake_90d": {
            "name": "重大误解撤销权（90日）",
            "basis": "《民法典》第一百五十二条（律师注明：原文未在线逐字核对）",
            "years": 0,
            "months": 0,
            "days": 90,
            "is_preclusive": True,
            "is_cancel_right": True,
        },
        "cancel_duress_1y": {
            "name": "胁迫终止之日起撤销权（除斥期间1年）",
            "basis": "《民法典》第一百五十二条第一款第二项（律师注明：原文未在线逐字核对）",
            "years": 1,
            "months": 12,
            "is_preclusive": True,
            "is_cancel_right": True,
        },
        "construction_priority_18m": {
            "name": "建设工程价款优先受偿权（除斥期间18个月）",
            "basis": "《最高人民法院关于审理建设工程施工合同纠纷案件适用法律问题的解释（一）》第四十一条（法释〔2020〕25号）",
            "years": 1.5,
            "months": 18,
            "is_preclusive": True,
            "special_notice": "起算点为发包人应当给付建设工程价款之日，请按此填写起算日",
        },
        "rescission_right_1y": {"name": "合同解除权除斥期间（合理催告期满或1年）", "basis": "《民法典》第五百六十四条", "years": 1, "months": 12, "is_preclusive": True}
    }

    rule = PERIOD_RULES.get(cause_type, PERIOD_RULES["general_3y"])
    is_preclusive = rule["is_preclusive"]
    is_cancel_right = bool(rule.get("is_cancel_right"))

    def add_years_exact(d: date, years: int) -> date:
        try:
            return d.replace(year=d.year + years)
        except ValueError:
            # 润年2月29日顺延处理
            return d.replace(year=d.year + years, month=2, day=28)

    # 初始到期日
    if rule.get("days"):
        initial_expire = d_start + timedelta(days=int(rule["days"]))
    elif rule["months"] % 12 == 0:
        initial_expire = add_years_exact(d_start, int(rule["years"]))
    else:
        initial_expire = add_months_exact(d_start, rule["months"])

    # 20年最长保护期：从权利受到损害之日 damage_date 起算（《民法典》第188条第二款）
    if damage_date:
        d_damage = datetime.strptime(damage_date, "%Y-%m-%d").date()
        max_20y_expire = add_years_exact(d_damage, 20)
    else:
        max_20y_expire = add_years_exact(d_start, 20)
        warnings.append("未提供权利受到损害之日，20 年最长期间按知道或应当知道之日近似计算")

    timeline_log = [{
        "date": start_date,
        "event": "起算点（知道或应当知道权利受损/义务人及除斥事由起算）",
        "action": "初始时效起算",
        "expire_date": initial_expire.strftime("%Y-%m-%d")
    }]

    current_expire = initial_expire
    effective_interruptions = []

    INTERRUPTION_TYPE_MAP = {
        "demand": "demand",
        "催告": "demand",
        "催告/主张": "demand",
        "主张权利": "demand",
        "acknowledgment": "acknowledgment",
        "自认": "acknowledgment",
        "自认/还款承诺": "acknowledgment",
        "同意履行": "acknowledgment",
        "义务人同意履行": "acknowledgment",
        "lawsuit": "lawsuit",
        "起诉": "lawsuit",
        "提起诉讼": "lawsuit",
        "arbitration": "arbitration",
        "仲裁": "arbitration",
        "申请仲裁": "arbitration",
        "other_equivalent": "other_equivalent",
        "同等效力情形": "other_equivalent",
    }

    if not is_preclusive and interruption_events:
        # 按事件时间先后排序
        sorted_events = sorted(interruption_events, key=lambda x: x.get("date", ""))
        for ev in sorted_events:
            ev_date_str = ev.get("date", "")
            ev_desc = ev.get("description", "主张权利/提起仲裁/当事人承诺还款")
            raw_type = ev.get("type", "demand")
            norm_type = INTERRUPTION_TYPE_MAP.get(raw_type, raw_type)
            if not ev_date_str:
                continue
            ev_d = datetime.strptime(ev_date_str, "%Y-%m-%d").date()

            # 只有在时效尚未届满前发生的行为才发生中断效力
            if ev_d <= current_expire:
                # 诉讼、仲裁、同等效力须提供 proceeding_end_date（程序终结日）
                if norm_type in ("lawsuit", "arbitration", "other_equivalent"):
                    proc_end_str = ev.get("proceeding_end_date")
                    if not proc_end_str:
                        warnings.append(f"{ev_desc}（{norm_type}）：程序未终结或终结日未知，时效暂不重新起算")
                        timeline_log.append({
                            "date": ev_date_str,
                            "event": f"【时效暂不重新起算】{raw_type}: {ev_desc}（程序未终结或终结日未知，时效暂不重新起算）",
                            "action": "程序未终结或终结日未知，时效暂不重新起算",
                            "expire_date": current_expire.strftime("%Y-%m-%d")
                        })
                        continue
                    recalc_start = datetime.strptime(proc_end_str, "%Y-%m-%d").date()
                    action_note = f"诉讼/仲裁程序于 {proc_end_str} 终结，时效自此日重新起算{rule['years']}年"
                else:
                    recalc_start = ev_d
                    action_note = f"时效中断并自事件发生日重新起算{rule['years']}年"

                new_expire = add_years_exact(recalc_start, int(rule["years"]))
                if new_expire > max_20y_expire:
                    new_expire = max_20y_expire

                current_expire = new_expire
                timeline_log.append({
                    "date": ev_date_str,
                    "event": f"【时效中断】{raw_type}: {ev_desc}",
                    "action": action_note,
                    "expire_date": current_expire.strftime("%Y-%m-%d")
                })
                effective_interruptions.append(ev)
            else:
                timeline_log.append({
                    "date": ev_date_str,
                    "event": f"【无效行为】{ev_desc}",
                    "action": "此时诉讼时效已于此前届满，普通催告行为不产生时效重新起算效力（除非构成新的债务承认/放弃时效利益）",
                    "expire_date": current_expire.strftime("%Y-%m-%d")
                })

    # ==========================================================================
    # 诉讼时效中止核算（《民法典》第一百九十四条）
    # 规则：在诉讼时效期间的最后六个月内，因法定障碍不能行使请求权的，时效中止；
    # 自中止时效的原因消除之日起满六个月，诉讼时效期间届满。
    # ==========================================================================
    effective_suspensions = []
    if not is_preclusive and suspension_events:
        for ev in suspension_events:
            ev_date_str = ev.get("date", "")
            ev_desc = ev.get("description", "不可抗力/法定代理人丧失等法定障碍")
            ev_resume_str = ev.get("resume_date", "")
            if not ev_date_str:
                continue
            ev_d = datetime.strptime(ev_date_str, "%Y-%m-%d").date()
            six_months_before = add_months_exact(current_expire, -6)

            if six_months_before <= ev_d <= current_expire:
                resume_d = datetime.strptime(ev_resume_str, "%Y-%m-%d").date() if ev_resume_str else d_today
                new_expire = add_months_exact(resume_d, 6)
                if new_expire > current_expire:
                    current_expire = min(new_expire, max_20y_expire)
                    timeline_log.append({
                        "date": ev_date_str,
                        "event": f"【时效中止】最后6个月内发生法定障碍: {ev_desc}",
                        "action": f"依据《民法典》第194条，自原因消除日({resume_d.strftime('%Y-%m-%d')})顺延满6个月",
                        "expire_date": current_expire.strftime("%Y-%m-%d")
                    })
                    effective_suspensions.append(ev)

    # 撤销权：自民事法律行为发生之日起 5 年最长除斥（《民法典》第152条）
    five_year_cap_date = None
    if is_cancel_right:
        if act_date:
            d_act = datetime.strptime(act_date, "%Y-%m-%d").date()
            five_year_cap_date = add_years_exact(d_act, 5)
            if current_expire > five_year_cap_date:
                current_expire = five_year_cap_date
                timeline_log.append({
                    "date": act_date,
                    "event": "民事法律行为发生日",
                    "action": "适用撤销权最长5年除斥期间上限",
                    "expire_date": current_expire.strftime("%Y-%m-%d")
                })
        else:
            warnings.append("未提供行为发生日，未校验 5 年最长期限")

    # 最终届满日如为法定节假日，调用节假日数据顺延（《民法典》第二百零三条）
    holiday_set = set(holidays) if holidays is not None else _load_cn_holidays_set(current_expire.year)
    if holidays is None:
        holiday_set |= _load_cn_holidays_set(current_expire.year + 1)

    orig_final_date = current_expire
    extended = False
    while current_expire.strftime("%Y-%m-%d") in holiday_set:
        current_expire = current_expire + timedelta(days=1)
        extended = True

    if extended:
        timeline_log.append({
            "date": orig_final_date.strftime("%Y-%m-%d"),
            "event": f"期间最后一日（{orig_final_date.strftime('%Y-%m-%d')}）为法定节假日，顺延至 {current_expire.strftime('%Y-%m-%d')}（顺延）",
            "action": "法定节假日顺延",
            "expire_date": current_expire.strftime("%Y-%m-%d")
        })

    days_remaining = (current_expire - d_today).days
    is_expired = days_remaining < 0

    if is_expired:
        status_level = "CRITICAL_EXPIRED"
        status_label = "【已过时效/除斥期间届满】"
        risk_alert = "诉讼时效或除斥期间已届满！对方若提出时效抗辩，己方法定胜诉权将被阻断；除斥期间权利直接消灭。需紧急核查是否存在未入卷的催告、还款协议自认或时效利益放弃证据。"
    elif days_remaining <= 30:
        status_level = "URGENT_RED"
        status_label = f"【极度紧急：仅剩 {days_remaining} 天】"
        risk_alert = f"执业重大红线警报：距时效届满仅余 {days_remaining} 天！必须立即采取中断措施（发送EMS律师催告函、向公证处申请保全送达、向法院提起立案或申请调解立案）。"
    elif days_remaining <= 90:
        status_level = "WARNING_AMBER"
        status_label = f"【高危预警：剩余 {days_remaining} 天】"
        risk_alert = f"注意防范时效风险：距离到期还剩 {days_remaining} 天，请及时推进起诉或获取借款人新的微信书面确认还款留痕。"
    else:
        status_level = "SAFE_GREEN"
        status_label = f"【时效充裕：剩余 {days_remaining} 天】"
        risk_alert = "诉讼时效或期间在执业安全窗口内。"

    return {
        "cause_type": cause_type,
        "rule_name": rule["name"],
        "legal_basis": rule["basis"],
        "special_notice": rule.get("special_notice"),
        "is_preclusive": is_preclusive,
        "preclusive_note": "除斥期间不适用中止、中断和延长规定，到期实体权利直接消灭" if is_preclusive else "适用法定中止、中断规则（《民法典》第194、195条）",
        "start_date": start_date,
        "act_date": act_date,
        "calculation_benchmark_today": d_today.strftime("%Y-%m-%d"),
        "initial_expire_date": initial_expire.strftime("%Y-%m-%d"),
        "final_expire_date": current_expire.strftime("%Y-%m-%d"),
        "five_year_cap_date": five_year_cap_date.strftime("%Y-%m-%d") if five_year_cap_date else None,
        "max_20y_deadline": max_20y_expire.strftime("%Y-%m-%d"),
        "max_20y_expire": max_20y_expire.strftime("%Y-%m-%d"),
        "days_remaining": days_remaining,
        "is_expired": is_expired,
        "status_level": status_level,
        "status_label": status_label,
        "risk_alert": risk_alert,
        "timeline_log": timeline_log,
        "effective_interruptions_count": len(effective_interruptions),
        "effective_suspensions_count": len(effective_suspensions),
        "warnings": warnings,
    }


# ==============================================================================
# 8. 财产保全续查封续冻结红线精算 (法释〔2016〕22号第十八条)
# ==============================================================================
def calculate_preservation_renewal(
    preservation_type: str,
    start_date: str,
    custom_years: Optional[float] = None,
    today_date: Optional[str] = None,
    internal_reminder_days: int = 30,
) -> Dict[str, Any]:
    """
    财产保全续行期限核算。
    续行申请时点：应在保全期限届满七日前申请续行
    ——《财产保全规定》（法释〔2016〕22号）第十八条，来源 https://www.court.gov.cn/zixun/xiangqing/30101.html
    期限上限（存款1年/动产2年/不动产及其他财产权3年）出自《民诉法解释》相关条款（条号 TODO(律师核实)）。
    """
    d_start = datetime.strptime(start_date, "%Y-%m-%d").date()
    d_today = datetime.strptime(today_date, "%Y-%m-%d").date() if today_date else date.today()

    TYPE_RULES = {
        "bank_deposit": {
            "name": "银行存款及现金理财冻结",
            "max_years": 1,
            "advance_days": 7,
            "statute": "《财产保全规定》（法释〔2016〕22号）第十八条；期限上限依据《民诉法解释》相关条款（条号 TODO(律师核实)）",
            "statute_url": "https://www.court.gov.cn/zixun/xiangqing/30101.html",
            "desc": "冻结银行存款及其他资金的期限不得超过一年；应在届满七日前申请续行"
        },
        "movable_property": {
            "name": "动产（汽车、机器设备、存货）查封扣押",
            "max_years": 2,
            "advance_days": 7,
            "statute": "《财产保全规定》（法释〔2016〕22号）第十八条；期限上限依据《民诉法解释》相关条款（条号 TODO(律师核实)）",
            "statute_url": "https://www.court.gov.cn/zixun/xiangqing/30101.html",
            "desc": "查封、扣押动产的期限不得超过二年；应在届满七日前申请续行"
        },
        "real_estate_equity": {
            "name": "不动产（房产土地）与股权/知识产权冻结",
            "max_years": 3,
            "advance_days": 7,
            "statute": "《财产保全规定》（法释〔2016〕22号）第十八条；期限上限依据《民诉法解释》相关条款（条号 TODO(律师核实)）",
            "statute_url": "https://www.court.gov.cn/zixun/xiangqing/30101.html",
            "desc": "查封不动产、冻结其他财产权的期限不得超过三年；应在届满七日前申请续行"
        }
    }

    if preservation_type not in TYPE_RULES:
        allowed = ", ".join(TYPE_RULES.keys())
        raise ValueError(f"preservation_type 非法，允许值: {allowed}")

    rule = TYPE_RULES[preservation_type]
    years = custom_years if custom_years else rule["max_years"]
    advance_days = rule["advance_days"]

    def add_years_exact(d: date, y: float) -> date:
        whole_y = int(y)
        try:
            res = d.replace(year=d.year + whole_y)
        except ValueError:
            res = d.replace(year=d.year + whole_y, month=2, day=28)
        if y > whole_y:
            import calendar
            target_month = (res.month + 6 - 1) % 12 + 1
            target_year = res.year + (res.month + 6 - 1) // 12
            max_day = calendar.monthrange(target_year, target_month)[1]
            res = date(target_year, target_month, min(res.day, max_day))
        return res

    expire_date = add_years_exact(d_start, years)
    renewal_deadline = expire_date - timedelta(days=advance_days)
    internal_reminder_date = expire_date - timedelta(days=int(internal_reminder_days))

    days_to_expire = (expire_date - d_today).days
    days_to_renewal = (renewal_deadline - d_today).days

    if days_to_renewal < 0 and days_to_expire >= 0:
        status_level = "CRITICAL_BREACH"
        status_label = "【已晚于法定续行申请时点】"
        alert_msg = "已晚于法定的续行申请时点（届满七日前），请立即核实保全状态并与承办法官沟通"
    elif days_to_expire < 0:
        status_level = "EXPIRED"
        status_label = "【保全期限已届满】"
        alert_msg = "该财产查封/冻结期限已届满，请立即核实保全状态并与承办法官沟通"
    elif days_to_renewal <= 15:
        status_level = "URGENT"
        status_label = f"【极度紧迫：距续行申请截止仅余 {days_to_renewal} 天】"
        alert_msg = f"须在 {renewal_deadline.strftime('%Y-%m-%d')} 前（届满七日前）向法院提交续行财产保全申请；距离法定截止只剩 {days_to_renewal} 天。"
    elif days_to_renewal <= 45:
        status_level = "WARNING"
        status_label = f"【续封预警窗口：剩余 {days_to_renewal} 天】"
        alert_msg = f"进入续封准备期：建议在 {renewal_deadline.strftime('%Y-%m-%d')} 前准备好续保担保材料与申请书并联系承办法官。"
    else:
        status_level = "SAFE"
        status_label = f"【保全状态安全：距续行申请截止 {days_to_renewal} 天】"
        alert_msg = "在正常保全有效期内。"

    return {
        "preservation_type": preservation_type,
        "type_name": rule["name"],
        "statute_basis": rule["statute"],
        "statute_url": rule.get("statute_url"),
        "statute_description": rule["desc"],
        "start_date": start_date,
        "expire_date": expire_date.strftime("%Y-%m-%d"),
        "advance_days_required": advance_days,
        "renewal_application_deadline": renewal_deadline.strftime("%Y-%m-%d"),
        "internal_reminder_days": int(internal_reminder_days),
        "internal_reminder_date": internal_reminder_date.strftime("%Y-%m-%d"),
        "internal_reminder_note": "内部提醒日，非法定期限",
        "days_to_expire": days_to_expire,
        "days_to_renewal_deadline": days_to_renewal,
        "status_level": status_level,
        "status_label": status_label,
        "alert_message": alert_msg
    }


# ==============================================================================
# 8b. 上诉期截止日测算（《民事诉讼法》第171条；送达次日起算）
# ==============================================================================
def _load_cn_holidays_set(year: Optional[int] = None) -> set:
    """从 data/legal/holidays_cn.json 加载节假日；verified 可能为 false。"""
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "data" / "legal" / "holidays_cn.json"
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return set()
    years = data.get("years") or {}
    out = set()
    if year is not None and str(year) in years:
        out.update(years[str(year)].get("dates") or [])
    else:
        for yinfo in years.values():
            out.update(yinfo.get("dates") or [])
    return out


def calculate_appeal_deadline(
    service_date: str,
    judgment_type: str,
    holidays: Optional[List[str]] = None,
    treat_weekend_as_holiday: bool = True,
) -> Dict[str, Any]:
    """
    上诉期截止日测算。
    《民事诉讼法》（2023修正）第171条：判决15日、裁定10日，自送达之日起计算；
    实务口径：自送达次日起算满相应日数之日为届满日；
    最后一日为法定节假日的，顺延至节假日后第一日（律师 L-I19）。
    周六、周日是否按节假日顺延：TODO(律师核实)；默认 treat_weekend_as_holiday=True 并在输出注明。
    """
    jt = (judgment_type or "").strip().lower()
    if jt in ("judgment", "判决", "判决书"):
        jt_norm = "judgment"
        period_days = 15
    elif jt in ("ruling", "裁定", "裁定书"):
        jt_norm = "ruling"
        period_days = 10
    else:
        raise ValueError('judgment_type 仅允许 "judgment"/"ruling"（或判决/裁定）')

    d_service = datetime.strptime(service_date, "%Y-%m-%d").date()
    # 送达次日起算：届满日 = 送达日 + period_days
    deadline = d_service + timedelta(days=period_days)

    holiday_set = set(holidays) if holidays is not None else _load_cn_holidays_set(d_service.year)
    # 若跨年，补充下一年
    if holidays is None:
        holiday_set |= _load_cn_holidays_set(deadline.year)

    def _is_non_working(d: date) -> bool:
        if d.strftime("%Y-%m-%d") in holiday_set:
            return True
        if treat_weekend_as_holiday and d.weekday() >= 5:
            return True
        return False

    extended = False
    while _is_non_working(deadline):
        deadline = deadline + timedelta(days=1)
        extended = True

    notes = [
        "起算：自送达次日起算（《民事诉讼法》第一百七十一条；律师 L-I19）。",
        f"期间：{'判决十五日' if jt_norm == 'judgment' else '裁定十日'}。",
        "最后一日为法定节假日的，以节假日后的第一日为期限届满日。",
        "周六、周日是否按节假日顺延的口径 TODO(律师核实)；"
        f"当前配置 treat_weekend_as_holiday={treat_weekend_as_holiday}。",
    ]
    if holidays is None:
        notes.append("节假日数据来源 data/legal/holidays_cn.json（source 为 TODO，verified 可能为 false）。")

    return {
        "service_date": service_date,
        "judgment_type": jt_norm,
        "period_days": period_days,
        "deadline": deadline.strftime("%Y-%m-%d"),
        "extended_for_holiday_or_weekend": extended,
        "treat_weekend_as_holiday": treat_weekend_as_holiday,
        "holidays_applied": sorted(holiday_set) if holidays is not None else "loaded_from_file_or_empty",
        "notes": notes,
        "legal_basis": "《中华人民共和国民事诉讼法》（2023修正）第一百七十一条",
    }


# ==============================================================================
# 9. 规范性法律文件现行有效性与废止拦截核验引擎
# 废止表/关键现行法名一律从 data/legal 统一加载（见 gateway.utils.legal_data）
# ==============================================================================


# ==============================================================================
# 8c. 迟延履行期间加倍部分债务利息计算器 (《民事诉讼法》第264条、法释〔2014〕8号)
# ==============================================================================
def _load_delay_interest_rate() -> float:
    from pathlib import Path
    p = Path(__file__).resolve().parents[2] / "data" / "legal" / "delay_interest.json"
    try:
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
            return float(d.get("daily_rate", 0.000175))
    except Exception:
        return 0.000175


def calculate_delayed_performance_interest(
    principal_unpaid: float | Decimal,
    start_date: str,
    end_date: str,
    daily_rate: Optional[float | Decimal] = None,
) -> Dict[str, Any]:
    """
    根据《民事诉讼法》第二百六十四条及法释〔2014〕8号核算迟延履行期间加倍部分债务利息。
    加倍部分债务利息 = 未清偿本金 × 日利率（默认日万分之一点七五）× 迟延天数。
    注意：只计算加倍部分，一般债务利息另计。
    """
    p_dec = Decimal(str(principal_unpaid)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if p_dec <= 0:
        raise ValueError("未清偿本金必须大于0")

    d_start = datetime.strptime(start_date, "%Y-%m-%d").date()
    d_end = datetime.strptime(end_date, "%Y-%m-%d").date()
    if d_end < d_start:
        raise ValueError("截止日期不能早于起算日期")

    days = (d_end - d_start).days
    warnings = ["日利率依据需律师核实：法释〔2014〕8号规定日万分之一点七五（律师未在线核实）"]

    if daily_rate is not None:
        rate_val = Decimal(str(daily_rate))
    else:
        rate_val = Decimal(str(_load_delay_interest_rate()))

    interest = (p_dec * rate_val * Decimal(days)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    return {
        "principal_unpaid": float(p_dec),
        "start_date": start_date,
        "end_date": end_date,
        "days": days,
        "daily_rate": float(rate_val),
        "interest": float(interest),
        "interest_capital": rmb_to_capital(interest),
        "legal_basis": "《中华人民共和国民事诉讼法》第二百六十四条；最高人民法院关于执行程序中计算迟延履行期间的债务利息适用法律若干问题的解释（法释〔2014〕8号）",
        "scope_note": "本计算器仅核算迟延履行期间加倍部分债务利息，原生效法律文书确定的一般债务利息另行计付。",
        "warnings": warnings,
    }


# ==============================================================================
# 8d. 违约金调减测算参考 (《合同编通则解释》第65条)
# ==============================================================================
def calculate_penalty_adjustment_reference(
    agreed_penalty: float | Decimal,
    actual_loss: float | Decimal,
) -> Dict[str, Any]:
    """
    违约金调减参考测算。
    依据《最高人民法院关于适用〈中华人民共和国民法典〉合同编通则若干问题的解释》第六十五条（原文需律师核实）：
    约定违约金超过造成损失的百分之三十的，一般可以认定为“过分高于造成的损失”。
    30% 是认定“过分高于”的一般标准，不是调减后的上限；是否调减及调减幅度由法院综合衡量。
    本计算器不输出“调减后金额”。
    """
    p_dec = Decimal(str(agreed_penalty)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    l_dec = Decimal(str(actual_loss)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if l_dec <= 0:
        raise ValueError("实际损失必须大于0")
    if p_dec < 0:
        raise ValueError("约定违约金不能为负数")

    ratio = (p_dec / l_dec) - Decimal("1.0")
    exceeds_30 = ratio > Decimal("0.30")

    note = (
        "30% 是认定'过分高于'的一般标准，不是调减后的上限；"
        "是否调减及调减幅度由法院综合衡量，不预设调减后固定金额。"
    )

    return {
        "agreed_penalty": float(p_dec),
        "actual_loss": float(l_dec),
        "excess_amount": float(max(p_dec - l_dec, Decimal("0"))),
        "ratio": float(ratio),
        "ratio_percent": f"{float(ratio * 100):.2f}%",
        "exceeds_30_percent": bool(exceeds_30),
        "evaluation": "约定违约金超过造成损失的30%，一般可以认定为'过分高于造成的损失'" if exceeds_30 else "约定违约金未超过造成损失的30%，一般不认定为过分高于造成的损失",
        "note": note,
        "legal_basis": "《最高人民法院关于适用〈中华人民共和国民法典〉合同编通则若干问题的解释》第六十五条（原文需律师核实）",
        "warnings": ["本参考测算仅供诉讼攻防参考，违约金司法酌减标准以法官裁量为准（需律师核实）"],
    }


def _load_abrogated_laws_db():
    """从统一数据文件加载废止法规（兼容旧字段形状）。"""
    from gateway.utils.legal_data import load_abrogated_laws, normalize_law_name

    out = {}
    for row in load_abrogated_laws():
        key = normalize_law_name(row.get("name") or "")
        if not key or key.startswith("TODO"):
            continue
        out[key] = {
            "full_name": f"《{row.get('full_name') or row.get('name')}》",
            "status": "已废止",
            "abrogated_date": row.get("abrogated_date"),
            "replaced_by": row.get("replaced_by"),
            "risk_tip": row.get("risk_tip") or "",
            "basis": row.get("basis"),
            "verified": row.get("verified", 1),
        }
    return out


def _extract_law_names_for_validity(citation_text: str) -> List[str]:
    """书名号优先；无书名号时对已知规范名做最长匹配且要求前后非汉字延续。"""
    import re
    from gateway.utils.legal_data import (
        get_abrogated_by_normalized,
        known_law_canonical_names,
        normalize_law_name,
    )

    found: List[str] = []
    for m in re.finditer(r"《([^》]+)》", citation_text):
        found.append(normalize_law_name(m.group(1)))

    if found:
        return found

    # 无书名号：最长匹配优先
    known = sorted(known_law_canonical_names() | set(get_abrogated_by_normalized().keys()), key=len, reverse=True)
    occupied = [False] * len(citation_text)
    for name in known:
        if not name or len(name) < 2:
            continue
        start = 0
        while True:
            idx = citation_text.find(name, start)
            if idx < 0:
                break
            end = idx + len(name)
            # 前后不得是汉字延续
            before_ok = idx == 0 or not ("\u4e00" <= citation_text[idx - 1] <= "\u9fff")
            after_ok = end >= len(citation_text) or not ("\u4e00" <= citation_text[end] <= "\u9fff")
            if before_ok and after_ok and not any(occupied[idx:end]):
                found.append(name)
                for i in range(idx, end):
                    occupied[i] = True
            start = idx + 1
    return found


def verify_statutory_validity(citation_text: str, incident_date: Optional[str] = None) -> Dict[str, Any]:
    """
    核验引用的法条或规范性文件是否现行有效、是否已被废止或由新法吸收替换。
    结合争议发生时间（incident_date）进行法不溯及既往的时间效力分析。
    """
    from gateway.utils.legal_data import get_abrogated_by_normalized, known_law_canonical_names
    from gateway.utils.legal_texts import CIVIL_CODE_TIME_EFFECT_ART1_PARA2

    clean_text = citation_text.strip()
    detected_abrogated = []
    detected_valid = []
    abrogated_map = get_abrogated_by_normalized()
    known_valid = known_law_canonical_names() - set(abrogated_map.keys())

    names = _extract_law_names_for_validity(clean_text)
    seen = set()
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        if name in abrogated_map:
            info = abrogated_map[name]
            detected_abrogated.append({
                "keyword": name,
                "full_name": f"《{info.get('full_name') or name}》" if not str(info.get("full_name", "")).startswith("《") else info.get("full_name"),
                "status": "已废止",
                "abrogated_date": info.get("abrogated_date"),
                "replaced_by": info.get("replaced_by"),
                "risk_tip": info.get("risk_tip") or "",
            })
        elif name in known_valid:
            detected_valid.append({
                "keyword": name,
                "full_name": f"《{name}》",
                "status": "现行有效或可识别",
                "effective_date": None,
            })

    time_validity_note = ""
    is_safe = len(detected_abrogated) == 0

    if detected_abrogated:
        if incident_date:
            d_inc = datetime.strptime(incident_date, "%Y-%m-%d").date()
            d_mfd = date(2021, 1, 1)
            if d_inc < d_mfd:
                time_validity_note = (
                    f"争议法律事实发生于 {incident_date}（早于《民法典》施行日2021年1月1日）。"
                    "依照《最高人民法院关于适用〈中华人民共和国民法典〉时间效力的若干规定》第一条第二款："
                    f"『{CIVIL_CODE_TIME_EFFECT_ART1_PARA2}』"
                    "本案援引旧法可能被法院采纳，但文书中必须增加民法典时间效力适用过渡条款说明！"
                )
            else:
                time_validity_note = (
                    f"争议法律事实发生于 {incident_date}（晚于《民法典》施行日2021年1月1日）。"
                    "严格禁止直接引用已废止的旧法作为裁判或诉求依据，否则将产生致命败诉或补正质证破绽！"
                )
        else:
            time_validity_note = (
                "检测到援引了已废止法规！请确认法律事实发生时间；"
                f"时间效力规定第一条第二款：{CIVIL_CODE_TIME_EFFECT_ART1_PARA2}"
            )

    return {
        "query_citation": clean_text,
        "is_safe": is_safe,
        "incident_date": incident_date,
        "detected_abrogated": detected_abrogated,
        "detected_valid": detected_valid,
        "time_validity_note": time_validity_note,
        "summary": "【现行合规】所检法条均在有效库内。" if is_safe else "【执业警示】检测到援引已废止法规，存在裁判不予采纳风险！"
    }


# ==============================================================================
# 9. 商业和解与以物抵债现值/回收率精算引擎 (Settlement NPV & Debt-for-Asset Simulator)
# ==============================================================================
def calculate_settlement_npv_and_recovery(
    total_claim_nominal: float | Decimal,
    plan_type: str = "hybrid",
    annual_discount_rate: float = 0.08,
    installments: Optional[List[Dict[str, Any]]] = None,
    asset_plan: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    商业诉讼和解与以物抵债（工抵房/设备/股权）净现值与真实回收率精算。
    针对一线合伙人核心痛点：刺破债务人'名义还款/虚高评估价'假象，
    穿透工程款在先优先受偿权、在先抵押权、司法法拍流拍折价、处置税费及时间折现，
    计算真实净现值(NPV)、实际回收率(Effective Recovery Rate)及实质让利幅度(Haircut)。
    """
    try:
        claim_nominal = float(Decimal(str(total_claim_nominal)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    except Exception as e:
        raise ValueError(f"无效的债权标的金额: {total_claim_nominal}") from e
    if claim_nominal <= 0:
        raise ValueError("债权标的名义总额须大于 0")

    discount_rate = max(0.001, min(0.50, float(annual_discount_rate)))
    plan_type = (plan_type or "").strip().lower()
    allowed_plans = ("cash_installments", "debt_for_asset", "hybrid")
    if plan_type not in allowed_plans:
        raise ValueError(f"plan_type 非法，允许值: {', '.join(allowed_plans)}")

    # 1. 现金分期现值核算
    installments_breakdown = []
    cash_nominal_total = 0.0
    cash_npv_total = 0.0

    if plan_type in ["cash_installments", "hybrid"] and installments:
        cum_nominal = 0.0
        cum_npv = 0.0
        for idx, item in enumerate(installments, 1):
            amount = float(item.get("amount", 0.0))
            months = int(item.get("months", 1))
            note = item.get("note", f"第 {idx} 期分期还款")
            if amount <= 0 or months < 0:
                continue

            discount_factor = 1.0 / ((1.0 + discount_rate) ** (months / 12.0))
            npv_amount = amount * discount_factor

            cash_nominal_total += amount
            cash_npv_total += npv_amount
            cum_nominal += amount
            cum_npv += npv_amount

            installments_breakdown.append({
                "period": idx,
                "note": note,
                "due_months": months,
                "nominal_amount": round(amount, 2),
                "discount_factor": round(discount_factor, 4),
                "npv_amount": round(npv_amount, 2),
                "cumulative_nominal": round(cum_nominal, 2),
                "cumulative_npv": round(cum_npv, 2),
                "time_erosion_loss": round(amount - npv_amount, 2)
            })

    # 2. 以物抵债清算净值与折现核算
    asset_info = {}
    asset_nominal_val = 0.0
    asset_auction_gross = 0.0
    asset_equity_after_liens = 0.0
    asset_net_realizable = 0.0
    asset_npv = 0.0

    if plan_type in ["debt_for_asset", "hybrid"] and asset_plan:
        asset_name = str(asset_plan.get("asset_name", "抵债不动产/在建工程/股权"))
        asset_nominal_val = float(asset_plan.get("nominal_asset_valuation", 0.0))
        prior_liens = float(asset_plan.get("prior_liens", 0.0))
        auction_discount = float(asset_plan.get("auction_discount_rate", 0.70))
        tax_cost_rate = float(asset_plan.get("liquidation_costs_rate", 0.12))
        liq_months = int(asset_plan.get("time_to_liquidate_months", 18))
        encumbrance_status = str(asset_plan.get("encumbrance_status", "待核实权属与查封登记"))

        # 司法法拍折价（最高法关于民事执行中拍卖变卖规定：一拍不低于评估价70%，二拍不低于一拍80%即56%）
        auction_discount = max(0.30, min(1.0, auction_discount))
        tax_cost_rate = max(0.0, min(0.40, tax_cost_rate))
        liq_months = max(1, liq_months)

        asset_auction_gross = asset_nominal_val * auction_discount
        auction_discount_loss = asset_nominal_val - asset_auction_gross

        # 扣除在先优先权（建设工程价款优先受偿权、第一顺位银行抵押权、劳动报酬等）
        asset_equity_after_liens = max(0.0, asset_auction_gross - prior_liens)
        uncovered_prior_debt = max(0.0, prior_liens - asset_auction_gross)

        # 扣除处置税费（土增税、契税、印花税、评估拍卖处置费及持有维护成本）
        taxes_and_costs = asset_equity_after_liens * tax_cost_rate
        asset_net_realizable = max(0.0, asset_equity_after_liens - taxes_and_costs)

        # 变现周期时间折现 NPV
        asset_discount_factor = 1.0 / ((1.0 + discount_rate) ** (liq_months / 12.0))
        asset_npv = asset_net_realizable * asset_discount_factor
        asset_time_erosion = asset_net_realizable - asset_npv

        asset_info = {
            "asset_name": asset_name,
            "nominal_valuation": round(asset_nominal_val, 2),
            "auction_discount_rate": round(auction_discount, 4),
            "auction_gross_value": round(asset_auction_gross, 2),
            "auction_discount_loss": round(auction_discount_loss, 2),
            "prior_liens": round(prior_liens, 2),
            "uncovered_prior_debt": round(uncovered_prior_debt, 2),
            "equity_after_liens": round(asset_equity_after_liens, 2),
            "liquidation_costs_rate": round(tax_cost_rate, 4),
            "taxes_and_carrying_costs": round(taxes_and_costs, 2),
            "net_realizable_cash": round(asset_net_realizable, 2),
            "liquidation_period_months": liq_months,
            "asset_discount_factor": round(asset_discount_factor, 4),
            "asset_npv": round(asset_npv, 2),
            "time_erosion_loss": round(asset_time_erosion, 2),
            "encumbrance_status": encumbrance_status
        }

    # 3. 综合汇总对比与虚胖差额
    total_nominal_settlement = cash_nominal_total + asset_nominal_val
    total_npv_settlement = cash_npv_total + asset_npv

    nominal_recovery_rate = (total_nominal_settlement / claim_nominal) * 100.0
    effective_recovery_rate = (total_npv_settlement / claim_nominal) * 100.0
    economic_haircut_rate = max(0.0, 100.0 - effective_recovery_rate)
    illusion_gap = max(0.0, nominal_recovery_rate - effective_recovery_rate)

    # 4. 生成合伙人实战战术决策与谈判备忘录
    tactical_memo = _generate_partner_settlement_memo(
        claim_nominal=claim_nominal,
        nominal_settlement=total_nominal_settlement,
        total_npv=total_npv_settlement,
        nominal_rate=nominal_recovery_rate,
        effective_rate=effective_recovery_rate,
        haircut_rate=economic_haircut_rate,
        illusion_gap=illusion_gap,
        plan_type=plan_type,
        cash_npv=cash_npv_total,
        asset_info=asset_info,
        discount_rate=discount_rate
    )

    return {
        "status": "success",
        "plan_type": plan_type,
        "annual_discount_rate": discount_rate,
        "metrics": {
            "total_claim_nominal": round(claim_nominal, 2),
            "total_nominal_settlement": round(total_nominal_settlement, 2),
            "total_npv_settlement": round(total_npv_settlement, 2),
            "nominal_recovery_rate": round(nominal_recovery_rate, 2),
            "effective_recovery_rate": round(effective_recovery_rate, 2),
            "economic_haircut_rate": round(economic_haircut_rate, 2),
            "illusion_gap": round(illusion_gap, 2),
            "cash_nominal_total": round(cash_nominal_total, 2),
            "cash_npv_total": round(cash_npv_total, 2),
            "asset_nominal_total": round(asset_nominal_val, 2),
            "asset_npv_total": round(asset_npv, 2)
        },
        "installments_breakdown": installments_breakdown,
        "asset_breakdown": asset_info,
        "partner_tactical_memo": tactical_memo
    }


def _generate_partner_settlement_memo(
    claim_nominal: float,
    nominal_settlement: float,
    total_npv: float,
    nominal_rate: float,
    effective_rate: float,
    haircut_rate: float,
    illusion_gap: float,
    plan_type: str,
    cash_npv: float,
    asset_info: Dict[str, Any],
    discount_rate: float
) -> str:
    """生成具备合伙人法言法语与博弈思维的和解备忘录"""
    memo_lines = []
    memo_lines.append("【合伙人核心财务审定与执业警告】")
    memo_lines.append(f"1. 纸面虚胖陷阱：债务人提议和解方案名义金额合计 ¥{nominal_settlement:,.2f} 元，名义清偿率高达 {nominal_rate:.1f}%。")
    memo_lines.append(
        f"2. 穿透实质净值：按年化 {discount_rate*100:.1f}% 资本成本折现并扣除处置税费、在先优先债权后，真实可收回净现值（NPV）仅为 ¥{total_npv:,.2f} 元，"
        f"实质有效回收率仅为 {effective_rate:.1f}%！"
    )
    if illusion_gap > 15.0:
        memo_lines.append(
            f"   🚨 虚胖差额高达 {illusion_gap:.1f}%！若直接按名义金额向当事人或管委会汇报同意和解，将导致客户承担巨额隐性经济损失！"
        )
    memo_lines.append("")

    if asset_info and asset_info.get("nominal_valuation", 0) > 0:
        nom_val = asset_info["nominal_valuation"]
        p_liens = asset_info["prior_liens"]
        net_cash = asset_info["net_realizable_cash"]
        a_npv = asset_info["asset_npv"]
        months = asset_info["liquidation_period_months"]

        memo_lines.append("【以物抵债法律定性与变现雷区诊断】")
        memo_lines.append(f"1. 抵债资产：{asset_info['asset_name']}（名义评估价 ¥{nom_val:,.2f} 元）。")
        memo_lines.append(
            f"2. 在先受偿权排挤：核查发现该资产存在在先优先权（如工程款优先受偿权、第一顺位抵押权）共计 ¥{p_liens:,.2f} 元。"
            "依照《民法典》第807条、《最高人民法院关于人民法院民事执行中拍卖、变卖财产的规定》及执行分配顺位，"
            "法拍变现款必须全额优先清偿在先顺位债权，我方仅能就扣除后的残值受偿！"
        )
        memo_lines.append(
            f"3. 司法处置折价与周期侵蚀：司法拍卖通常经历一拍（评估价7折）、二拍（56折）甚至流拍变卖，"
            f"加上过户税费与持有成本，预计变现净额仅 ¥{net_cash:,.2f} 元。叠加 {months} 个月处置周期的时间折现，"
            f"该项抵债资产对我方债权的真实贡献值仅为 ¥{a_npv:,.2f} 元（折合原评估价的 {(a_npv/nom_val*100) if nom_val else 0:.1f}%）！"
        )
        memo_lines.append(
            "4. 履行期届满前达成的以物抵债协议，适用《合同编通则解释》第二十八条（原文需律师核实）；"
            "涉及流押/流质约定的，依《九民纪要》第71条、《民法典》第401条、第428条，"
            "该部分约定无效，但不影响合同其他部分的效力，可以就该财产优先受偿。"
        )
        memo_lines.append("")

    memo_lines.append("【合伙人实战谈判反制策略清单】")
    memo_lines.append("1. 【穿透增信底线】：坚决拒绝纯资产挂账抵顶！必须要求债务人控股股东、实际控制人及其配偶签署《个人无限连带责任保证书》，锁定高管个人财产线索。")
    memo_lines.append("2. 【惩罚性加速到期条款】：在和解协议中必须加入严密的违约条款：")
    memo_lines.append("   『若债务人迟延履行任何一期款项或迟延办理抵债资产网签过户超过 7 日，我方所作出的任何金额让利承诺立即自动失效，全部剩余债权（包含原全部本金、按LPR 4倍计算之利息及诉讼费）立即视为全部到期，我方有权就未受偿全额立即申请人民法院强制执行原生效法律文书！』")
    memo_lines.append("3. 【差额现金兜底补足】：抵债资产变现价值不足抵偿我方债权净额的部分，必须约定由债务人在法拍/处置完毕后 30 日内以现金全额补齐，不得作为豁免债务。")

    return "\n".join(memo_lines)

