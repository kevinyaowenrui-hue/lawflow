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



# 中国人民银行金融机构人民币贷款基准利率。

# 1Y = 一年以内（含一年）；5Y = 五年以上。

# 只收录有公布日期的档次。更早的期间不计息，避免用最后一档 4.35% 倒推。

PBOC_BENCHMARK_1Y_RATE = 4.35

PBOC_BENCHMARK_SCHEDULE = {

    "1Y": (

        (date(2012, 7, 6), 6.00),

        (date(2014, 11, 22), 5.60),

        (date(2015, 3, 1), 5.35),

        (date(2015, 5, 11), 5.10),

        (date(2015, 6, 28), 4.85),

        (date(2015, 8, 26), 4.60),

        (date(2015, 10, 24), 4.35),

    ),

    "5Y": (

        (date(2014, 11, 22), 6.15),

        (date(2015, 3, 1), 5.90),

        (date(2015, 5, 11), 5.65),

        (date(2015, 6, 28), 5.40),

        (date(2015, 8, 26), 5.15),

        (date(2015, 10, 24), 4.90),

    ),

}





def lookup_pboc_benchmark(on_date: date, term: str = "1Y") -> Optional[float]:

    """返回 on_date 当天有效的贷款基准利率；早于本表第一档则返回 None。"""

    schedule = PBOC_BENCHMARK_SCHEDULE.get(term) or PBOC_BENCHMARK_SCHEDULE["1Y"]

    rate = None

    for start, value in schedule:

        if on_date >= start:

            rate = value

        else:

            break

    return rate





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



def validate_and_parse_idcard(

    id_card: str,

    is_cadre: Optional[bool] = None,

    receives_pension: Optional[bool] = None,

) -> Dict[str, Any]:

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

    # 女性岗位必须由律师选择。未选择时不按女工人 50 周岁推算退休日期。
    if gender == "女" and is_cadre is None:
        actual_check = id_card[17]
        check_match = (actual_check == expected_check)
        position_prompt = (
            "请先选岗位。女性须由律师选择「管理/技术」或「工人」后，才能测算法定退休时间。"
            "岗位不是身份证号码推出来的。"
        )
        return {
            "valid": check_match,
            "id_card": id_card,
            "province": province,
            "birth_date": birth_date.strftime("%Y-%m-%d"),
            "age": age,
            "gender": gender,
            "is_retired": None,
            "receives_pension": receives_pension,
            "badge_text": "请先选岗位",
            "relationship_conclusion": "position_required",
            "relationship_note": position_prompt,
            "orig_retire_age": None,
            "delay_months": None,
            "statutory_retire_date": None,
            "standard_retire_age": None,
            "effective_retire_age_str": None,
            "retirement_note": position_prompt,
            "position_selected": None,
            "position_source": "unselected",
            "retirement_date_available": False,
            "expected_check": expected_check,
            "actual_check": actual_check,
            "check_digit_match": check_match,
            "error_message": None if check_match else f"校验码不匹配: 实际为'{actual_check}', 理论应为'{expected_check}'",
        }



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



    badge_text = f"{age}岁 · {gender} · 法定退休时间 {statutory_retire_date_str}"

    if is_retired and receives_pension is True:

        relationship_conclusion = "pension_confirmed_service"

        relationship_note = (

            "已另行确认其依法享受养老保险待遇或领取退休金。"

            "依据《最高人民法院关于审理劳动争议案件适用法律问题的解释（一）》第三十二条，"

            "该用工争议按劳务关系处理。仅达到退休年龄、未确认养老待遇的，不得作此认定。"

        )

    elif is_retired and receives_pension is False:

        relationship_conclusion = "retired_without_pension"

        relationship_note = (

            "已届满测算的法定退休时间，但未享受养老保险待遇、也未领取退休金。"

            "达到退休年龄本身不当然转为劳务关系，劳动关系是否延续须按用工事实另行判断。"

        )

    elif is_retired:

        relationship_conclusion = "age_only"

        relationship_note = (

            "已届满测算的法定退休时间。未填写是否享受养老保险待遇或领取退休金，"

            "本结果不认定劳务关系，也不排除劳动关系。"

        )

    else:

        relationship_conclusion = "not_yet_retired"

        relationship_note = "尚未达到测算的法定退休时间。本结果只核算年龄，不认定劳动关系。"



    if is_retired:

        retirement_note = (

            f"该当事人现年 {age} 周岁。依据《全国人大常委会关于实施渐进式延迟法定退休年龄的决定》（2025年1月1日起施行），"

            f"其原法定退休年龄为 {orig_retire_age} 周岁，经依法测算延迟 {delay_months} 个月，"

            f"改革后法定退休时间为 {statutory_retire_date_str}（即满 {effective_retire_age_str}）。"

            + relationship_note

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

            + relationship_note

        )

    if gender == "女":
        position_selected = "管理/技术" if is_cadre else "工人"
        position_source = "lawyer_selected"
        position_choice_note = f"岗位为律师选择的「{position_selected}」，不是从身份证推出来的。"
        badge_text = f"{badge_text} · 律师选择的{position_selected}岗位"
    else:
        position_selected = "男职工"
        position_source = "male_worker_schedule"
        position_choice_note = "男性按男职工渐进式延迟规则测算，不从身份证推断管理或工人岗位。"
    retirement_note += position_choice_note
    relationship_note += position_choice_note



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

        "receives_pension": receives_pension,

        "badge_text": badge_text,

        "relationship_conclusion": relationship_conclusion,

        "relationship_note": relationship_note,

        "orig_retire_age": orig_retire_age,

        "delay_months": delay_months,

        "statutory_retire_date": statutory_retire_date_str,

        "standard_retire_age": orig_retire_age,

        "effective_retire_age_str": effective_retire_age_str,

        "retirement_note": retirement_note,

        "position_selected": position_selected,

        "position_source": position_source,

        "retirement_date_available": True,

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

# 4. 《诉讼费用交纳办法》财产与非财产案件受理费、保全费分段精算及诉责险估算

# ==============================================================================

