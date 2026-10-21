"""
LawFlow 智律工作台 - 三大高频案由全套标准法律文书 Jinja2 Word (.docx) 模板自动化生成脚本
排版严格遵循《党政机关公文格式》(GB/T 9704-2012) 与中国各级法院立案公文规范：
- 标题：二号（22pt）黑体/方正小标宋，加粗居中
- 正文：仿宋_GB2312 / 仿宋，四号（14pt）或三号（16pt），固定行距 28 磅，首行缩进 2 字符
- 表格：标准公文三线表或法院立案确认表，单线/双线标准磅值
- 模板内置 docxtpl / Jinja2 占位符标签，可直接动态注入案件要素

三大高频案由模板清单：
1. 民间借贷纠纷全套：
   - 《民事起诉状》(借贷版) (civil_complaint_loan_template.docx)
   - 《民事授权委托书》 (power_of_attorney_template.docx)
   - 《法定代表人身份证明书》 (legal_representative_template.docx)
   - 《送达地址确认书》 (service_address_template.docx)
2. 劳动人事争议全套：
   - 《劳动人事争议仲裁申请书》 (labor_arbitration_template.docx)
   - 《经济补偿金计算清单》 (labor_compensation_calc_template.docx)
3. 买卖合同欠款纠纷全套：
   - 《民事起诉状》(买卖合同版) (civil_complaint_sales_template.docx)
   - 《财产保全申请书》 (property_preservation_template.docx)
"""

import os
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls


def set_run_font(run, font_name="仿宋", size_pt=14, bold=False, color_rgb=(0, 0, 0)):
    """设置文本块的中西文字体、字号与加粗（四号字14pt，正文公文标准）"""
    run.font.name = font_name
    run.font.size = Pt(size_pt)
    run.font.bold = bold
    run.font.color.rgb = RGBColor(*color_rgb)
    rPr = run._r.get_or_add_rPr()
    rFonts = parse_xml(f'<w:rFonts {nsdecls("w")} w:ascii="{font_name}" w:hAnsi="{font_name}" w:eastAsia="{font_name}"/>')
    rPr.append(rFonts)


def format_paragraph(p, align=WD_ALIGN_PARAGRAPH.JUSTIFY, first_line_indent_chars=2, line_spacing_pt=28):
    """标准公文段落排版：两端对齐、首行缩进2字符、固定行距28磅"""
    p.alignment = align
    p.paragraph_format.first_line_indent = Pt(14 * first_line_indent_chars) if first_line_indent_chars > 0 else Pt(0)
    p.paragraph_format.line_spacing = Pt(line_spacing_pt)
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(4)


def set_cell_border(cell, **kwargs):
    """设置表格单元格边框"""
    tcPr = cell._tc.get_or_add_tcPr()
    tcBorders = parse_xml(
        f'<w:tcBorders {nsdecls("w")}>\n'
        f'  <w:top w:val="{kwargs.get("top", "single")}" w:sz="{kwargs.get("top_sz", "4")}" w:space="0" w:color="000000"/>\n'
        f'  <w:left w:val="{kwargs.get("left", "single")}" w:sz="{kwargs.get("left_sz", "4")}" w:space="0" w:color="000000"/>\n'
        f'  <w:bottom w:val="{kwargs.get("bottom", "single")}" w:sz="{kwargs.get("bottom_sz", "4")}" w:space="0" w:color="000000"/>\n'
        f'  <w:right w:val="{kwargs.get("right", "single")}" w:sz="{kwargs.get("right_sz", "4")}" w:space="0" w:color="000000"/>\n'
        f'</w:tcBorders>'
    )
    tcPr.append(tcBorders)


def apply_page_margins(doc):
    """公文边距：上3.7cm，下3.5cm，左2.8cm，右2.6cm"""
    for section in doc.sections:
        section.top_margin = Inches(1.4)
        section.bottom_margin = Inches(1.3)
        section.left_margin = Inches(1.1)
        section.right_margin = Inches(1.0)


