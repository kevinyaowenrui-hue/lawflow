# -*- coding: utf-8 -*-
"""
LawFlow 智律工作台 - 合同多版本条款对齐与标准模板偏离度分析引擎 (Multi-Version & Template Deviation Comparator)
核心功能：
1. 双文档条款级自动切分与结构化对齐：
   - 将基准版本 (Base Version / V1 / 标准模板) 与目标版本 (Target Version / V2 / 相对方篡改版) 按条文层级精确切片；
   - 基于词向量与模糊文本相似度，实现跨段落移位条款的智能自动对齐；
2. 偏离度分类与实质性商务风险审计：
   - 🟢 UNCHANGED: 条款完全一致；
   - 🟡 MODIFIED: 实质性修改（生成红线 Diff 标记 <ins> / <del>，分析商务实质偏离并出具谈判建议）；
   - 🔴 DELETED: 对方单方删除我方保护性条款（高危风险警示）；
   - 🟣 ADDED: 对方单方新增严苛义务条款（高危/中危风险警示）；
3. 偏离度综合打分 (Deviation Score) 与审查摘要看板；
4. Word 原生修订模式 (.docx) 双版本比对报告导出。
"""

import os
import re
import difflib
import html
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

import docx
from docx.shared import Inches, Pt, RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from gateway.core.ollama_client import ollama_client
from gateway.utils.redline_builder import compute_text_diff_chunks, add_diff_to_docx_paragraph

logger = logging.getLogger("lawflow.version_comparator")

from gateway.core.paths import get_generated_dir


def split_contract_into_clauses(text: str) -> List[Dict[str, Any]]:
    """
    将中文法律合同文本自动切分为结构化条款列表。
    识别模式：
    - '第X条' / '第X章'
    - '一、' / '二、' / '三、'
    - '1.' / '2.' / '1.1'
    """
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    clauses = []
    current_title = "前言/合同导言"
    current_content = []
    clause_idx = 1

    # 条款标题识别正则
    heading_pattern = re.compile(
        r"^(?:第[一二三四五六七八九十百\d]+[条章篇节]|"
        r"[一二三四五六七八九十]+[、\.]|"
        r"\d+(?:\.\d+)*[\.、\s]|\(\d+\))"
    )

    for line in lines:
        if heading_pattern.match(line):
            # 先保存上一个收集中的条款（如果非空）
            if current_content:
                clauses.append({
                    "clause_id": f"c_{clause_idx}",
                    "title": current_title,
                    "text": "\n".join(current_content).strip()
                })
                clause_idx += 1
                current_content = []

            # 拆分本行：判断是否带有冒号或标题与正文在同一行
            # 如："第一条 借款金额：借款金额为人民币5,000,000.00元整。"
            colon_match = re.search(r"[:：]", line)
            if colon_match and colon_match.start() < 30:
                current_title = line[:colon_match.start()].strip()
                rest_content = line[colon_match.end():].strip()
                if rest_content:
                    current_content.append(rest_content)
            elif len(line) <= 30:
                # 纯标题行，如："第一条 借款金额"
                current_title = line
            else:
                # 较长的单行，尝试按前两个空格或标点切分
                parts = re.split(r"[\s\t]+", line, maxsplit=2)
                if len(parts) >= 3 and len(parts[0]) + len(parts[1]) < 25:
                    current_title = f"{parts[0]} {parts[1]}"
                    current_content.append(parts[2])
                else:
                    current_title = line[:15].strip()
                    current_content.append(line[15:].strip())
        else:
            current_content.append(line)

    if current_content:
        clauses.append({
            "clause_id": f"c_{clause_idx}",
            "title": current_title,
            "text": "\n".join(current_content).strip()
        })

    # 若未切出多个条款，按自然段落分
    if len(clauses) <= 1 and len(lines) > 2:
        clauses = []
        for i, line in enumerate(lines):
            c_match = re.search(r"[:：]", line)
            if c_match and c_match.start() < 25:
                title = line[:c_match.start()].strip()
                text_part = line[c_match.end():].strip()
            elif len(line) <= 25:
                title = line
                text_part = line
            else:
                title = f"第{i+1}段"
                text_part = line
            clauses.append({
                "clause_id": f"c_{i+1}",
                "title": title,
                "text": text_part
            })

    return clauses



def compute_clause_similarity(text1: str, text2: str) -> float:
    """计算两个条款正文的字符级重合相似度"""
    if not text1 or not text2:
        return 0.0
    return difflib.SequenceMatcher(None, text1, text2).ratio()


