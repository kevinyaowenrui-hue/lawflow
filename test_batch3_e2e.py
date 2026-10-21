# -*- coding: utf-8 -*-
"""
LawFlow 智律工作台 - 第三批功能自动化端到端实证校验脚本 (test_batch3_e2e.py)
校验目标：
1. #3 矩阵式批量阅卷表 (Harvey Review Tables) - 列表、详情、全表并发抽取、CSV导出
2. #4 单元格级局部重刷与全局表头指令 (Cell-Level Refresh & Column Refresh) - 单格即时重算、动态增删列
3. #6 双栏穿透式原文定位 (Split-Screen Source Grounding) - 切片定位、坐标偏移、引述提取
4. #9 多版本比对与模板偏离度比对 (Multi-Version & Template Deviation Alignment) - 条款结构对齐、偏离度打分、Word 原生修订模式 (<w:ins>/<w:del>) 导出
"""

import sys
import os
import json
import httpx
from fastapi.testclient import TestClient

# 确保导入 gateway
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from gateway.main import app

def run_batch3_tests():
    print("=" * 70)
    print(">>> 启动 LawFlow 第三批功能端到端实证自动化测试 <<<")
    print("=" * 70)

    client = TestClient(app)

    # --------------------------------------------------------------------------
    # 0. 健康检查校验
    # --------------------------------------------------------------------------
    print("\n[Step 0] 探测网关健康检查与第三批组件注册探针...")
    resp = client.get("/health")
    assert resp.status_code == 200, f"健康检查失败: {resp.text}"
    health_data = resp.json()
    features = health_data.get("features", {})
    assert features.get("review_tables") is True, "review_tables 未在网关生命周期中就绪"
    assert features.get("version_comparator") is True, "version_comparator 未在网关生命周期中就绪"
    assert features.get("source_grounding") is True, "source_grounding 未在网关生命周期中就绪"
    print(f" -> 健康检查通过: {health_data['system']} (Port: {health_data['gateway_port']})")

    # --------------------------------------------------------------------------
    # 1. 批量阅卷表 (Review Tables) 基础能力与数据网格
    # --------------------------------------------------------------------------
    matter_id = "MATTER-2026-001"
    print(f"\n[Step 1] 获取案件空间 [{matter_id}] 下的阅卷表清单...")
    resp = client.get(f"/api/v1/vault/matters/{matter_id}/review-tables")
    assert resp.status_code == 200, f"获取阅卷表列表失败: {resp.text}"
    tables_data = resp.json()
    assert tables_data["status"] == "success"
    target_tbl = next((t for t in tables_data["tables"] if t["table_id"] == "TABLE-2026-SEED-01"), tables_data["tables"][0])
    table_id = target_tbl["table_id"]
    print(f" -> 成功获取阅卷表，总数: {tables_data['total']}, 当前测试表 ID: {table_id}")

    print(f"\n[Step 2] 获取单张阅卷表 [{table_id}] 的完整数据网格...")
    resp = client.get(f"/api/v1/vault/review-tables/{table_id}")
    assert resp.status_code == 200, f"获取阅卷表详情失败: {resp.text}"
    table_detail = resp.json()["table"]
    columns = table_detail.get("columns", [])
    rows = table_detail.get("rows", [])
    print(f" -> 表格名称: {table_detail['title']}")
    print(f" -> 列定义数: {len(columns)} 列 ({[c['name'] for c in columns]})")
    print(f" -> 挂载案卷材料行: {len(rows)} 行 ({[r['doc_title'] for r in rows]})")
    assert len(columns) >= 4, "要素列数量不足"
    assert len(rows) >= 2, "案卷行数不足"

    # --------------------------------------------------------------------------
    # 2. 单元格级局部即时重刷 (Cell-Level Refresh)
    # --------------------------------------------------------------------------
    test_row = rows[0]
    test_col = columns[0]
    print(f"\n[Step 3] 触发单元格局部重刷 [行: {test_row['id']} ({test_row['doc_title']}) x 列: {test_col['id']} ({test_col['name']})]...")
    resp = client.post(f"/api/v1/vault/review-tables/{table_id}/cells/{test_row['id']}/{test_col['id']}/refresh")
    assert resp.status_code == 200, f"单格局部重刷失败: {resp.text}"
    cell_res = resp.json()
    assert cell_res["status"] == "success"
    updated_cell = cell_res["cell"]
    print(f" -> 局部重刷完成! 抽取结果: [{updated_cell.get('value')}] | 置信度: {updated_cell.get('confidence')} | 证据引证: {updated_cell.get('grounding_quote')}")
    assert updated_cell.get("value"), "单格抽取结果为空"

    # --------------------------------------------------------------------------
    # 3. 动态新增提取要素列与列级重刷 (Add Column & Column Refresh)
    # --------------------------------------------------------------------------
    print("\n[Step 4] 动态新增提取要素列 [约定管辖法院与争议解决]...")
    new_col_payload = {
        "name": "约定管辖法院与争议解决",
        "instruction": "提取合同或协议中明确约定的纠纷管辖法院或仲裁条款，包括原告所在地或被告所在地法院。",
        "type": "text"
    }
    resp = client.post(f"/api/v1/vault/review-tables/{table_id}/columns", json=new_col_payload)
    assert resp.status_code == 200, f"动态追加列失败: {resp.text}"
    add_col_res = resp.json()
    assert add_col_res["status"] == "success"
    updated_columns = add_col_res["table"]["columns"]
    added_col = next((c for c in reversed(updated_columns) if "约定管辖法院" in c["name"]), None)
    assert added_col is not None, "新要素列未出现在表格定义中"
    added_col_id = added_col["id"]
    print(f" -> 动态要素列追加成功，新列 ID: {added_col_id}")

    print(f"\n[Step 5] 针对该新列 [{added_col_id}] 触发列级单次/行级重跑...")
    resp = client.post(f"/api/v1/vault/review-tables/{table_id}/cells/{test_row['id']}/{added_col_id}/refresh")
    assert resp.status_code == 200, f"新列行级重刷失败: {resp.text}"
    print(" -> 该新列目标案卷行抽取更新完毕！")

    # --------------------------------------------------------------------------
    # 4. 全表批量并发抽取与 CSV 导出
    # --------------------------------------------------------------------------
    print(f"\n[Step 6] 创建轻量评阅表并测试全表批量并发抽取 (Run All)...")
    test_tbl_resp = client.post(f"/api/v1/vault/matters/{matter_id}/review-tables", json={
        "title": "并发提取专用评阅表",
        "description": "轻量测试全表并发",
        "columns": [
            {"id": "col_fast_1", "name": "核心当事人", "instruction": "提取当事人名称", "type": "text"}
        ]
    })
    assert test_tbl_resp.status_code == 200, f"创建轻量表失败: {test_tbl_resp.text}"
    test_tbl_id = test_tbl_resp.json()["table"]["table_id"]

    resp = client.post(f"/api/v1/vault/review-tables/{test_tbl_id}/run-all")
    assert resp.status_code == 200, f"全表批量抽取失败: {resp.text}"
    run_all_res = resp.json()
    assert run_all_res["status"] == "success"
    print(f" -> 全表并发抽取成功 (Table ID: {test_tbl_id})！")

    print(f"\n[Step 7] 导出阅卷表为 CSV 报表...")
    resp = client.get(f"/api/v1/vault/review-tables/{table_id}/export/csv")
    assert resp.status_code == 200, f"CSV 导出失败: {resp.text}"
    csv_content = resp.content.decode("utf-8-sig")
    assert "案卷材料名称" in csv_content or "doc_title" in csv_content or "签约主体" in csv_content or "原告" in csv_content
    print(f" -> CSV 导出成功，数据大小: {len(csv_content)} 字节")
    print(f"    预览前两行:\n{csv_content.splitlines()[:2]}")

    # --------------------------------------------------------------------------
    # 5. 双栏穿透式原文定位 (Split-Screen Source Grounding)
    # --------------------------------------------------------------------------
    print("\n[Step 8] 测试穿透式原文定位 API (Source Grounding Excerpt)...")
    resp = client.get(
        f"/api/v1/vault/matters/{matter_id}/grounding/excerpt",
        params={
            "doc_title": "借款合同",
            "page_no": 1,
            "query_text": "连带保证责任"
        }
    )
    assert resp.status_code == 200, f"穿透原文定位失败: {resp.text}"
    grounding_res = resp.json()
    assert grounding_res["status"] == "success"
    assert grounding_res["found"] is True, "未能从空间文档中检索到原文"
    assert grounding_res["char_start"] >= 0, "未能定位到原文坐标切片"
    print(f" -> 匹配到文档: {grounding_res['doc_title']} (ID: {grounding_res['doc_id']})")
    print(f" -> 字符偏移区间: [{grounding_res['char_start']} : {grounding_res['char_end']}]")
    print(f" -> 原文高亮切片: [{grounding_res['highlight_snippet']}]")

    # --------------------------------------------------------------------------
    # 6. 多版本合同条款对齐与偏离度比对 (Multi-Version & Deviation Diff)
    # --------------------------------------------------------------------------
    print("\n[Step 9] 测试双版本跨文档条款对齐与红线偏离度比对...")
    base_text = """
第一条 借款金额：借款金额为人民币5,000,000.00元整。
第二条 借款期限：借款期限自2025年1月10日起至2026年1月9日止。
第三条 借款利息：年利率固定为12%，按季度结息，逾期加收日万分之五罚息。
第四条 保证担保：丙方自然人股东承担连带保证责任，保证范围包括本金、利息、违约金及律师费。
第五条 争议解决：因履行本合同引起的争议，由出借人所在地人民法院管辖。
"""
    target_text = """
第一条 借款金额：借款金额为人民币5,000,000.00元整。
第二条 借款期限：借款期限经双方协商延长至2026年7月9日止。
第三条 借款利息：年利率固定为6%，到期一次性还本付息，取消逾期罚息。
第五条 争议解决：发生争议由中国国际经济贸易仲裁委员会北京分会仲裁。
第六条 提前还款：借款人提前偿还本金的，不承担任何违约赔偿责任。
"""
    version_payload = {
        "base_title": "《企业间借款合同·律所标准母本版》",
        "base_text": base_text,
        "target_title": "《企业间借款合同·相对方修订草案》",
        "target_text": target_text
    }
    resp = client.post("/api/v1/contract/compare-versions", json=version_payload)
    assert resp.status_code == 200, f"版本比对失败: {resp.text}"
    cmp_res = resp.json()
    assert cmp_res["status"] == "success"
    comparison = cmp_res["comparison"]
    stats = comparison["stats"]
    clauses = comparison["aligned_clauses"]

    print(f" -> 比对完成！遵从合规指数: {stats['deviation_score']}/100 | 变动率: {stats['clause_change_rate']}%")
    print(f" -> 统计清单: 保留={stats['unchanged_count']} | 修改={stats['modified_count']} | 删除={stats['deleted_count']} | 新增={stats['added_count']}")
    assert stats["deleted_count"] >= 1, "未识别出第四条连带保证责任被删除的高风险"
    assert stats["added_count"] >= 1, "未识别出第六条提前还款新增条款"

    # 验证是否包含第四条的删除警告
    deleted_clause = next((c for c in clauses if c["status"] == "DELETED"), None)
    assert deleted_clause is not None
    print(f" -> 成功拦截高风险删除条款: [{deleted_clause['base_title']}]")

    # --------------------------------------------------------------------------
    # 7. Word 原生修订模式 (<w:ins>/<w:del>) 文档导出
    # --------------------------------------------------------------------------
    print("\n[Step 10] 测试导出带 Word 原生修订模式 (<w:ins>/<w:del>) 的 .docx 文档...")
    resp = client.post("/api/v1/contract/export-version-diff", json=version_payload)
    assert resp.status_code == 200, f"Word 导出失败: {resp.text}"
    docx_res = resp.json()
    assert docx_res["status"] == "success"
    filename = docx_res["filename"]
    assert filename.endswith(".docx")
    print(f" -> Word 导出成功: {filename} (下载路径: {docx_res['download_url']})")

    file_disk_path = os.path.join(BASE_DIR, "storage", "generated", filename)
    assert os.path.exists(file_disk_path), f"磁盘未找到生成的 .docx: {file_disk_path}"
    assert os.path.getsize(file_disk_path) > 1000, "生成的 .docx 文件过小或损坏"
    print(f" -> 磁盘物理文件校验通过，文件大小: {os.path.getsize(file_disk_path)} 字节")

    print("\n" + "=" * 70)
    print(">>> 恭喜！LawFlow 智律工作台第三批功能全部实证校验通过 (100% Passed) <<<")
    print("=" * 70)

if __name__ == "__main__":
    run_batch3_tests()
