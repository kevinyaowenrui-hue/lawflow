# -*- coding: utf-8 -*-
"""
tests/test_inplace_redline.py
验收标准：
用 python-docx 生成一份中文合同 docx：
- 标题用自定义样式
- 第 3 条正文故意拆成 3 个 run（不同加粗），内容"乙方应于收到货物后三十日内付款"
- 审查意见把"三十日"改为"十五日"
-> 输出 docx 的 document.xml 中含 w:del（"三十"）与 w:ins（"十五"），revisions_count >= 1
-> 原自定义样式名仍存在
-> 故意给一条原文中不存在的条款 -> 出现在 unmatched_clauses
-> 原有英文样例测试（test_p0_english_redline）仍通过
"""
from __future__ import annotations

import os
import tempfile
import docx
from docx.enum.style import WD_STYLE_TYPE

from gateway.utils.redline_builder import apply_in_place_docx_redline


def test_chinese_inplace_redline_with_custom_style_and_split_runs():
    with tempfile.TemporaryDirectory() as tmpdir:
        doc_path = os.path.join(tmpdir, "chinese_contract.docx")
        out_path = os.path.join(tmpdir, "chinese_contract_redlined.docx")

        doc = docx.Document()

        # 1. 创建并使用自定义样式
        custom_style_name = "LawFlowCustomHeading"
        try:
            custom_style = doc.styles.add_style(custom_style_name, WD_STYLE_TYPE.PARAGRAPH)
            custom_style.font.name = "黑体"
        except Exception:
            custom_style = doc.styles[custom_style_name]

        p_title = doc.add_paragraph("商品买卖与供应协议", style=custom_style_name)

        p1 = doc.add_paragraph("第一条 标的物与数量约定。")
        p2 = doc.add_paragraph("第二条 交付期限与交付地点。")

        # 第 3 条正文故意拆成 3 个 run（不同加粗），内容"乙方应于收到货物后三十日内付款"
        p3 = doc.add_paragraph()
        r1 = p3.add_run("乙方应于")
        r1.bold = False
        r2 = p3.add_run("收到货物后三十日")
        r2.bold = True
        r3 = p3.add_run("内付款。")
        r3.bold = False

        doc.save(doc_path)

        # 审查意见：把"三十日"改为"十五日"，并故意加一条原文不存在的条款
        clause_reviews = [
            {
                "clause_title": "付款期限条款",
                "original_clause": "乙方应于收到货物后三十日内付款",
                "suggested_clause": "乙方应于收到货物后十五日内付款",
            },
            {
                "clause_title": "不存在的违约条款",
                "original_clause": "本合同约定的违约金为总金额的一百倍且不得由法院酌减",
                "suggested_clause": "本合同约定的违约金按实际损失计算",
            }
        ]

        res = apply_in_place_docx_redline(doc_path, clause_reviews, out_path)

        assert os.path.exists(out_path)
        stats = getattr(res, "stats", {})
        revisions_count = stats.get("revisions_count", 0)
        unmatched_clauses = stats.get("unmatched_clauses", [])

        # 断言 revisions_count >= 1
        assert revisions_count >= 1, f"revisions_count 应 >= 1，实际: {revisions_count}"

        # 故意给的不存在条款应出现在 unmatched_clauses 中
        assert any("不存在" in str(u) or "一百倍" in str(u) for u in unmatched_clauses), (
            f"不存在条款必须出现在 unmatched_clauses: {unmatched_clauses}"
        )

        # 读取输出文档的 XML
        doc_out = docx.Document(out_path)
        xml = doc_out._body._element.xml

        # 输出 docx 的 document.xml 中含 w:del（"三十"）与 w:ins（"十五"）
        assert "w:del" in xml, "document.xml 必须包含 w:del"
        assert "w:ins" in xml, "document.xml 必须包含 w:ins"
        assert "三十" in xml, "w:del 必须包含被删除的'三十'"
        assert "十五" in xml, "w:ins 必须包含被插入的'十五'"

        # 原自定义样式名仍存在
        style_names = [p.style.name for p in doc_out.paragraphs]
        assert custom_style_name in style_names, f"原自定义样式名 {custom_style_name} 必须仍存在于段落样式中: {style_names}"