# ==============================================================================
# 案由一：民间借贷纠纷全套
# ==============================================================================
def create_civil_complaint_loan_template(output_path: str):
    """民间借贷《民事起诉状》模板"""
    doc = Document()
    apply_page_margins(doc)

    title_p = doc.add_paragraph()
    format_paragraph(title_p, align=WD_ALIGN_PARAGRAPH.CENTER, first_line_indent_chars=0, line_spacing_pt=32)
    r = title_p.add_run("民 事 起 诉 状")
    set_run_font(r, font_name="黑体", size_pt=22, bold=True)
    doc.add_paragraph()

    # 原被告
    p1 = doc.add_paragraph()
    format_paragraph(p1, first_line_indent_chars=0)
    r = p1.add_run("原告：")
    set_run_font(r, font_name="黑体", size_pt=14, bold=True)
    r = p1.add_run("{{ plaintiff_name }}，{{ plaintiff_gender }}，{{ plaintiff_birth }}出生，{{ plaintiff_ethnicity }}，住址：{{ plaintiff_address }}。身份证号码：{{ plaintiff_id }}。联系电话：{{ plaintiff_phone }}。")
    set_run_font(r, font_name="仿宋", size_pt=14)

    p2 = doc.add_paragraph()
    format_paragraph(p2, first_line_indent_chars=0)
    r = p2.add_run("被告：")
    set_run_font(r, font_name="黑体", size_pt=14, bold=True)
    r = p2.add_run("{{ defendant_name }}，{{ defendant_gender }}，{{ defendant_birth }}出生，{{ defendant_ethnicity }}，住址：{{ defendant_address }}。公民身份号码：{{ defendant_id }}。联系电话：{{ defendant_phone }}。")
    set_run_font(r, font_name="仿宋", size_pt=14)
    doc.add_paragraph()

    # 诉讼请求
    p3 = doc.add_paragraph()
    format_paragraph(p3, first_line_indent_chars=0)
    r = p3.add_run("诉讼请求：")
    set_run_font(r, font_name="黑体", size_pt=14, bold=True)

    p_claims = doc.add_paragraph()
    format_paragraph(p_claims, first_line_indent_chars=2)
    r = p_claims.add_run(
        "1. 判令被告立即向原告偿还借款本金人民币 {{ loan_principal }} 元（大写：{{ loan_principal_capital }}）；\n"
        "2. 判令被告向原告支付自 {{ interest_start_date }} 起至实际清偿之日止的借期内利息及逾期违约利息（暂计至 {{ interest_end_date }} 为人民币 {{ total_interest }} 元，大写：{{ total_interest_capital }}）；\n"
        "3. 判令被告承担原告为主张本案债权所支出的律师费人民币 {{ lawyer_fee }} 元；\n"
        "4. 判令本案全部案件受理费、保全申请费及公告费由被告承担。"
    )
    set_run_font(r, font_name="仿宋", size_pt=14)

    # 事实与理由
    p4 = doc.add_paragraph()
    format_paragraph(p4, first_line_indent_chars=0)
    r = p4.add_run("事实与理由：")
    set_run_font(r, font_name="黑体", size_pt=14, bold=True)

    p_facts = doc.add_paragraph()
    format_paragraph(p_facts, first_line_indent_chars=2)
    r = p_facts.add_run("{{ facts_and_reasons }}\n\n{{ interest_calc_statement }}")
    set_run_font(r, font_name="仿宋", size_pt=14)
    doc.add_paragraph()

    # 此致
    p_to = doc.add_paragraph()
    format_paragraph(p_to, first_line_indent_chars=0)
    r = p_to.add_run("此致\n")
    set_run_font(r, font_name="仿宋", size_pt=14)
    r2 = p_to.add_run("{{ court_name }}人民法院")
    set_run_font(r2, font_name="黑体", size_pt=14, bold=True)
    doc.add_paragraph()

    # 具状人与附项
    p_sign = doc.add_paragraph()
    format_paragraph(p_sign, align=WD_ALIGN_PARAGRAPH.RIGHT, first_line_indent_chars=0)
    r = p_sign.add_run("具状人（签名/盖章）：{{ plaintiff_name }}          \n\n日期：{{ filing_date }}          ")
    set_run_font(r, font_name="仿宋", size_pt=14)

    p_attach = doc.add_paragraph()
    format_paragraph(p_attach, first_line_indent_chars=0)
    r = p_attach.add_run("附：\n1. 借条/借款协议、银行转账凭证等主要证据材料复印件 1 套；\n2. 原告身份证复印件 1 份；\n3. 本起诉状副本 1 份。")
    set_run_font(r, font_name="仿宋", size_pt=12)

    doc.save(output_path)
    print(f"[*] 成功生成民间借贷起诉状模板: {output_path}")


def create_legal_representative_template(output_path: str):
    """《法定代表人身份证明书》模板"""
    doc = Document()
    apply_page_margins(doc)

    title_p = doc.add_paragraph()
    format_paragraph(title_p, align=WD_ALIGN_PARAGRAPH.CENTER, first_line_indent_chars=0, line_spacing_pt=32)
    r = title_p.add_run("法定代表人身份证明书")
    set_run_font(r, font_name="黑体", size_pt=22, bold=True)
    doc.add_paragraph()

    p_body = doc.add_paragraph()
    format_paragraph(p_body, first_line_indent_chars=2, line_spacing_pt=30)
    r = p_body.add_run(
        "{{ legal_rep_name }}（性别：{{ legal_rep_gender }}，公民身份号码：{{ legal_rep_id }}）在我单位担任 {{ legal_rep_position }} 职务，"
        "系我单位（{{ company_name }}，统一社会信用代码：{{ company_uscc }}）的法定代表人。"
    )
    set_run_font(r, font_name="仿宋", size_pt=14)

    p_body2 = doc.add_paragraph()
    format_paragraph(p_body2, first_line_indent_chars=2, line_spacing_pt=30)
    r = p_body2.add_run(
        "特此证明。\n\n"
        "附注：该法定代表人有权代表本单位参加关于与 {{ opponent_name }} 之 {{ cause_of_action }} 一案的各项民事诉讼或仲裁活动。"
    )
    set_run_font(r, font_name="仿宋", size_pt=14)
    doc.add_paragraph()

    p_sign = doc.add_paragraph()
    format_paragraph(p_sign, align=WD_ALIGN_PARAGRAPH.RIGHT, first_line_indent_chars=0)
    r = p_sign.add_run("证明单位（公章）：{{ company_name }}          \n\n日期：{{ sign_date }}          ")
    set_run_font(r, font_name="仿宋", size_pt=14)

    doc.save(output_path)
    print(f"[*] 成功生成法定代表人身份证明书模板: {output_path}")


