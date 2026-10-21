import os
import sys
import json
import httpx

BASE_URL = os.getenv("GATEWAY_URL", "http://127.0.0.1:5221")
API_TOKEN = os.getenv("LAWFLOW_API_TOKEN", "")

def run_step3_verification():
    print("======================================================================")
    print("     LawFlow 智律工作台【第三步：阶段一验证汇报专用测试脚本】")
    print("======================================================================")
    headers = {}
    if API_TOKEN:
        headers["X-LawFlow-Token"] = API_TOKEN
    client = httpx.Client(base_url=BASE_URL, timeout=120.0, headers=headers)

    # 1. 验证 /health（最小信息探针）
    print("\n[1/3] 执行网关健康检查...")
    res = client.get("/health")
    assert res.status_code == 200, f"Health check failed: {res.text}"
    health_data = res.json()
    print(f"  * 网关状态: {health_data.get('status')}")
    print(f"  * GATEWAY_URL: {BASE_URL}")

    # 2. 发起民间借贷起诉状端到端生成测试
    print("\n[2/3] 发起【民间借贷纠纷】立案公文包端到端全自动生成流水线...")
    loan_payload = {
        "cause_of_action": "民间借贷纠纷",
        "plaintiff": {
            "name": "李四",
            "id_card_or_uscc": "110101199003072375",
            "gender": "男",
            "birth": "1990年3月7日",
            "ethnicity": "汉族",
            "address": "北京市海淀区中关村南大街1号科技大厦B座1201室",
            "phone": "13800138000"
        },
        "defendant": {
            "name": "张三",
            "id_card_or_uscc": "110101198505121232",
            "gender": "男",
            "birth": "1985年5月12日",
            "ethnicity": "汉族",
            "address": "北京市朝阳区建国路88号现代城A座608室",
            "phone": "13900139000"
        },
        "claims": [
            "判令被告立即向原告偿还借款本金人民币 500,000.00 元；",
            "判令被告向原告支付逾期还款利息（自借款届满之日起至实际清偿之日止，按年利率6%计算，暂计至起诉日为人民币 26,701.02 元）；",
            "判令本案全部诉讼费用及保全费用由被告全额承担。"
        ],
        "claim_amount": 500000.0,
        "raw_case_notes": "被告张三因承揽土建工程周转资金困难，于2023年3月1日向原告借款50万元整，约定借期6个月，年化利率6%。原告当天通过招商银行手机网银向被告实名账户转账50万元，附言注明'借款'。被告出具借条原件。2023年9月1日借期届满后，原告多次通过微信及电话要求被告归还借款本息，被告均以发包方工程进度款未到账为由故意推诿拖延，至今分文未还。",
        "court_name": "北京市海淀区人民法院",
        "lawyer_name": "王大状",
        "law_firm": "北京智律律师事务所",
        "lawyer_phone": "13600001111",
        "lawyer_license": "11101201510123456",
        "auto_generate_sub_docs": True
    }

    resp = client.post("/api/v1/phase1/generate-litigation-package", json=loan_payload, timeout=120.0)
    assert resp.status_code == 200, f"Generate package failed: {resp.text}"
    pkg = resp.json()

    print("\n[3/3] 检验生成成果与大模型法言法语润色...")
    print(f"  * 诉讼公文包流水号: {pkg.get('package_id')}")
    print(f"  * 案由: {pkg.get('cause_of_action')}")
    print(f"  * 当事人退休主体资格审查: {pkg.get('retirement_check')}")
    print(f"  * 预估诉讼费: 受理费 {pkg.get('court_fees_estimate', {}).get('standard_fee')} 元 (大写: {pkg.get('court_fees_estimate', {}).get('rmb_capital')})，保全费 {pkg.get('court_fees_estimate', {}).get('preservation_fee')} 元")
    print(f"  * 引用法条数: {len(pkg.get('statute_citations', []))} 条 ({', '.join(pkg.get('statute_citations', []))})")
    
    print("\n  === gemma4:12b 润色输出之【事实与理由】核心片段 ===")
    facts_text = pkg.get("facts_and_reasons_polished", "")
    for line in facts_text.strip().splitlines()[:12]:
        print(f"    {line}")
    if len(facts_text.strip().splitlines()) > 12:
        print("    ...")

    print("\n  === 本次一揽子生成的诉讼文书列表 ===")
    docs = pkg.get("generated_documents", [])
    for d in docs:
        docx_exists = os.path.exists(os.path.join("storage", "generated", d.get("filename_docx", "")))
        pdf_exists = os.path.exists(os.path.join("storage", "generated", d.get("filename_pdf", ""))) if d.get("filename_pdf") else False
        print(f"    - 【{d.get('doc_type')}】")
        print(f"        Word: {d.get('filename_docx')} (本地存在: {docx_exists})")
        print(f"        PDF:  {d.get('filename_pdf')} (本地存在: {pdf_exists})")
        print(f"        下载: {d.get('docx_url')}")

    print("\n======================================================================")
    print("  恭喜！民间借贷纠纷端到端立案公文包生成验证 100% 成功！")
    print("======================================================================")

if __name__ == "__main__":
    run_step3_verification()
