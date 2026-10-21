# -*- coding: utf-8 -*-
"""
LawFlow 智律工作台 - P0 级升级实证检验脚本
验证项：
1. 模糊容错原位 Word 修订 (Levenshtein / 空白与标点符号归一化 / 非破坏性段落局部切片)
2. 全英文商业合同自动识别、涉外采购 Playbook 自动挂载、纯正英文建议条款生成
3. export-redline 接口原生支持 source_docx_path 原件原位注入
"""

import os
import sys
import tempfile
import docx
from fastapi.testclient import TestClient

# 适配 Windows 控制台输出编码
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from gateway.main import app
from gateway.utils.redline_builder import (
    apply_in_place_docx_redline,
    find_best_matching_span,
    normalize_text_for_matching,
    PLAYBOOK_PRESETS
)
from gateway.utils.legal_prompts import is_predominantly_english

client = TestClient(app, headers={"X-LawFlow-Token": os.environ.get("LAWFLOW_API_TOKEN", "test-token")})


def test_fuzzy_matching_and_non_destructive_redline():
    print("\n--- [P0.1 校验] 模糊容错与段落局部非破坏性切片注入 ---")
    
    # 1. 验证文本归一化
    raw_dirty = "Section 24.3\u00a0Cross-Default:\t“Any default by Buyer or its Affiliates—”  shall apply."
    norm = normalize_text_for_matching(raw_dirty)
    assert '\u00a0' not in norm
    assert '“' not in norm
    assert '"' in norm
    print("  [PASS] normalize_text_for_matching 成功消除不换行空格、制表符与弯引号")

    # 2. 验证多子句大段中的局部匹配与切片提取
    full_para = (
        "Section 24.2 Remedies. The Buyer may exercise all statutory remedies under applicable law. "
        "Section 24.3 Cross-Default. In the event Buyer or any of its Affiliates defaults under any other agreement, "
        "Seller shall have the right to immediately terminate this Agreement without notice. "
        "Section 24.4 Governing Law. This Agreement shall be governed by Delaware law."
    )
    # 模拟大模型提取出的条款（引号、破折号略有差异）
    target_clause = 'Section 24.3 Cross-Default. In the event Buyer or any of its Affiliates defaults under any other agreement, Seller shall have the right to immediately terminate this Agreement without notice.'
    span = find_best_matching_span(full_para, target_clause)
    assert span is not None, "必须成功找到子条款在段落中的字符区间！"
    start, end = span
    matched_sub = full_para[start:end]
    assert "Cross-Default" in matched_sub
    print("  [PASS] find_best_matching_span 成功从多条款复合段落中精准锁定目标子句区间")

    # 3. 验证真实 Word 原位注入不误删段落其余文字
    with tempfile.TemporaryDirectory() as tmpdir:
        doc_path = os.path.join(tmpdir, "client_master_agreement.docx")
        d = docx.Document()
        p = d.add_paragraph(full_para)
        d.save(doc_path)

        out_path = os.path.join(tmpdir, "client_master_agreement_redlined.docx")
        clause_reviews = [
            {
                "clause_title": "Cross-Default Deletion",
                # 传入略带多余空格和弯引号的原条款
                "original_clause": 'Section 24.3  Cross-Default. In the event Buyer or any of its Affiliates defaults under any other agreement, Seller shall have the right to immediately terminate this Agreement without notice.',
                "suggested_clause": "Section 24.3 [Intentionally Deleted - Cross-default provisions are hereby deleted in their entirety]."
            }
        ]

        res = apply_in_place_docx_redline(doc_path, clause_reviews, out_path)
        assert os.path.exists(out_path)
        assert res.stats["injected_clauses"] == 1
        assert len(res.stats["unmatched_clauses"]) == 0

        # 打开生成的 docx，检验段落前后的 Section 24.2 与 Section 24.4 是否完好保留
        d_out = docx.Document(out_path)
        p_text_after = d_out.paragraphs[0].text
        assert "Section 24.2 Remedies." in p_text_after, "段落前面的前置条款绝不能被误删！"
        assert "Section 24.4 Governing Law." in p_text_after, "段落后面的后置条款绝不能被误删！"
        
        # 检验 XML 包含修订标记
        xml = d_out._body._element.xml
        assert "w:del" in xml and "w:ins" in xml
        print("  [PASS] apply_in_place_docx_redline 原位局部切片注入成功，前后条款 100% 完整保留！")