def create_service_address_template(output_path: str):
    """《送达地址确认书》模板（法院诉讼专用格式）"""
    doc = Document()
    apply_page_margins(doc)

    title_p = doc.add_paragraph()
    format_paragraph(title_p, align=WD_ALIGN_PARAGRAPH.CENTER, first_line_indent_chars=0, line_spacing_pt=32)
    r = title_p.add_run("送达地址确认书")
    set_run_font(r, font_name="黑体", size_pt=20, bold=True)

    intro_p = doc.add_paragraph()
    format_paragraph(intro_p, first_line_indent_chars=0, line_spacing_pt=22)
    r = intro_p.add_run("案由：{{ cause_of_action }}    受送达人姓名/单位：{{ recipient_name }}")
    set_run_font(r, font_name="仿宋", size_pt=12)

    table = doc.add_table(rows=6, cols=2)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False

    col_widths = [Inches(2.0), Inches(4.5)]
    fields = [
        ("受送达当事人主体", "{{ recipient_name }} (证件号/代码: {{ recipient_id }})"),
        ("委托诉讼代理人", "{{ lawyer_name }} ({{ law_firm }}, 电话: {{ lawyer_phone }})"),
        ("纸质邮寄送达地址", "{{ mail_address }} (邮政编码: {{ postal_code }})"),
        ("移动电话及短信送达号码", "{{ mobile_phone }}"),
        ("电子邮箱送达地址", "{{ email_address }}"),
        ("当事人电子送达确认意向", "【同意】受诉人民法院采用短信、电子邮件或统一微法院等方式送达传票、裁定书、判决书等各项法律文书。")
    ]

    for i, (label, val) in enumerate(fields):
        row_cells = table.rows[i].cells
        row_cells[0].width = col_widths[0]
        row_cells[1].width = col_widths[1]

        p0 = row_cells[0].paragraphs[0]
        format_paragraph(p0, align=WD_ALIGN_PARAGRAPH.CENTER, first_line_indent_chars=0, line_spacing_pt=20)
        r0 = p0.add_run(label)
        set_run_font(r0, font_name="黑体", size_pt=12, bold=True)
        set_cell_border(row_cells[0])

        p1 = row_cells[1].paragraphs[0]
        format_paragraph(p1, align=WD_ALIGN_PARAGRAPH.LEFT, first_line_indent_chars=0, line_spacing_pt=20)
        r1 = p1.add_run(val)
        set_run_font(r1, font_name="仿宋", size_pt=12)
        set_cell_border(row_cells[1])

    doc.add_paragraph()
    p_note = doc.add_paragraph()
    format_paragraph(p_note, first_line_indent_chars=2, line_spacing_pt=22)
    r = p_note.add_run(
        "承诺：本人/本单位已阅读并知悉《民事诉讼法》关于送达的各项规定。上述确认的送达地址在第一审、第二审以及执行程序中持续有效。"
        "送达地址若有变更，将及时向人民法院提交书面变更告知。"
    )
    set_run_font(r, font_name="仿宋", size_pt=11)

    p_sign = doc.add_paragraph()
    format_paragraph(p_sign, align=WD_ALIGN_PARAGRAPH.RIGHT, first_line_indent_chars=0)
    r = p_sign.add_run("确认人（签字/盖章）：{{ recipient_name }}          \n\n确认日期：{{ sign_date }}          ")
    set_run_font(r, font_name="仿宋", size_pt=12)

    doc.save(output_path)
    print(f"[*] 成功生成送达地址确认书模板: {output_path}")


