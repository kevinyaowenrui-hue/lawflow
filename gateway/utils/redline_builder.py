"""
LawFlow 智律工作台 - 合同审查红线手册 (Playbook) 与 Word 原生修订模式 (Track Changes) 导出引擎
核心功能：
1. 内置多套工业级法律实务红线手册 (通用商业 / 软件技术服务 / 大宗采购 / 劳动人事)；
2. 文本字符级 Diff 算法对比（原文 vs 审查建议加固条文）；
3. 借助 python-docx 与 Word OpenXML 生成带原生 <w:ins> 和 <w:del> 的修订模式 .docx 文档；
4. 输出带 3 栏修订卡片（原文 / 修订标记 / 谈判说辞）及偏离度审计表的完整审阅底稿。
"""

import os
import re
import time
import difflib
import copy
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import qn, nsdecls

PLAYBOOK_PRESETS = {
    "general": {
        "name": "通用商业合同红线库",
        "description": "适用于常规买卖、服务、租赁等商事交易合同",
        "rules": [
            "违约金总额必须设定上限（原则上不超过合同总金额的20%或以守约方实际直接损失为限）",
            "严禁约定无限连带责任，明确排除间接损失、利润损失及商誉损失",
            "争议管辖条款约定原告所在地人民法院或公允商事仲裁机构，防范异地应诉高额差旅成本",
            "单方解除权必须明确设置书面催告通知与不少于7个工作日的补正宽限期",
            "送达条款必须明确当事人有效书面通信地址及电子送达确认规范"
        ]
    },
    "tech_service": {
        "name": "软件开发与技术服务红线库",
        "description": "适用于IT外包、软件定制研发、系统集成与技术咨询服务",
        "rules": [
            "知识产权归属必须明确区分：开发方原有基础技术与工具包（Background IP）严格归开发方保留",
            "发包方验收期设定逾期推定合格机制（自交付之日起10个工作日内无书面异议的视为验收合格）",
            "需求变更条款必须约定双方书面确认工期顺延及追加研发服务费用",
            "开源软件与第三方组件合规免责声明，发包方不得要求交付包含受GPL感染的原生商业代码",
            "维护期与质保期明确为验收合格之日起至多12个月，超出范围按人天另行收费"
        ]
    },
    "procurement": {
        "name": "大宗买卖与设备采购红线库",
        "description": "适用于物资设备采购、货物购销与供应链合同",
        "rules": [
            "交货与检验条款设定明确异议期（到货后5日内核对外观，30日内提出内在质量异议）",
            "逾期付款违约金以一年期LPR标准计算或每日最高不超过万分之三",
            "不可抗力事件定义包含政策限产、交通管制及核心原材料全国性断供",
            "分期付款各节点必须与到货、初验、复验严格绑定，保留5%-10%质保尾款"
        ]
    },
    "labor": {
        "name": "企业劳动用工与保密竞业红线库",
        "description": "适用于劳动合同、保密与竞业限制协议、高级管理人员聘用书",
        "rules": [
            "竞业限制条款必须明确按月支付不低于劳动合同解除前12个月月平均工资30%的经济补偿金",
            "知识产权职务发明界定必须严格限定为执行本单位工作任务或主要利用本单位物质技术条件",
            "解除劳动合同法定事由与工会通知程序严格恪守《劳动合同法》第39/40/43条"
        ]
    },
    "cross_border_procurement": {
        "name": "涉外与跨国商事采购红线库 (International Master Agreement Playbook)",
        "description": "适用于跨国采购主协议 (MPA/MSA)、涉外供应链、英文商业合同",
        "rules": [
            "Cross-Default（交叉违约）条款必须整条删除或严格限定为本合同项下已经法院终审裁判确定的实质性债务违约",
            "Liquidated Damages（违约金）总额必须设定封顶上限（原则上不超过相关采购订单金额的10%），且明确排除间接损失（Consequential/Indirect Damages）",
            "Indemnification（赔偿与责任限制）必须设定责任上限（Cap at Aggregate Contract Value）并排除无过错连带责任",
            "Governing Law & Dispute Resolution（管辖与法律适用）约定公允中立国际仲裁机构（如HKIAC/SIAC/CIETAC）并适用公允法域",
            "Termination for Convenience（单方任意解除权）必须明确提前至少30天书面通知并补偿已发生的不可撤销沉没成本"
        ]
    }
}


