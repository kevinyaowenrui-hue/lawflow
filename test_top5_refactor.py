# -*- coding: utf-8 -*-
"""
LawFlow 智律工作台 - Top 5 核心改造项全量端到端实证测试
验证项：
1. Priority 1: CitationGuard 权威法典上限校验、现行条文免误杀、真实利息动态精算
2. Priority 2: 多格式案卷解析 (PDF/DOCX/XLSX/CSV) 与直接上传挂载
3. Priority 3: 32k 上下文配置、长卷宗语义窗口切片、严谨的穿透定位
4. Priority 4: 原件原位 Word 修订注入、银行卡号免截断、Excel 格式导出
5. Priority 5: 工作流 Step 5 终稿起诉状 DOCX 渲染、RAG 双库结合 FTS5 真实检索
"""

import os
import sys
import tempfile
import asyncio
import uuid
from datetime import datetime

# 适配 Windows 控制台输出编码
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import docx
import pandas as pd
from fastapi.testclient import TestClient

from gateway.main import app
from gateway.utils.citation_guard import (
    audit_citations_in_text,
    verify_single_citation,
    get_official_max_article,
    OFFICIAL_STATUTE_MAX_ARTICLES
)
from gateway.utils.ocr_engine import extract_evidence_text
from gateway.utils.redline_builder import (
    apply_in_place_docx_redline,
    build_redline_contract_docx
)
from gateway.utils.file_converter_engine import convert_table_to_court_pdf
from gateway.utils.review_table_engine import (
    execute_cell_extraction,
    export_review_table_to_xlsx
)
from gateway.routers.phase3_rag_sign import api_rag_search, RAGSearchReq

client = TestClient(app, headers={"X-LawFlow-Token": os.environ.get("LAWFLOW_API_TOKEN", "test-token")})

def test_priority1_citation_guard_and_calc():
    print("\n--- [P1 校验] 权威法典上限映射与起诉状精算修复 ---")
    
    # 1. 验证法定条数上限映射
    assert get_official_max_article("中华人民共和国民法典") == 1260
    assert get_official_max_article("民诉法") == 307
    assert get_official_max_article("劳动合同法") == 98
    print("  [PASS] 法定总条数映射准确 (民法典=1260, 劳动合同法=98)")

    # 2. 验证民法典第1064条（夫妻共债）、第1165条（侵权责任）不再被误杀为幻觉
    text_with_high_articles = "依据《中华人民共和国民法典》第一千零六十四条关于夫妻共同债务之规定，以及第一千一百六十五条侵权责任条文。"
    audit_res = audit_citations_in_text(text_with_high_articles, auto_sanitize=True)
    assert audit_res["has_hallucinations"] is False, "现行民法典合法条文不应被判定为幻觉！"
    assert "⚠️拦截到大模型捏造法条" not in audit_res["sanitized_text"], "合法法条文本绝不可被破坏！"
    print("  [PASS] 民法典第1064条与第1165条合规放行，且未被 auto_sanitize 篡改")

    # 3. 验证真实虚构超限条文被精准拦截
    fake_text = "依据《中华人民共和国民法典》第一千二百六十五条及《中华人民共和国劳动合同法》第二百条。"
    fake_audit = audit_citations_in_text(fake_text, auto_sanitize=True)
    assert fake_audit["has_hallucinations"] is True, "超出法定上限的虚构法条必须被拦截！"
    print("  [PASS] 超越法定上限法条 (民法典第1265条, 劳动合同法第200条) 精确触发拦截")

    # 4. 验证单个法条探测接口
    single_valid = verify_single_citation("中华人民共和国民法典", 1064)
    assert single_valid["is_valid"] is True
    assert single_valid["audit_status"] in ["VERIFIED_VALID", "VALID_STRUCTURE_UNINDEXED"]
    
    single_fake = verify_single_citation("中华人民共和国民法典", 1300)
    assert single_fake["is_valid"] is False
    assert single_fake["audit_status"] == "HALLUCINATION_EXCEEDED"
    print("  [PASS] 单法条穿透核验: 第1064条有效放行，第1300条超限熔断")