# ==============================================================================
# 案由二：劳动人事争议全套
# ==============================================================================
def create_labor_compensation_calc_template(output_path: str):
    """《经济补偿金计算清单》模板（用于仲裁委员会与庭审证据附件）"""
    doc = Document()
    apply_page_margins(doc)

    title_p = doc.add_paragraph()
    format_paragraph(title_p, align=WD_ALIGN_PARAGRAPH.CENTER, first_line_indent_chars=0, line_spacing_pt=32)
    r = title_p.add_run("经济补偿金与赔偿金精算清单")
    set_run_font(r, font_name="黑体", size_pt=20, bold=True)

    p_meta = doc.add_paragraph()
    format_paragraph(p_meta, first_line_indent_chars=0, line_spacing_pt=24)
    r = p_meta.add_run(
        "申请人：{{ applicant_name }}    被申请人：{{ respondent_name }}\n"
        "入职日期：{{ hire_date }}    解除日期：{{ termination_date }}    折算工龄：{{ tenure_str }}"
    )
    set_run_font(r, font_name="仿宋", size_pt=12)

    table = doc.add_table(rows=5, cols=4)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False

    widths = [Inches(1.8), Inches(1.8), Inches(1.6), Inches(1.8)]
    headers = ["补偿项目", "核算公式与基数", "主张金额", "法律依据条文"]
    hdr_cells = table.rows[0].cells
    for i, h in enumerate(headers):
        hdr_cells[i].width = widths[i]
        p = hdr_cells[i].paragraphs[0]
        format_paragraph(p, align=WD_ALIGN_PARAGRAPH.CENTER, first_line_indent_chars=0, line_spacing_pt=20)
        r = p.add_run(h)
        set_run_font(r, font_name="黑体", size_pt=12, bold=True)
        set_cell_border(hdr_cells[i], top="double", top_sz="8", bottom="single", bottom_sz="6")

    rows_data = [
        ("法定经济补偿 (N)", "{{ monthly_salary }}元 × {{ compensation_months }}个月", "￥{{ amount_n }}", "《劳动合同法》第47条第一款"),
        ("未提前通知代通知金 (+1)", "上月实际工资标准", "￥{{ amount_plus_1_notice }}", "《劳动合同法》第40条"),
        ("违法解除赔偿金 (2N)", "法定经济补偿 N × 2倍", "￥{{ amount_2n }}", "《劳动合同法》第87条"),
        ("离职前12个月月均工资", "实发与应发平均工资核定", "￥{{ monthly_salary }}", "《劳动合同法实施条例》第27条")
    ]

    for i, row in enumerate(rows_data, 1):
        cells = table.rows[i].cells
        for j, text in enumerate(row):
            cells[j].width = widths[j]
            p = cells[j].paragraphs[0]
            align = WD_ALIGN_PARAGRAPH.CENTER if j != 1 else WD_ALIGN_PARAGRAPH.LEFT
            format_paragraph(p, align=align, first_line_indent_chars=0, line_spacing_pt=20)
            r = p.add_run(text)
            set_run_font(r, font_name="仿宋", size_pt=11)
            set_cell_border(cells[j])

    doc.add_paragraph()
    p_cap = doc.add_paragraph()
    format_paragraph(p_cap, first_line_indent_chars=2, line_spacing_pt=22)
    r = p_cap.add_run("封顶核定说明：{{ cap_reason }}")
    set_run_font(r, font_name="仿宋", size_pt=11)

    p_sign = doc.add_paragraph()
    format_paragraph(p_sign, align=WD_ALIGN_PARAGRAPH.RIGHT, first_line_indent_chars=0)
    r = p_sign.add_run("编制人（申请人/代理律师）：{{ applicant_name }}          \n\n日期：{{ filing_date }}          ")
    set_run_font(r, font_name="仿宋", size_pt=12)

    doc.save(output_path)
    print(f"[*] 成功生成经济补偿金计算清单模板: {output_path}")


# ==============================================================================
# 案由三：买卖合同欠款纠纷全套
# ==============================================================================
def create_civil_complaint_sales_template(output_path: str):
    """买卖合同欠款《民事起诉状》模板"""
    doc = Document()
    apply_page_margins(doc)

    title_p = doc.add_paragraph()
    format_paragraph(title_p, align=WD_ALIGN_PARAGRAPH.CENTER, first_line_indent_chars=0, line_spacing_pt=32)
    r = title_p.add_run("民 事 起 诉 状")
    set_run_font(r, font_name="黑体", size_pt=22, bold=True)
    doc.add_paragraph()

    # 原告与被告（支持法人/单位）
    p1 = doc.add_paragraph()
    format_paragraph(p1, first_line_indent_chars=0)
    r = p1.add_run("原告：")
    set_run_font(r, font_name="黑体", size_pt=14, bold=True)
    r = p1.add_run("{{ plaintiff_name }}，住所地：{{ plaintiff_address }}。统一社会信用代码：{{ plaintiff_id }}。法定代表人：{{ plaintiff_legal_rep }}，职务：{{ plaintiff_rep_position }}。联系电话：{{ plaintiff_phone }}。")
    set_run_font(r, font_name="仿宋", size_pt=14)

    p2 = doc.add_paragraph()
    format_paragraph(p2, first_line_indent_chars=0)
    r = p2.add_run("被告：")
    set_run_font(r, font_name="黑体", size_pt=14, bold=True)
    r = p2.add_run("{{ defendant_name }}，住所地：{{ defendant_address }}。统一社会信用代码/公民身份号码：{{ defendant_id }}。法定代表人：{{ defendant_legal_rep }}。联系电话：{{ defendant_phone }}。")
    set_run_font(r, font_name="仿宋", size_pt=14)
    doc.add_paragraph()

    p3 = doc.add_paragraph()
    format_paragraph(p3, first_line_indent_chars=0)
    r = p3.add_run("诉讼请求：")
    set_run_font(r, font_name="黑体", size_pt=14, bold=True)

    p_claims = doc.add_paragraph()
    format_paragraph(p_claims, first_line_indent_chars=2)
    r = p_claims.add_run(
        "1. 判令被告立即向原告支付拖欠的货物采购货款人民币 {{ contract_arrears }} 元（大写：{{ contract_arrears_capital }}）；\n"
        "2. 判令被告向原告支付自逾期之日起至实际清偿之日止的逾期付款违约金（按照全国银行间同业拆借中心公布的一年期贷款市场报价利率 LPR 加计 50% 计算，暂计至起诉日为人民币 {{ liquidated_damages }} 元）；\n"
        "3. 判令本案全部诉讼费用、保全责任保险费及保全申请费由被告承担。"
    )
    set_run_font(r, font_name="仿宋", size_pt=14)

    p4 = doc.add_paragraph()
    format_paragraph(p4, first_line_indent_chars=0)
    r = p4.add_run("事实与理由：")
    set_run_font(r, font_name="黑体", size_pt=14, bold=True)

    p_facts = doc.add_paragraph()
    format_paragraph(p_facts, first_line_indent_chars=2)
    r = p_facts.add_run("{{ facts_and_reasons }}")
    set_run_font(r, font_name="仿宋", size_pt=14)
    doc.add_paragraph()

    p_to = doc.add_paragraph()
    format_paragraph(p_to, first_line_indent_chars=0)
    r = p_to.add_run("此致\n")
    set_run_font(r, font_name="仿宋", size_pt=14)
    r2 = p_to.add_run("{{ court_name }}人民法院")
    set_run_font(r2, font_name="黑体", size_pt=14, bold=True)
    doc.add_paragraph()

    p_sign = doc.add_paragraph()
    format_paragraph(p_sign, align=WD_ALIGN_PARAGRAPH.RIGHT, first_line_indent_chars=0)
    r = p_sign.add_run("具状人（盖章）：{{ plaintiff_name }}          \n\n日期：{{ filing_date }}          ")
    set_run_font(r, font_name="仿宋", size_pt=14)

    doc.save(output_path)
    print(f"[*] 成功生成买卖合同起诉状模板: {output_path}")


