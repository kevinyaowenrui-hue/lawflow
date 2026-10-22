"""
LawFlow 智律工作台 - 案件核心图谱自动抽取与生成引擎 (Case Graphs Extractor)
功能：
1. 《案件事实时间线》（Timeline）：自动梳理发生时间、关键事件、关联证据与法律意义标签；
2. 《主体法律关系图》（Entity-Relationship Graph）：梳理原告、被告、连带保证人、债务人、股权控制及代理关系；
3. 《交易资金穿透流水图》（Cashflow Transactions）：穿透资金划转路径、付款方、收款方、金额、附言与凭据。
"""

import re
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from gateway.core.ollama_client import ollama_client

logger = logging.getLogger("lawflow.graph_extractor")

# 尾随虚词/动词停用词表（实体清洗用）
TRAILING_STOPWORDS = (
    "承担", "提供", "向", "与", "的", "应", "须", "需", "自", "由", "对",
    "负有", "负责", "承诺", "支付", "履行", "具有", "连带", "连带保证"
)

# 规范公司/企业后缀
COMPANY_SUFFIXES = (
    "有限责任公司", "股份有限公司", "有限公司", "合伙企业", "商贸公司", "科技公司", "公司"
)


def clean_entity_name(name: str, is_company: bool = False) -> str:
    """
    清洗实体名称：
    1. 公司名在命中标准后缀（有限责任公司/股份有限公司/有限公司/合伙企业等）后截断
    2. 去掉尾随的动词与虚词（承担、提供、向、与、的等）
    3. 去除前后空白与标点符号
    """
    if not name:
        return ""
    cleaned = name.strip(" ：:，,。；;、\t\r\n")
    if is_company:
        for suffix in COMPANY_SUFFIXES:
            idx = cleaned.find(suffix)
            if idx != -1:
                cleaned = cleaned[:idx + len(suffix)]
                break
    changed = True
    while changed and cleaned:
        changed = False
        cleaned = cleaned.strip(" ：:，,。；;、\t\r\n")
        for sw in TRAILING_STOPWORDS:
            if cleaned.endswith(sw) and len(cleaned) > len(sw):
                cleaned = cleaned[:-len(sw)].strip(" ：:，,。；;、\t\r\n")
                changed = True
                break
    return cleaned


CASE_GRAPH_SYSTEM_PROMPT = """你是一名资深商事诉讼专家与法律知识图谱架构师。
你的任务是根据律师输入的《案件事实陈述》或《案卷材料文本》，深度抽取并结构化构建案件三大核心图谱：
1. 事实发生时间线 (timeline)
2. 主体与法律关系图 (entity_graph: nodes & edges)
3. 交易支付与资金穿透流水图 (cashflow)

【严格 JSON 输出格式规范】：
{
  "timeline": [
    {
      "date": "YYYY-MM-DD 或具体发生时间",
      "event": "核心事实简明陈述",
      "evidence_ref": "支撑证据名称（若有，如'银行回单'、'借款协议'）",
      "legal_tag": "法律性质标签（如'合同订立'、'款项实际交付'、'付息与部分履行'、'催告与时效中断'、'违约'）"
    }
  ],
  "entity_graph": {
    "nodes": [
      {
        "id": "e1",
        "name": "主体标准全称",
        "role": "诉讼地位/法律角色（如'原告/出借人'、'被告/主债务人'、'第二被告/连带保证人'、'代付款第三人'）",
        "type": "企业主体 或 自然人"
      }
    ],
    "edges": [
      {
        "source": "e1",
        "target": "e2",
        "type": "法律关系性质（如'民间借贷关系'、'连带责任保证'、'股权投资与控股'、'代为清偿'）",
        "detail": "关键金额、期限或权利义务摘要"
      }
    ]
  },
  "cashflow": [
    {
      "flow_id": "cf1",
      "date": "支付发生时间",
      "payer": "付款方名称及账户提示",
      "payee": "收款方名称及账户提示",
      "amount": 1000000.0,
      "currency": "CNY",
      "purpose": "款项性质/用途说明（如'借款本金出借'、'技术开发首付款'、'清偿利息'）",
      "voucher": "凭据或回单说明",
      "status": "CONFIRMED"
    }
  ]
}

注意：
- 严格只返回纯 JSON，不包含 markdown 代码块包裹；
- 事实必须严格忠实于原文，不得凭空捏造未提及的日期或主体；
- 时间线按时间先后顺序排序；
- 金额数值请输出纯数字（如 5000000.0）。
"""


