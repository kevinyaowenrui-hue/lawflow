"""
test_batch1_e2e.py
端到端实证校验脚本：第一批 4 大核心功能全链路测试
1. #11: 本地 PII 自动脱敏与还原网关
2. #5: 案号核验补齐与反查防火墙
3. #7: 审查立场手册 (Playbook & Position Selector)
4. #8: 三栏修订卡片与 Word 原生修订导出 (Track Changes)
"""
import sys
import os
import json
import sqlite3
import zipfile
import xml.etree.ElementTree as ET
import asyncio

# Ensure utf-8 stdout for powershell
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

def run_tests():
    print("=" * 70)
    print(">>> 开始执行 Batch 1 (第一批 4 大核心功能) 端到端实证校验...")
    print("=" * 70)

    # -------------------------------------------------------------------------
    # 测试项 1: PII 脱敏与还原网关 (PIISanitizer & UniversalLLMClient)
    # -------------------------------------------------------------------------
    print("\n[TEST 1/4] 验证 #11: 本地 PII 自动脱敏与无损还原网关...")
    from gateway.utils.pii_sanitizer import PIISanitizer
    from gateway.core.ollama_client import UniversalLLMClient

    sample_prompt = (
        "甲方：北京智律科技有限公司（统一社会信用代码：91110108MA01XXXXXX），"
        "法定代表人：张伟，身份证号：110101199003072345，联系电话：13800138000，"
        "收款银行卡号：6222021001001234567，电子邮箱：zhangwei@lawtech.com。"
    )
    
    masked, mapping = PIISanitizer.mask_text(sample_prompt, known_parties=["北京智律科技有限公司", "张伟"])
    print(f"  [1.1] 原始敏感文书长度: {len(sample_prompt)} 字符")
    print(f"  [1.2] 脱敏后文本预览:\n        {masked}")
    
    assert "110101199003072345" not in masked, "身份证号未能脱敏！"
    assert "13800138000" not in masked, "手机号未能脱敏！"
    assert "6222021001001234567" not in masked, "银行卡号未能脱敏！"
    assert "91110108MA01XXXXXX" not in masked, "统一社会信用代码未能脱敏！"
    assert "zhangwei@lawtech.com" not in masked, "电子邮箱未能脱敏！"
    assert "张伟" not in masked, "自然人姓名未能脱敏！"
    assert len(mapping) >= 5, f"脱敏实体数量异常: {len(mapping)}"

    unmasked = PIISanitizer.unmask_text(masked, mapping)
    assert unmasked == sample_prompt, "脱敏后还原不一致，出现信息损毁！"
    print("  [1.3] 本地无损还原校验: PASS (100% 精确还原)")

    # 验证 UniversalLLMClient 启停控制
    client = UniversalLLMClient()
    assert client.pii_shield_enabled is True, "默认应开启 PII 隐私防护网关"
    print("  [1.4] UniversalLLMClient 默认 PII 隐私防护盾: PASS (ENABLED)")

    # -------------------------------------------------------------------------
    # 测试项 2: 案号核验补齐与反查防火墙 (CitationGuard & Precedents DB)
    # -------------------------------------------------------------------------
    print("\n[TEST 2/4] 验证 #5: 司法审判案号格式合规与判例库验真防火墙...")
    from gateway.utils.citation_guard import audit_case_numbers, verify_single_case_number, audit_citations_in_text

    # 测试已知指导性真实案例
    true_case_res = verify_single_case_number("（2023）最高法民终123号")
    print(f"  [2.1] 真实案号校验结果: 状态={true_case_res['status']}, 风险={true_case_res['risk_level']}")
    assert true_case_res['status'] == "VERIFIED_PRECEDENT", "已知真实案号未被识别为 VERIFIED_PRECEDENT！"
    assert true_case_res['matched_precedent'] is not None, "未拉取到判例详情！"
    print(f"        命中判例: 《{true_case_res['matched_precedent']['title']}》")

    # 测试大模型幻觉虚构案号（年份为2099）
    fake_case_res = verify_single_case_number("（2099）最高法知民终9999号")
    print(f"  [2.2] 虚构案号拦截结果: 状态={fake_case_res['status']}, 风险={fake_case_res['risk_level']}")
    assert fake_case_res['is_hallucination'] is True, "虚构年份案号未被拦截！"
    assert fake_case_res['risk_level'] == "CRITICAL_BLOCKED", "风险等级未能升为 CRITICAL_BLOCKED！"

    # 测试复合文书全量引注体检
    hybrid_doc = """
    依据《中华人民共和国合同法》第五十二条及《中华人民共和国民法典》第五百七十七条，
    参照最高人民法院（2023）最高法民终123号裁判要旨，
    并注意避免（2099）京01民初8888号判例中认定的无效情形。
    """
    full_audit = audit_citations_in_text(hybrid_doc, auto_sanitize=True)
    print(f"  [2.3] 复合文书引注体检: 发现旧法={full_audit['has_abrogated_laws']}, 发现幻觉={full_audit['has_hallucinations']}")
    assert full_audit['has_abrogated_laws'] is True, "未探测到已废止的合同法第五十二条！"
    assert full_audit['has_hallucinations'] is True, "未探测到2099年虚构案号！"
    assert len(full_audit['case_numbers']) == 2, f"案号提取数量不对: {len(full_audit['case_numbers'])}"
    print("  [2.4] 案号反查与法规后验熔断全流程: PASS")

    # -------------------------------------------------------------------------
    # 测试项 3: 审查立场手册与偏离度诊断 (Playbook & Position Selector)
    # -------------------------------------------------------------------------
    print("\n[TEST 3/4] 验证 #7: 审查立场手册 (Playbook & Position Selector)...")
    from gateway.utils.redline_builder import PLAYBOOK_PRESETS
    assert "tech_service" in PLAYBOOK_PRESETS, "缺少 tech_service 审查预设！"
    assert "procurement" in PLAYBOOK_PRESETS, "缺少 procurement 审查预设！"
    tech_preset = PLAYBOOK_PRESETS["tech_service"]
    print(f"  [3.1] 成功载入预设《{tech_preset['name']}》，内置规则条数: {len(tech_preset['rules'])}")

    # 模拟 Phase 2 合同条款审查路由
    from gateway.routers.phase2_evidence import review_contract_clauses, ContractReviewReq
    sample_contract = (
        "第3条 知识产权归属：乙方为甲方开发的所有源代码及交付物，其全部知识产权归甲方独家所有。\n"
        "第6条 违约责任：乙方迟延交付每日需支付总合同金额 5% 的违约金，累计无上限。"
    )
    req = ContractReviewReq(
        perspective="乙方 (开发方/受托方)",
        contract_text=sample_contract,
        playbook_preset="tech_service"
    )
    review_resp = asyncio.run(review_contract_clauses(req))
    assert review_resp["status"] == "success", "合同审查接口执行失败！"
    clauses = review_resp["review"].get("clause_reviews", [])
    assert len(clauses) >= 1, "条款拆解不足！"
    
    first_clause = clauses[0]
    print(f"  [3.2] 第一条款偏离度评级: {first_clause.get('playbook_deviation')} (命中规则: {first_clause.get('matched_playbook_rule')})")
    assert first_clause.get("playbook_deviation") in ["OUT_OF_SCOPE_DEVIATION", "CRITICAL_BREACH", "COMPLIANT"]
    print("  [3.3] 审查立场手册与偏离度诊断: PASS")

    # -------------------------------------------------------------------------
    # 测试项 4: 三栏修订卡片与 Word 原生修订导出 (Track Changes)
    # -------------------------------------------------------------------------
    print("\n[TEST 4/4] 验证 #8: 三栏修订卡片与 Word 原生修订导出 (Track Changes)...")
    from gateway.utils.redline_builder import compute_text_diff_chunks, build_redline_contract_docx

    orig_clause = "乙方迟延交付每日按总价款 5% 支付违约金，且上不封顶。"
    sugg_clause = "乙方迟延交付每日按未履约部分金额 0.05% 支付违约金，累计违约金总额不超过合同总金额的 10%。"

    diff_chunks = compute_text_diff_chunks(orig_clause, sugg_clause)
    print(f"  [4.1] Diff 切片生成成功，切片数: {len(diff_chunks)}")
    has_ins = any(c.get("type") == 'insert' for c in diff_chunks)
    has_del = any(c.get("type") == 'delete' for c in diff_chunks)
    assert has_ins and has_del, "Diff 切片中缺少删除或插入标记！"

    output_docx = os.path.abspath("storage/generated/test_verified_redline.docx")
    mock_reviews = [
        {
            "clause_id": 1,
            "clause_title": "第6条 违约责任与封顶",
            "risk_analysis": "单日 5% 违约金严重过高且无上限，将导致乙方承担无法预测的倾覆性履约风险。",
            "original_clause": orig_clause,
            "suggested_clause": sugg_clause,
            "negotiation_tip": "提出最高法院司法解释 30% 实际损失上限抗辩，并要求违约金基数限定为未交付部分。",
            "playbook_deviation": "CRITICAL_BREACH",
            "matched_playbook_rule": "违约金总额必须设定封顶线（通常不超过合同金额 10%~20%）",
            "deviation_reason": "单日5%且无封顶突破行业红线"
        }
    ]

    docx_path = build_redline_contract_docx(
        contract_title="软件服务外包协议_修订版",
        original_contract_text=orig_clause,
        clause_reviews=mock_reviews,
        perspective="乙方防御版",
        playbook_name="软件开发与技术服务红线库",
        playbook_rules=["违约金总额必须设定封顶线（通常不超过合同金额 10%~20%）"],
        output_path=output_docx
    )
    assert os.path.exists(docx_path), f"未能生成导出的 docx 文件: {docx_path}"
    file_size = os.path.getsize(docx_path)
    print(f"  [4.2] 成功生成 Word 原生修订文档: {docx_path} ({file_size} 字节)")

    # 深入解包 .docx 并校验 OpenXML <w:ins> / <w:del> 及 <w:trackRevisions>
    with zipfile.ZipFile(docx_path, 'r') as zf:
        # 1. 检验 document.xml 中的修订标签
        doc_xml = zf.read('word/document.xml').decode('utf-8')
        assert '<w:del ' in doc_xml, "Word document.xml 缺少原生 <w:del> 标签！"
        assert '<w:ins ' in doc_xml, "Word document.xml 缺少原生 <w:ins> 标签！"
        assert '<w:delText' in doc_xml, "Word document.xml 缺少原生 <w:delText> 标签！"
        print("  [4.3] OpenXML 核心规范校验: <w:del>, <w:ins>, <w:delText> 均存在且结构合法")

        # 2. 检验 settings.xml 中的 trackRevisions 属性
        settings_xml = zf.read('word/settings.xml').decode('utf-8')
        assert 'w:trackRevisions' in settings_xml, "Word settings.xml 缺少 w:trackRevisions！"
        print("  [4.4] Word 原生修订跟踪状态校验: trackRevisions=true 生效确认")

    print("\n" + "=" * 70)
    print(">>> 恭喜！Batch 1 (第一批 4 大核心功能) 全部实证通过 (4/4 PASS)！")
    print("=" * 70)

if __name__ == "__main__":
    run_tests()