def create_property_preservation_template(output_path: str):
    """《财产保全申请书》模板（诉前/诉中保全）"""
    doc = Document()
    apply_page_margins(doc)

    title_p = doc.add_paragraph()
    format_paragraph(title_p, align=WD_ALIGN_PARAGRAPH.CENTER, first_line_indent_chars=0, line_spacing_pt=32)
    r = title_p.add_run("财产保全申请书")
    set_run_font(r, font_name="黑体", size_pt=22, bold=True)
    doc.add_paragraph()

    p1 = doc.add_paragraph()
    format_paragraph(p1, first_line_indent_chars=0)
    r = p1.add_run("申请人：")
    set_run_font(r, font_name="黑体", size_pt=14, bold=True)
    r = p1.add_run("{{ applicant_name }}，身份证号码/统一社会信用代码：{{ applicant_id }}，联系电话：{{ applicant_phone }}。")
    set_run_font(r, font_name="仿宋", size_pt=14)

    p2 = doc.add_paragraph()
    format_paragraph(p2, first_line_indent_chars=0)
    r = p2.add_run("被申请人：")
    set_run_font(r, font_name="黑体", size_pt=14, bold=True)
    r = p2.add_run("{{ respondent_name }}，身份证号码/统一社会信用代码：{{ respondent_id }}，住所地：{{ respondent_address }}。")
    set_run_font(r, font_name="仿宋", size_pt=14)
    doc.add_paragraph()

    p_req_title = doc.add_paragraph()
    format_paragraph(p_req_title, first_line_indent_chars=0)
    r = p_req_title.add_run("请求事项：")
    set_run_font(r, font_name="黑体", size_pt=14, bold=True)

    p_req = doc.add_paragraph()
    format_paragraph(p_req, first_line_indent_chars=2)
    r = p_req.add_run(
        "依法查封、扣押、冻结被申请人名下价值人民币 {{ preservation_amount }} 元（大写：{{ preservation_amount_capital }}）的银行存款或其他等值财产。"
    )
    set_run_font(r, font_name="仿宋", size_pt=14)

    p_facts_title = doc.add_paragraph()
    format_paragraph(p_facts_title, first_line_indent_chars=0)
    r = p_facts_title.add_run("事实与理由：")
    set_run_font(r, font_name="黑体", size_pt=14, bold=True)

    p_facts = doc.add_paragraph()
    format_paragraph(p_facts, first_line_indent_chars=2)
    r = p_facts.add_run(
        "申请人诉被申请人关于 {{ cause_of_action }} 一案已向贵院提起诉讼。为防止被申请人转移、隐匿财产导致日后判决难以执行，"
        "特依据《中华人民共和国民事诉讼法》第一百零三条、第一百零五条之规定，申请财产保全。\n\n"
        "担保说明：申请人已通过中国人民财产保险股份有限公司提供等额诉讼财产保全责任保险保函作为担保（附《保全保函》及保险单）。"
    )
    set_run_font(r, font_name="仿宋", size_pt=14)

    p_clue_title = doc.add_paragraph()
    format_paragraph(p_clue_title, first_line_indent_chars=0)
    r = p_clue_title.add_run("被申请人财产线索：")
    set_run_font(r, font_name="黑体", size_pt=14, bold=True)

    p_clue = doc.add_paragraph()
    format_paragraph(p_clue, first_line_indent_chars=2)
    r = p_clue.add_run("{{ property_clues }}")
    set_run_font(r, font_name="仿宋", size_pt=14)
    doc.add_paragraph()

    p_to = doc.add_paragraph()
    format_paragraph(p_to, first_line_indent_chars=0)
    r = p_to.add_run("此致\n")
    set_run_font(r, font_name="仿宋", size_pt=14)
    r2 = p_to.add_run("{{ court_name }}人民法院")
    set_run_font(r2, font_name="黑体", size_pt=14, bold=True)
    doc.add_paragraph()

    p_sign = doc.add_paragraph()
    format_paragraph(p_sign, align=WD_ALIGN_PARAGRAPH.RIGHT, first_line_indent_chars=0)
    r = p_sign.add_run("申请人（签名/盖章）：{{ applicant_name }}          \n\n申请日期：{{ sign_date }}          ")
    set_run_font(r, font_name="仿宋", size_pt=14)

    doc.save(output_path)
    print(f"[*] 成功生成财产保全申请书模板: {output_path}")