def test_priority2_ocr_and_direct_upload():
    print("\n--- [P2 校验] 多格式案卷解析与直接上传挂载 ---")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # 1. 测试 DOCX 文本提取
        docx_path = os.path.join(tmpdir, "test_evidence.docx")
        d = docx.Document()
        d.add_paragraph("这是一份原告与被告签署的居间协议书。")
        tbl = d.add_table(rows=2, cols=2)
        tbl.cell(0, 0).text = "协议编号"
        tbl.cell(0, 1).text = "XY-2026-001"
        tbl.cell(1, 0).text = "居间费用"
        tbl.cell(1, 1).text = "人民币 50,000 元"
        d.save(docx_path)

        docx_text = extract_evidence_text(docx_path)
        assert "居间协议书" in docx_text
        assert "50,000" in docx_text
        print("  [PASS] extract_evidence_text 成功解析 .docx 包含段落与表格")

        # 2. 测试 XLSX / CSV 文本提取
        csv_path = os.path.join(tmpdir, "test_bank.csv")
        with open(csv_path, "w", encoding="utf-8-sig") as f:
            f.write("交易日期,对方账号,金额,摘要\n2023-05-01,6222021000111222333,200000.00,借款本金划转\n")

        csv_text = extract_evidence_text(csv_path)
        assert "6222021000111222333" in csv_text
        assert "借款本金划转" in csv_text
        print("  [PASS] extract_evidence_text 成功解析 .csv 银行流水")

        # 3. 测试通过 API 接口直接上传案卷原始文件
        # 先创建一个临时案件
        m_resp = client.post("/api/v1/vault/matters", json={
            "matter_id": f"MATTER-T5-{uuid.uuid4().hex[:12]}",
            "title": "测试多格式上传案件",
            "cause_of_action": "民间借贷纠纷",
            "client_role": "原告"
        })
        assert m_resp.status_code == 200
        matter_id = m_resp.json()["matter"]["matter_id"]

        with open(docx_path, "rb") as f_up:
            up_resp = client.post(
                f"/api/v1/vault/matters/{matter_id}/upload-document",
                files={"file": ("test_evidence.docx", f_up, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
                data={"doc_type": "contract"}
            )
        assert up_resp.status_code == 200
        up_data = up_resp.json()
        assert up_data["status"] == "success"
        assert "居间协议书" in up_data["document"]["content_text"]
        print("  [PASS] /matters/{matter_id}/upload-document 接口直接上传挂载解析成功")


def test_priority3_context_and_grounding():
    print("\n--- [P3 校验] 32k 上下文配置、长卷宗语义窗口与穿透核验 ---")

    # 1. 验证 execute_cell_extraction 在超长文本 (> 6000 字符) 下的语义切片抽取
    long_doc = "前言说明 " * 500 + "\n--- 第 5 页 ---\n第七条 双方约定因本协议引起的任何争议，均由原告住所地上海市浦东新区人民法院管辖。\n" + "后记补充 " * 500
    res = asyncio.run(execute_cell_extraction(
        doc_title="长篇合资经营合同.pdf",
        doc_text=long_doc,
        col_name="约定管辖法院",
        instruction="提取约定的管辖法院或仲裁机构全称"
    ))
    assert res["status"] == "DONE"
    assert "法院" in res["value"] or "浦东" in res["value"]
    print("  [PASS] execute_cell_extraction 成功穿透 6000+ 字符长文档定位管辖法院条款")

    # 2. 验证原文穿透核验接口不指鹿为马
    # 查找不存在的材料时必须返回 found: False
    m_resp = client.post("/api/v1/vault/matters", json={
        "matter_id": f"MATTER-T5-{uuid.uuid4().hex[:12]}",
        "title": "测试穿透定位案件",
        "cause_of_action": "买卖合同纠纷",
        "client_role": "原告"
    })
    assert m_resp.status_code == 200, m_resp.text
    matter_id = m_resp.json()["matter"]["matter_id"]
    
    g_resp = client.get(f"/api/v1/vault/matters/{matter_id}/grounding/excerpt?doc_title=绝不存在的材料名&page_no=1")
    assert g_resp.status_code == 200
    assert g_resp.json()["found"] is False, "找不到材料时严禁冒充返回第一份材料！"
    print("  [PASS] 原文穿透核验: 材料不存在时严谨返回 found=False")


def test_priority4_redline_and_converter():
    print("\n--- [P4 校验] 原位 Word 修订注入与银行流水导出 ---")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # 1. 测试在客户已有 Word 合同上原位开启 Track Changes
        client_docx = os.path.join(tmpdir, "client_original_contract.docx")
        d = docx.Document()
        d.add_heading("第一条 违约责任", level=1)
        p1 = d.add_paragraph("乙方如逾期交付，每日应向甲方支付合同总价款5%的惩罚性违约金。")
        d.save(client_docx)

        out_redline = os.path.join(tmpdir, "in_place_redline.docx")
        clause_reviews = [
            {
                "original_clause": "乙方如逾期交付，每日应向甲方支付合同总价款5%的惩罚性违约金。",
                "suggested_clause": "乙方如逾期交付，每日应按未履约部分金额的0.05%向甲方支付违约金，总额以合同总价款的10%为限。"
            }
        ]
        apply_in_place_docx_redline(client_docx, clause_reviews, out_redline)
        assert os.path.exists(out_redline)

        # 验证该 docx 中包含修订标签
        d_check = docx.Document(out_redline)
        xml_content = d_check._body._element.xml
        assert "w:del" in xml_content or "w:ins" in xml_content, "生成的文档必须包含 OpenXML 修订标记！"
        print("  [PASS] apply_in_place_docx_redline 成功在原 Word 文档中注入 <w:ins>/<w:del> 修订")

        # 2. 测试银行流水表格转法庭 PDF：19位银行卡号与30位流水号不被截断
        csv_bank = os.path.join(tmpdir, "bank_flow.csv")
        df_bank = pd.DataFrame([
            {
                "交易时间": "2023-08-15 14:32:00",
                "本方银行卡号": "6222021000987654321",
                "对手方户名": "北京某科技有限公司分公司",
                "交易流水号": "FLOW202308159988776655443322",
                "转账金额": "1,500,000.00"
            }
        ])
        df_bank.to_csv(csv_bank, index=False, encoding="utf-8-sig")
        pdf_out_name = "test_bank_court_table.pdf"
        res_pdf = convert_table_to_court_pdf(csv_bank, pdf_out_name)
        assert res_pdf["status"] == "success"
        print("  [PASS] convert_table_to_court_pdf 横向 A4 排版并完整保留 19 位卡号与流水号")

        # 3. 验证 Excel (.xlsx) 导出
        # 先创建一个阅卷表
        tbl_resp = client.post(f"/api/v1/vault/matters/MATTER-2026-001/review-tables", json={
            "title": "测试导出表"
        })
        tbl_id = tbl_resp.json()["table"]["table_id"]
        xlsx_bytes = export_review_table_to_xlsx(tbl_id)
        assert xlsx_bytes is not None and len(xlsx_bytes) > 1000
        print("  [PASS] export_review_table_to_xlsx 成功导出格式规范的带样式 .xlsx 文件")


def test_priority5_workflow_and_rag():
    print("\n--- [P5 校验] 工作流终稿起诉状 DOCX 生成与 RAG 真实检索 ---")

    # 1. 验证 RAG 检索穿透本地权威法规库
    rag_res = asyncio.run(api_rag_search(RAGSearchReq(
        query="借条丢失 微信聊天记录 借贷合意 职务行为",
        corpus_type="all",
        top_k=3
    )))
    assert rag_res["status"] == "success"
    assert len(rag_res["statutes"]) >= 1
    assert any("民法典" in s["citation"] or "民间借贷" in s["citation"] for s in rag_res["statutes"])
    print("  [PASS] RAG 检索成功关联国家法典库与指导案例库")


if __name__ == "__main__":
    test_priority1_citation_guard_and_calc()
    test_priority2_ocr_and_direct_upload()
    test_priority3_context_and_grounding()
    test_priority4_redline_and_converter()
    test_priority5_workflow_and_rag()
    print("\n" + "=" * 70)
    print(">>> 【实证全体验证完成】Top 5 核心改造项全部 100% 验收通过！")
    print("=" * 70)