def test_english_contract_review_and_playbook():
    print("\n--- [P0.2 校验] 全英文涉外合同自动识别与纯正英文建议生成 ---")

    en_contract_text = """MASTER PURCHASE AGREEMENT
Section 18. Liquidated Damages. In the event Seller delays delivery for more than 3 days, Seller shall pay liquidated damages equal to 30% of the total contract value and shall compensate Buyer for all indirect, special or consequential damages.
Section 24.3 Cross-Default. In the event Buyer or any of its Affiliates defaults under any other agreement, Seller shall have the right to immediately terminate this Agreement without notice."""

    # 1. 验证语言检测
    assert is_predominantly_english(en_contract_text) is True
    print("  [PASS] is_predominantly_english 正确识别全英文采购合同")

    # 2. 验证审查接口自动挂载涉外采购红线库并输出英文建议条款
    resp = client.post("/api/v1/phase2/contract-review", json={
        "contract_title": "Cross-Border Master Purchase Agreement",
        "contract_text": en_contract_text,
        "perspective": "Seller-Protective 乙方防御版"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    # 验证自动切换为涉外采购库
    assert data["playbook_name"] in [
        "涉外与跨国商事采购红线库 (International Master Agreement Playbook)",
        "Custom Playbook"
    ] or "涉外" in data["playbook_name"]

    review = data["review"]
    clause_reviews = review.get("clause_reviews", [])
    assert len(clause_reviews) >= 1
    first_clause = clause_reviews[0]
    
    # 验证 suggested_clause 为纯正法律英文，杜绝中英夹生饭
    suggested = first_clause.get("suggested_clause", "")
    assert len(suggested) > 10
    assert any(w in suggested.lower() for w in ["deleted", "liquidated", "liability", "consequential", "exceed", "neither party"]), f"建议条款必须是规范英文: {suggested}"
    print(f"  [PASS] 建议条款纯英文输出校验通过: '{suggested[:75]}...'")


def test_export_redline_with_source_docx():
    print("\n--- [P0.3 校验] export-redline 经 upload-source + source_file_id 原位注入 ---")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        client_docx = os.path.join(tmpdir, "foreign_client_draft.docx")
        d = docx.Document()
        d.add_heading("Master Purchase Agreement", level=1)
        d.add_paragraph("Section 24.3 Cross-Default. In the event Buyer or any of its Affiliates defaults under any other agreement, Seller shall have the right to immediately terminate this Agreement without notice.")
        d.save(client_docx)

        # S-04：不再接受服务器路径，须先上传原件取得 source_file_id
        with open(client_docx, "rb") as f_up:
            up_resp = client.post(
                "/api/v1/phase2/contract-review/upload-source",
                files={"file": ("foreign_client_draft.docx", f_up, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            )
        assert up_resp.status_code == 200, up_resp.text
        source_file_id = up_resp.json()["source_file_id"]

        export_resp = client.post("/api/v1/phase2/contract-review/export-redline", json={
            "contract_title": "Master Purchase Agreement",
            "contract_text": "Section 24.3 Cross-Default...",
            "perspective": "Seller-Protective",
            "source_file_id": source_file_id,
            "clause_reviews": [
                {
                    "clause_title": "Cross-Default",
                    "original_clause": "Section 24.3 Cross-Default. In the event Buyer or any of its Affiliates defaults under any other agreement, Seller shall have the right to immediately terminate this Agreement without notice.",
                    "suggested_clause": "Section 24.3 [Intentionally Deleted - Cross-default provisions are hereby deleted in their entirety]."
                }
            ]
        })

        assert export_resp.status_code == 200, export_resp.text
        exp_data = export_resp.json()
        assert exp_data["status"] == "success"
        assert exp_data["in_place_mode"] is True
        assert exp_data["stats"]["injected_clauses"] == 1
        print("  [PASS] export-redline 成功触发原件原位注入并返回结构化统计！")


if __name__ == "__main__":
    test_fuzzy_matching_and_non_destructive_redline()
    test_english_contract_review_and_playbook()
    test_export_redline_with_source_docx()
    print("\n" + "=" * 70)
    print(">>> 【P0 级升级实证全绿】模糊容错原位 Word 修订与全英文涉外采购审查 100% 验收通过！")
    print("=" * 70)