def create_power_of_attorney_template(output_path: str):
    """《民事授权委托书》模板"""
    doc = Document()
    apply_page_margins(doc)
    title_p = doc.add_paragraph()
    format_paragraph(title_p, align=WD_ALIGN_PARAGRAPH.CENTER, first_line_indent_chars=0, line_spacing_pt=32)
    r = title_p.add_run("民 事 授 权 委 托 书")
    set_run_font(r, font_name="黑体", size_pt=22, bold=True)
    doc.add_paragraph()

    p_c = doc.add_paragraph()
    format_paragraph(p_c, first_line_indent_chars=0)
    r = p_c.add_run("委托人：")
    set_run_font(r, font_name="黑体", size_pt=14, bold=True)
    r = p_c.add_run("{{ client_name }}，公民身份号码/统一社会信用代码：{{ client_id }}。联系电话：{{ client_phone }}。")
    set_run_font(r, font_name="仿宋", size_pt=14)

    p_l = doc.add_paragraph()
    format_paragraph(p_l, first_line_indent_chars=0)
    r = p_l.add_run("受托人：")
    set_run_font(r, font_name="黑体", size_pt=14, bold=True)
    r = p_l.add_run("{{ lawyer_name }}，系 {{ law_firm }} 律师，执业证号：{{ lawyer_license }}，联系电话：{{ lawyer_phone }}。")
    set_run_font(r, font_name="仿宋", size_pt=14)
    doc.add_paragraph()

    p_matter = doc.add_paragraph()
    format_paragraph(p_matter, first_line_indent_chars=2)
    r = p_matter.add_run("现委托受托人在委托人与 {{ opponent_name }} 关于 {{ cause_of_action }} 一案中，担任委托人的诉讼代理人。")
    set_run_font(r, font_name="仿宋", size_pt=14)

    p_scope_title = doc.add_paragraph()
    format_paragraph(p_scope_title, first_line_indent_chars=0)
    r = p_scope_title.add_run("代理权限为：")
    set_run_font(r, font_name="黑体", size_pt=14, bold=True)

    p_scope = doc.add_paragraph()
    format_paragraph(p_scope, first_line_indent_chars=2)
    r = p_scope.add_run("{{ authorization_scope }}")
    set_run_font(r, font_name="仿宋", size_pt=14)

    p_term = doc.add_paragraph()
    format_paragraph(p_term, first_line_indent_chars=2)
    r = p_term.add_run("委托期限：自本委托书签署之日起至本案审理终结或执行完毕之日止。")
    set_run_font(r, font_name="仿宋", size_pt=14)
    doc.add_paragraph()

    p_sign = doc.add_paragraph()
    format_paragraph(p_sign, align=WD_ALIGN_PARAGRAPH.RIGHT, first_line_indent_chars=0)
    r = p_sign.add_run("委托人（签字/盖章）：{{ client_name }}          \n\n受托人（签字）：{{ lawyer_name }}          \n\n签署日期：{{ sign_date }}          ")
    set_run_font(r, font_name="仿宋", size_pt=14)

    doc.save(output_path)
    print(f"[*] 成功生成授权委托书模板: {output_path}")


