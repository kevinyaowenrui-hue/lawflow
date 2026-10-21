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

from datetime import datetime, date
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, List, Optional, Tuple

try:
    import cn2an
except ImportError:
    cn2an = None


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
        except Exception:
            pass

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
    is_summary_procedure: bool = False
) -> Dict[str, Any]:
    """
    根据《诉讼费用交纳办法》（国务院令第481号）第十三条精确计算诉讼费用。
    """
    amount = Decimal(str(claim_amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if amount < 0:
        raise ValueError("诉讼标的额不能为负数")

    breakdown = []
    standard_fee = Decimal("0")

    if case_type == "labor":
        standard_fee = Decimal("10.00")
        breakdown.append({"tier": "劳动人事争议案件固定收费", "rate": "法定10元/件", "fee": 10.00})
    elif case_type == "divorce":
        base_fee = Decimal("100.00")
        if amount <= Decimal("200000"):
            standard_fee = base_fee
            breakdown.append({"tier": "不超过20万元财产分割", "rate": "基准100元", "fee": float(base_fee)})
        else:
            excess = amount - Decimal("200000")
            excess_fee = (excess * Decimal("0.005")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            standard_fee = base_fee + excess_fee
            breakdown.append({"tier": "基础规费(20万以内)", "rate": "100元", "fee": 100.00})
            breakdown.append({"tier": f"超过20万部分({excess:.2f}元)", "rate": "0.5%", "fee": float(excess_fee)})
    else:
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
        "actual_fee": float(actual_fee),
        "preservation_fee": float(preservation_fee),
        "tier_breakdown": breakdown,
        "rmb_capital": rmb_to_capital(actual_fee)
    }


# ==============================================================================
# 5. 央行 LPR 历期分段计息算法与起诉状《利息计算明细说明》生成
# ==============================================================================
LPR_HISTORY: List[Tuple[str, float, float]] = [
    ("2019-08-20", 4.25, 4.85),
    ("2019-09-20", 4.20, 4.85),
    ("2019-11-20", 4.15, 4.80),
    ("2020-02-20", 4.05, 4.75),
    ("2020-04-20", 3.85, 4.65),
    ("2021-12-20", 3.80, 4.65),
    ("2022-01-20", 3.70, 4.60),
    ("2022-05-20", 3.70, 4.45),
    ("2022-08-22", 3.65, 4.30),
    ("2023-06-20", 3.55, 4.20),
    ("2023-08-21", 3.45, 4.20),
    ("2024-02-20", 3.45, 3.95),
    ("2024-07-22", 3.35, 3.85),
    ("2024-10-21", 3.10, 3.60),
    ("2025-05-20", 3.00, 3.50),
    ("2026-01-20", 2.90, 3.40),
]

def calculate_lpr_interest(
    principal: float | Decimal,
    start_date: str,
    end_date: str,
    multiplier: float = 1.0,
    term: str = "1Y",
    fixed_annual_rate: Optional[float] = None,
    rule_mode: str = "commercial_floating", # commercial_floating (商事同期浮动) 或 private_lending_cap (民间借贷司法保护上限)
    contract_date: Optional[str] = None     # 民间借贷合同成立日期 (锚定成立时1年期LPR4倍上限)
) -> Dict[str, Any]:
    """
    分段计算自起始日起至截止日期的逾期利息 / 资金占用损失。
    支持两大实务核心模式：
    1. commercial_floating（默认）：商事买卖/工程等违约金，按同期全国银行间同业拆借中心公布的LPR浮动分段计息；
    2. private_lending_cap：民间借贷司法保护上限精算（《民间借贷司法解释》法释〔2020〕17号 第25/28/31条），
       以借款合同成立时一年期LPR的4倍为固定上限，并严格区分2020年8月20日前（年化24%上限）与之后（4倍LPR）的新旧法衔接。
    生成直接写入起诉状的《利息计算明细说明》规范公文段落。
    """
    d_start = datetime.strptime(start_date, "%Y-%m-%d").date()
    d_end = datetime.strptime(end_date, "%Y-%m-%d").date()

    if d_end < d_start:
        raise ValueError("计息截止日期不能早于起始日期")

    total_days = (d_end - d_start).days
    p_dec = Decimal(str(principal)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    sorted_lpr = sorted(LPR_HISTORY, key=lambda x: x[0])

    periods = []
    total_interest = Decimal("0.00")

    # ==========================================================================
    # 模式 A：固定年化利率模式（如当事人合同约定年化 12%）
    # ==========================================================================
    if fixed_annual_rate is not None and rule_mode != "private_lending_cap":
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
    # 模式 B：民间借贷司法保护上限穿透模式 (严格依据法释〔2020〕17号第25/31条)
    # ==========================================================================
    elif rule_mode == "private_lending_cap" or (contract_date is not None and rule_mode != "commercial_floating"):
        # 1. 确定借款合同成立时的一年期 LPR
        ref_contract_date = datetime.strptime(contract_date, "%Y-%m-%d").date() if contract_date else d_start
        contract_lpr = None
        for dt_str, r1, r5 in reversed(sorted_lpr):
            pub_dt = datetime.strptime(dt_str, "%Y-%m-%d").date()
            if pub_dt <= ref_contract_date:
                contract_lpr = r1
                break
        if contract_lpr is None:
            # 2019年8月20日LPR改革前合同，依司法解释第31条参照2020-08-20发布的LPR 3.85%计算
            contract_lpr = 3.85

        cap_rate_post = round(contract_lpr * 4, 4) # 合同成立时一年期LPR的4倍
        rate_pre_2020 = 24.0 # 2020-08-20前司法保护上限为年化24%

        d_pivot = date(2020, 8, 20)
        user_agreed_rate = fixed_annual_rate if fixed_annual_rate is not None else cap_rate_post

        # 分段：以 2020-08-20 为法定分水岭
        split_dates = [d_start]
        if d_start < d_pivot < d_end:
            split_dates.append(d_pivot)
        split_dates.append(d_end)

        for i in range(len(split_dates) - 1):
            s_dt = split_dates[i]
            e_dt = split_dates[i+1]
            s_days = (e_dt - s_dt).days
            if s_days <= 0:
                continue

            if e_dt <= d_pivot:
                # 2020年8月20日前：上限为年化24%
                applicable_cap = rate_pre_2020
                seg_label = "2020-08-20前（适用原司法解释24%上限）"
            else:
                # 2020年8月20日及之后：上限为合同成立时一年期LPR四倍
                applicable_cap = cap_rate_post
                seg_label = f"2020-08-20后（适用成立时LPR四倍 {cap_rate_post}% 上限）"

            # 最终执行利率不得超过法定上限
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
                "statutory_cap_rate": applicable_cap,
                "applied_annual_rate": effective_rate,
                "is_rate_capped": user_agreed_rate > applicable_cap,
                "interest": float(seg_int)
            })

        rate_desc = f"民间借贷法定利率保护上限标准（合同成立日 {ref_contract_date} 对应LPR {contract_lpr}% 之4倍即年化 {cap_rate_post}%）"

    # ==========================================================================
    # 模式 C：商事违约同期 LPR 浮动分段计息模式（默认）
    # ==========================================================================
    else:
        breakpoints = []
        for dt_str, r1, r5 in sorted_lpr:
            dt = datetime.strptime(dt_str, "%Y-%m-%d").date()
            if d_start < dt < d_end:
                breakpoints.append(dt)

        all_points = [d_start] + breakpoints + [d_end]

        for i in range(len(all_points) - 1):
            seg_start = all_points[i]
            seg_end = all_points[i + 1]
            seg_days = (seg_end - seg_start).days
            if seg_days <= 0:
                continue

            active_rate = None
            for dt_str, r1, r5 in reversed(sorted_lpr):
                pub_dt = datetime.strptime(dt_str, "%Y-%m-%d").date()
                if pub_dt <= seg_start:
                    active_rate = r1 if term == "1Y" else r5
                    break

            if active_rate is None:
                active_rate = 4.25 if term == "1Y" else 4.85

            actual_rate = active_rate * multiplier
            rate_dec = Decimal(str(actual_rate)) / Decimal("100")
            seg_interest = (p_dec * rate_dec * Decimal(seg_days) / Decimal("365")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            total_interest += seg_interest
            periods.append({
                "segment_start": seg_start.strftime("%Y-%m-%d"),
                "segment_end": seg_end.strftime("%Y-%m-%d"),
                "days": seg_days,
                "base_lpr": active_rate,
                "multiplier": multiplier,
                "applied_annual_rate": round(actual_rate, 4),
                "interest": float(seg_interest)
            })
        rate_desc = f"同期全国银行间同业拆借中心公布的一年期贷款市场报价利率（LPR）的 {multiplier} 倍"

    total_amount = p_dec + total_interest

    # 自动生成直接写入起诉状的《利息计算明细说明》公文段落
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
            complaint_lines.append(
                f"  ({idx}) {p['segment_start']} 至 {p['segment_end']}（共 {p['days']} 天）：基准LPR {p['base_lpr']}% × {p['multiplier']}倍 = 执行年化 {p['applied_annual_rate']}%，该段利息为人民币 {p['interest']:,.2f} 元；"
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
        "segments": periods
    }


# ==============================================================================
# 6. 《劳动合同法》第47/87条经济补偿金与赔偿金精算
# ==============================================================================
def calculate_labor_compensation(
    monthly_salary: float | Decimal,
    hire_date: str,
    termination_date: str,
    local_avg_salary: Optional[float | Decimal] = None,
    prior_30days_notice: bool = False
) -> Dict[str, Any]:
    """
    根据《劳动合同法》第47条、第87条核算劳动争议补偿金与赔偿金。
    输出：
      - N（经济补偿）
      - N+1（含未提前30天代通知金）
      - 2N（违法解除赔偿金）
    三档精确金额及社平3倍封顶核算明细。
    """
    d_hire = datetime.strptime(hire_date, "%Y-%m-%d").date()
    d_term = datetime.strptime(termination_date, "%Y-%m-%d").date()

    if d_term < d_hire:
        raise ValueError("解除劳动合同日期不能早于入职日期")

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
        comp_m_pre = Decimal(str(y_pre))
        if m_pre >= 6:
            comp_m_pre += Decimal("1.0")
        elif m_pre > 0 or d_pre > 0:
            comp_m_pre += Decimal("0.5")

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
            "note": "跨2008年分段精算：2008年前工作年限月薪不予三倍社平封顶，2008年后工作年限适用三倍社平及12年双封顶。"
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
        "segment_2008": segment_2008_info
    }


# ==============================================================================
# 7. 诉讼时效与除斥期间精确核算器 (《民法典》第188、194、195、199条)
# ==============================================================================
def calculate_statute_of_limitations(
    start_date: str,
    cause_type: str = "general_3y",
    interruption_events: Optional[List[Dict[str, str]]] = None,
    suspension_events: Optional[List[Dict[str, str]]] = None,
    today_date: Optional[str] = None
) -> Dict[str, Any]:
    """
    精确核算民事诉讼时效与除斥期间：
    - 普通民事诉讼时效：3年（《民法典》第188条）
    - 国际货物买卖/技术进出口合同争议：4年（《民法典》第594条）
    - 最长权利保护期：自权利受损之日起20年（《民法典》第188条第二款）
    - 撤销权除斥期间：1年/90日（《民法典》第152条，不适用中止中断）
    - 建设工程优先受偿权除斥期间：18个月（《最高法建工解释一》第36条）
    - 一般保证保证期间（除斥期间6个月，必须起诉主债务人，《民法典》第693条）
    - 连带保证保证期间（除斥期间6个月，必须向保证人主张权利，《民法典》第693条）
    
    支持多轮时效中断事件自动推演（催告、自认还款、仲裁、诉讼），以及最后6个月法定事由时效中止（《民法典》第194条）。
    """
    d_start = datetime.strptime(start_date, "%Y-%m-%d").date()
    d_today = datetime.strptime(today_date, "%Y-%m-%d").date() if today_date else date.today()

    # 基础期限定义（月数）
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
        "cancel_right_1y": {"name": "重大误解/显失公平/欺诈撤销权（除斥期间1年）", "basis": "《民法典》第一百五十二条第一款", "years": 1, "months": 12, "is_preclusive": True},
        "cancel_duress_1y": {"name": "胁迫终止之日起撤销权（除斥期间1年）", "basis": "《民法典》第一百五十二条第一款第二项", "years": 1, "months": 12, "is_preclusive": True},
        "construction_priority_18m": {"name": "建设工程价款优先受偿权（除斥期间18个月）", "basis": "《最高法建设工程施工合同纠纷解释一》第三十六条", "years": 1.5, "months": 18, "is_preclusive": True},
        "rescission_right_1y": {"name": "合同解除权除斥期间（合理催告期满或1年）", "basis": "《民法典》第五百六十四条", "years": 1, "months": 12, "is_preclusive": True}
    }

    rule = PERIOD_RULES.get(cause_type, PERIOD_RULES["general_3y"])
    is_preclusive = rule["is_preclusive"]

    def add_years_exact(d: date, years: int) -> date:
        try:
            return d.replace(year=d.year + years)
        except ValueError:
            # 润年2月29日顺延处理
            return d.replace(year=d.year + years, month=2, day=28)

    def add_months_exact(d: date, months: int) -> date:
        new_year = d.year + (d.month + months - 1) // 12
        new_month = (d.month + months - 1) % 12 + 1
        import calendar
        max_day = calendar.monthrange(new_year, new_month)[1]
        new_day = min(d.day, max_day)
        return date(new_year, new_month, new_day)

    # 初始到期日
    if rule["months"] % 12 == 0:
        initial_expire = add_years_exact(d_start, int(rule["years"]))
    else:
        initial_expire = add_months_exact(d_start, rule["months"])

    # 20年绝对保护期
    max_20y_expire = add_years_exact(d_start, 20)

    timeline_log = [{
        "date": start_date,
        "event": "起算点（知道或应当知道权利受损/义务人及除斥事由起算）",
        "action": "初始时效起算",
        "expire_date": initial_expire.strftime("%Y-%m-%d")
    }]

    current_expire = initial_expire
    effective_interruptions = []

    if not is_preclusive and interruption_events:
        # 按事件时间先后排序
        sorted_events = sorted(interruption_events, key=lambda x: x.get("date", ""))
        for ev in sorted_events:
            ev_date_str = ev.get("date", "")
            ev_desc = ev.get("description", "主张权利/提起仲裁/当事人承诺还款")
            ev_type = ev.get("type", "催告/主张")
            if not ev_date_str:
                continue
            ev_d = datetime.strptime(ev_date_str, "%Y-%m-%d").date()

            # 只有在时效尚未届满前发生的行为才发生中断效力
            if ev_d <= current_expire:
                # 中断并重新计算3年
                new_expire = add_years_exact(ev_d, int(rule["years"]))
                # 不得超过20年绝对限制
                if new_expire > max_20y_expire:
                    new_expire = max_20y_expire

                current_expire = new_expire
                timeline_log.append({
                    "date": ev_date_str,
                    "event": f"【时效中断】{ev_type}: {ev_desc}",
                    "action": f"时效中断并自此日重新起算{rule['years']}年",
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
        "calculation_benchmark_today": d_today.strftime("%Y-%m-%d"),
        "initial_expire_date": initial_expire.strftime("%Y-%m-%d"),
        "final_expire_date": current_expire.strftime("%Y-%m-%d"),
        "max_20y_deadline": max_20y_expire.strftime("%Y-%m-%d"),
        "days_remaining": days_remaining,
        "is_expired": is_expired,
        "status_level": status_level,
        "status_label": status_label,
        "risk_alert": risk_alert,
        "timeline_log": timeline_log,
        "effective_interruptions_count": len(effective_interruptions),
        "effective_suspensions_count": len(effective_suspensions)
    }


# ==============================================================================
# 8. 财产保全续查封续冻结红线精算 (法释〔2016〕22号第十八条)
# ==============================================================================
def calculate_preservation_renewal(
    preservation_type: str,
    start_date: str,
    custom_years: Optional[float] = None,
    today_date: Optional[str] = None
) -> Dict[str, Any]:
    """
    根据《最高人民法院关于人民法院办理财产保全案件若干问题的规定》（法释〔2016〕22号）第十八条：
    - 冻结银行存款及其他资金：期限不得超过 1 年；应当在期限届满前 15 日内申请续冻。
    - 查封、扣押动产（车辆/存货）：期限不得超过 2 年；应当在期限届满前 15 日内申请续封。
    - 查封不动产（房屋/土地）、冻结其他财产权（股权/专利）：期限不得超过 3 年；应当在期限届满前 30 日内申请续封。
    """
    d_start = datetime.strptime(start_date, "%Y-%m-%d").date()
    d_today = datetime.strptime(today_date, "%Y-%m-%d").date() if today_date else date.today()

    TYPE_RULES = {
        "bank_deposit": {
            "name": "银行存款及现金理财冻结",
            "max_years": 1,
            "advance_days": 15,
            "statute": "《最高法院关于人民法院办理财产保全案件若干问题的规定》第十八条第一款",
            "desc": "冻结银行存款及其他资金的期限不得超过一年"
        },
        "movable_property": {
            "name": "动产（汽车、机器设备、存货）查封扣押",
            "max_years": 2,
            "advance_days": 15,
            "statute": "《最高法院关于人民法院办理财产保全案件若干问题的规定》第十八条第一款",
            "desc": "查封、扣押动产的期限不得超过二年"
        },
        "real_estate_equity": {
            "name": "不动产（房产土地）与股权/知识产权冻结",
            "max_years": 3,
            "advance_days": 30,
            "statute": "《最高法院关于人民法院办理财产保全案件若干问题的规定》第十八条第一款",
            "desc": "查封不动产、冻结其他财产权的期限不得超过三年"
        }
    }

    rule = TYPE_RULES.get(preservation_type, TYPE_RULES["bank_deposit"])
    years = custom_years if custom_years else rule["max_years"]
    advance_days = rule["advance_days"]

    def add_years_exact(d: date, y: float) -> date:
        whole_y = int(y)
        try:
            res = d.replace(year=d.year + whole_y)
        except ValueError:
            res = d.replace(year=d.year + whole_y, month=2, day=28)
        if y > whole_y:
            # 增加半年的情况
            import calendar
            target_month = (res.month + 6 - 1) % 12 + 1
            target_year = res.year + (res.month + 6 - 1) // 12
            max_day = calendar.monthrange(target_year, target_month)[1]
            res = date(target_year, target_month, min(res.day, max_day))
        return res

    expire_date = add_years_exact(d_start, years)
    from datetime import timedelta
    renewal_deadline = expire_date - timedelta(days=advance_days)

    days_to_expire = (expire_date - d_today).days
    days_to_renewal = (renewal_deadline - d_today).days

    if days_to_renewal < 0 and days_to_expire >= 0:
        status_level = "CRITICAL_BREACH"
        status_label = "【续封申请法定期限已违约逾期】"
        alert_msg = f"已超过法定提前 {advance_days} 日申请续封红线！虽财产暂未到期解封，但法院极可能因超期排期不予受理续保全，导致首封优势丧失或被轮候查封人上位！需紧急联系执行法官采取紧急补救措施。"
    elif days_to_expire < 0:
        status_level = "EXPIRED"
        status_label = "【保全已自然失效解封】"
        alert_msg = "该财产查封/冻结期限已完全届满，已自动失去保全效力，被执行人可随时转移财产！"
    elif days_to_renewal <= 15:
        status_level = "URGENT"
        status_label = f"【极度紧迫：距续封截止仅余 {days_to_renewal} 天】"
        alert_msg = f"执业穿仓红线警告：必须在 {renewal_deadline.strftime('%Y-%m-%d')} 前向法院提交《续行财产保全申请书》！距离法定截止只剩 {days_to_renewal} 天。"
    elif days_to_renewal <= 45:
        status_level = "WARNING"
        status_label = f"【续封预警窗口：剩余 {days_to_renewal} 天】"
        alert_msg = f"进入续封准备期：建议在 {renewal_deadline.strftime('%Y-%m-%d')} 前准备好续保担保材料与申请书并邮寄法院承办法官。"
    else:
        status_level = "SAFE"
        status_label = f"【保全状态安全：距续封截止 {days_to_renewal} 天】"
        alert_msg = "在正常保全有效期内。"

    return {
        "preservation_type": preservation_type,
        "type_name": rule["name"],
        "statute_basis": rule["statute"],
        "statute_description": rule["desc"],
        "start_date": start_date,
        "expire_date": expire_date.strftime("%Y-%m-%d"),
        "advance_days_required": advance_days,
        "renewal_application_deadline": renewal_deadline.strftime("%Y-%m-%d"),
        "days_to_expire": days_to_expire,
        "days_to_renewal_deadline": days_to_renewal,
        "status_level": status_level,
        "status_label": status_label,
        "alert_message": alert_msg
    }


# ==============================================================================
# 9. 规范性法律文件现行有效性与废止拦截核验引擎
# ==============================================================================
ABROGATED_LAWS_DB = {
    "合同法": {
        "full_name": "《中华人民共和国合同法》",
        "status": "已废止",
        "abrogated_date": "2021-01-01",
        "replaced_by": "《中华人民共和国民法典》第三编合同（第四百六十三条至第七百一十三条）",
        "risk_tip": "严禁在2021年1月1日后起诉状中作为现行有效法条援引。若法律事实发生于2021年前，依《最高法关于适用民法典时间效力的若干规定》第一条第二款可适用当时法律，但必须显式注明溯及力依据。"
    },
    "民法通则": {
        "full_name": "《中华人民共和国民法通则》",
        "status": "已废止",
        "abrogated_date": "2021-01-01",
        "replaced_by": "《中华人民共和国民法典》第一编总则",
        "risk_tip": "已于2021年1月1日废止。民事权利能力、诉讼时效等已被《民法典》总则编吸收重构。"
    },
    "民法总则": {
        "full_name": "《中华人民共和国民法总则》",
        "status": "已废止",
        "abrogated_date": "2021-01-01",
        "replaced_by": "《中华人民共和国民法典》第一编总则",
        "risk_tip": "已于2021年1月1日废止，全部内容融入《民法典》第一编。"
    },
    "物权法": {
        "full_name": "《中华人民共和国物权法》",
        "status": "已废止",
        "abrogated_date": "2021-01-01",
        "replaced_by": "《中华人民共和国民法典》第二编物权",
        "risk_tip": "已于2021年1月1日废止。居住权、动产质押与浮动抵押规则全面升级为民法典物权编。"
    },
    "担保法": {
        "full_name": "《中华人民共和国担保法》",
        "status": "已废止",
        "abrogated_date": "2021-01-01",
        "replaced_by": "《民法典》物权编担保物权及《最高法适用民法典有关担保制度的解释》（法释〔2020〕28号）",
        "risk_tip": "《担保法》及担保法解释已全面废止。注意保证方式推定规则重大逆转：未约定保证方式的，《民法典》第686条推定为【一般保证】（原担保法第19条推定为连带责任保证）！"
    },
    "侵权责任法": {
        "full_name": "《中华人民共和国侵权责任法》",
        "status": "已废止",
        "abrogated_date": "2021-01-01",
        "replaced_by": "《中华人民共和国民法典》第七编侵权责任",
        "risk_tip": "已于2021年1月1日废止。自甘风险原则、自力救济及高空抛物规则已在民法典侵权编中全新确立。"
    },
    "婚姻法": {
        "full_name": "《中华人民共和国婚姻法》",
        "status": "已废止",
        "abrogated_date": "2021-01-01",
        "replaced_by": "《中华人民共和国民法典》第五编婚姻家庭",
        "risk_tip": "已废止。离婚冷静期、夫妻共同债务（共债共签）均适用民法典新规。"
    },
    "继承法": {
        "full_name": "《中华人民共和国继承法》",
        "status": "已废止",
        "abrogated_date": "2021-01-01",
        "replaced_by": "《中华人民共和国民法典》第六编继承",
        "risk_tip": "已废止。遗嘱效力规则重大改变：公证遗嘱不再具有法定最高效力，多份遗嘱冲突以【最后的遗嘱】为准。"
    }
}

VALID_KEY_STATUTES = {
    "民法典": {
        "full_name": "《中华人民共和国民法典》",
        "status": "现行有效",
        "effective_date": "2021-01-01",
        "core_articles": {
            "577": "违约责任基本规范（当事人一方不履行合同义务或者履行合同义务不符合约定的，应当承担继续履行、采取补救措施或者赔偿损失等违约责任）",
            "585": "约定违约金及其司法调减（约定的违约金低于造成的损失的，可以增加；过分高于造成的损失的，可以适当减少）",
            "563": "合同法定解除权情形",
            "667": "借款合同定义与要件",
            "675": "借款人还款期限与合理期限催告",
            "676": "借款人逾期利息责任",
            "188": "普通民事诉讼时效期间三年",
            "195": "诉讼时效中断事由（主张权利、同意履行、提起诉讼/仲裁）",
            "985": "不当得利返还请求权"
        }
    },
    "民间借贷司法解释": {
        "full_name": "《最高人民法院关于审理民间借贷案件适用法律若干问题的规定》（法释〔2020〕17号）",
        "status": "现行有效",
        "effective_date": "2020-08-20",
        "core_articles": {
            "25": "借贷双方约定的利率未超过合同成立时一年期LPR四倍的，人民法院应予支持",
            "28": "逾期利息、违约金或者其他费用总计不得超过一年期LPR四倍上限",
            "13": "套取金融机构贷款转贷、以向其他营利法人借贷取得的资金转贷的，借贷合同无效"
        }
    },
    "九民纪要": {
        "full_name": "《全国法院民商事审判工作会议纪要》（法发〔2019〕25号）",
        "status": "审判业务指导文件（现行参照适用）",
        "effective_date": "2019-11-14",
        "core_articles": {
            "46": "合同解除的效力与违约金条款的适用关系",
            "53": "盖章行为与代表行为效力认定（看人不看章、盖章人是否享有代理权）",
            "71": "让与担保的效力与清算义务"
        }
    }
}

def verify_statutory_validity(citation_text: str, incident_date: Optional[str] = None) -> Dict[str, Any]:
    """
    核验引用的法条或规范性文件是否现行有效、是否已被废止或由新法吸收替换。
    结合争议发生时间（incident_date）进行法不溯及既往的时间效力分析。
    """
    clean_text = citation_text.strip()
    detected_abrogated = []
    detected_valid = []

    # 1. 检查已废止法律
    for key, info in ABROGATED_LAWS_DB.items():
        if key in clean_text:
            detected_abrogated.append({
                "keyword": key,
                "full_name": info["full_name"],
                "status": info["status"],
                "abrogated_date": info["abrogated_date"],
                "replaced_by": info["replaced_by"],
                "risk_tip": info["risk_tip"]
            })

    # 2. 检查现行有效法律
    for key, info in VALID_KEY_STATUTES.items():
        if key in clean_text:
            detected_valid.append({
                "keyword": key,
                "full_name": info["full_name"],
                "status": info["status"],
                "effective_date": info["effective_date"]
            })

    # 3. 时间效力分析
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
                    "『民法典施行前的法律事实引起的民事纠纷案件，适用当时的法律规定，但是法律、司法解释另有规定的除外。』"
                    "本案援引旧法可能被法院采纳，但文书中必须增加民法典时间效力适用过渡条款说明！"
                )
            else:
                time_validity_note = (
                    f"争议法律事实发生于 {incident_date}（晚于《民法典》施行日2021年1月1日）。"
                    "绝对禁止直接引用已废止的旧法作为裁判或诉求依据，否则将产生致命败诉或补正质证破绽！"
                )
        else:
            time_validity_note = "检测到援引了已废止法规！请确认法律事实发生时间；若属于2021年之后案情，必须全面替换为《民法典》及现行司法解释对应条款。"

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
    except Exception:
        claim_nominal = 1.0
    if claim_nominal <= 0:
        claim_nominal = 1.0

    discount_rate = max(0.001, min(0.50, float(annual_discount_rate)))
    plan_type = plan_type.lower()
    if plan_type not in ["cash_installments", "debt_for_asset", "hybrid"]:
        plan_type = "hybrid"

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

    # 4. 生成红圈所合伙人实战战术决策与谈判备忘录
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
    """生成具备红圈所合伙人法言法语与博弈思维的和解备忘录"""
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
            "4. 《九民纪要》第71条合规防线：若双方在履行期届满前达成以物抵债，法律性质属于'让与担保'，"
            "严禁约定'债务不履行直接归债权人所有'（流押/流质绝对无效条款）。必须明确约定清算义务，"
            "且必须在产权登记机关办理正式抵押登记或预告登记网签，防范债务人擅自二抵或被第三方债权人抢先首封！"
        )
        memo_lines.append("")

    memo_lines.append("【红圈所合伙人实战谈判反制策略清单】")
    memo_lines.append("1. 【穿透增信底线】：坚决拒绝纯资产挂账抵顶！必须要求债务人控股股东、实际控制人及其配偶签署《个人无限连带责任保证书》，锁定高管个人财产线索。")
    memo_lines.append("2. 【惩罚性加速到期条款】：在和解协议中必须加入严密的违约条款：")
    memo_lines.append("   『若债务人迟延履行任何一期款项或迟延办理抵债资产网签过户超过 7 日，我方所作出的任何金额让利承诺立即自动失效，全部剩余债权（包含原全部本金、按LPR 4倍计算之利息及诉讼费）立即视为全部到期，我方有权就未受偿全额立即申请人民法院强制执行原生效法律文书！』")
    memo_lines.append("3. 【差额现金兜底补足】：抵债资产变现价值不足抵偿我方债权净额的部分，必须约定由债务人在法拍/处置完毕后 30 日内以现金全额补齐，不得作为豁免债务。")

    return "\n".join(memo_lines)