def compute_text_diff_chunks(orig_text: str, rev_text: str) -> List[Dict[str, str]]:
    """计算两段文本的字符级差异，返回 HTML 高亮或结构化列表"""
    sm = difflib.SequenceMatcher(None, orig_text, rev_text)
    chunks = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            chunks.append({"type": "equal", "text": orig_text[i1:i2]})
        elif tag == 'delete':
            chunks.append({"type": "delete", "text": orig_text[i1:i2]})
        elif tag == 'insert':
            chunks.append({"type": "insert", "text": rev_text[j1:j2]})
        elif tag == 'replace':
            chunks.append({"type": "delete", "text": orig_text[i1:i2]})
            chunks.append({"type": "insert", "text": rev_text[j1:j2]})
    return chunks


class RedlineResult(str):
    """兼容旧版 str 返回值，同时携带结构化修订统计指标"""
    def __new__(cls, output_path: str, stats: Optional[Dict[str, Any]] = None):
        instance = super(RedlineResult, cls).__new__(cls, output_path)
        instance.output_path = output_path
        instance.stats = stats or {}
        return instance

    def get(self, key, default=None):
        return self.stats.get(key, default)


def normalize_text_for_matching(text: str) -> str:
    """归一化连续空白、中英引号、破折号及不可见控制字符"""
    if not text:
        return ""
    # 替换不换行空格、全角空格等特殊空白
    t = re.sub(r'[\r\n\t\u00a0\u2000-\u200b\u3000]+', ' ', text)
    # 统一弯双引号与单引号
    t = re.sub(r'[“”„”«»]', '"', t)
    t = re.sub(r"[‘’`´]", "'", t)
    # 统一各种破折号与连字符
    t = re.sub(r'[—–―−_]', '-', t)
    # 压缩多空格
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def is_predominantly_english(text: str) -> bool:
    """判断待审文本是否主要为英文合同"""
    if not text:
        return False
    alpha_count = len(re.findall(r'[a-zA-Z]', text))
    cjk_count = len(re.findall(r'[\u4e00-\u9fff]', text))
    return alpha_count > 30 and alpha_count > cjk_count * 1.5


def find_best_matching_span(full_text: str, target_clause: str) -> Optional[Tuple[int, int]]:
    """
    在 full_text 中高精度寻找 target_clause 的字符区间 [start, end]。
    层级容错策略：
    1. 精确子串包含
    2. 大小写不敏感包含
    3. 空白与标点符号正则柔性匹配 (忽略中英文引号、连字符差异及不换行空格)
    4. 剥离条款前缀编号或末尾标点匹配
    5. 句子级滑动窗口局部比对
    6. 全段 Levenshtein 模糊比对
    """
    if not full_text or not target_clause:
        return None
    
    clean_target = target_clause.strip()
    if not clean_target:
        return None

    # 1. 精确子串
    idx = full_text.find(clean_target)
    if idx != -1:
        return (idx, idx + len(clean_target))

    # 2. 忽略大小写
    idx_lower = full_text.lower().find(clean_target.lower())
    if idx_lower != -1:
        return (idx_lower, idx_lower + len(clean_target))

    # 3. 构造柔性正则 (将标点和空白转为宽容正则)
    try:
        collapsed_target = re.sub(r'\s+', ' ', clean_target)
        escaped = re.escape(collapsed_target)
        pattern_str = re.sub(r'\\ ', r'\s*', escaped)
        pattern_str = re.sub(r'\\-', r'[\-—–―_]', pattern_str)
        pattern_str = re.sub(r'\\"', r'["“”„«»]', pattern_str)
        pattern_str = re.sub(r"\\'", r"['‘’`]", pattern_str)
        pattern_str = re.sub(r'\\\(|\\（', r'[\(（]', pattern_str)
        pattern_str = re.sub(r'\\\)|\\）', r'[\)）]', pattern_str)
        pattern_str = re.sub(r'\\:|\\：', r'[:：]', pattern_str)
        pattern_str = re.sub(r'\\,|\\，|\\、', r'[,，、]', pattern_str)
        pattern_str = re.sub(r'\\\.|\\。', r'[\.。]', pattern_str)
        m = re.search(pattern_str, full_text, flags=re.IGNORECASE)
        if m:
            return (m.start(), m.end())
    except Exception:
        pass

    # 4. 剥离条款可能带有的前缀编号（如第X条、1.、（1）等）或末尾句号后匹配
    sub_clean = re.sub(r'^(?:第[0-9一二三四五六七八九十百]+条|\d+[\.\、\s]|\([0-9一二三四五六七八九十]+\)|（[0-9一二三四五六七八九十]+）)\s*', '', clean_target).strip()
    if sub_clean and len(sub_clean) >= 4:
        idx_sub = full_text.find(sub_clean)
        if idx_sub != -1:
            return (idx_sub, idx_sub + len(sub_clean))

    # 5. 句子级滑动窗口 (处理多句大段中嵌套子条款)
    sentence_spans = []
    for m in re.finditer(r'[^。；;\.\n]+[。；;\.\n]?', full_text):
        if m.group().strip():
            sentence_spans.append((m.start(), m.end(), m.group()))
    
    norm_target = normalize_text_for_matching(clean_target)
    if len(sentence_spans) >= 1:
        best_ratio = 0.0
        best_span = None
        for w_len in range(1, min(len(sentence_spans) + 1, 6)):
            for i in range(len(sentence_spans) - w_len + 1):
                s_start = sentence_spans[i][0]
                s_end = sentence_spans[i + w_len - 1][1]
                sub_str = full_text[s_start:s_end]
                norm_sub = normalize_text_for_matching(sub_str)
                r = difflib.SequenceMatcher(None, norm_sub.lower(), norm_target.lower()).ratio()
                if r > best_ratio and r >= 0.70:
                    best_ratio = r
                    best_span = (s_start, s_end)
        if best_span:
            return best_span

    # 6. 全段极高相似度比对
    norm_full = normalize_text_for_matching(full_text)
    len_diff = abs(len(norm_full) - len(norm_target))
    ratio = difflib.SequenceMatcher(None, norm_full.lower(), norm_target.lower()).ratio()
    if ratio >= 0.85 or (ratio >= 0.70 and len_diff < 30):
        return (0, len(full_text))

    return None