def create_labor_arbitration_template(output_path: str):
    """《劳动人事争议仲裁申请书》模板"""
    doc = Document()
    apply_page_margins(doc)
    title_p = doc.add_paragraph()
    format_paragraph(title_p, align=WD_ALIGN_PARAGRAPH.CENTER, first_line_indent_chars=0, line_spacing_pt=32)
    r = title_p.add_run("劳动人事争议仲裁申请书")
    set_run_font(r, font_name="黑体", size_pt=22, bold=True)
    doc.add_paragraph()

    p_app = doc.add_paragraph()
    format_paragraph(p_app, first_line_indent_chars=0)
    r = p_app.add_run("申请人：")
    set_run_font(r, font_name="黑体", size_pt=14, bold=True)
    r = p_app.add_run("{{ applicant_name }}，{{ applicant_gender }}，{{ applicant_birth }}出生，住址：{{ applicant_address }}。身份证号码：{{ applicant_id }}。联系电话：{{ applicant_phone }}。")
    set_run_font(r, font_name="仿宋", size_pt=14)

    p_resp = doc.add_paragraph()
    format_paragraph(p_resp, first_line_indent_chars=0)
    r = p_resp.add_run("被申请人：")
    set_run_font(r, font_name="黑体", size_pt=14, bold=True)
    r = p_resp.add_run("{{ respondent_name }}，住所地：{{ respondent_address }}。统一社会信用代码：{{ respondent_id }}。法定代表人：{{ respondent_legal_rep }}。联系电话：{{ respondent_phone }}。")
    set_run_font(r, font_name="仿宋", size_pt=14)
    doc.add_paragraph()

    p_req = doc.add_paragraph()
    format_paragraph(p_req, first_line_indent_chars=0)
    r = p_req.add_run("仲裁请求：")
    set_run_font(r, font_name="黑体", size_pt=14, bold=True)

    p_claims = doc.add_paragraph()
    format_paragraph(p_claims, first_line_indent_chars=2)
    r = p_claims.add_run("{% for req in arbitration_claims %}{{ loop.index }}、{{ req }}\n{% endfor %}")
    set_run_font(r, font_name="仿宋", size_pt=14)

    p_facts_title = doc.add_paragraph()
    format_paragraph(p_facts_title, first_line_indent_chars=0)
    r = p_facts_title.add_run("事实与理由：")
    set_run_font(r, font_name="黑体", size_pt=14, bold=True)

    p_facts = doc.add_paragraph()
    format_paragraph(p_facts, first_line_indent_chars=2)
    r = p_facts.add_run("{{ facts_and_reasons }}")
    set_run_font(r, font_name="仿宋", size_pt=14)
    doc.add_paragraph()

    p_to = doc.add_paragraph()
    format_paragraph(p_to, first_line_indent_chars=0)
    r = p_to.add_run("此致\n")
    set_run_font(r, font_name="仿宋", size_pt=14)
    r2 = p_to.add_run("{{ arbitration_committee }}劳动人事争议仲裁委员会")
    set_run_font(r2, font_name="黑体", size_pt=14, bold=True)
    doc.add_paragraph()

    p_sign = doc.add_paragraph()
    format_paragraph(p_sign, align=WD_ALIGN_PARAGRAPH.RIGHT, first_line_indent_chars=0)
    r = p_sign.add_run("申请人（签名）：{{ applicant_name }}          \n\n申请日期：{{ filing_date }}          ")
    set_run_font(r, font_name="仿宋", size_pt=14)

    doc.save(output_path)
    print(f"[*] 成功生成劳动人事争议仲裁申请书模板: {output_path}")


def create_civil_complaint_template(output_path: str):
    """通用民事起诉状模板"""
    doc = Document()
    apply_page_margins(doc)
    title_p = doc.add_paragraph()
    format_paragraph(title_p, align=WD_ALIGN_PARAGRAPH.CENTER, first_line_indent_chars=0, line_spacing_pt=32)
    r = title_p.add_run("民 事 起 诉 状")
    set_run_font(r, font_name="黑体", size_pt=22, bold=True)
    doc.add_paragraph()

    p1 = doc.add_paragraph()
    format_paragraph(p1, first_line_indent_chars=0)
    r = p1.add_run("原告：")
    set_run_font(r, font_name="黑体", size_pt=14, bold=True)
    r = p1.add_run("{{ plaintiff_name }}，{{ plaintiff_gender }}，{{ plaintiff_birth }}出生，{{ plaintiff_ethnicity }}，住址：{{ plaintiff_address }}。身份证号码/代码：{{ plaintiff_id }}。联系电话：{{ plaintiff_phone }}。")
    set_run_font(r, font_name="仿宋", size_pt=14)

    p2 = doc.add_paragraph()
    format_paragraph(p2, first_line_indent_chars=0)
    r = p2.add_run("被告：")
    set_run_font(r, font_name="黑体", size_pt=14, bold=True)
    r = p2.add_run("{{ defendant_name }}，住址/经营地：{{ defendant_address }}。统一社会信用代码/身份证号：{{ defendant_id }}。联系电话：{{ defendant_phone }}。")
    set_run_font(r, font_name="仿宋", size_pt=14)
    doc.add_paragraph()

    p3 = doc.add_paragraph()
    format_paragraph(p3, first_line_indent_chars=0)
    r = p3.add_run("诉讼请求：")
    set_run_font(r, font_name="黑体", size_pt=14, bold=True)

    p_claims = doc.add_paragraph()
    format_paragraph(p_claims, first_line_indent_chars=2)
    r = p_claims.add_run("{% for claim in claims %}{{ loop.index }}、{{ claim }}\n{% endfor %}")
    set_run_font(r, font_name="仿宋", size_pt=14)

    p4 = doc.add_paragraph()
    format_paragraph(p4, first_line_indent_chars=0)
    r = p4.add_run("事实与理由：")
    set_run_font(r, font_name="黑体", size_pt=14, bold=True)

    p_facts = doc.add_paragraph()
    format_paragraph(p_facts, first_line_indent_chars=2)
    r = p_facts.add_run("{{ facts_and_reasons }}")
    set_run_font(r, font_name="仿宋", size_pt=14)
    doc.add_paragraph()

    p_to = doc.add_paragraph()
    format_paragraph(p_to, first_line_indent_chars=0)
    r = p_to.add_run("此致\n")
    set_run_font(r, font_name="仿宋", size_pt=14)
    r2 = p_to.add_run("{{ court_name }}人民法院")
    set_run_font(r2, font_name="黑体", size_pt=14, bold=True)
    doc.add_paragraph()

    p_sign = doc.add_paragraph()
    format_paragraph(p_sign, align=WD_ALIGN_PARAGRAPH.RIGHT, first_line_indent_chars=0)
    r = p_sign.add_run("具状人（签名/盖章）：{{ plaintiff_name }}          \n\n日期：{{ filing_date }}          ")
    set_run_font(r, font_name="仿宋", size_pt=14)

    doc.save(output_path)
    print(f"[*] 成功生成通用民事起诉状模板: {output_path}")