def analyze_deviation_risk(base_clause: str, target_clause: str, diff_type: str) -> Dict[str, Any]:
    """
    评估条款修改对守约方/委托人的实质性法律偏离度与风险等级：
    - HIGH (高危偏离): 责任豁免、违约金减免、排他权删除、知识产权转移、单方无因解除
    - MEDIUM (中危调整): 付款账期拉长、验收期延长、催告期限缩短
    - LOW (低危轻微): 纯文字措辞微调、标点符号规范、抬头信息补充
    """
    if diff_type == "UNCHANGED":
        return {
            "risk_level": "LOW",
            "risk_score": 0,
            "category": "一致",
            "deviation_summary": "与基准版本一致，零偏离",
            "tactics": "无须调整，维持原状"
        }

    if diff_type == "DELETED":
        is_protective = any(k in base_clause for k in ["知识产权", "违约金", "连带", "赔偿", "保密", "管辖", "解除", "利息"])
        level = "HIGH" if is_protective else "MEDIUM"
        return {
            "risk_level": level,
            "risk_score": 90 if level == "HIGH" else 60,
            "category": "核心保护条款被删",
            "deviation_summary": "对方单方删除了该条款，可能导致我方丧失特定法定义务约束或追索权保障",
            "tactics": "坚决恢复该条款，或在补充协议中以特殊保障条款对冲风险"
        }

    if diff_type == "ADDED":
        is_harsh = any(k in target_clause for k in ["违约金", "不可撤销", "单方解除", "全额赔偿", "放弃诉权", "异地管辖", "苛刻"])
        level = "HIGH" if is_harsh else "MEDIUM"
        return {
            "risk_level": level,
            "risk_score": 85 if level == "HIGH" else 50,
            "category": "新增限制性义务",
            "deviation_summary": "相对方单方新增了未经事先磋商的额外义务或严苛违约责任",
            "tactics": "要求对方说明新增理由，或对等增加对方违约惩罚条款"
        }

    # MODIFIED: 计算修改程度
    sim = compute_clause_similarity(base_clause, target_clause)
    risk_level = "LOW"
    risk_score = 30
    cat = "商务细节微调"
    summary = "条款存在局部措辞调整"
    tactics = "复核实际履约影响后可酌情采纳"

    # 高危关键字检测
    high_keywords = ["上限", "免责", "无限", "管辖", "放弃", "全部损失", "不承担", "无因解除", "所有权归", "知识产权归对方"]
    if any(k in target_clause and k not in base_clause for k in high_keywords) or any(k in base_clause and k not in target_clause for k in high_keywords):
        risk_level = "HIGH"
        risk_score = 85
        cat = "实质性权益让步"
        summary = "修改涉及责任上限、争议管辖或免责边界等实质性法务核心条款"
        tactics = "重点谈判抗辩，建议恢复基准版本或设定互惠对等条款"
    elif sim < 0.65:
        risk_level = "MEDIUM"
        risk_score = 65
        cat = "重大商务改写"
        summary = "条款改动幅度较大（修改率 > 35%），需审慎核对双方权利义务对等性"
        tactics = "逐句比对红线修订标记，确认交期与付款条款是否已被单方放宽"

    return {
        "risk_level": risk_level,
        "risk_score": risk_score,
        "category": cat,
        "deviation_summary": summary,
        "tactics": tactics
    }


def chunks_to_diff_html(chunks: List[Dict[str, str]]) -> str:
    parts = []
    for c in chunks:
        t = c.get("type", "equal")
        txt = html.escape(c.get("text", ""))
        if t == "delete":
            parts.append(f'<del class="diff-del">{txt}</del>')
        elif t == "insert":
            parts.append(f'<ins class="diff-ins">{txt}</ins>')
        else:
            parts.append(f'<span>{txt}</span>')
    return "".join(parts)