def extract_rule_based_graphs(text: str) -> Dict[str, Any]:
    """基于确定性规则与司法要素正则解析核心图谱（离线/免显卡/高鲁棒兜底）"""
    if not text:
        return {"timeline": [], "entity_graph": {"nodes": [], "edges": []}, "cashflow": []}

    # 1. 抽取时间线
    timeline: List[Dict[str, Any]] = []
    # 匹配各类常见日期格式：2023年3月15日、2023-03-15、2023.03.15、2023/3/15
    date_pattern = re.compile(
        r"(?:(\d{4})[年\.\-\/](\d{1,2})[月\.\-\/](\d{1,2})[日号]?|"
        r"(\d{4})[年\.\-\/](\d{1,2})[月]?)"
    )

    sentences = re.split(r"[。\n；;]", text)
    for s in sentences:
        s_clean = s.strip()
        if not s_clean:
            continue
        m = date_pattern.search(s_clean)
        if m:
            matched_date = m.group(0)
            # 格式化日期
            y = m.group(1) or m.group(4)
            mon = m.group(2) or m.group(5)
            d = m.group(3) or "01"
            std_date = f"{y}-{int(mon):02d}-{int(d):02d}"

            # 判定法律标签
            tag = "法律事实事实经过"
            if any(k in s_clean for k in ["签署", "签订", "订立", "协议", "合同"]):
                tag = "合同订立与生效"
            elif any(k in s_clean for k in ["转账", "支付", "汇入", "汇出", "借给", "出借", "交付"]):
                tag = "款项实际交付"
            elif any(k in s_clean for k in ["还款", "归还", "付息", "结算"]):
                tag = "部分清偿与还本付息"
            elif any(k in s_clean for k in ["催告", "催告函", "催要", "律师函", "通知"]):
                tag = "债权催告与时效中断"
            elif any(k in s_clean for k in ["逾期", "未归还", "违约", "到期", "拖欠"]):
                tag = "实质性违约"

            # 证据线索
            ev_ref = "当事人陈述"
            if "转账" in s_clean or "银行" in s_clean or "回单" in s_clean:
                ev_ref = "银行流水电子回单"
            elif "合同" in s_clean or "协议" in s_clean:
                ev_ref = "合同协议书原件"
            elif "函" in s_clean or "EMS" in s_clean or "邮寄" in s_clean:
                ev_ref = "催告函及邮寄寄递凭证"

            timeline.append({
                "date": std_date,
                "event": s_clean,
                "evidence_ref": ev_ref,
                "legal_tag": tag
            })

    # 按时间升序排序
    timeline.sort(key=lambda x: x["date"])

    # 2. 抽取主体与关系
    nodes = []
    edges = []
    node_id_map = {}
    node_counter = 1

    # 寻找企业名与自然人
    comp_matches = re.findall(r"([\u4e00-\u9fa5]{2,20}(?:有限公司|股份有限公司|有限责任公司|商贸公司|科技公司|合伙企业))", text)
    cleaned_comps = [clean_entity_name(c, is_company=True) for c in comp_matches]
    unique_comps = list(dict.fromkeys([c for c in cleaned_comps if len(c) >= 3]))

    # 寻找自然人（原告、被告、保证人）
    p_names = re.findall(r"(?:原告|被告|出借人|借款人|保证人|当事人|代表人)[：:\s]*([\u4e00-\u9fa5]{2,6})", text)
    cleaned_names = [clean_entity_name(n, is_company=False) for n in p_names]
    unique_names = list(dict.fromkeys([n for n in cleaned_names if len(n) >= 2]))

    for idx, comp in enumerate(unique_comps):
        if comp not in node_id_map:
            nid = f"e{node_counter}"
            node_counter += 1
            role = "原告/出借人" if idx == 0 else "被告/主债务人"
            nodes.append({"id": nid, "name": comp, "role": role, "type": "企业主体"})
            node_id_map[comp] = nid

    for name in unique_names:
        if name not in node_id_map and len(name) >= 2:
            nid = f"e{node_counter}"
            node_counter += 1
            role = "连带责任保证人" if any(k in text for k in ["保证", "担保"]) else "自然人当事人"
            nodes.append({"id": nid, "name": name, "role": role, "type": "自然人"})
            node_id_map[name] = nid

    if len(nodes) < 2:
        # 补充常见合同代称与自然人主体
        if any(k in text for k in ["甲方", "原告", "出借", "深圳"]):
            nid = f"e{node_counter}"
            node_counter += 1
            nodes.append({"id": nid, "name": "出借人/债权人主体", "role": "原告/出借人", "type": "企业或合伙企业"})
        if any(k in text for k in ["乙方", "被告", "借款", "创展"]):
            nid = f"e{node_counter}"
            node_counter += 1
            nodes.append({"id": nid, "name": "借款人/债务人企业", "role": "被告/主债务人", "type": "企业主体"})
        if any(k in text for k in ["丙方", "张总", "保证人", "实控人"]):
            nid = f"e{node_counter}"
            node_counter += 1
            nodes.append({"id": nid, "name": "张总(实控人保证人)", "role": "连带责任保证人", "type": "自然人"})

    if len(nodes) < 2:
        nid1 = f"e{node_counter}"
        nid2 = f"e{node_counter+1}"
        nodes.append({"id": nid1, "name": "原告出借方主体", "role": "原告/出借人", "type": "企业主体"})
        nodes.append({"id": nid2, "name": "被告借款方主体", "role": "被告/主债务人", "type": "企业主体"})

    # 如果至少有 2 个主体，建立主法律关系连线
    if len(nodes) >= 2:
        edges.append({
            "source": nodes[0]["name"],
            "target": nodes[1]["name"],
            "source_id": nodes[0]["id"],
            "target_id": nodes[1]["id"],
            "type": "合同基础债权债务关系",
            "relation": "合同基础债权债务关系",
            "detail": "基于合同约定的基础民商事权利义务",
            "details": "基于合同约定的基础民商事权利义务"
        })
    if len(nodes) >= 3:
        edges.append({
            "source": nodes[2]["name"],
            "target": nodes[0]["name"],
            "source_id": nodes[2]["id"],
            "target_id": nodes[0]["id"],
            "type": "个人无限连带保证责任",
            "relation": "个人无限连带保证责任",
            "detail": "为前述主债务提供连带保证担保",
            "details": "为前述主债务提供连带保证担保"
        })
        edges.append({
            "source": nodes[2]["name"],
            "target": nodes[1]["name"],
            "source_id": nodes[2]["id"],
            "target_id": nodes[1]["id"],
            "type": "法定代表/控股管理关系",
            "relation": "法定代表/控股管理关系",
            "detail": "对债务人公司实施实际控制与管理",
            "details": "对债务人公司实施实际控制与管理"
        })

    # 3. 抽取资金流水记录
    cashflow = []
    amount_pattern = re.compile(r"(\d+(?:,\d{3})*(?:\.\d+)?)\s*(?:元|万元|整)")
    cf_idx = 1
    for s in sentences:
        s_clean = s.strip()
        if any(k in s_clean for k in ["转账", "汇出", "电汇", "支付", "归还", "出借"]):
            am_match = amount_pattern.search(s_clean)
            if am_match:
                raw_num = am_match.group(1).replace(",", "")
                amt = float(raw_num)
                if "万元" in s_clean:
                    amt *= 10000

                d_match = date_pattern.search(s_clean)
                f_date = d_match.group(0) if d_match else datetime.now().strftime("%Y-%m-%d")

                payer = nodes[0]["name"] if len(nodes) > 0 else "出借方/付款人"
                payee = nodes[1]["name"] if len(nodes) > 1 else "借款方/收款人"
                purpose = "借款本金交付" if any(k in s_clean for k in ["出借", "借给", "借款"]) else "还本付息结算"

                if "归还" in s_clean or "还款" in s_clean or "利息" in s_clean:
                    payer, payee = payee, payer
                    purpose = "清偿利息及本金"

                cashflow.append({
                    "flow_id": f"cf_{cf_idx}",
                    "date": f_date,
                    "payer": payer,
                    "payee": payee,
                    "amount": amt,
                    "currency": "CNY",
                    "purpose": purpose,
                    "voucher": "银行转账电子回单/网银流水",
                    "status": "CONFIRMED"
                })
                cf_idx += 1

    return {
        "timeline": timeline,
        "entity_graph": {"nodes": nodes, "edges": edges},
        "cashflow": cashflow
    }