def add_diff_to_docx_paragraph(paragraph, orig_text: str, rev_text: str, author: str = "LawFlow 智能审查建议"):
    """
    使用 SequenceMatcher 将 orig_text 与 rev_text 比对，
    并将差异转换为 Word 原生修订模式标签 (<w:del> 与 <w:ins>)。
    自适应文档原语种字体（英文使用 Times New Roman / Calibri，中文使用 仿宋）。
    """
    sm = difflib.SequenceMatcher(None, orig_text, rev_text)
    run_id = int(time.time() % 1000000)

    # 判断是否主要为英文
    alpha_count = len(re.findall(r'[a-zA-Z]', orig_text + rev_text))
    cjk_count = len(re.findall(r'[\u4e00-\u9fff]', orig_text + rev_text))
    is_en = alpha_count > cjk_count * 1.5 and alpha_count > 15
    default_font_name = "Times New Roman" if is_en else "仿宋"

    def make_del(text):
        dell = OxmlElement('w:del')
        dell.set(qn('w:id'), str(run_id))
        dell.set(qn('w:author'), author)
        dell.set(qn('w:date'), datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"))
        r_del = OxmlElement('w:r')
        rPr = OxmlElement('w:rPr')
        strike = OxmlElement('w:strike')
        color = OxmlElement('w:color')
        color.set(qn('w:val'), 'E11D48')
        rPr.append(strike)
        rPr.append(color)
        r_del.append(rPr)
        t_del = OxmlElement('w:delText')
        t_del.text = text
        r_del.append(t_del)
        dell.append(r_del)
        return dell

    def make_ins(text):
        ins = OxmlElement('w:ins')
        ins.set(qn('w:id'), str(run_id + 1))
        ins.set(qn('w:author'), author)
        ins.set(qn('w:date'), datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"))
        r_ins = OxmlElement('w:r')
        rPr = OxmlElement('w:rPr')
        u = OxmlElement('w:u')
        u.set(qn('w:val'), 'single')
        color = OxmlElement('w:color')
        color.set(qn('w:val'), '0284C7')
        rPr.append(u)
        rPr.append(color)
        r_ins.append(rPr)
        t_ins = OxmlElement('w:t')
        t_ins.text = text
        r_ins.append(t_ins)
        ins.append(r_ins)
        return ins

    sm = difflib.SequenceMatcher(None, orig_text, rev_text)
    # 当整条被大面积替换或删除插入（重合度 < 0.55）时，直接做整段删除+插入，杜绝字符散乱交错
    if sm.ratio() < 0.55:
        if orig_text:
            paragraph._p.append(make_del(orig_text))
        if rev_text:
            paragraph._p.append(make_ins(rev_text))
        return

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            r = paragraph.add_run(orig_text[i1:i2])
            r.font.size = Pt(10.5)
            r.font.name = default_font_name
        elif tag == 'delete':
            paragraph._p.append(make_del(orig_text[i1:i2]))
            run_id += 1
        elif tag == 'insert':
            paragraph._p.append(make_ins(rev_text[j1:j2]))
            run_id += 1
        elif tag == 'replace':
            paragraph._p.append(make_del(orig_text[i1:i2]))
            paragraph._p.append(make_ins(rev_text[j1:j2]))
            run_id += 2


def enable_track_revisions_in_doc(doc: docx.Document):
    """设置 Word 打开时自动激活 Track Changes 修订模式"""
    try:
        settings = doc.settings.element
        track = OxmlElement('w:trackRevisions')
        track.set(qn('w:val'), 'true')
        settings.append(track)
    except Exception:
        pass


def set_cell_background(cell, hex_color: str):
    """设置 Word 单元格底色"""
    shading_elm = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{hex_color}"/>')
    cell._tc.get_or_add_tcPr().append(shading_elm)


def build_redline_contract_docx(
    contract_title: str,
    original_contract_text: str,
    clause_reviews: List[Dict[str, Any]],
    perspective: str,
    playbook_name: str,
    playbook_rules: List[str],
    overall_risk_level: str = "中",
    review_summary: str = "",
    compliance_score: int = 85,
    output_path: str = ""
) -> str:
    """
    生成完整的《商业合同红线审查与原生修订底稿.docx》
    包含：
    1. 封面与审查概览
    2. 审查红线手册（Playbook）偏离度审计表
    3. 三栏修订卡片（原文 / Word 原生修订对比 / 谈判说辞与法律依据）
    4. 合同全文修订合并稿（带原生 <w:ins> / <w:del> 追踪）
    """
    doc = docx.Document()
    enable_track_revisions_in_doc(doc)

    # 样式配置
    normal_style = doc.styles['Normal']
    normal_style.font.name = '仿宋'
    normal_style.font.size = Pt(11)

    # 1. 大标题
    title_p = doc.add_paragraph()
    title_p.paragraph_format.space_before = Pt(12)
    title_p.paragraph_format.space_after = Pt(8)
    title_run = title_p.add_run(f"《{contract_title}》\n商业合同审查红线报告与原生修订底稿")
    title_run.font.size = Pt(18)
    title_run.font.bold = True
    title_run.font.color.rgb = RGBColor(15, 23, 42)
    title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    sub_p = doc.add_paragraph()
    sub_run = sub_p.add_run(f"审查立场：{perspective}  ·  审查引擎：LawFlow 智律工作台  ·  日期：{datetime.now().strftime('%Y年%m月%d日')}")
    sub_run.font.size = Pt(10)
    sub_run.font.color.rgb = RGBColor(100, 116, 139)
    sub_p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    doc.add_paragraph()  # 间距

    # 2. 审查概况表格
    meta_table = doc.add_table(rows=4, cols=2)
    meta_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    meta_data = [
        ("审查立场与角色", f"{perspective}"),
        ("红线规则手册 (Playbook)", f"{playbook_name} (共 {len(playbook_rules)} 项红线标准)"),
        ("综合风险评级与合规分", f"综合风险评级：{overall_risk_level} 风险  |  红线遵从度：{compliance_score} 分"),
        ("总体审查策略意见", review_summary or f"根据【{perspective}】要求，已重点识别合同中的单方解约陷阱、过高惩罚性违约金及异地管辖风险。")
    ]
    for row_idx, (k, v) in enumerate(meta_data):
        row = meta_table.rows[row_idx]
        cell_k, cell_v = row.cells[0], row.cells[1]
        cell_k.width = Inches(2.2)
        cell_v.width = Inches(4.5)
        set_cell_background(cell_k, "F1F5F9")
        set_cell_background(cell_v, "FAFAFA")
        
        rk = cell_k.paragraphs[0].add_run(k)
        rk.font.bold = True
        rk.font.size = Pt(10)
        rk.font.color.rgb = RGBColor(30, 41, 59)
        
        rv = cell_v.paragraphs[0].add_run(v)
        rv.font.size = Pt(10)
        rv.font.color.rgb = RGBColor(51, 65, 85)

    doc.add_paragraph()

    # 3. 第一部分：审查红线手册 (Playbook) 偏离度清单
    h1 = doc.add_paragraph()
    h1_run = h1.add_run("一、审查红线手册（Playbook）偏离度清单")
    h1_run.font.size = Pt(14)
    h1_run.font.bold = True
    h1_run.font.color.rgb = RGBColor(15, 23, 42)

    pb_table = doc.add_table(rows=1, cols=4)
    pb_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    headers = ["条款名称", "对应审查红线规则", "偏离度判定", "偏离原因与改进方向"]
    hdr_cells = pb_table.rows[0].cells
    col_widths = [Inches(1.5), Inches(2.3), Inches(1.2), Inches(2.0)]
    for i, h in enumerate(headers):
        hdr_cells[i].width = col_widths[i]
        set_cell_background(hdr_cells[i], "0F172A")
        r = hdr_cells[i].paragraphs[0].add_run(h)
        r.font.bold = True
        r.font.color.rgb = RGBColor(255, 255, 255)
        r.font.size = Pt(9.5)

    for item in clause_reviews:
        row = pb_table.add_row()
        cells = row.cells
        for i, w in enumerate(col_widths):
            cells[i].width = w

        c_title = item.get("clause_title", "核心条款")
        c_rule = item.get("matched_playbook_rule") or "通用商业风险平衡规则"
        c_dev = item.get("playbook_deviation", "OUT_OF_SCOPE_DEVIATION")
        c_reason = item.get("deviation_reason") or item.get("risk_analysis", "")

        dev_label = "偏离标准红线"
        dev_bg = "FEF3C7"
        if c_dev == "CRITICAL_BREACH":
            dev_label = "⛔ 严重踩雷"
            dev_bg = "FFE4E6"
        elif c_dev == "COMPLIANT":
            dev_label = "✓ 遵从红线"
            dev_bg = "DCFCE7"

        cells[0].paragraphs[0].add_run(c_title).font.size = Pt(9.5)
        cells[1].paragraphs[0].add_run(c_rule).font.size = Pt(9.0)
        
        dev_p = cells[2].paragraphs[0]
        dev_run = dev_p.add_run(dev_label)
        dev_run.font.bold = True
        dev_run.font.size = Pt(9.0)
        set_cell_background(cells[2], dev_bg)

        cells[3].paragraphs[0].add_run(c_reason[:80] + ("..." if len(c_reason) > 80 else "")).font.size = Pt(9.0)

    doc.add_paragraph()

    # 4. 第二部分：逐条三栏修订卡片与谈判交涉话术
    h2 = doc.add_paragraph()
    h2_run = h2.add_run("二、三栏逐条修订卡片与谈判交涉话术 (Track Changes)")
    h2_run.font.size = Pt(14)
    h2_run.font.bold = True
    h2_run.font.color.rgb = RGBColor(15, 23, 42)

    for idx, item in enumerate(clause_reviews, 1):
        clause_title = item.get("clause_title", f"风险条款 {idx}")
        orig_clause = item.get("original_clause", "")
        sugg_clause = item.get("suggested_clause", "")
        risk_analysis = item.get("risk_analysis", "")
        negotiation_tip = item.get("negotiation_tip", "")
        deviation = item.get("playbook_deviation", "OUT_OF_SCOPE_DEVIATION")

        # 条款小标题
        cp = doc.add_paragraph()
        cp.paragraph_format.space_before = Pt(8)
        cp.paragraph_format.space_after = Pt(3)
        c_run = cp.add_run(f"条款 {idx}：{clause_title}")
        c_run.font.bold = True
        c_run.font.size = Pt(12)
        c_run.font.color.rgb = RGBColor(15, 23, 42)

        # 3 栏对比框 (表格)
        card_table = doc.add_table(rows=4, cols=2)
        card_table.alignment = WD_TABLE_ALIGNMENT.CENTER
        
        # 1) 原文
        r0 = card_table.rows[0]
        r0.cells[0].width = Inches(1.8)
        r0.cells[1].width = Inches(5.2)
        set_cell_background(r0.cells[0], "F8FAFC")
        r0.cells[0].paragraphs[0].add_run("【合同原文】").font.bold = True
        r0.cells[1].paragraphs[0].add_run(orig_clause).font.size = Pt(10)

        # 2) 原生 Word 修订对比建议
        r1 = card_table.rows[1]
        r1.cells[0].width = Inches(1.8)
        r1.cells[1].width = Inches(5.2)
        set_cell_background(r1.cells[0], "F0FDF4")
        set_cell_background(r1.cells[1], "F8FAFC")
        r1_title = r1.cells[0].paragraphs[0].add_run("【AI加固修订稿】\n(带Word原生标记)")
        r1_title.font.bold = True
        r1_title.font.color.rgb = RGBColor(16, 185, 129)
        # 注入 <w:del> 与 <w:ins>
        add_diff_to_docx_paragraph(r1.cells[1].paragraphs[0], orig_clause, sugg_clause)

        # 3) 风险漏洞分析
        r2 = card_table.rows[2]
        r2.cells[0].width = Inches(1.8)
        r2.cells[1].width = Inches(5.2)
        set_cell_background(r2.cells[0], "FEF2F2")
        r2.cells[0].paragraphs[0].add_run("【法律漏洞分析】").font.bold = True
        r2.cells[1].paragraphs[0].add_run(risk_analysis).font.size = Pt(10)

        # 4) 谈判桌话术
        r3 = card_table.rows[3]
        r3.cells[0].width = Inches(1.8)
        r3.cells[1].width = Inches(5.2)
        set_cell_background(r3.cells[0], "FFFBEB")
        r3.cells[0].paragraphs[0].add_run("【谈判桌交涉话术】").font.bold = True
        r3.cells[1].paragraphs[0].add_run(negotiation_tip).font.size = Pt(10)

        doc.add_paragraph()  # 间距

    # 5. 第三部分：带 Track Changes 的合同正文合并修订稿
    h3 = doc.add_paragraph()
    h3_run = h3.add_run("三、合同正文合并修订稿 (Word 原生 Track Changes 模式)")
    h3_run.font.size = Pt(14)
    h3_run.font.bold = True
    h3_run.font.color.rgb = RGBColor(15, 23, 42)

    tip_p = doc.add_paragraph()
    tip_run = tip_p.add_run("注：以下内容已在 OpenXML 层注入 <w:ins> 与 <w:del> 标签。使用 Microsoft Word 或 WPS 打开本文件时，可直接在审阅选项卡中点击【接受所有修订】或【拒绝修订】。")
    tip_run.font.size = Pt(9.5)
    tip_run.font.color.rgb = RGBColor(100, 116, 139)

    # 替换全文中的条款为带有原生修订的段落
    contract_paragraphs = [p for p in original_contract_text.splitlines() if p.strip()]
    if not contract_paragraphs:
        contract_paragraphs = [original_contract_text]

    for para_text in contract_paragraphs:
        matched_review = None
        matched_span = None
        for item in clause_reviews:
            orig = item.get("original_clause", "").strip()
            if not orig:
                continue
            span = find_best_matching_span(para_text, orig)
            if span:
                matched_review = item
                matched_span = span
                break

        p_out = doc.add_paragraph()
        p_out.paragraph_format.line_spacing = 1.25
        p_out.paragraph_format.space_after = Pt(4)

        if matched_review and matched_span:
            s_i, e_i = matched_span
            sugg = matched_review.get("suggested_clause", "")
            is_en = is_predominantly_english(para_text)
            font_name = "Times New Roman" if is_en else "仿宋"
            if s_i > 0:
                r_pre = p_out.add_run(para_text[:s_i])
                r_pre.font.size = Pt(10.5)
                r_pre.font.name = font_name
            add_diff_to_docx_paragraph(p_out, para_text[s_i:e_i], sugg)
            if e_i < len(para_text):
                r_post = p_out.add_run(para_text[e_i:])
                r_post.font.size = Pt(10.5)
                r_post.font.name = font_name
        else:
            r = p_out.add_run(para_text)
            r.font.size = Pt(10.5)

    doc.save(output_path)
    return output_path


def refine_diff_opcodes(opcodes, a: str, b: str):
    """
    后处理 SequenceMatcher opcodes：
    避免出现 "~~三~~十五" 这种将 "三十" 与 "十五" 中间字 "十" 当作不变而导致的残缺交错，
    当短字符 (<= 2 字) 夹在修改操作之间时，合并为整词替换。
    """
    merged = []
    i = 0
    while i < len(opcodes):
        tag, i1, i2, j1, j2 = opcodes[i]
        if tag == 'equal':
            eq_len = i2 - i1
            if eq_len <= 2 and i > 0 and i + 1 < len(opcodes):
                prev_tag = merged[-1][0]
                next_tag = opcodes[i + 1][0]
                if prev_tag in ('delete', 'replace', 'insert') and next_tag in ('delete', 'replace', 'insert'):
                    p_tag, p_i1, p_i2, p_j1, p_j2 = merged.pop()
                    n_tag, n_i1, n_i2, n_j1, n_j2 = opcodes[i + 1]
                    merged.append(('replace', p_i1, n_i2, p_j1, n_j2))
                    i += 2
                    continue
        merged.append((tag, i1, i2, j1, j2))
        i += 1
    return merged

def _make_del_element(text: str, author: str, run_id: int, rPr_template=None) -> OxmlElement:
    dell = OxmlElement('w:del')
    dell.set(qn('w:id'), str(run_id))
    dell.set(qn('w:author'), author)
    dell.set(qn('w:date'), datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"))
    r_del = OxmlElement('w:r')
    if rPr_template is not None:
        rPr = copy.deepcopy(rPr_template)
    else:
        rPr = OxmlElement('w:rPr')
    strike = OxmlElement('w:strike')
    color = OxmlElement('w:color')
    color.set(qn('w:val'), 'E11D48')
    rPr.append(strike)
    rPr.append(color)
    r_del.append(rPr)
    t_del = OxmlElement('w:delText')
    t_del.text = text
    if text.startswith(" ") or text.endswith(" "):
        t_del.set(qn('xml:space'), 'preserve')
    r_del.append(t_del)
    dell.append(r_del)
    return dell


def _make_ins_element(text: str, author: str, run_id: int, rPr_template=None) -> OxmlElement:
    ins = OxmlElement('w:ins')
    ins.set(qn('w:id'), str(run_id))
    ins.set(qn('w:author'), author)
    ins.set(qn('w:date'), datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"))
    r_ins = OxmlElement('w:r')
    if rPr_template is not None:
        rPr = copy.deepcopy(rPr_template)
    else:
        rPr = OxmlElement('w:rPr')
    u = OxmlElement('w:u')
    u.set(qn('w:val'), 'single')
    color = OxmlElement('w:color')
    color.set(qn('w:val'), '0284C7')
    rPr.append(u)
    rPr.append(color)
    r_ins.append(rPr)
    t_ins = OxmlElement('w:t')
    t_ins.text = text
    if text.startswith(" ") or text.endswith(" "):
        t_ins.set(qn('xml:space'), 'preserve')
    r_ins.append(t_ins)
    ins.append(r_ins)
    return ins


def _make_run_element(text: str, rPr_template=None) -> OxmlElement:
    r = OxmlElement('w:r')
    if rPr_template is not None:
        r.append(copy.deepcopy(rPr_template))
    t = OxmlElement('w:t')
    t.text = text
    if text.startswith(" ") or text.endswith(" "):
        t.set(qn('xml:space'), 'preserve')
    r.append(t)
    return r


def apply_in_place_docx_redline(
    source_docx_path: str,
    clause_reviews: List[Dict[str, Any]],
    output_path: str
) -> RedlineResult:
    """
    非诉律师实务级：直接在客户发来的原始 .docx 合同中原位注入 <w:ins> 和 <w:del> 修订模式，
    100% 完整保留客户合同原件的排版、页眉页脚、封面、样式与表格结构。
    按段落合并 run 后的文本进行匹配，匹配成功后在对应 run 位置插入 <w:del>/<w:ins>；
    匹配不到的条款放入 unmatched_clauses 返回，不静默忽略。
    """
    doc = docx.Document(source_docx_path)
    enable_track_revisions_in_doc(doc)

    injected_indices = set()
    unmatched_clauses = []
    total_revisions_count = 0
    run_id_counter = int(time.time() % 1000000)

    def process_p(p):
        nonlocal total_revisions_count, run_id_counter
        if not p.runs and p.text:
            p.add_run(p.text)

        raw_text = "".join(r.text for r in p.runs)
        if not raw_text.strip():
            return

        run_ranges = []
        curr = 0
        for r in p.runs:
            rlen = len(r.text)
            rPr = r._r.rPr if hasattr(r._r, "rPr") else None
            run_ranges.append((curr, curr + rlen, rPr))
            curr += rlen

        def get_rPr_at_pos(pos: int):
            for r_start, r_end, rPr in run_ranges:
                if r_start <= pos < r_end:
                    return rPr
            if run_ranges:
                return run_ranges[-1][2]
            return None

        for idx, item in enumerate(clause_reviews):
            if idx in injected_indices:
                continue
            orig = item.get("original_clause", "").strip()
            sugg = item.get("suggested_clause", "")
            if not orig or not sugg:
                continue

            span = find_best_matching_span(raw_text, orig)
            if not span:
                continue

            start_i, end_i = span
            matched_orig = raw_text[start_i:end_i]

            sm = difflib.SequenceMatcher(None, matched_orig, sugg)
            author = "LawFlow 智能审查建议"
            new_elements = []
            local_revisions = 0

            # 1. 前置未受影响文字
            if start_i > 0:
                for r_start, r_end, rPr in run_ranges:
                    s_a = max(0, r_start)
                    s_b = min(start_i, r_end)
                    if s_b > s_a:
                        new_elements.append(_make_run_element(raw_text[s_a:s_b], rPr))

            # 2. 目标条款局部注入修订
            for tag, i1, i2, j1, j2 in refine_diff_opcodes(sm.get_opcodes(), matched_orig, sugg):
                if tag == 'equal':
                    chunk_start = start_i + i1
                    chunk_end = start_i + i2
                    for r_start, r_end, rPr in run_ranges:
                        s_a = max(chunk_start, r_start)
                        s_b = min(chunk_end, r_end)
                        if s_b > s_a:
                            new_elements.append(_make_run_element(raw_text[s_a:s_b], rPr))
                elif tag == 'delete':
                    chunk_start = start_i + i1
                    chunk_end = start_i + i2
                    for r_start, r_end, rPr in run_ranges:
                        s_a = max(chunk_start, r_start)
                        s_b = min(chunk_end, r_end)
                        if s_b > s_a:
                            new_elements.append(_make_del_element(raw_text[s_a:s_b], author, run_id_counter, rPr))
                            run_id_counter += 1
                            local_revisions += 1
                elif tag == 'insert':
                    ins_sub = sugg[j1:j2]
                    pos = start_i + i1
                    rPr = get_rPr_at_pos(pos)
                    new_elements.append(_make_ins_element(ins_sub, author, run_id_counter, rPr))
                    run_id_counter += 1
                    local_revisions += 1
                elif tag == 'replace':
                    chunk_start = start_i + i1
                    chunk_end = start_i + i2
                    for r_start, r_end, rPr in run_ranges:
                        s_a = max(chunk_start, r_start)
                        s_b = min(chunk_end, r_end)
                        if s_b > s_a:
                            new_elements.append(_make_del_element(raw_text[s_a:s_b], author, run_id_counter, rPr))
                            run_id_counter += 1
                            local_revisions += 1
                    ins_sub = sugg[j1:j2]
                    pos = start_i + i1
                    rPr = get_rPr_at_pos(pos)
                    new_elements.append(_make_ins_element(ins_sub, author, run_id_counter, rPr))
                    run_id_counter += 1
                    local_revisions += 1

            # 3. 后置未受影响文字
            if end_i < len(raw_text):
                for r_start, r_end, rPr in run_ranges:
                    s_a = max(end_i, r_start)
                    s_b = min(len(raw_text), r_end)
                    if s_b > s_a:
                        new_elements.append(_make_run_element(raw_text[s_a:s_b], rPr))

            # 替换 p._p 中的 runs，同时完整保留 <w:pPr> 与样式
            first_r = None
            for child in list(p._p):
                if child.tag.endswith('}r') or child.tag.endswith('}del') or child.tag.endswith('}ins'):
                    first_r = child
                    break

            if first_r is not None:
                for elem in new_elements:
                    first_r.addprevious(elem)
                for child in list(p._p):
                    if (child.tag.endswith('}r') or child.tag.endswith('}del') or child.tag.endswith('}ins')) and child not in new_elements:
                        p._p.remove(child)
            else:
                for elem in new_elements:
                    p._p.append(elem)

            injected_indices.add(idx)
            total_revisions_count += local_revisions
            break

    for p in doc.paragraphs:
        process_p(p)

    for tbl in doc.tables:
        for row in tbl.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    process_p(p)

    for idx, item in enumerate(clause_reviews):
        if idx not in injected_indices:
            unmatched_clauses.append(item.get("clause_title") or item.get("original_clause", "")[:40])

    doc.save(output_path)
    stats = {
        "status": "success",
        "output_path": output_path,
        "total_clauses": len(clause_reviews),
        "injected_clauses": len(injected_indices),
        "revisions_count": total_revisions_count,
        "unmatched_clauses": unmatched_clauses
    }
    return RedlineResult(output_path, stats=stats)