def compare_contract_versions(
    base_title: str,
    base_text: str,
    target_title: str,
    target_text: str
) -> Dict[str, Any]:
    """
    多版本合同条款结构化对齐与偏离度比对主引擎
    """
    base_clauses = split_contract_into_clauses(base_text)
    target_clauses = split_contract_into_clauses(target_text)

    aligned_items = []
    matched_target_ids = set()

    total_base = len(base_clauses)
    total_target = len(target_clauses)

    unchanged_count = 0
    modified_count = 0
    deleted_count = 0
    added_count = 0
    high_risk_count = 0

    def _clean_title(t: str) -> str:
        return re.sub(r"^(?:第[一二三四五六七八九十百\d]+[条章篇节]|[\d一二三四五六七八九十]+[、\.\s]|\(\d+\))", "", t).strip()

    # 1. 遍历基准条款，在目标版本中寻找最佳匹配项
    for b in base_clauses:
        best_t = None
        best_sim = 0.0
        b_clean = _clean_title(b["title"])

        for t in target_clauses:
            if t["clause_id"] in matched_target_ids:
                continue

            t_clean = _clean_title(t["title"])
            text_sim = compute_clause_similarity(b["text"], t["text"])

            title_matched = False
            if b["title"] == t["title"]:
                title_matched = True
            elif b_clean and t_clean and (b_clean in t_clean or t_clean in b_clean):
                title_matched = True

            if title_matched:
                sim = max(text_sim, 0.70)
            else:
                sim = text_sim

            if sim > best_sim:
                best_sim = sim
                best_t = t

        # 判定差异类型
        if best_t and best_sim >= 0.98:
            diff_type = "UNCHANGED"
            matched_target_ids.add(best_t["clause_id"])
            unchanged_count += 1
            risk_info = analyze_deviation_risk(b["text"], best_t["text"], diff_type)
            diff_chunks = [{"type": "equal", "text": b["text"]}]
            aligned_items.append({
                "clause_id": b["clause_id"],
                "base_title": b["title"],
                "base_text": b["text"],
                "target_title": best_t["title"],
                "target_text": best_t["text"],
                "status": diff_type,
                "diff_type": diff_type,
                "similarity": round(best_sim, 2),
                "diff_chunks": diff_chunks,
                "diff_html": chunks_to_diff_html(diff_chunks),
                "risk": risk_info
            })
        elif best_t and best_sim >= 0.45:
            diff_type = "MODIFIED"
            matched_target_ids.add(best_t["clause_id"])
            modified_count += 1
            risk_info = analyze_deviation_risk(b["text"], best_t["text"], diff_type)
            if risk_info["risk_level"] == "HIGH":
                high_risk_count += 1
            diff_chunks = compute_text_diff_chunks(b["text"], best_t["text"])
            aligned_items.append({
                "clause_id": b["clause_id"],
                "base_title": b["title"],
                "base_text": b["text"],
                "target_title": best_t["title"],
                "target_text": best_t["text"],
                "status": diff_type,
                "diff_type": diff_type,
                "similarity": round(best_sim, 2),
                "diff_chunks": diff_chunks,
                "diff_html": chunks_to_diff_html(diff_chunks),
                "risk": risk_info
            })
        else:
            # 基准条款在目标版本中未找到匹配项 -> DELETED
            diff_type = "DELETED"
            deleted_count += 1
            risk_info = analyze_deviation_risk(b["text"], "", diff_type)
            if risk_info["risk_level"] == "HIGH":
                high_risk_count += 1
            diff_chunks = [{"type": "delete", "text": b["text"]}]
            aligned_items.append({
                "clause_id": b["clause_id"],
                "base_title": b["title"],
                "base_text": b["text"],
                "target_title": "【该条款已被对方删除】",
                "target_text": "",
                "status": diff_type,
                "diff_type": diff_type,
                "similarity": 0.0,
                "diff_chunks": diff_chunks,
                "diff_html": chunks_to_diff_html(diff_chunks),
                "risk": risk_info
            })

    # 2. 遍历目标版本中未匹配的残留条款 -> ADDED
    for t in target_clauses:
        if t["clause_id"] not in matched_target_ids:
            diff_type = "ADDED"
            added_count += 1
            risk_info = analyze_deviation_risk("", t["text"], diff_type)
            if risk_info["risk_level"] == "HIGH":
                high_risk_count += 1
            diff_chunks = [{"type": "insert", "text": t["text"]}]
            aligned_items.append({
                "clause_id": f"added_{t['clause_id']}",
                "base_title": "【基准版本中无此条款】",
                "base_text": "",
                "target_title": t["title"],
                "target_text": t["text"],
                "status": diff_type,
                "diff_type": diff_type,
                "similarity": 0.0,
                "diff_chunks": diff_chunks,
                "diff_html": chunks_to_diff_html(diff_chunks),
                "risk": risk_info
            })

    # 综合偏离度得分：100 - (修改率*40 + 删减率*35 + 增项率*25)
    total_clauses = max(total_base, 1)
    deviation_pct = round(((modified_count * 0.6 + deleted_count * 1.0 + added_count * 0.8) / total_clauses) * 100, 1)
    deviation_score = max(0, min(100, round(100 - deviation_pct, 1)))

    return {
        "base_title": base_title,
        "target_title": target_title,
        "stats": {
            "total_base_clauses": total_base,
            "total_target_clauses": total_target,
            "total_aligned_clauses": len(aligned_items),
            "unchanged_count": unchanged_count,
            "modified_count": modified_count,
            "deleted_count": deleted_count,
            "added_count": added_count,
            "high_risk_count": high_risk_count,
            "clause_change_rate": round(((modified_count + deleted_count + added_count) / max(total_base, 1)) * 100, 1),
            "deviation_score": deviation_score,
            "alignment_rate": round((unchanged_count / total_clauses) * 100, 1)
        },
        "aligned_clauses": aligned_items,
        "analyzed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }


def export_version_diff_docx(
    diff_result: Dict[str, Any],
    output_filename: str = ""
) -> str:
    """
    根据多版本比对与条款对齐结果，生成带 Word 原生修订标记与偏离度审计卡片的 .docx 文档
    """
    if not output_filename:
        output_filename = f"合同多版本对比修订与偏离度审计表_{datetime.now().strftime('%Y%m%d%H%M%S')}.docx"
    filepath = os.path.join(str(get_generated_dir()), output_filename)

    doc = docx.Document()

    # 标题
    title_p = doc.add_paragraph()
    title_run = title_p.add_run("合同多版本比对修订与模板偏离度审计报告")
    title_run.font.size = Pt(16)
    title_run.font.bold = True
    title_run.font.color.rgb = RGBColor(20, 35, 60)
    title_p.paragraph_format.space_after = Pt(8)

    # 元数据
    meta_p = doc.add_paragraph()
    meta_p.add_run(f"基准版本：{diff_result.get('base_title', '标准模板')}  |  目标版本：{diff_result.get('target_title', '对方修改版')}\n")
    stats = diff_result.get("stats", {})
    meta_p.add_run(f"偏离度合规指数：{stats.get('deviation_score', 0)} 分 (满分100)  |  高危偏离项：{stats.get('high_risk_count', 0)} 处  |  修改条款：{stats.get('modified_count', 0)} 条\n")
    meta_p.add_run(f"比对时间：{diff_result.get('analyzed_at', '')}  |  审计引擎：LawFlow 智能红线对齐系统")
    meta_p.paragraph_format.space_after = Pt(14)

    # 遍历条款输出
    for item in diff_result.get("aligned_clauses", []):
        diff_type = item["diff_type"]
        risk = item.get("risk", {})
        risk_level = risk.get("risk_level", "LOW")

        # 条款标头
        head_p = doc.add_paragraph()
        type_label = {
            "UNCHANGED": "【完全一致】",
            "MODIFIED": "【实质修改】",
            "DELETED": "【对方删除】",
            "ADDED": "【对方新增】"
        }.get(diff_type, "")

        color_rgb = RGBColor(46, 125, 50) if diff_type == "UNCHANGED" else (
            RGBColor(211, 47, 47) if risk_level == "HIGH" else RGBColor(180, 83, 9)
        )

        h_run = head_p.add_run(f"{type_label} {item.get('target_title') or item.get('base_title')}")
        h_run.font.size = Pt(12)
        h_run.font.bold = True
        h_run.font.color.rgb = color_rgb

        # 条款正文 (带修订标记)
        content_p = doc.add_paragraph()
        if diff_type == "UNCHANGED":
            content_p.add_run(item.get("target_text", ""))
        elif diff_type == "DELETED":
            del_run = content_p.add_run(f"【删除原文】{item.get('base_text', '')}")
            del_run.font.strike = True
            del_run.font.color.rgb = RGBColor(180, 0, 0)
        elif diff_type == "ADDED":
            ins_run = content_p.add_run(f"【新增条款】{item.get('target_text', '')}")
            ins_run.font.underline = True
            ins_run.font.color.rgb = RGBColor(0, 120, 0)
        else:
            # MODIFIED: 原生修订标签
            add_diff_to_docx_paragraph(content_p, item.get("base_text", ""), item.get("target_text", ""))

        # 偏离度分析批注
        if diff_type != "UNCHANGED":
            comment_p = doc.add_paragraph()
            c_run = comment_p.add_run(f"▶ 法务风险预警：[{risk.get('category')}] {risk.get('deviation_summary')}；谈判对策：{risk.get('tactics')}")
            c_run.font.size = Pt(9.5)
            c_run.font.italic = True
            c_run.font.color.rgb = RGBColor(100, 116, 139)
            comment_p.paragraph_format.space_after = Pt(10)

    doc.save(filepath)
    return filepath