def calculate_preservation_insurance(

    preservation_amount: float | Decimal,

    min_rate: float | Decimal = Decimal("0.0008"),

    max_rate: float | Decimal = Decimal("0.0015"),

    min_premium: float | Decimal = Decimal("500.00"),

) -> Dict[str, Any]:

    """

    测算诉讼保全责任保险（诉责险）市场参考保费成本。

    法律依据：《最高人民法院关于人民法院办理财产保全案件若干问题的规定》（法释〔2016〕22号）第七条。

    """

    p_amount = Decimal(str(preservation_amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    if p_amount < Decimal("0"):

        raise ValueError("保全金额不能为负数")



    r_min = Decimal(str(min_rate))

    r_max = Decimal(str(max_rate))

    if r_min < Decimal("0") or r_max < Decimal("0") or r_min > r_max:

        raise ValueError("保全险费率设置无效，费率不能为负且最低费率不能大于最高费率")



    m_premium = Decimal(str(min_premium)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    if m_premium < Decimal("0"):

        raise ValueError("起保最低保费不能为负数")



    if p_amount == Decimal("0.00"):

        cost_low = Decimal("0.00")

        cost_high = Decimal("0.00")

        is_min_low = False

        is_min_high = False

    else:

        raw_low = (p_amount * r_min).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        raw_high = (p_amount * r_max).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        cost_low = max(raw_low, m_premium)

        cost_high = max(raw_high, m_premium)

        is_min_low = bool(raw_low < m_premium)

        is_min_high = bool(raw_high < m_premium)



    min_pct_str = f"{float(r_min * Decimal('100')):.2f}%"

    max_pct_str = f"{float(r_max * Decimal('100')):.2f}%"



    return {

        "preservation_amount": float(p_amount),

        "min_rate": float(r_min),

        "max_rate": float(r_max),

        "min_rate_pct": min_pct_str,

        "max_rate_pct": max_pct_str,

        "rate_range_desc": f"{min_pct_str} ~ {max_pct_str}",

        "min_premium": float(m_premium),

        "cost_low": float(cost_low),

        "cost_high": float(cost_high),

        "cost_range_display": f"¥ {cost_low:,.2f} ~ ¥ {cost_high:,.2f}",

        "is_minimum_charge_applied_low": is_min_low,

        "is_minimum_charge_applied_high": is_min_high,

        "statutory_basis": "《最高人民法院关于人民法院办理财产保全案件若干问题的规定》（法释〔2016〕22号）第七条",

        "note": "市场参考费率 0.08%~0.15%，起保最低收费 500.00 元（具体以承保金融机构核保单为准）",

    }





def calculate_court_fees(

    claim_amount: float | Decimal,

    case_type: str = "property",

    is_summary_procedure: bool = False,

    is_mediation_or_withdrawal: bool = False,

    is_counterclaim: bool = False,

    divorce_base_fee: float | Decimal = 100,

    preservation_amount: Optional[float | Decimal] = None,

    personality_base_fee: float | Decimal = 300,

    execution_flat_fee: float | Decimal = 50,

) -> Dict[str, Any]:

    """

    根据《诉讼费用交纳办法》（国务院令第481号）第十三条精确计算诉讼费用。

    """

    amount = Decimal(str(claim_amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    if amount < 0:

        raise ValueError("诉讼标的额不能为负数")



    div_base = Decimal(str(divorce_base_fee)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    personality_base = Decimal(str(personality_base_fee)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    execution_flat = Decimal(str(execution_flat_fee)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)



    # 未填写保全金额时不计保全费、不计诉责险。不得默认成诉讼标的。

    preservation_included = preservation_amount is not None

    if preservation_amount is not None:

        p_amount_dec = Decimal(str(preservation_amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        if p_amount_dec < Decimal("0"):

            raise ValueError("保全金额不能为负数")

    else:

        p_amount_dec = Decimal("0")



    breakdown = []

    standard_fee = Decimal("0")

    labor_court_fee_note = None



    # 归一化案件类型（前端可能传中文）

    ct = (case_type or "property").strip().lower()

    if ct in ("财产案件", "property", "财产"):

        ct = "property"

    elif ct in ("劳动", "labor", "劳动人事争议"):

        ct = "labor"

    elif ct in ("离婚", "divorce"):

        ct = "divorce"

    elif ct in ("人格权", "personality", "personality_right"):

        ct = "personality"

    elif ct in ("执行", "申请执行", "execution"):

        ct = "execution"

    elif ct in ("支付令", "payment_order"):

        ct = "payment_order"

    elif ct in ("公示催告", "public_summons"):

        ct = "public_summons"

    elif ct in ("撤销仲裁", "确认仲裁协议效力", "arbitration_revoke"):

        ct = "arbitration_revoke"



    acceptance_fee_types = {"property", "labor", "divorce", "personality"}

    fee_nature = "案件受理费" if ct in acceptance_fee_types else "申请费"



    if ct == "divorce" and (div_base < Decimal("50") or div_base > Decimal("300")):

        raise ValueError(f"离婚案件基础规费应在 50 至 300 元之间，当前为 {divorce_base_fee}")

    if ct == "personality" and (personality_base < Decimal("100") or personality_base > Decimal("500")):

        raise ValueError(f"人格权案件每件基础收费应在 100 至 500 元之间，当前为 {personality_base_fee}")

    if ct == "execution" and amount <= 0 and (execution_flat < Decimal("50") or execution_flat > Decimal("500")):

        raise ValueError(f"没有执行金额的案件，申请费应在 50 至 500 元之间，当前为 {execution_flat_fee}")



    if case_type == "labor" or ct == "labor":

        standard_fee = Decimal("10.00")

        labor_court_fee_note = (
            "向人民法院起诉的劳动争议案件受理费，每件 10 元。劳动仲裁不收费，不要用本项。"
            "依据《诉讼费用交纳办法》第十三条、《劳动争议调解仲裁法》第五十三条。"
        )

        breakdown.append({
            "tier": "向人民法院起诉的劳动争议案件受理费，每件 10 元。劳动仲裁不收费，不要用本项。",
            "rate": "《诉讼费用交纳办法》第十三条；《劳动争议调解仲裁法》第五十三条",
            "fee": 10.00,
        })

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

    elif ct == "personality":

        rate_desc = f"每件 100—500 元，由各地确定，本次按 {float(personality_base):g} 元计算（《诉讼费用交纳办法》第十三条）"

        if amount <= Decimal("50000"):

            standard_fee = personality_base

            breakdown.append({"tier": "损害赔偿不超过5万元", "rate": rate_desc, "fee": float(personality_base)})

        elif amount <= Decimal("100000"):

            excess = amount - Decimal("50000")

            excess_fee = (excess * Decimal("0.01")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            standard_fee = personality_base + excess_fee

            breakdown.append({"tier": "基础规费(5万以内不另计)", "rate": rate_desc, "fee": float(personality_base)})

            breakdown.append({"tier": f"超过5万至10万部分({excess:.2f}元)", "rate": "1%", "fee": float(excess_fee)})

        else:

            mid = Decimal("50000") * Decimal("0.01")

            excess = amount - Decimal("100000")

            excess_fee = (excess * Decimal("0.005")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            standard_fee = personality_base + mid + excess_fee

            breakdown.append({"tier": "基础规费(5万以内不另计)", "rate": rate_desc, "fee": float(personality_base)})

            breakdown.append({"tier": "超过5万至10万部分", "rate": "1%", "fee": float(mid)})

            breakdown.append({"tier": f"超过10万部分({excess:.2f}元)", "rate": "0.5%", "fee": float(excess_fee)})

    elif ct == "public_summons":

        standard_fee = Decimal("100.00")

        breakdown.append({"tier": "申请公示催告", "rate": "每件100元", "fee": 100.00})

    elif ct == "arbitration_revoke":

        standard_fee = Decimal("400.00")

        breakdown.append({"tier": "申请撤销仲裁裁决或认定仲裁协议效力", "rate": "每件400元", "fee": 400.00})

    elif ct == "execution":

        if amount <= 0:

            standard_fee = execution_flat

            breakdown.append({

                "tier": "没有执行金额或者价额",

                "rate": f"每件 50—500 元，本次按 {float(execution_flat):g} 元",

                "fee": float(execution_flat),

            })

        elif amount <= Decimal("10000"):

            standard_fee = Decimal("50.00")

            breakdown.append({"tier": "执行金额不超过1万元", "rate": "50元", "fee": 50.00})

        else:

            standard_fee = Decimal("50.00")

            breakdown.append({"tier": "不超过1万元", "rate": "50元", "fee": 50.00})

            exec_tiers = [

                (Decimal("10000"), Decimal("500000"), Decimal("0.015")),

                (Decimal("500000"), Decimal("5000000"), Decimal("0.01")),

                (Decimal("5000000"), Decimal("10000000"), Decimal("0.005")),

                (Decimal("10000000"), Decimal("Infinity"), Decimal("0.001")),

            ]

            for low, high, rate in exec_tiers:

                if amount > low:

                    taxable = min(amount, high) - low

                    seg_fee = (taxable * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

                    standard_fee += seg_fee

                    high_label = "无上限" if high == Decimal("Infinity") else f"{int(high/10000)}万"

                    breakdown.append({

                        "tier": f"{int(low/10000)}万 - {high_label}",

                        "taxable_amount": float(taxable),

                        "rate": f"{float(rate)*100:g}%",

                        "fee": float(seg_fee),

                    })

                else:

                    break

    elif ct == "payment_order":

        if amount <= 0:

            raise ValueError("支付令申请金额须大于 0")

        property_fee = calculate_court_fees(

            claim_amount=amount,

            case_type="property",

            preservation_amount=None,

        )["standard_fee"]

        standard_fee = (Decimal(str(property_fee)) / Decimal("3")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        breakdown.append({

            "tier": "申请支付令",

            "rate": "比照财产案件受理费的三分之一",

            "fee": float(standard_fee),

        })

    elif ct == "property":

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

                        "rate": f"{float(rate * Decimal('100')):g}%",

                        "fee": float(seg_fee)

                    })

                else:

                    break

    else:

        raise ValueError(f"不支持的案件类型: {case_type}")



    half_requested = is_summary_procedure or is_mediation_or_withdrawal or is_counterclaim

    is_half_fee = half_requested and ct in acceptance_fee_types

    actual_fee = (standard_fee / 2).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if is_half_fee else standard_fee

    reduction_amount = (standard_fee - actual_fee).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    reduction_ratio = 0.5 if is_half_fee else 1.0



    reduction_rules = []

    if ct not in acceptance_fee_types and half_requested:

        reduction_rules.append("申请费不适用简易程序、调解撤诉或反诉减半，本次按申请费全额计算。")

    if is_half_fee and is_summary_procedure:

        reduction_rules.append(
            "《诉讼费用交纳办法》第十六条：适用简易程序审理的案件，减半交纳案件受理费。"
            "未确定适用简易程序时，立案预交按全额计算。结案减半是退费口径，不是立案就预交一半。"
        )

    if is_half_fee and is_mediation_or_withdrawal:

        reduction_rules.append(
            "《诉讼费用交纳办法》第十五条：以调解方式结案或者当事人申请撤诉的案件，减半交纳案件受理费。"
            "这是结案退费口径，不是立案就预交一半。"
        )

    if is_half_fee and is_counterclaim:

        reduction_rules.append("《诉讼费用交纳办法》第十八条：被告提起反诉，人民法院决定合并审理的，分别减半交纳案件受理费。未合并审理的不要按减半预交。")



    statutory_reduction_rule = "；".join(reduction_rules) if reduction_rules else None

    # 未确定适用简易程序时，预交按全额。简易程序第16条、调解撤诉第15条的减半都是结案退费。
    # 反诉在法院决定合并审理时，才按第十八条减半预交。
    summary_or_settlement_half = is_half_fee and (is_summary_procedure or is_mediation_or_withdrawal)
    counterclaim_filing_half = is_half_fee and is_counterclaim
    if counterclaim_filing_half:
        filing_prepay_fee = actual_fee
        filing_prepay_note = "反诉且法院决定合并审理的，按《诉讼费用交纳办法》第十八条分别减半预交。未合并审理的不要按减半预交。"
        if is_summary_procedure:
            filing_prepay_note += "未确定适用简易程序时，不要把简易程序减半再当成立案预交。结案减半是退费口径，不是立案就预交一半。"
        if is_mediation_or_withdrawal:
            filing_prepay_note += "调解或撤诉减半是结案退费口径，不是立案就预交一半。"
    elif summary_or_settlement_half:
        filing_prepay_fee = standard_fee
        prepay_notes = []
        if is_summary_procedure:
            prepay_notes.append("未确定适用简易程序时，立案预交按全额计算。结案减半是退费口径，不是立案就预交一半。")
        if is_mediation_or_withdrawal:
            prepay_notes.append("调解或撤诉减半发生在结案时。立案预交仍按全额，结案后退还减半部分。这是结案退费口径，不是立案就预交一半。")
        filing_prepay_note = "".join(prepay_notes)
    else:
        filing_prepay_fee = actual_fee
        filing_prepay_note = "按本次勾选的程序，立案预交金额与本次测算的应交金额一致。"



    # 保全申请费（第十四条第二项）封顶5000元，基于保全标的额 p_amount_dec 计算

    preservation_fee = Decimal("0")

    if p_amount_dec > 0:

        if p_amount_dec <= Decimal("1000"):

            preservation_fee = Decimal("30.00")

        elif p_amount_dec <= Decimal("100000"):

            preservation_fee = Decimal("30.00") + ((p_amount_dec - Decimal("1000")) * Decimal("0.01")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        else:

            p_fee = Decimal("30.00") + (Decimal("99000") * Decimal("0.01")) + ((p_amount_dec - Decimal("100000")) * Decimal("0.005")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            preservation_fee = min(p_fee, Decimal("5000.00"))



    # 诉讼保全责任保险（诉责险）市场参考成本估算

    preservation_insurance = calculate_preservation_insurance(p_amount_dec)



    return {

        "claim_amount": float(amount),

        "case_type": case_type,

        "is_summary_procedure": is_summary_procedure,

        "is_mediation_or_withdrawal": is_mediation_or_withdrawal,

        "is_counterclaim": is_counterclaim,

        "is_half_fee": is_half_fee,

        "normalized_case_type": ct,

        "fee_nature": fee_nature,

        "standard_fee": float(standard_fee),

        "actual_fee": float(actual_fee),

        "court_fee": float(actual_fee),

        "fee_amount": float(actual_fee),

        "filing_prepay_fee": float(filing_prepay_fee),

        "filing_prepay_note": filing_prepay_note,

        "fee_reduction_ratio": reduction_ratio,

        "reduction_amount": float(reduction_amount),

        "statutory_reduction_rule": statutory_reduction_rule,

        "labor_court_fee_note": labor_court_fee_note,

        "preservation_fee": float(preservation_fee),

        "preservation_included": preservation_included,

        "preservation_amount": float(p_amount_dec),

        "preservation_insurance": preservation_insurance,

        "tier_breakdown": breakdown,

        "rmb_capital": rmb_to_capital(actual_fee),

    }



# ==============================================================================

# 各省市上一年度居民人均可支配收入与社平工资基准字典 (2025-2026 实务速查)

# ==============================================================================

PROVINCIAL_INCOME_BASELINES_2025_2026: Dict[str, Dict[str, Any]] = {

    "北京": {

        "province": "北京市",

        "annual_disposable_income": 89400.0,

        "monthly_avg_wage": 11298.0,

        "monthly_three_times_cap": 33894.0,

        "source": "北京市统计局公布上一年度城镇居民人均可支配收入及全口径城镇单位就业人员月平均工资",

    },

    "上海": {

        "province": "上海市",

        "annual_disposable_income": 89800.0,

        "monthly_avg_wage": 12307.0,

        "monthly_three_times_cap": 36921.0,

        "source": "上海市统计局公布上一年度城镇居民人均可支配收入及城镇单位就业人员月平均工资",

    },

    "广东": {

        "province": "广东省",

        "annual_disposable_income": 59300.0,

        "monthly_avg_wage": 9100.0,

        "monthly_three_times_cap": 27300.0,

        "source": "广东省统计局公布上一年度城镇居民人均可支配收入及非私营单位在岗职工月平均工资",

    },

    "深圳": {

        "province": "深圳市",

        "annual_disposable_income": 79000.0,

        "monthly_avg_wage": 13730.0,

        "monthly_three_times_cap": 41190.0,

        "source": "深圳市统计局及人社局公布在岗职工月平均工资及居民人均可支配收入",

    },

    "浙江": {

        "province": "浙江省",

        "annual_disposable_income": 74900.0,

        "monthly_avg_wage": 8520.0,

        "monthly_three_times_cap": 25560.0,

        "source": "浙江省统计局公布上一年度城镇居民人均可支配收入及非私营单位就业人员月平均工资",

    },

    "江苏": {

        "province": "江苏省",

        "annual_disposable_income": 63200.0,

        "monthly_avg_wage": 8850.0,

        "monthly_three_times_cap": 26550.0,

        "source": "江苏省统计局公布上一年度城镇居民人均可支配收入及非私营单位就业人员月平均工资",

    },

    "四川": {

        "province": "四川省",

        "annual_disposable_income": 47600.0,

        "monthly_avg_wage": 7550.0,

        "monthly_three_times_cap": 22650.0,

        "source": "四川省统计局公布上一年度城镇居民人均可支配收入及城镇单位就业人员月平均工资",

    },

    "湖北": {

        "province": "湖北省",

        "annual_disposable_income": 45100.0,

        "monthly_avg_wage": 7200.0,

        "monthly_three_times_cap": 21600.0,

        "source": "湖北省统计局公布上一年度城镇居民人均可支配收入及城镇单位就业人员月平均工资",

    },

    "山东": {

        "province": "山东省",

        "annual_disposable_income": 51200.0,

        "monthly_avg_wage": 7450.0,

        "monthly_three_times_cap": 22350.0,

        "source": "山东省统计局公布上一年度城镇居民人均可支配收入及城镇单位就业人员月平均工资",

    },

    "河南": {

        "province": "河南省",

        "annual_disposable_income": 40200.0,

        "monthly_avg_wage": 6580.0,

        "monthly_three_times_cap": 19740.0,

        "source": "河南省统计局公布上一年度城镇居民人均可支配收入及城镇单位就业人员月平均工资",

    },

}



for _baseline in PROVINCIAL_INCOME_BASELINES_2025_2026.values():

    _baseline["verified"] = False

    _baseline["cap_allowed"] = False

    _baseline["baseline_year"] = None

    _baseline["cap_note"] = (

        "内置数字是取整估算，没有统计公报年份和口径，不得用于社平三倍封顶。"

        "封顶须律师按解除时当地职工月平均工资手填。"

    )





def get_provincial_income_baseline(region_name: str) -> Optional[Dict[str, Any]]:

    """根据省份/城市名称速查上一年度收入与社平工资基准。"""

    if not region_name:

        return None

    rn = region_name.strip().replace("省", "").replace("市", "")

    for k, v in PROVINCIAL_INCOME_BASELINES_2025_2026.items():

        if k in rn or rn in k:

            return v

    return None





def calculate_private_lending_segmented_interest(

    principal: float | Decimal | str,

    start_date: str,

    end_date: str,

    agreed_annual_rate: float | Decimal,

    filing_date_lpr_1y: float | Decimal | None = None,

    include_delayed_performance_days: int = 0,

    contract_date: Optional[str] = None,

    filing_date: Optional[str] = None,

) -> Dict[str, Any]:

    """

    民间借贷 2020-08-20 跨期分段利息精算及《利息计算明细说明》起诉状公文生成。

    2020-08-20 之后成立的合同，保护上限是合同成立时一年期贷款市场报价利率的四倍。

    2020-08-20 之前成立的合同，该日之前按当时司法解释年利率 24% 的保护上限；

    该日之后按起诉时本规定的利率保护标准，必须提供起诉日期或起诉时一年期贷款市场报价利率，不默认 3%。

    迟延履行期间加倍部分债务利息按日万分之一点七五，只在另行传入天数时计算。

    """

    p_dec = Decimal(str(principal)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    if p_dec <= 0:

        raise ValueError("借款本金必须大于0")



    d_start = datetime.strptime(start_date, "%Y-%m-%d").date()

    d_end = datetime.strptime(end_date, "%Y-%m-%d").date()

    if d_end < d_start:

        raise ValueError("截止日期不能早于起算日期")



    # 规范化约定年利率

    rate_val = float(agreed_annual_rate)

    if rate_val > 1.0:

        rate_val = rate_val / 100.0

    user_rate_dec = Decimal(str(rate_val))



    # 2020-08-20 之后的保护上限。不默认 3%。

    d_pivot = date(2020, 8, 20)

    cap_pre_dec = Decimal("0.24")

    ref_contract = contract_date or start_date

    d_contract = datetime.strptime(ref_contract, "%Y-%m-%d").date()

    cap_notes: List[str] = []



    def _as_rate(raw: float | Decimal) -> Decimal:

        rate_number = float(raw)

        if rate_number > 1.0:

            rate_number = rate_number / 100.0

        return Decimal(str(rate_number))



    needs_post_cap = d_end >= d_pivot

    if d_contract >= d_pivot:

        cap_info = get_private_lending_four_times_lpr_cap(ref_contract)

        lpr_dec = Decimal(str(cap_info["lpr_base_percent"])) / Decimal("100")

        four_lpr_dec = Decimal(str(cap_info["cap_rate_decimal"]))

        post_basis = (

            f"《民间借贷规定》第二十五条：合同成立时一年期贷款市场报价利率"

            f"{float(lpr_dec) * 100:.2f}%的四倍（{float(four_lpr_dec) * 100:.2f}%）"

        )

        if contract_date is None:

            cap_notes.append("未另填合同成立日，按计息起算日检索一年期贷款市场报价利率。合同成立日不同的，请改填合同成立日。")

    else:

        if not needs_post_cap:

            lpr_dec = Decimal("0")

            four_lpr_dec = Decimal("0")

            post_basis = "本段利息全部发生在2020年8月20日之前，按当时司法解释年利率24%的保护上限。"

        else:

            if filing_date_lpr_1y is not None:

                lpr_dec = _as_rate(filing_date_lpr_1y)

                four_lpr_dec = (lpr_dec * Decimal("4")).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

            elif filing_date:

                cap_info = get_private_lending_four_times_lpr_cap(ref_contract, filing_date)

                lpr_dec = Decimal(str(cap_info["lpr_base_percent"])) / Decimal("100")

                four_lpr_dec = Decimal(str(cap_info["cap_rate_decimal"]))

            else:

                raise ValueError(

                    "合同成立于2020-08-20之前的，2020-08-20之后的利息要按起诉时的保护标准。"

                    "请填写起诉日期或起诉时一年期贷款市场报价利率。不能默认按3%计算。"

                )

            post_basis = (

                f"《民间借贷规定》第三十一条第二款：2020年8月20日之后的利息，按起诉时一年期贷款市场报价利率"

                f"{float(lpr_dec) * 100:.2f}%的四倍（{float(four_lpr_dec) * 100:.2f}%）。"

                "2020年8月19日以前仍按当时司法解释年利率24%的保护上限。"

            )



    segments = []

    total_general_interest = Decimal("0.00")



    if d_start < d_pivot:

        # 跨期切分两段

        seg1_end = min(d_end, date(2020, 8, 19))

        days_seg1 = (seg1_end - d_start).days + 1

        effective_rate_seg1 = min(user_rate_dec, cap_pre_dec)

        interest_seg1 = (p_dec * effective_rate_seg1 * Decimal(days_seg1) / Decimal("365")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        total_general_interest += interest_seg1



        segments.append({

            "segment_name": "第一阶段（2020-08-20前）",

            "start_date": d_start.strftime("%Y-%m-%d"),

            "end_date": seg1_end.strftime("%Y-%m-%d"),

            "days": days_seg1,

            "agreed_annual_rate": float(user_rate_dec),

            "cap_annual_rate": float(cap_pre_dec),

            "effective_annual_rate": float(effective_rate_seg1),

            "interest_amount": float(interest_seg1),

            "basis": "最高法民间借贷规定第31条第2款：2020年8月20日前借贷以年利率24%为保护上限"

        })



        if d_end >= d_pivot:

            days_seg2 = (d_end - d_pivot).days + 1

            effective_rate_seg2 = min(user_rate_dec, four_lpr_dec)

            interest_seg2 = (p_dec * effective_rate_seg2 * Decimal(days_seg2) / Decimal("365")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            total_general_interest += interest_seg2



            segments.append({

                "segment_name": "第二阶段（2020-08-20及之后）",

                "start_date": d_pivot.strftime("%Y-%m-%d"),

                "end_date": d_end.strftime("%Y-%m-%d"),

                "days": days_seg2,

                "agreed_annual_rate": float(user_rate_dec),

                "cap_annual_rate": float(four_lpr_dec),

                "effective_annual_rate": float(effective_rate_seg2),

                "interest_amount": float(interest_seg2),

                "basis": post_basis

            })

    else:

        # 起算日已在 2020-08-20 之后

        days_seg = (d_end - d_start).days + 1

        effective_rate = min(user_rate_dec, four_lpr_dec)

        interest_amount = (p_dec * effective_rate * Decimal(days_seg) / Decimal("365")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        total_general_interest += interest_amount



        segments.append({

            "segment_name": "全阶段（2020-08-20后借贷）",

            "start_date": d_start.strftime("%Y-%m-%d"),

            "end_date": d_end.strftime("%Y-%m-%d"),

            "days": days_seg,

            "agreed_annual_rate": float(user_rate_dec),

            "cap_annual_rate": float(four_lpr_dec),

            "effective_annual_rate": float(effective_rate),

            "interest_amount": float(interest_amount),

            "basis": post_basis

        })



    # 迟延履行加倍部分债务利息

    delayed_days = max(0, int(include_delayed_performance_days))

    delayed_interest = Decimal("0.00")

    if delayed_days > 0:

        delayed_interest = (p_dec * Decimal("0.000175") * Decimal(delayed_days)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)



    total_amount = p_dec + total_general_interest + delayed_interest



    # 生成规范起诉状附注说明文本

    text_lines = [

        "【民间借贷分段利息计算明细说明】",

        "依据《最高人民法院关于审理民间借贷案件适用法律若干问题的规定》（法释〔2020〕17号）第二十五条、第二十八条、第二十九条及第三十一条规定：",

        f"一、一般债务利息计算明细（借款本金基数：人民币 {p_dec:,.2f} 元）："

    ]

    for idx, s in enumerate(segments, 1):

        text_lines.append(

            f"  {idx}. {s['segment_name']}（{s['start_date']} 至 {s['end_date']}，计 {s['days']} 天）："

            f"约定年利率 {s['agreed_annual_rate']*100:.2f}%，法定保护上限为 {s['cap_annual_rate']*100:.2f}%，"

            f"实际执行年利率 {s['effective_annual_rate']*100:.2f}%，产生利息人民币 {s['interest_amount']:,.2f} 元。"

            f"依据：{s['basis']}"

        )

    text_lines.append(f"一般债务利息合计：人民币 {total_general_interest:,.2f} 元（{rmb_to_capital(total_general_interest)}）。")



    if delayed_days > 0:

        text_lines.append(

            f"二、迟延履行期间加倍部分债务利息（依据《中华人民共和国民事诉讼法》第二百六十四条）：\n"

            f"  迟延履行天数 {delayed_days} 天，按日万分之一点七五（0.0175%）计付加倍利息人民币 {delayed_interest:,.2f} 元（{rmb_to_capital(delayed_interest)}）。"

        )

    text_lines.append(f"本息总计诉讼标的额：人民币 {total_amount:,.2f} 元（{rmb_to_capital(total_amount)}）。")

    text_lines.extend(cap_notes)

    explanation_text = "\n".join(text_lines)



    return {

        "principal": float(p_dec),

        "start_date": start_date,

        "end_date": end_date,

        "agreed_annual_rate": float(user_rate_dec),

        "filing_date_lpr_1y": float(lpr_dec),

        "four_times_lpr": float(four_lpr_dec),

        "total_general_interest": float(total_general_interest),

        "delayed_performance_days": delayed_days,

        "delayed_performance_interest": float(delayed_interest),

        "total_claim_amount": float(total_amount),

        "total_claim_amount_capital": rmb_to_capital(total_amount),

        "segments": segments,

        "calculation_explanation_text": explanation_text,

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

    if contract_lpr is None and ref_contract_date >= d_pivot:

        raise ValueError("无法确定合同成立日的一年期贷款市场报价利率，不能用其他日期的利率代替")



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

    1. commercial_floating（默认）：商事同期 LPR 浮动；2019-08-20 前按已收录的央行贷款基准利率分档，不把 4.35% 套到更早的日期。

    2. private_lending_cap：有约定利率时，按第二十五条、第二十八条截断到保护上限；借期和逾期利率都没约定时，按第二十八条第一项参照当时一年期 LPR，不用四倍代替约定。2020-08-20 前成立的合同，该日之后的上限按第三十一条第二款用起诉时的标准。

    3. sales_fixed_lpr_markup：买卖合同未约定逾期付款违约金时，以违约行为发生日的利率为基数加计 30%–50%，整段固定。2019-08-20 起用一年期 LPR，此前用一年以内贷款基准利率。

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

    # 模式 sales_fixed_lpr_markup：买卖合同未约定逾期付款违约金

    # 《最高人民法院关于审理买卖合同纠纷案件适用法律问题的解释》（2020年修正）第十八条第四款

    # 违约日在 2019-08-20 及以后：违约行为发生时一年期 LPR 加计 30%–50%，整段不浮动。

    # 违约日在 2019-08-19 及以前：同期同类人民币贷款基准利率为基础，参照逾期罚息上浮 30%–50%。

    # ==========================================================================

    elif rule_mode == "sales_fixed_lpr_markup":

        if markup_ratio is None:

            raise ValueError("sales_fixed_lpr_markup 模式须提供 markup_ratio（0.3–0.5）")

        mr = float(markup_ratio)

        if mr < 0.3 or mr > 0.5:

            raise ValueError("markup_ratio 须在 0.3–0.5 之间")

        lpr_reform = date(2019, 8, 20)

        legal_basis = "《最高人民法院关于审理买卖合同纠纷案件适用法律问题的解释》（2020年修正）第十八条第四款"

        if d_start >= lpr_reform:

            base_rate = _lookup_lpr_on_date(sorted_lpr, d_start, "1Y")

            base_kind = "lpr"

            base_name = "一年期贷款市场报价利率"

        else:

            base_rate = lookup_pboc_benchmark(d_start, "1Y")

            base_kind = "pboc"

            base_name = "一年以内（含一年）人民币贷款基准利率"

        if base_rate is None:

            warnings.append("违约行为发生日没有已收录的对应利率，本段未计息。请改用当时有效的利率，或缩短到已收录的区间。")

            periods.append({

                "segment_start": start_date,

                "segment_end": end_date,

                "days": total_days,

                "base_lpr": None,

                "base_kind": base_kind,

                "markup_ratio": mr,

                "applied_annual_rate": None,

                "interest": 0.0,

                "rate_basis": legal_basis,

            })

            rate_desc = f"{legal_basis}。违约行为发生日的{base_name}未收录，未计息"

        else:

            applied = round(base_rate * (1.0 + mr), 4)

            rate_dec = Decimal(str(applied)) / Decimal("100")

            interest = (p_dec * rate_dec * Decimal(total_days) / Decimal("365")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            total_interest = interest

            periods.append({

                "segment_start": start_date,

                "segment_end": end_date,

                "days": total_days,

                "base_lpr": base_rate,

                "base_kind": base_kind,

                "markup_ratio": mr,

                "applied_annual_rate": applied,

                "interest": float(interest),

                "rate_basis": legal_basis,

            })

            if base_kind == "lpr":

                rate_desc = (

                    f"违约行为发生时{base_name} {base_rate}% 加计 {mr * 100:.0f}%"

                    f"（年利率 {applied}%，自违约行为发生日起整段固定，不随后续报价调整）"

                )

            else:

                rate_desc = (

                    f"违约行为发生时{base_name} {base_rate}% 上浮 {mr * 100:.0f}%"

                    f"（年利率 {applied}%，参照逾期罚息标准，整段不随后续基准利率调整）"

                )

        warnings.append("只适用于买卖合同没有约定逾期付款违约金或者其计算方法的情形。合同有约定的，按约定计算，不要用本口径覆盖约定。")

        warnings.append("起息日按违约行为发生日填写。利率取这一天，不按后来的 LPR 重新分段。")

        warnings.append("本地法条库尚未收录该司法解释全文。写入诉状前，请对照最高人民法院公布的 2020 年修正文本。")



    # ==========================================================================

    # 模式 B：民间借贷司法保护上限（法释〔2020〕17号第31条第2款）

    # 摘录："……对于自2020年8月20日到借款返还之日的利息部分，适用起诉时本规定的利率保护标准计算。"

    # 来源：court.gov.cn 249051

    # ==========================================================================

    elif rule_mode == "private_lending_cap" or (contract_date is not None and rule_mode != "commercial_floating"):

        ref_contract_date = datetime.strptime(contract_date, "%Y-%m-%d").date() if contract_date else d_start

        d_pivot = date(2020, 8, 20)

        rate_pre_2020 = 24.0



        if fixed_annual_rate is None:

            base = calculate_lpr_interest(

                principal,

                start_date,

                end_date,

                multiplier=1.0,

                term="1Y",

                rule_mode="commercial_floating",

                today_date=today_date,

            )

            base["rule_mode"] = "private_lending_cap"

            note = (

                "未填写约定年利率。依据《中华人民共和国民法典》第六百八十条第二款及《最高人民法院关于审理民间借贷案件适用法律若干问题的规定》"

                "第二十四条第一款：借款合同对支付利息没有约定的，视为没有利息，出借人主张支付借期内利息的，人民法院不予支持。"

                "依第二十八条第一项，双方对逾期利率也未约定的，出借人可自逾期还款之日起参照当时一年期贷款市场报价利率（1倍 LPR）主张资金占用期间利息。"

                "【醒目提示】四倍 LPR 是约定利率的司法保护上限，绝非未约定利率时的计息标准，严禁以四倍 LPR 代替约定利率！"

                "若双方已约定借期年利率、仅未约定逾期利率，请填写约定年利率后重新测算。"

            )

            base["warnings"] = [note] + list(base.get("warnings") or [])

            base["complaint_statement"] = note + "\n" + base.get("complaint_statement", "")

            return base



        contract_lpr = _lookup_lpr_on_date(sorted_lpr, ref_contract_date, "1Y")

        if ref_contract_date >= d_pivot and contract_lpr is None:

            raise ValueError("无法确定合同成立日的一年期贷款市场报价利率，不能用其他日期的利率代替")



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



        if ref_contract_date >= d_pivot:

            rate_desc = (

                f"《最高人民法院关于审理民间借贷案件适用法律若干问题的规定》第二十五条：合同成立时一年期贷款市场报价利率（{contract_lpr}%）的四倍（{cap_rate_post}%）司法保护上限。"

            )

        else:

            rate_desc = (

                f"《最高人民法院关于审理民间借贷案件适用法律若干问题的规定》第三十一条第二款：2020年8月20日以前适用当时司法解释规定的年利率24%保护上限；该日之后的利息，适用起诉时保护标准（{post_lpr_base}%×4 = {cap_rate_post}%）。"

            )



    # ==========================================================================

    # 模式 C：商事违约同期 LPR 浮动分段计息（默认）

    # ==========================================================================

    else:

        lpr_reform = date(2019, 8, 20)

        breakpoints = []

        if d_start < lpr_reform < d_end:

            breakpoints.append(lpr_reform)

        benchmark_term = term if term in PBOC_BENCHMARK_SCHEDULE else "1Y"

        for bench_start, _bench_rate in PBOC_BENCHMARK_SCHEDULE[benchmark_term]:

            if d_start < bench_start < d_end and bench_start < lpr_reform and bench_start not in breakpoints:

                breakpoints.append(bench_start)

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

                active_rate = lookup_pboc_benchmark(seg_start, benchmark_term)

                if active_rate is None:

                    earliest = PBOC_BENCHMARK_SCHEDULE[benchmark_term][0][0].isoformat()

                    warnings.append(

                        f"有计息日落在 {earliest} 之前。本表未收录当时的"

                        f"{'一年以内' if benchmark_term == '1Y' else '五年以上'}贷款基准利率，该段不计息，请按中国人民银行当时公布的利率手算。"

                    )

                    periods.append({

                        "segment_start": seg_start.strftime("%Y-%m-%d"),

                        "segment_end": seg_end.strftime("%Y-%m-%d"),

                        "days": seg_days,

                        "base_lpr": None,

                        "rate_basis": "贷款基准利率未收录",

                        "multiplier": multiplier,

                        "applied_annual_rate": None,

                        "interest": 0.0,

                    })

                    continue

                rate_basis = (

                    f"中国人民银行金融机构人民币贷款基准利率"

                    f"（{'一年以内（含一年）' if benchmark_term == '1Y' else '五年以上'} {active_rate}%）"

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

                active_rate = lookup_pboc_benchmark(seg_start, benchmark_term)

                if active_rate is None:

                    warnings.append("该段无法对应 LPR 或已收录的贷款基准利率，未计息。")

                    periods.append({

                        "segment_start": seg_start.strftime("%Y-%m-%d"),

                        "segment_end": seg_end.strftime("%Y-%m-%d"),

                        "days": seg_days,

                        "base_lpr": None,

                        "rate_basis": "利率未收录",

                        "multiplier": multiplier,

                        "applied_annual_rate": None,

                        "interest": 0.0,

                    })

                    continue

                rate_basis = "中国人民银行金融机构人民币贷款基准利率"

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

        f"以{'借款' if rule_mode == 'private_lending_cap' else '拖欠款项'}本金人民币 {p_dec:,.2f} 元为基数，自 {start_date} 起至 {end_date} 止，按照{rate_desc}{'标准分段计算逾期违约利息' if rule_mode != 'private_lending_cap' else '分段计算利息'}。",

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

                if p.get("applied_annual_rate") is None:

                    complaint_lines.append(

                        f"  ({idx}) {p['segment_start']} 至 {p['segment_end']}（共 {p['days']} 天）：违约行为发生日没有已收录利率，该段未计息（{basis_note}）；"

                    )

                else:

                    base_word = "贷款市场报价利率" if p.get("base_kind") == "lpr" else "贷款基准利率"

                    complaint_lines.append(

                        f"  ({idx}) {p['segment_start']} 至 {p['segment_end']}（共 {p['days']} 天）：违约行为发生时{base_word} {p['base_lpr']}% × (1+{p['markup_ratio']}) = 执行年化 {p['applied_annual_rate']}%（{basis_note}），该段利息为人民币 {p['interest']:,.2f} 元；"

                    )

            elif p.get("applied_annual_rate") is None:

                complaint_lines.append(

                    f"  ({idx}) {p['segment_start']} 至 {p['segment_end']}（共 {p['days']} 天）：{basis_note}，该段未计息；"

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





LABOR_ARBITRATION_LIMITATION_NOTE = (

    "《劳动争议调解仲裁法》第二十七条：申请仲裁的时效期间为一年，从当事人知道或者应当知道其权利被侵害之日起计算。"

    "向对方主张权利、向有关部门请求救济，或者对方同意履行的，时效中断并重新计算。"

    "劳动关系存续期间因拖欠劳动报酬发生争议的，不受该一年限制；劳动关系终止的，应当自终止之日起一年内提出。"

)





SALES_COMPLAINT_OVERDUE_RATE_DESC = (

    "合同有约定的从约定。没有约定逾期付款违约金的，按《最高人民法院关于审理买卖合同纠纷案件适用法律问题的解释》（2020年修正）第十八条第四款："

    "违约发生在2019年8月20日之后的，以违约行为发生时的一年期贷款市场报价利率加计百分之三十至百分之五十，整个逾期期间利率不再浮动；"

    "违约发生在该日之前的，以当时中国人民银行一年以内（含一年）贷款基准利率加计同样幅度。"

    "本地库未收录该解释全文，引用前请核对公报原文。"

)





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

        labor_warnings.append("三倍封顶基数来自手填。请核对解除时当地职工月平均工资的公报年份和口径，不要使用本工具内置的未核验估算。")

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



    # 代通知金仅在《劳动合同法》第四十条解除且未提前三十日书面通知时计入。

    # 违法解除的最终请求是 2N，不能与 N / N+1 同时作为最终请求。

    article40 = termination_reason == "employer_dismissal_with_notice"

    notice_applicable = article40 and not prior_30days_notice

    if notice_applicable:

        notice_pay = salary_dec

        amount_n_plus_1 = (amount_n + notice_pay).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        notice_note = "解除事由为第四十条且未提前三十日书面通知，计入一个月代通知金（实施条例第二十条，按解除前上月工资；此处以上述月平均工资计入）。"

    elif article40 and prior_30days_notice:

        notice_pay = Decimal("0.00")

        amount_n_plus_1 = amount_n

        notice_note = "已提前三十日书面通知，不计入代通知金。N+1 与 N 相同。"

    else:

        notice_pay = Decimal("0.00")

        amount_n_plus_1 = amount_n

        notice_note = "未按第四十条且未提前通知来计算，N+1 不另加一个月。协商解除、到期终止、劳动者因用人单位过错解除、违法解除，均不计代通知金。"

        if termination_reason is None:

            labor_warnings.append("未选择解除事由，未计代通知金。请选定事由后再决定最终请求。")



    if termination_reason == "unlawful_dismissal":

        claim_mutex_note = "违法解除的最终请求是赔偿金 2N。经济补偿 N 与代通知金不能与 2N 同时作为最终请求金额。"

    elif article40:

        claim_mutex_note = "第四十条解除的最终请求是经济补偿 N；仅在未提前三十日书面通知时再加一个月代通知金。不能同时把 2N 作为最终请求。"

    else:

        claim_mutex_note = "N、N+1、2N 是对照口径，不能相加，也不能同时作为最终请求。请先选定解除事由。"

    labor_warnings.append(claim_mutex_note)



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

        labor_warnings.append("2008年前工龄按劳部发〔1994〕481号计算，月工资按实发、不套用三倍社平封顶。受诉仲裁委或法院另有当地口径的，以当地口径为准。")

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

            "note": "跨2008年分段精算：2008年前工龄按劳部发〔1994〕481号计算，月工资按实发、不套用三倍社平封顶；2008年后工作年限适用三倍社平及12年双封顶。受诉地另有口径的，以当地口径为准。",

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

                "legal_basis": "《劳动合同法》第四十条、第四十七条；《劳动合同法实施条例》第二十条",

                "amount": float(amount_n_plus_1),

                "rmb_capital": rmb_to_capital(amount_n_plus_1),

                "notice_pay": float(notice_pay),

                "notice_applicable": notice_applicable,

                "notice_note": notice_note,

                "formula": (

                    f"经济补偿N({amount_n:,.2f}元) + 1个月代通知金({notice_pay:,.2f}元)"

                    if notice_applicable

                    else f"未计代通知金，金额等于经济补偿N({amount_n:,.2f}元)"

                ),

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

        "notice_applicable": notice_applicable,

        "claim_mutex_note": claim_mutex_note,

        "warnings": list(dict.fromkeys(labor_warnings)),

        "pleading_basis": (

            "segment_2008"

            if segment_2008_info is not None

            else "single_period"

        ),

        "pleading_note": (

            "入职早于2008年1月1日。写入仲裁请求的经济补偿用 segment_2008.total_segmented_n，不要用整段工龄合并后的 N。"

            if segment_2008_info is not None

            else "未跨2008年1月1日，按整段工龄的 N 主张。"

        ),

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

            "special_notice": "只在保证合同没有约定保证期间、约定不明确，或者约定的期间早于主债务履行期限、与主债务履行期限同时届满时，才按届满之日起六个月计算。已经约定明确期间的，按约定，不要用这六个月覆盖。保证期间不发生中止、中断和延长。一般保证的债权人必须在保证期间内起诉主债务人或者申请仲裁，只发函催告不能维持保证责任。"

        },

        "guarantee_joint_6m": {

            "name": "连带责任保证期间（法定除斥期间6个月）",

            "basis": "《民法典》第六百九十二条第二款、第六百九十三条第二款",

            "years": 0.5,

            "months": 6,

            "is_preclusive": True,

            "special_notice": "只在没有约定、约定不明确，或者约定期间早于主债务履行期限、与主债务履行期限同时届满时，才按届满之日起六个月计算。已经约定明确期间的，按约定。保证期间不发生中止、中断和延长。连带责任保证的债权人必须在保证期间内向保证人请求承担保证责任，请求之后对保证人的诉讼时效另行起算三年。"

        },

        "cancel_right_1y": {

            "name": "欺诈/显失公平撤销权（1年）",

            "basis": "《民法典》第一百五十二条",

            "years": 1,

            "months": 12,

            "is_preclusive": True,

            "is_cancel_right": True,

        },

        "cancel_mistake_90d": {

            "name": "重大误解撤销权（90日）",

            "basis": "《民法典》第一百五十二条",

            "years": 0,

            "months": 0,

            "days": 90,

            "is_preclusive": True,

            "is_cancel_right": True,

        },

        "cancel_duress_1y": {

            "name": "胁迫终止之日起撤销权（除斥期间1年）",

            "basis": "《民法典》第一百五十二条第一款第二项",

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

            "special_notice": "起算点按法释〔2020〕25号第四十一条，为发包人应当给付建设工程价款之日。本地库未收录该解释全文，起诉前请核对公报原文。该期间是除斥期间，不适用中止、中断。",

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



    # 期间最后一日顺延（《民法典》第二百零三条、《民事诉讼法》第八十五条）。

    # 显式传入 holidays 时只按该列表顺延，便于核对单一假日。

    # 未传入时：诉讼时效同时顺延法定节假日和未调休的周六、周日，补班日不顺延。

    # 除斥期间只顺延节假日表中的日期，普通周末不自动顺延。

    explicit_holidays = holidays is not None

    if explicit_holidays:

        holiday_set = set(holidays)

        workdays_makeup: set = set()

        treat_weekend = False

    else:

        holiday_set, workdays_makeup = _load_cn_holidays_and_workdays(current_expire.year)

        h_next, w_next = _load_cn_holidays_and_workdays(current_expire.year + 1)

        holiday_set |= h_next

        workdays_makeup |= w_next

        treat_weekend = not is_preclusive



    def _period_is_non_working(d: date) -> bool:

        ds = d.strftime("%Y-%m-%d")

        if ds in holiday_set:

            return True

        if ds in workdays_makeup:

            return False

        if treat_weekend and d.weekday() >= 5:

            return True

        return False



    orig_final_date = current_expire

    extended = False

    while _period_is_non_working(current_expire):

        current_expire = current_expire + timedelta(days=1)

        extended = True



    if extended:

        timeline_log.append({

            "date": orig_final_date.strftime("%Y-%m-%d"),

            "event": f"期间最后一日（{orig_final_date.strftime('%Y-%m-%d')}）为法定休假日，顺延至 {current_expire.strftime('%Y-%m-%d')}（顺延）",

            "action": "法定休假日顺延",

            "expire_date": current_expire.strftime("%Y-%m-%d")

        })



    days_remaining = (current_expire - d_today).days

    is_expired = days_remaining < 0



    if is_expired:

        status_level = "CRITICAL_EXPIRED"

        status_label = "【已过时效/除斥期间届满】"

        if is_preclusive:

            risk_alert = "除斥期间已经届满，权利消灭。催告、对方同意履行都不能让这个期间重新计算。不要把除斥期间说成诉讼时效。"

        else:

            risk_alert = "诉讼时效期间已经届满。对方可以提出不履行义务的抗辩，债权本身不消灭。催告或对方同意履行可以中断时效，但要核对日期和送达。不要把债权说成已经消灭。"

    elif days_remaining <= 30:

        status_level = "URGENT_RED"

        status_label = f"【极度紧急：仅剩 {days_remaining} 天】"

        if is_preclusive:

            risk_alert = f"除斥期间只剩 {days_remaining} 天。这个期间不能中断，发催告函不能续期，要在届满前完成法律规定的主张。"

        else:

            risk_alert = f"诉讼时效只剩 {days_remaining} 天。主张权利或对方同意履行可以中断，但要留下日期和送达。"

    elif days_remaining <= 90:

        status_level = "WARNING_AMBER"

        status_label = f"【高危预警：剩余 {days_remaining} 天】"

        if is_preclusive:

            risk_alert = f"除斥期间还剩 {days_remaining} 天。这个期间不能中断，要在届满前起诉或完成法定主张。"

        else:

            risk_alert = f"诉讼时效还剩 {days_remaining} 天。准备起诉，或留下有日期、能证明送达的主张权利记录。"

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

    《民事诉讼法解释》第一百五十六条：诉中保全的方法和措施，依照执行程序办理。

    第四百八十五条：银行存款及其他资金不得超过一年，动产不得超过二年，不动产和其他财产权不得超过三年；续行不得超过该期限。

    申请续行应当在届满七日前提出（《人民法院办理财产保全案件若干问题的规定》法释〔2016〕22号第十八条）。

    2004年《查封、扣押、冻结财产的规定》第二十九条“续行不得超过二分之一”已废止。

    """

    d_start = datetime.strptime(start_date, "%Y-%m-%d").date()

    d_today = datetime.strptime(today_date, "%Y-%m-%d").date() if today_date else date.today()



    TYPE_RULES = {

        "bank_deposit": {

            "name": "银行存款及现金理财冻结",

            "max_years": 1,

            "advance_days": 7,

            "statute": "《民事诉讼法解释》第一百五十六条、第四百八十五条；续行申请时点见法释〔2016〕22号第十八条。2004年查封规定第二十九条“续行不得超过二分之一”已废止",

            "statute_url": "https://www.court.gov.cn/zixun/xiangqing/30101.html",

            "desc": "冻结银行存款及其他资金的期限不得超过一年；应在届满七日前申请续行"

        },

        "movable_property": {

            "name": "动产（汽车、机器设备、存货）查封扣押",

            "max_years": 2,

            "advance_days": 7,

            "statute": "《民事诉讼法解释》第一百五十六条、第四百八十五条；续行申请时点见法释〔2016〕22号第十八条。2004年查封规定第二十九条“续行不得超过二分之一”已废止",

            "statute_url": "https://www.court.gov.cn/zixun/xiangqing/30101.html",

            "desc": "查封、扣押动产的期限不得超过二年；应在届满七日前申请续行"

        },

        "real_estate_equity": {

            "name": "不动产（房产土地）与股权/知识产权冻结",

            "max_years": 3,

            "advance_days": 7,

            "statute": "《民事诉讼法解释》第一百五十六条、第四百八十五条；续行申请时点见法释〔2016〕22号第十八条。2004年查封规定第二十九条“续行不得超过二分之一”已废止",

            "statute_url": "https://www.court.gov.cn/zixun/xiangqing/30101.html",

            "desc": "查封不动产、冻结其他财产权的期限不得超过三年；应在届满七日前申请续行"

        }

    }



    if preservation_type not in TYPE_RULES:

        allowed = ", ".join(TYPE_RULES.keys())

        raise ValueError(f"preservation_type 非法，允许值: {allowed}")



    rule = TYPE_RULES[preservation_type]

    if custom_years is not None and float(custom_years) > float(rule["max_years"]):

        raise ValueError(

            f"查封、扣押、冻结期限及续行期限均不得超过{rule['max_years']}年。"

            "已废止的“续行不得超过二分之一”不再适用，但也不能超过首次法定上限。"

        )

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

        "renewal_max_years": rule["max_years"],

        "half_term_rule_abolished": True,

        "duration_note": (

            f"首次与续行期限均不得超过{rule['max_years']}年。"

            "2004年《查封规定》第二十九条“续行不得超过二分之一”已废止，不要再按一半排期。"

        ),

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

# 8a. 申请执行期间（《民事诉讼法》2023年修正第二百五十条）

# ==============================================================================

def calculate_enforcement_application_deadline(

    anchor_date: str,

    anchor_type: str = "performance_last_day",

    performance_days: int = 10,

    today_date: Optional[str] = None,

    treat_weekend_as_holiday: bool = True,

) -> Dict[str, Any]:

    """

    申请执行期间为二年。

    《民事诉讼法》（2023修正）第二百五十条：

    - 从法律文书规定履行期间的最后一日起计算；

    - 规定分期履行的，从最后一期履行期限届满之日起计算；

    - 未规定履行期间的，从法律文书生效之日起计算。

    期间开始的当日不计入（《民事诉讼法》第八十五条）。

    届满日为法定休假日的，顺延至休假日后的第一日。

    中止、中断适用诉讼时效规则，本函数只算没有中断时的二年届满日。

    """

    anchors = {

        "performance_last_day": "法律文书规定履行期间的最后一日",

        "last_installment": "最后一期履行期限届满之日",

        "effective_date": "法律文书生效之日（文书未规定履行期间）",

        "effective_plus_days": "法律文书生效之日，并按指定履行天数算出履行期间最后一日",

    }

    kind = (anchor_type or "").strip()

    if kind not in anchors:

        raise ValueError("anchor_type 仅允许 performance_last_day、last_installment、effective_date、effective_plus_days")

    if performance_days < 0:

        raise ValueError("履行天数不能为负数")



    d_anchor = datetime.strptime(anchor_date, "%Y-%m-%d").date()

    d_today = datetime.strptime(today_date, "%Y-%m-%d").date() if today_date else date.today()



    if kind == "effective_plus_days":

        period_start = d_anchor + timedelta(days=int(performance_days))

        start_note = (

            f"文书于 {anchor_date} 生效，并规定生效之日起 {int(performance_days)} 日内履行。"

            f"生效当日不计入，履行期间最后一日为 {period_start.strftime('%Y-%m-%d')}。"

        )

    else:

        period_start = d_anchor

        start_note = f"起算点（{anchors[kind]}）为 {anchor_date}。该日不计入二年期间。"



    try:

        raw_deadline = period_start.replace(year=period_start.year + 2)

    except ValueError:

        raw_deadline = period_start.replace(year=period_start.year + 2, month=2, day=28)



    holiday_set, workdays_makeup = _load_cn_holidays_and_workdays(raw_deadline.year)

    h_next, w_next = _load_cn_holidays_and_workdays(raw_deadline.year + 1)

    holiday_set |= h_next

    workdays_makeup |= w_next



    def _is_non_working(d: date) -> bool:

        ds = d.strftime("%Y-%m-%d")

        if ds in holiday_set:

            return True

        if ds in workdays_makeup:

            return False

        if treat_weekend_as_holiday and d.weekday() >= 5:

            return True

        return False



    deadline = raw_deadline

    extended = False

    while _is_non_working(deadline):

        deadline = deadline + timedelta(days=1)

        extended = True



    days_remaining = (deadline - d_today).days

    if days_remaining < 0:

        status_label = "【申请执行期间已届满】"

        risk_alert = "二年申请执行期间已经届满。请先核查是否存在中断事由；对方提出时效抗辩时，不能再按本届满日申请执行。"

    elif days_remaining <= 30:

        status_label = f"【极度紧急：仅剩 {days_remaining} 天】"

        risk_alert = "须立即准备执行申请材料。本结果不含中止、中断；若有中断，届满日要另算。"

    elif days_remaining <= 90:

        status_label = f"【临近届满：剩余 {days_remaining} 天】"

        risk_alert = "进入执行立案准备期。分期履行的，现行法从最后一期届满日起算，不要再按每一期单独起算。"

    else:

        status_label = f"【期间尚余 {days_remaining} 天】"

        risk_alert = "在二年申请执行期间内。发生催收、部分履行等中断事由时，不要继续用本次届满日。"



    return {

        "anchor_date": anchor_date,

        "anchor_type": kind,

        "anchor_label": anchors[kind],

        "performance_days": int(performance_days) if kind == "effective_plus_days" else None,

        "period_start_date": period_start.strftime("%Y-%m-%d"),

        "raw_deadline": raw_deadline.strftime("%Y-%m-%d"),

        "deadline": deadline.strftime("%Y-%m-%d"),

        "extended_for_holiday_or_weekend": extended,

        "days_remaining": days_remaining,

        "is_expired": days_remaining < 0,

        "status_label": status_label,

        "risk_alert": risk_alert,

        "start_note": start_note,

        "legal_basis": "《中华人民共和国民事诉讼法》（2023修正）第二百五十条、第八十五条",

        "interruption_note": "申请执行时效的中止、中断，适用诉讼时效的中止、中断。本测算只给出没有中断时的二年届满日。",

        "installment_note": "法律文书规定分期履行的，从最后一期履行期限届满之日起计算，不是从每一期分别起算。",

    }





# ==============================================================================

# 8b. 上诉期截止日测算（《民事诉讼法》第171条；送达次日起算）

# ==============================================================================

def _load_cn_holidays_and_workdays(year: Optional[int] = None) -> Tuple[set, set]:

    """从 data/legal/holidays_cn.json 加载节假日集合与周末调休上班（补班）集合。"""

    from pathlib import Path



    path = Path(__file__).resolve().parents[2] / "data" / "legal" / "holidays_cn.json"

    try:

        with open(path, encoding="utf-8") as f:

            data = json.load(f)

    except Exception:

        return set(), set()

    years = data.get("years") or {}

    holidays = set()

    workdays_makeup = set()

    if year is not None and str(year) in years:

        yinfo = years[str(year)]

        holidays.update(yinfo.get("dates") or [])

        workdays_makeup.update(yinfo.get("workdays_makeup") or [])

    else:

        for yinfo in years.values():

            holidays.update(yinfo.get("dates") or [])

            workdays_makeup.update(yinfo.get("workdays_makeup") or [])

    return holidays, workdays_makeup





def _load_cn_holidays_set(year: Optional[int] = None) -> set:

    """保持向后兼容：从 data/legal/holidays_cn.json 加载节假日。"""

    holidays, _ = _load_cn_holidays_and_workdays(year)

    return holidays





def is_prc_non_working_day(target_date_str: str, treat_weekend_as_holiday: bool = True) -> bool:

    """

    判断指定日期是否为中国法律意义上的非工作日（法定休假日或周末未调休）。

    依据《民法典》第203条及《民事诉讼法》第85条第2款：

    - 若该日为国务院公布的法定节假日：返回 True；

    - 若该日为周六/周日但属于国务院调休补班工作日（workdays_makeup）：返回 False（正常工作日，不顺延）；

    - 若该日为周六/周日且未调休：若 treat_weekend_as_holiday 为 True 则返回 True，否则返回 False；

    - 其它正常周一至周五工作日：返回 False。

    """

    d = datetime.strptime(target_date_str, "%Y-%m-%d").date()

    holidays, workdays_makeup = _load_cn_holidays_and_workdays(d.year)

    ds = d.strftime("%Y-%m-%d")

    if ds in holidays:

        return True

    if ds in workdays_makeup:

        return False

    if treat_weekend_as_holiday and d.weekday() >= 5:

        return True

    return False





def calculate_appeal_deadline(

    service_date: str,

    judgment_type: str,

    holidays: Optional[List[str]] = None,

    treat_weekend_as_holiday: bool = True,

    party_without_domicile: bool = False,

) -> Dict[str, Any]:

    """

    上诉期截止日测算。

    《民事诉讼法》（2023修正）第171条：判决15日、裁定10日，自送达之日起计算；

    实务口径：自送达次日起算满相应日数之日为届满日；

    最后一日为法定节假日的，顺延至节假日后第一日（《民法典》第二百零三条、《民事诉讼法》第八十五条第二款）。

    未调休的周六、周日按非工作日顺延；国务院调休补班日不顺延。节假日见 data/legal/holidays_cn.json。

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



    if party_without_domicile:

        period_days = 30



    d_service = datetime.strptime(service_date, "%Y-%m-%d").date()

    # 送达次日起算：届满日 = 送达日 + period_days

    deadline = d_service + timedelta(days=period_days)



    holiday_set, workdays_makeup = _load_cn_holidays_and_workdays(d_service.year)

    if holidays is None:

        h_next, w_next = _load_cn_holidays_and_workdays(deadline.year)

        holiday_set |= h_next

        workdays_makeup |= w_next

    else:

        holiday_set = set(holidays)



    def _is_non_working(d: date) -> bool:

        ds = d.strftime("%Y-%m-%d")

        if ds in holiday_set:

            return True

        if ds in workdays_makeup:

            return False

        if treat_weekend_as_holiday and d.weekday() >= 5:

            return True

        return False



    extended = False

    while _is_non_working(deadline):

        deadline = deadline + timedelta(days=1)

        extended = True



    warnings: List[str] = []

    if holidays is None:

        from pathlib import Path

        h_path = Path(__file__).resolve().parents[2] / "data" / "legal" / "holidays_cn.json"

        try:

            with open(h_path, encoding="utf-8") as f_h:

                h_data = json.load(f_h)

            known_years = set((h_data.get("years") or {}).keys())

        except Exception:

            known_years = set()

        missing_years = [y for y in sorted(set([d_service.year, deadline.year])) if str(y) not in known_years]

        if missing_years:

            m_str = "、".join(str(y) for y in missing_years)

            warn_msg = (

                f"【法定节假日数据缺失警告】系统节假日库中尚未收录 {m_str} 年的国务院办公厅节假日安排通知。"

                f"当前仅能按普通周六日规则粗算，无法自动识别法定休假日与调休上班日，可能导致届满日计算偏差。承办律师请务必核对官方最新通知人工核实！"

            )

            warnings.append(warn_msg)



    notes = [

        (

            "在中华人民共和国领域内没有住所的当事人，不服第一审判决、裁定的，上诉期为三十日，自送达次日起算（《民事诉讼法》第二百八十六条）。"

            if party_without_domicile

            else "起算：自送达次日起算（《民事诉讼法》第一百七十一条）。"

        ),

        (

            "期间：三十日。判决和裁定相同，不按国内的十五日或十日。"

            if party_without_domicile

            else f"期间：{'判决十五日' if jt_norm == 'judgment' else '裁定十日'}。"

        ),

        "最后一日为法定休假日的，以休假日后的第一日为届满日（《民法典》第二百零三条、《民事诉讼法》第八十五条第二款）。",

        (

            "未调休的周六、周日按非工作日顺延；国务院安排的补班日不顺延。"

            if treat_weekend_as_holiday

            else "当前只顺延法定节假日，普通周六、周日不顺延。"

        ),

    ]

    if warnings:

        notes = warnings + notes

    elif holidays is None:

        notes.append("2024至2027年节假日与补班日来自国务院办公厅假期安排通知（data/legal/holidays_cn.json，已核验）。尚未公布的年份仍会提示节假日数据缺失。")



    return {

        "service_date": service_date,

        "judgment_type": jt_norm,

        "period_days": period_days,

        "deadline": deadline.strftime("%Y-%m-%d"),

        "extended_for_holiday_or_weekend": extended,

        "treat_weekend_as_holiday": treat_weekend_as_holiday,

        "holidays_applied": sorted(holiday_set) if holidays is not None else "loaded_from_file_or_empty",

        "notes": notes,

        "warnings": warnings,

        "legal_basis": (

            "《中华人民共和国民事诉讼法》（2023修正）第二百八十六条"

            if party_without_domicile

            else "《中华人民共和国民事诉讼法》（2023修正）第一百七十一条"

        ),

        "party_without_domicile": bool(party_without_domicile),

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

    warnings = [

        "这里只算加倍部分。生效文书确定的一般债务利息要另计，两笔不能揉成一个数。",

        "分期履行时，每一期从该期履行期间届满日分别起算。这和申请执行期间从最后一期起算不是同一口径。",

        "天数按清偿日减去履行期间届满日。届满当日不计入，清偿当日计入。起算日请填届满日，不要填届满次日。",

    ]



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

        "day_count_note": "天数＝清偿日减去履行期间届满日。届满当日不计入，清偿当日计入。",

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

    依据《最高人民法院关于适用〈中华人民共和国民法典〉合同编通则若干问题的解释》第六十五条：

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

        "legal_basis": "《最高人民法院关于适用〈中华人民共和国民法典〉合同编通则若干问题的解释》第六十五条",

        "warnings": [

            "超过损失百分之三十只是一般可以认定为过分高于，恶意违约一方请求减少的，一般不予支持。",

            "是否调减以及减多少，由法院兼顾合同履行、过错和履约背景衡量，这里不计算减到多少。",

        ],

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

            "4. 债务履行期限届满前达成的以物抵债协议，适用《九民纪要》第44条及《合同编通则解释》第二十八条："

            "约定到期不清偿则抵债财产归债权人所有的，该约定无效，但不影响合同其他部分的效力，债权人可以请求拍卖、变卖、折价。"

            "财产权利尚未转移到债权人名下的，不能据此主张优先受偿。"

        )

        memo_lines.append("")



    memo_lines.append("【合伙人实战谈判反制策略清单】")

    memo_lines.append("1. 【穿透增信底线】：坚决拒绝纯资产挂账抵顶！必须要求债务人控股股东、实际控制人及其配偶签署《个人无限连带责任保证书》，锁定高管个人财产线索。")

    memo_lines.append("2. 【惩罚性加速到期条款】：在和解协议中必须加入严密的违约条款：")

    memo_lines.append("   『若债务人迟延履行任何一期款项或迟延办理抵债资产网签过户超过 7 日，我方所作出的任何金额让利承诺立即自动失效，全部剩余债权（包含原全部本金、按LPR 4倍计算之利息及诉讼费）立即视为全部到期，我方有权就未受偿全额立即申请人民法院强制执行原生效法律文书！』")

    memo_lines.append("3. 【差额现金兜底补足】：抵债资产变现价值不足抵偿我方债权净额的部分，必须约定由债务人在法拍/处置完毕后 30 日内以现金全额补齐，不得作为豁免债务。")



    return "\n".join(memo_lines)



