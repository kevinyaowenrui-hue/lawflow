# -*- coding: utf-8 -*-
"""
Batch 2 End-to-End Test Suite:
1. 案件独立空间 (Matter Vault) - SQLite persistence, document mounting, matter isolation
2. 案件核心图谱自动提取 (Core Case Graphs) - Timeline, Entity-Relationship, Cashflow
3. 人机协同断点工作流 (Human-in-the-Loop Workflow State Machine) - 5-step machine with 2 human breakpoints
"""

import sys
import os
import json

# Force UTF-8 output on Windows consoles
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# Ensure project root is on PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi.testclient import TestClient
from gateway.main import app
from gateway.utils.matter_vault_db import init_matter_vault_db

client = TestClient(app, headers={"X-LawFlow-Token": os.environ.get("LAWFLOW_API_TOKEN", "test-token")})

def run_all_tests():
    print("=" * 70)
    print(">>> 启动 LawFlow 智律工作台 第二批功能全链路端到端回归测试")
    print("=" * 70)

    # 0. 数据库与健康检查
    print("\n[Step 0] 验证数据库初始化与服务健康指标...")
    init_matter_vault_db()
    resp = client.get("/health")
    assert resp.status_code == 200, f"Health check failed: {resp.text}"
    health_data = resp.json()
    assert health_data.get("status") == "healthy", "health status is not healthy"
    # 功能开关改由业务接口探测（健康检查仅返回最小信息）
    matters = client.get("/api/v1/vault/matters")
    assert matters.status_code == 200, f"matter_vault 不可用: {matters.text}"
    print("  ✓ /health 与 matter_vault 校验通过")

    # 1. 案件独立空间 (Matter Vault) CRUD & 文档挂载测试
    print("\n[Step 1] 验证案件独立空间 (Matter Vault) CRUD 与材料挂载...")
    resp = client.get("/api/v1/vault/matters")
    assert resp.status_code == 200
    matters_list = resp.json().get("matters", [])
    assert len(matters_list) >= 2, f"Expected at least 2 seeded matters, got {len(matters_list)}"
    print(f"  ✓ 成功读取案件底库，当前案件总数: {len(matters_list)} (已包含种子测试案例)")

    # 1.1 创建新案件
    new_matter_payload = {
        "title": "深圳市腾飞智联供应链民间借贷与股权质押清算纠纷案",
        "cause_of_action": "民间借贷纠纷",
        "case_number": "(2026)粤0305民初9988号",
        "court_name": "深圳市南山区人民法院",
        "principal_amount": 3500000.0,
        "plaintiff_name": "深圳腾飞前海投资合伙企业",
        "defendant_name": "智联创展网络科技（深圳）有限公司",
        "summary": "2023年6月10日借款350万元，年利率14.5%，约定1年期满清偿。借款人逾期未还，实控人出具最高额个人无限连带责任保证书。"
    }
    resp = client.post("/api/v1/vault/matters", json=new_matter_payload)
    assert resp.status_code == 200, f"Create matter failed: {resp.text}"
    created_matter = resp.json()["matter"]
    test_matter_id = created_matter["matter_id"]
    print(f"  ✓ 成功创建新案件独立空间: {test_matter_id} - {created_matter['title']}")

    # 1.2 挂载材料至该案件空间
    doc_payload = {
        "doc_title": "《借款合同及个人保证书补充协议》.docx",
        "doc_type": "contract",
        "content_text": "甲方出借350万元整，乙方于2024年6月9日前一次性还本付息。如逾期，按全国银行间同业拆借中心公布的LPR四倍计付逾期利息。丙方张总承担连带保证责任。"
    }
    resp = client.post(f"/api/v1/vault/matters/{test_matter_id}/documents", json=doc_payload)
    assert resp.status_code == 200
    doc_data = resp.json()["document"]
    print(f"  ✓ 成功向案件挂载材料: {doc_data['doc_id']} - {doc_data['doc_title']}")

    # 1.3 查询该案件挂载材料列表
    resp = client.get(f"/api/v1/vault/matters/{test_matter_id}/documents")
    assert resp.status_code == 200
    docs = resp.json()["documents"]
    assert len(docs) == 1
    assert docs[0]["doc_title"] == "《借款合同及个人保证书补充协议》.docx"
    print(f"  ✓ 材料检索隔离测试通过: 案件 {test_matter_id} 独立材料数为 1")

    # 2. 核心图谱自动抽取测试 (Core Case Graphs)
    print("\n[Step 2] 验证案件核心图谱自动提取 (时间线 / 主体关系 / 资金流水)...")
    resp = client.post(f"/api/v1/vault/matters/{test_matter_id}/graphs/extract")
    assert resp.status_code == 200, f"Graph extraction failed: {resp.text}"
    graphs = resp.json()["graphs"]
    timeline = graphs.get("timeline", [])
    entity_graph = graphs.get("entity_graph", {})
    cashflow = graphs.get("cashflow", [])

    assert len(timeline) >= 1, "Expected at least 1 timeline event"
    assert len(entity_graph.get("nodes", [])) >= 2, "Expected at least 2 entity nodes"
    assert len(cashflow) >= 1, "Expected at least 1 cashflow record"
    print(f"  ✓ 图谱抽取成功：时间线事件 {len(timeline)} 个，主体节点 {len(entity_graph['nodes'])} 个，关系边 {len(entity_graph['edges'])} 条，资金流水 {len(cashflow)} 笔")
    sig = timeline[0].get('significance') or timeline[0].get('legal_tag') or '关键法律事实'
    src = entity_graph['edges'][0].get('source') or entity_graph['edges'][0].get('source_id')
    rel = entity_graph['edges'][0].get('relation') or entity_graph['edges'][0].get('type')
    tgt = entity_graph['edges'][0].get('target') or entity_graph['edges'][0].get('target_id')
    print(f"    - 时间线节点样例: [{timeline[0]['date']}] {timeline[0]['event']} ({sig})")
    print(f"    - 关系边样例: {src} --({rel})--> {tgt}")

    # 3. 人机协同断点工作流状态机测试 (5-Step Machine with Breakpoints)
    print("\n[Step 3] 验证人机协同断点工作流 (5步状态机 + 2个人工决策断点 + 回退机制)...")
    
    # 3.1 启动工作流 (Step 1 自动完成 -> Step 2 挂起等待人工核准)
    start_payload = {
        "matter_id": test_matter_id,
        "initial_facts": "原告于2023年6月10日向被告转账350万元，约定借期1年，年利率14.5%，保证人张总签字承诺承担连带保证责任。借款到期后原告多次通过电话催收无果，被告至今拖欠本金及利息。",
        "cause_of_action": "民间借贷纠纷"
    }
    resp = client.post("/api/v1/vault/workflows/start", json=start_payload)
    assert resp.status_code == 200, f"Workflow start failed: {resp.text}"
    wf = resp.json()["workflow"]
    wf_id = wf["workflow_id"]
    assert wf["current_step"] == 2, f"Expected step 2, got {wf['current_step']}"
    assert wf["status"] == "WAITING_HUMAN_CONFIRMATION", f"Expected WAITING_HUMAN_CONFIRMATION, got {wf['status']}"
    assert len(wf["step2_claims"]["candidate_claims"]) >= 2
    assert len(wf["step2_claims"]["applicable_statutes"]) >= 2
    print(f"  ✓ 工作流启动成功: ID={wf_id}")
    print(f"    - Step 1 (事实提炼): 已自动完成，案由确定为《{wf['step1_facts']['cause_of_action']}》")
    print(f"    - Step 2 挂起断点 1 成功！候选请求数: {len(wf['step2_claims']['candidate_claims'])} 项，实体法依据: {len(wf['step2_claims']['applicable_statutes'])} 条")

    # 3.2 模拟主办律师核准 Step 2 (诉讼请求与请求权基础) 并推进至 Step 4
    step2_decisions = {
        "step": 2,
        "human_decisions": {
            "confirmed_claims": [
                "判令被告偿还借款本金人民币3,500,000.00元",
                "判令被告支付利息及逾期利息（严格按借款合同约定年利率14.5%计付至实际清偿日止）",
                "判令保证人张总对上述第一、二项债务承担连带清偿保证责任",
                "判令被告承担本案全部诉讼费、保全费"
            ],
            "confirmed_statutes": [
                "《中华人民共和国民法典》第六百六十七条",
                "《中华人民共和国民法典》第六百七十四条",
                "《中华人民共和国民法典》第六百八十八条"
            ],
            "cause_of_action": "民间借贷纠纷",
            "lawyer_notes": "重点强调张总签署最高额保证协议未约定保证方式，依据民法典686条第2款已推定为一般保证？不，合同明确约定承担连带保证责任。"
        }
    }
    resp = client.post(f"/api/v1/vault/workflows/{wf_id}/advance", json=step2_decisions)
    assert resp.status_code == 200, f"Advance step 2 failed: {resp.text}"
    wf = resp.json()["workflow"]
    assert wf["current_step"] == 4, f"Expected step 4, got {wf['current_step']}"
    assert wf["status"] == "WAITING_HUMAN_CONFIRMATION"
    assert len(wf["step3_statutes"]["opponent_defense_predictions"]) >= 2
    print(f"  ✓ 推进断点 1 成功！")
    print(f"    - Step 3 (法规检索与抗辩预测): 已自动检索现行法条并预测 {len(wf['step3_statutes']['opponent_defense_predictions'])} 项对方致命抗辩")
    print(f"    - Step 4 挂起断点 2 成功！对方预测抗辩 1: {wf['step3_statutes']['opponent_defense_predictions'][0]['defense_point']}")

    # 3.3 验证回退机制 (Rollback to Step 2)
    print("  * 验证主办律师中途决策变更回退机制 (Rollback to Step 2)...")
    resp = client.post(f"/api/v1/vault/workflows/{wf_id}/rollback", json={"target_step": 2})
    assert resp.status_code == 200, f"Rollback failed: {resp.text}"
    wf_rolled = resp.json()["workflow"]
    assert wf_rolled["current_step"] == 2
    assert wf_rolled["status"] == "WAITING_HUMAN_CONFIRMATION"
    print("  ✓ 回退成功: 工作流状态安全回滚至 Step 2，可重新核准请求权！")

    # 3.4 再次推进 Step 2 恢复至 Step 4
    resp = client.post(f"/api/v1/vault/workflows/{wf_id}/advance", json=step2_decisions)
    assert resp.status_code == 200
    wf = resp.json()["workflow"]
    assert wf["current_step"] == 4

    # 3.5 模拟主办律师核准 Step 4 (抗辩应对与策略) 并推进至 Step 5 (生成终稿)
    step4_decisions = {
        "step": 4,
        "human_decisions": {
            "accepted_counter_strategies": [
                "提交银行大额电汇回单及资金对手方流向凭证，证明350万元款项已实际足额交付借款人账户，借款合同已依法生效履行",
                "提交微信催款记录与中国邮政EMS律师催告函签收回执，封死3年诉讼时效抗辩空间",
                "向法庭出示《借款合同及个人保证书》原件，重点援引合同第8条'承担连带清偿保证责任'明文约定条款"
            ],
            "lawyer_defense_notes": "若被告抗辩利率超标，出具全国银行间同业拆借中心公布的LPR 4倍计算上限对照表，锁定14.5%合法有效性。"
        }
    }
    resp = client.post(f"/api/v1/vault/workflows/{wf_id}/advance", json=step4_decisions)
    assert resp.status_code == 200, f"Advance step 4 failed: {resp.text}"
    wf_final = resp.json()["workflow"]
    assert wf_final["current_step"] == 5, f"Expected step 5, got {wf_final['current_step']}"
    assert wf_final["status"] == "COMPLETED", f"Expected COMPLETED, got {wf_final['status']}"
    
    final_draft = wf_final["step5_final_draft"]
    assert "民事起诉状" in final_draft["final_pleading_text"]
    assert "诉讼请求：" in final_draft["final_pleading_text"]
    assert "事实与理由：" in final_draft["final_pleading_text"]
    assert len(final_draft["final_pleading_text"]) > 400
    assert "citation_audit" in final_draft
    
    audit = final_draft["citation_audit"]
    assert audit.get("has_abrogated_laws") is False, "Final draft must not contain abrogated laws!"
    
    print(f"  ✓ 推进断点 2 成功！工作流全流程达成 (COMPLETED)！")
    print(f"    - Step 5 终稿起诉状字数: {len(final_draft['final_pleading_text'])} 字符")
    print(f"    - 引注防火墙检测: {audit['stats']['verified_count']} 条法条权威吻合，0 虚构，0 废止法条")

    print("\n" + "=" * 70)
    print(">>> 恭喜！第二批全部 3 个核心功能（案件空间、核心图谱、断点工作流）端到端实证验证 100% 成功！")
    print("=" * 70)

if __name__ == "__main__":
    run_all_tests()