def create_evidence_catalog_template(output_path: str):
    """《证据目录与证明目的清单》模板"""
    doc = Document()
    apply_page_margins(doc)
    title_p = doc.add_paragraph()
    format_paragraph(title_p, align=WD_ALIGN_PARAGRAPH.CENTER, first_line_indent_chars=0, line_spacing_pt=30)
    r = title_p.add_run("证 据 目 录")
    set_run_font(r, font_name="黑体", size_pt=22, bold=True)

    meta_p = doc.add_paragraph()
    format_paragraph(meta_p, first_line_indent_chars=0)
    r = meta_p.add_run("案由：{{ cause_of_action }}    举证人：{{ plaintiff_name }}    提交日期：{{ filing_date }}")
    set_run_font(r, font_name="仿宋", size_pt=12)

    table = doc.add_table(rows=2, cols=6)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False

    col_widths = [Inches(0.6), Inches(1.8), Inches(1.0), Inches(2.3), Inches(1.0), Inches(0.8)]
    headers = ["序号", "证据名称", "证据种类", "证明目的", "证据来源", "页数"]

    hdr_cells = table.rows[0].cells
    for i, title in enumerate(headers):
        hdr_cells[i].width = col_widths[i]
        p = hdr_cells[i].paragraphs[0]
        format_paragraph(p, align=WD_ALIGN_PARAGRAPH.CENTER, first_line_indent_chars=0, line_spacing_pt=20)
        r = p.add_run(title)
        set_run_font(r, font_name="黑体", size_pt=11, bold=True)
        set_cell_border(hdr_cells[i], top="double", top_sz="8", bottom="single", bottom_sz="6")

    row_cells = table.rows[1].cells
    data_tags = [
        "{{ loop.index }}",
        "{{ item.name }}",
        "{{ item.category }}",
        "{{ item.purpose }}",
        "{{ item.source }}",
        "{{ item.pages }}"
    ]
    for i, tag in enumerate(data_tags):
        row_cells[i].width = col_widths[i]
        p = row_cells[i].paragraphs[0]
        align = WD_ALIGN_PARAGRAPH.CENTER if i in (0, 2, 4, 5) else WD_ALIGN_PARAGRAPH.LEFT
        format_paragraph(p, align=align, first_line_indent_chars=0, line_spacing_pt=20)
        if i == 0:
            r = p.add_run("{% for item in evidence_items %}{{ loop.index }}")
        elif i == len(data_tags) - 1:
            r = p.add_run("{{ item.pages }}{% endfor %}")
        else:
            r = p.add_run(tag)
        set_run_font(r, font_name="仿宋", size_pt=10)
        set_cell_border(row_cells[i], top="single", top_sz="4", bottom="single", bottom_sz="4")

    doc.add_paragraph()
    p_sign = doc.add_paragraph()
    format_paragraph(p_sign, align=WD_ALIGN_PARAGRAPH.RIGHT, first_line_indent_chars=0)
    r = p_sign.add_run("举证人（签名/盖章）：{{ plaintiff_name }}          \n\n日期：{{ filing_date }}          ")
    set_run_font(r, font_name="仿宋", size_pt=12)

    doc.save(output_path)
    print(f"[*] 成功生成证据清单模板: {output_path}")

if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.makedirs(base_dir, exist_ok=True)

    # 1. 民间借贷纠纷全套
    create_civil_complaint_loan_template(os.path.join(base_dir, "civil_complaint_loan_template.docx"))
    create_power_of_attorney_template(os.path.join(base_dir, "power_of_attorney_template.docx"))
    create_legal_representative_template(os.path.join(base_dir, "legal_representative_template.docx"))
    create_service_address_template(os.path.join(base_dir, "service_address_template.docx"))

    # 2. 劳动人事争议全套
    create_labor_arbitration_template(os.path.join(base_dir, "labor_arbitration_template.docx"))
    create_labor_compensation_calc_template(os.path.join(base_dir, "labor_compensation_calc_template.docx"))

    # 3. 买卖合同欠款纠纷全套
    create_civil_complaint_sales_template(os.path.join(base_dir, "civil_complaint_sales_template.docx"))
    create_property_preservation_template(os.path.join(base_dir, "property_preservation_template.docx"))

    # 基础通用模板
    create_civil_complaint_template(os.path.join(base_dir, "civil_complaint_template.docx"))
    create_evidence_catalog_template(os.path.join(base_dir, "evidence_catalog_template.docx"))

    print("\n[SUCCESS] 三大高频案由全套标准法律公文模板已全部生成完毕！")
