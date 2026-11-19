# -*- coding: utf-8 -*-
"""
LawFlow 智律工作台 - 最高人民法院《要素式民事起诉状》（民间借贷纠纷示范文本）Word 模板生成器
依据 2024–2026 年最高人民法院、司法部、中华全国律师协会联合印发的
《关于印发部分案件民事起诉状、答辩状示范文本（试行）的通知》（法〔2024〕46号）标准研制。
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml import parse_xml, OxmlElement
from docx.oxml.ns import nsdecls, qn


def set_run_font(run, font_name="仿宋", size_pt=12, bold=False, color_rgb=(0, 0, 0)):
    run.font.name = font_name
    run.font.size = Pt(size_pt)
    run.font.bold = bold
    run.font.color.rgb = RGBColor(*color_rgb)
    rPr = run._r.get_or_add_rPr()
    rFonts = parse_xml(f'<w:rFonts {nsdecls("w")} w:ascii="{font_name}" w:hAnsi="{font_name}" w:eastAsia="{font_name}"/>')
    rPr.append(rFonts)


def format_paragraph(p, align=WD_ALIGN_PARAGRAPH.LEFT, line_spacing_pt=20, space_after=3):
    p.alignment = align
    p.paragraph_format.line_spacing = Pt(line_spacing_pt)
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(space_after)


def set_cell_border(cell, **kwargs):
    """设置单元格四周边框"""
    tcPr = cell._tc.get_or_add_tcPr()
    tcBorders = parse_xml(
        f'<w:tcBorders {nsdecls("w")}>\n'
        f'  <w:top w:val="{kwargs.get("top", "single")}" w:sz="{kwargs.get("top_sz", "4")}" w:space="0" w:color="{kwargs.get("color", "000000")}"/>\n'
        f'  <w:left w:val="{kwargs.get("left", "single")}" w:sz="{kwargs.get("left_sz", "4")}" w:space="0" w:color="{kwargs.get("color", "000000")}"/>\n'
        f'  <w:bottom w:val="{kwargs.get("bottom", "single")}" w:sz="{kwargs.get("bottom_sz", "4")}" w:space="0" w:color="{kwargs.get("color", "000000")}"/>\n'
        f'  <w:right w:val="{kwargs.get("right", "single")}" w:sz="{kwargs.get("right_sz", "4")}" w:space="0" w:color="{kwargs.get("color", "000000")}"/>\n'
        f'</w:tcBorders>'
    )
    tcPr.append(tcBorders)


def set_cell_background(cell, hex_color="F2F4F8"):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{hex_color}"/>')
    tcPr.append(shd)


def build_spc_element_complaint_docx(
    target_path: Optional[str] = None,
    fields: Optional[dict] = None,
    cause: str = "民间借贷纠纷",
) -> str:
    """
    按案由生成要素式起诉状（或劳动争议仲裁申请要素表），并把案件字段填进表格。
    空字段写作【待填写】。民间借贷参照法〔2024〕46号示范文本的要素，不是官方空白表扫描件。
    """
    if target_path is None:
        root = Path(__file__).resolve().parents[2]
        target_path = str(root / "templates" / "spc_element_complaint_private_lending.docx")

    os.makedirs(os.path.dirname(target_path) or ".", exist_ok=True)
    data = dict(fields or {})
    cause = (cause or "民间借贷纠纷").strip()
    titles = {
        "民间借贷纠纷": "民 事 起 诉 状\n（民间借贷纠纷要素式）",
        "买卖合同纠纷": "民 事 起 诉 状\n（买卖合同纠纷要素式）",
        "劳动争议": "劳动争议仲裁申请要素表\n（劳动争议原则上先仲裁）",
        "离婚纠纷": "民 事 起 诉 状\n（离婚纠纷要素式）",
    }
    title_text = titles.get(cause, f"民 事 起 诉 状\n（{cause}要素式）")

    def fill(text: str) -> str:
        def repl(match: re.Match) -> str:
            key = match.group(1).strip()
            val = data.get(key)
            if val is None or str(val).strip() == "":
                return "【待填写】"
            return str(val)
        return re.sub(r"\{\{\s*([^{}]+?)\s*\}\}", repl, text)

    doc = Document()

    # 设置 A4 页边距：上 2.54cm，下 2.54cm，左 2.8cm，右 2.6cm
    sections = doc.sections
    for section in sections:
        section.top_margin = Inches(1.0)
        section.bottom_margin = Inches(1.0)
        section.left_margin = Inches(1.1)
        section.right_margin = Inches(1.0)

    # 1. 标题
    title_p = doc.add_paragraph()
    format_paragraph(title_p, align=WD_ALIGN_PARAGRAPH.CENTER, line_spacing_pt=32, space_after=12)
    t_run = title_p.add_run(title_text)
    set_run_font(t_run, font_name="黑体", size_pt=18, bold=True)

    # 表头说明
    note_p = doc.add_paragraph()
    format_paragraph(note_p, align=WD_ALIGN_PARAGRAPH.LEFT, line_spacing_pt=16, space_after=8)
    n_run = note_p.add_run("【填表提示】依据最高人民法院、司法部、中华全国律师协会《示范文本》规范，请在对应要素栏完整填报。带 * 项为关键法律适用与证据核验要素。")
    set_run_font(n_run, font_name="楷体", size_pt=10, color_rgb=(100, 100, 100))

    # 表格：2 列（要素类别 / 要素内容）
    table = doc.add_table(rows=0, cols=2)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False

    col_widths = [Inches(1.8), Inches(4.7)]

    def add_element_row(header_text: str, content_template: str, is_section_header: bool = False, bg_color: str = "FFFFFF"):
        header_text = fill(header_text)
        content_template = fill(content_template)
        row = table.add_row()
        cell_0 = row.cells[0]
        cell_1 = row.cells[1]

        cell_0.width = col_widths[0]
        cell_1.width = col_widths[1]

        set_cell_border(cell_0, top_sz="4", bottom_sz="4", left_sz="4", right_sz="4", color="888888")
        set_cell_border(cell_1, top_sz="4", bottom_sz="4", left_sz="4", right_sz="4", color="888888")

        if is_section_header:
            set_cell_background(cell_0, "E9EDF4")
            set_cell_background(cell_1, "E9EDF4")
            p0 = cell_0.paragraphs[0]
            format_paragraph(p0, align=WD_ALIGN_PARAGRAPH.LEFT, line_spacing_pt=18, space_after=2)
            r0 = p0.add_run(header_text)
            set_run_font(r0, font_name="黑体", size_pt=11, bold=True, color_rgb=(20, 50, 120))

            p1 = cell_1.paragraphs[0]
            format_paragraph(p1, align=WD_ALIGN_PARAGRAPH.LEFT, line_spacing_pt=18, space_after=2)
            r1 = p1.add_run(content_template)
            set_run_font(r1, font_name="黑体", size_pt=11, bold=True, color_rgb=(20, 50, 120))
        else:
            if bg_color != "FFFFFF":
                set_cell_background(cell_0, bg_color)
                set_cell_background(cell_1, bg_color)
            else:
                set_cell_background(cell_0, "F8F9FA")

            p0 = cell_0.paragraphs[0]
            format_paragraph(p0, align=WD_ALIGN_PARAGRAPH.LEFT, line_spacing_pt=16, space_after=2)
            r0 = p0.add_run(header_text)
            set_run_font(r0, font_name="仿宋", size_pt=10.5, bold=True)

            p1 = cell_1.paragraphs[0]
            format_paragraph(p1, align=WD_ALIGN_PARAGRAPH.LEFT, line_spacing_pt=16, space_after=2)
            r1 = p1.add_run(content_template)
            set_run_font(r1, font_name="仿宋", size_pt=10.5)

    # 一、当事人信息
    add_element_row("一、当事人信息", "主体基本信息", is_section_header=True)
    add_element_row("原告（自然人/法人）", "姓名/名称：{{ plaintiff_name }}\n证件类型及号码：{{ plaintiff_id_or_uscc }}\n联系方式及住所地：{{ plaintiff_phone }} / {{ plaintiff_address }}")
    add_element_row("委托诉讼代理人", "姓名：{{ lawyer_name }}\n执业机构：{{ law_firm_name }}\n联系电话及代理权限：{{ lawyer_phone }} / {{ lawyer_auth_scope }}")
    add_element_row("被告（自然人/法人）", "姓名/名称：{{ defendant_name }}\n身份证号/统一代码：{{ defendant_id_or_uscc }}\n联系电话及经常居住地：{{ defendant_phone }} / {{ defendant_address }}")
    add_element_row("保证人/第三人", "姓名/名称：{{ guarantor_name }}\n身份信息及联系方式：{{ guarantor_info }}")

    # 二、请求与事实。民间借贷保持原要素；其余案由用对应要素，不把借贷栏套到离婚或劳动上。
    if cause == "买卖合同纠纷":
        add_element_row("二、诉讼请求要素", "货款与违约", is_section_header=True)
        add_element_row("1. 货款 *", "请求判令被告支付货款人民币 {{ principal_amount }} 元（大写：{{ principal_capital }}）。")
        add_element_row("2. 逾期利息或违约金", "{{ overdue_interest }}")
        add_element_row("3. 诉讼费用", "本案案件受理费由被告承担。")
        add_element_row("三、事实要素", "买卖合同", is_section_header=True)
        add_element_row("合同与交付 *", "合同签订：{{ contract_date }}。标的与交付：{{ payment_method }}。")
        add_element_row("欠付金额 *", "约定价款 {{ agreed_amount }} 元，已付 {{ repaid_amount }} 元，尚欠 {{ actual_lent_amount }} 元。")
        add_element_row("事实与理由", "{{ facts_and_reasons }}")
    elif cause == "劳动争议":
        add_element_row("二、仲裁请求要素", "经济补偿与工资。N 与 2N 不能同时作为最终请求。", is_section_header=True)
        add_element_row("1. 请求金额 *", "请求金额人民币 {{ principal_amount }} 元。解除事由与是否提前三十日通知：{{ loan_term_desc }}。")
        add_element_row("2. 工资与补偿口径", "离职前十二个月平均工资：{{ agreed_rate_desc }}。经济补偿 / 代通知金 / 赔偿金请按已选定的单一请求填写，不要三档相加。")
        add_element_row("三、用工事实", "先仲裁", is_section_header=True)
        add_element_row("入职与解除 *", "入职：{{ contract_date }}。解除：{{ transfer_date }}。岗位与工资：{{ payment_method }}。")
        add_element_row("事实与理由", "{{ facts_and_reasons }}")
    elif cause == "离婚纠纷":
        add_element_row("二、诉讼请求要素", "身份、子女、财产", is_section_header=True)
        add_element_row("1. 解除婚姻关系 *", "请求判决解除婚姻关系。结婚登记时间：{{ contract_date }}。")
        add_element_row("2. 子女抚养", "{{ guarantee_claim_desc }}")
        add_element_row("3. 财产与债务", "{{ in_term_interest }}")
        add_element_row("三、事实要素", "婚姻基础事实", is_section_header=True)
        add_element_row("感情与分居", "{{ facts_and_reasons }}")
    else:
        add_element_row("二、诉讼请求要素", "请求项目与数额清单", is_section_header=True)
        add_element_row("1. 借款本金 *", "请求判令被告向原告偿还借款本金：人民币 {{ principal_amount }} 元（大写：{{ principal_capital }}）。")
        add_element_row("2. 利息及违约金 *", "借期内利息：{{ in_term_interest }}\n逾期利息（以民间借贷司法解释规定的上限为限，不是当然按四倍 LPR）：{{ overdue_interest }}")
        add_element_row("3. 担保权利主张 *", "{{ guarantee_claim_desc }}")
        add_element_row("4. 实现债权费用", "律师费/保全担保费/诉讼保全险费：{{ legal_costs }}")
        add_element_row("5. 诉讼费用负担", "本案案件受理费、保全申请费由被告承担。")
        add_element_row("三、管辖与保全", "程序要素", is_section_header=True)
        add_element_row("管辖约定", "合同是否有管辖约定：{{ jurisdiction_clause }}")
        add_element_row("财产保全情况", "是否已申请财产保全：{{ preservation_status }}")
        add_element_row("四、事实与理由要素", "借贷事实认定核心链条", is_section_header=True)
        add_element_row("1. 借款合同签订情况 *", "合同签订时间：{{ contract_date }}，签订方式：{{ contract_sign_type }}（书面/电子转账微信借条）")
        add_element_row("2. 约定金额与实借金额 *", "约定借款：{{ agreed_amount }} 元；实际出借：{{ actual_lent_amount }} 元（须律师核查有无预扣利息）")
        add_element_row("3. 款项交付方式与时间 *", "交付方式：{{ payment_method }}，交付时间：{{ transfer_date }}")
        add_element_row("4. 借款期限与利率 *", "约定借款期限：{{ loan_term_desc }}；约定年利率：{{ agreed_rate_desc }}")
        add_element_row("5. 还款与抵充情况 *", "被告已还款金额：{{ repaid_amount }} 元。抵充顺序须律师按《民法典》第五百六十一条核算：{{ payment_offset_desc }}")
        add_element_row("6. 保证担保事实 *", "保证方式：{{ guarantee_type }}；保证期间及催告证据：{{ guarantee_period_desc }}")
        add_element_row("7. 事实与法理陈述", "{{ facts_and_reasons }}")

    add_element_row("五、附项", "附送材料清单", is_section_header=True)
    add_element_row("证据清单与页码", "详见随卷《证据目录》。页码以贝茨编码合卷为准。")

    # 署名区
    doc.add_paragraph()
    footer_p1 = doc.add_paragraph()
    format_paragraph(footer_p1, align=WD_ALIGN_PARAGRAPH.RIGHT, line_spacing_pt=26, space_after=4)
    r_court = footer_p1.add_run(fill("此致\n{{ court_name }}\n\n"))
    set_run_font(r_court, font_name="仿宋", size_pt=14)

    footer_p2 = doc.add_paragraph()
    format_paragraph(footer_p2, align=WD_ALIGN_PARAGRAPH.RIGHT, line_spacing_pt=26, space_after=4)
    r_sign = footer_p2.add_run(fill("具状人（签名或盖章）：{{ plaintiff_name }}\n\n{{ current_date_cn }}"))
    set_run_font(r_sign, font_name="仿宋", size_pt=14)

    doc.save(target_path)
    return target_path


if __name__ == "__main__":
    out = build_spc_element_complaint_docx()
    print(f"SPC Element Complaint template generated at: {out}")