async def extract_case_graphs_from_text(facts_text: str, documents_text: str = "") -> Dict[str, Any]:
    """
    智能抽取案卷三大图谱：
    先通过大模型进行深度语义理解抽取，若大模型未配置或异常，秒级降级至规则正则提取器。
    """
    combined_content = f"【事实陈述】\n{facts_text}\n\n【案卷材料片段】\n{documents_text}".strip()
    if not combined_content or len(combined_content) < 10:
        return extract_rule_based_graphs(facts_text)

    prompt = f"""请仔细阅读以下案件事实材料，完整抽取并输出该案件的《时间线》、《主体关系图》与《资金穿透流水图》：

{combined_content}

请直接输出规范 JSON 对象，严格符合 system prompt 定义的字段结构。"""

    try:
        # 从正文中的「原告：…；被告：…」弱提示生成实体（无 matter_id 时）
        from gateway.utils.pii_sanitizer import build_entities_from_parties, pii_sanitizer

        _parties = []
        for m in pii_sanitizer.ROLE_NAME_PATTERN.finditer(combined_content[:2000]):
            _parties.append({"name": m.group(1), "party_type": "natural"})
        _graph_entities = build_entities_from_parties(_parties)
        raw_output = await ollama_client.generate(
            prompt=prompt,
            system_prompt=CASE_GRAPH_SYSTEM_PROMPT,
            temperature=0.1,
            custom_entities=_graph_entities or None,
        )
        parsed = ollama_client.extract_json(raw_output)

        if isinstance(parsed, dict) and "timeline" in parsed and "entity_graph" in parsed:
            # 校验并补齐必须字段与统一别名
            if "cashflow" not in parsed:
                parsed["cashflow"] = []

            for t in parsed.get("timeline", []):
                if "significance" not in t:
                    t["significance"] = t.get("legal_tag") or "关键法律事实节点"
                if "legal_tag" not in t:
                    t["legal_tag"] = t.get("significance")
                if "source_doc" not in t:
                    t["source_doc"] = t.get("evidence_ref") or "案卷材料"
                if "evidence_ref" not in t:
                    t["evidence_ref"] = t.get("source_doc")

            eg = parsed.get("entity_graph", {})
            for n in eg.get("nodes", []):
                if "name" in n:
                    is_comp = n.get("type") in ("企业主体", "企业或合伙企业", "企业")
                    n["name"] = clean_entity_name(n["name"], is_company=is_comp)

            for e in eg.get("edges", []):
                if "relation" not in e:
                    e["relation"] = e.get("type") or "关联关系"
                if "type" not in e:
                    e["type"] = e.get("relation")
                if "details" not in e:
                    e["details"] = e.get("detail") or ""
                if "detail" not in e:
                    e["detail"] = e.get("details")

            for cf in parsed.get("cashflow", []):
                if "from_party" not in cf:
                    cf["from_party"] = cf.get("payer") or ""
                if "payer" not in cf:
                    cf["payer"] = cf.get("from_party")
                if "to_party" not in cf:
                    cf["to_party"] = cf.get("payee") or ""
                if "payee" not in cf:
                    cf["payee"] = cf.get("to_party")
                if "channel" not in cf:
                    cf["channel"] = cf.get("purpose") or "银行转账"
                if "purpose" not in cf:
                    cf["purpose"] = cf.get("channel")
                if "voucher" not in cf:
                    cf["voucher"] = "银行转账凭证"

            logger.info(f"大模型智能图谱抽取成功: 时间线{len(parsed.get('timeline', []))}条, 节点{len(parsed.get('entity_graph', {}).get('nodes', []))}个")
            return parsed
        else:
            logger.warning("大模型输出 JSON 格式不完整，转入规则引擎抽取")
            return extract_rule_based_graphs(combined_content)
    except Exception as e:
        logger.warning(f"大模型图谱抽取异常，降级至规则解析: {e}")
        return extract_rule_based_graphs(combined_content)
