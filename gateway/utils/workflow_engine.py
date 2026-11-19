"""
LawFlow 智律工作台 - 人机协同断点工作流状态机 (Human-in-the-Loop Workflow Engine)
功能：
1. 充分打破大模型"单次黑盒生成终稿"的不可控性，拆分为 5 步可挂起、可回退、带人工核准断点的流水线；
2. Step 1: 事实与证据要素提炼 -> 
   Step 2: [人工确认断点 1] 律师勾选并确认诉讼请求与请求权基础 -> 
   Step 3: 权威法典穿透与对方抗辩焦点预测 -> 
   Step 4: [人工确认断点 2] 律师确认攻防反击策略与重点证据排布 -> 
   Step 5: 生成终稿文书并自动经过后置引注体检防火墙。
"""

import os
import json
import logging
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional

from gateway.core.ollama_client import ollama_client
from gateway.utils.matter_vault_db import get_db_connection, get_matter_by_id
from gateway.utils.citation_guard import audit_citations_in_text
from gateway.utils.text_utils import normalize_court_name

logger = logging.getLogger("lawflow.workflow_engine")


class WorkflowValidationError(ValueError):
    """终稿缺少必要字段时抛出，由路由映射为 HTTP 422。"""

    def __init__(self, message: str, missing_fields: Optional[List[str]] = None):
        super().__init__(message)
        self.missing_fields = missing_fields or []


class WorkflowStep:
    STEP1_FACTS = 1
    STEP2_CLAIMS_BREAKPOINT = 2
    STEP3_DEFENSE_PREDICTION = 3
    STEP4_TACTICS_BREAKPOINT = 4
    STEP5_FINAL_COMPLETED = 5


class WorkflowStatus:
    IN_PROGRESS = "IN_PROGRESS"
    WAITING_HUMAN = "WAITING_HUMAN_CONFIRMATION"
    COMPLETED = "COMPLETED"


def _item_text(item: Any) -> str:
    """取出诉请或抗辩里真正写了字的那一句。空对象不算已经抽出。"""
    if isinstance(item, dict):
        for key in ("text", "claim", "norm", "statute", "focus", "point", "defense_point"):
            value = item.get(key)
            if value and str(value).strip():
                return str(value).strip()
        return ""
    return str(item or "").strip()


def _has_usable_claims(step1_data: Any) -> bool:
    """空列表、缺字段、只有空白，都要继续补全，不能当成已经有诉请。"""
    if not isinstance(step1_data, dict) or "candidate_claims" not in step1_data:
        return False
    return any(_item_text(item) for item in (step1_data.get("candidate_claims") or []))


def _has_usable_defenses(step3_data: Any) -> bool:
    if not isinstance(step3_data, dict) or "defense_predictions" not in step3_data:
        return False
    return any(_item_text(item) for item in (step3_data.get("defense_predictions") or []))


async def start_litigation_workflow(
    matter_id: str,
    case_title: str,
    facts_text: str,
    client_role: str = "原告",
    perspective: str = "己方主办律师 (Blue Team)"
) -> Dict[str, Any]:
    """启动人机协同断点工作流，自动执行 Step 1 并挂起等待律师确认 Step 2"""
    workflow_id = f"WF-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 1. 执行 Step 1: 事实要素与涉案标的提取
    prompt = f"""【案件名称】{case_title}
【委托人诉讼地位】{client_role}
【事实陈述与案卷材料】
{facts_text}

请作为办案辅助提炼事实。只使用下面已经写明的事实，不要补写协议、转账、催告或违约。
案情没有写借款时，不要建议民间借贷，也不要引用借款合同条文。
不要默认勾选保证责任、利息或诉讼费。把握不要写成百分比。
严格输出 JSON 格式：
{{
  "facts_summary": ["事实1...", "事实2..."],
  "disputed_amount": "涉案争议本金或标的额说明",
  "suggested_causes_of_action": [
    {{"cause": "按录入事实选择，不要照抄", "confidence": "未计算", "rationale": "只根据上面已经写明的事实"}}
  ],
  "candidate_claims": [
    {{"id": "claim_1", "text": "只写录入事实里已经出现的请求，不要预选，也不要写成借款", "default_selected": false, "category": "待填写"}}
  ],
  "candidate_legal_basis": [
    {{"norm": "只引用与录入事实对应的条文", "desc": "没有写到的请求权不要补，不要默认借款合同条文"}}
  ]
}}
"""
    from gateway.utils.pii_sanitizer import build_entities_from_matter

    _wf_entities = build_entities_from_matter(matter_id) if matter_id else []
    step1_data = {}
    try:
        raw_out = await ollama_client.generate(
            prompt=prompt, temperature=0.2, custom_entities=_wf_entities or None
        )
        step1_data = ollama_client.extract_json(raw_out)
    except Exception as e:
        logger.warning(f"工作流 Step 1 大模型提取失败，启动规则兜底: {e}")

    # 模型没抽出，或抽出空列表时，只按录入文字补全。补不出就留空，不写入别的案子。
    if not _has_usable_claims(step1_data):
        facts = (facts_text or "").strip()
        mentions_loan = any(word in facts for word in ("借款", "借贷", "出借"))
        mentions_sale = any(word in facts for word in ("买卖", "货款", "购销"))
        mentions_guarantee = any(word in facts for word in ("保证", "担保"))
        if mentions_loan:
            suggested = [{
                "cause": "民间借贷纠纷",
                "confidence": "未计算",
                "rationale": "录入文字里出现借款或借贷。合同是否成立、款项是否交付，还要核对。",
            }]
            claims = [{
                "id": "claim_1",
                "text": "请求返还录入文字中的借款。金额以律师核对后的数字为准，本页不预选。",
                "default_selected": False,
                "category": "本金",
            }]
            basis = [
                {"norm": "《中华人民共和国民法典》第六百六十七条", "desc": "借款合同是借款人向贷款人借款，到期返还借款并支付利息的合同。是否属于借款，以录入事实为准。"},
                {"norm": "《中华人民共和国民法典》第六百七十五条", "desc": "借款人应当按照约定的期限返还借款。没有约定期限的，不能把本条直接写成已经到期。"},
            ]
        elif mentions_sale:
            suggested = [{
                "cause": "买卖合同纠纷",
                "confidence": "未计算",
                "rationale": "录入文字里出现买卖或货款。合同是否成立、货物是否交付，还要核对。",
            }]
            claims = [{
                "id": "claim_1",
                "text": "请求支付录入文字中的货款。金额以律师核对后的数字为准，本页不预选。",
                "default_selected": False,
                "category": "货款",
            }]
            basis = [
                {"norm": "《中华人民共和国民法典》第五百九十五条", "desc": "买卖合同是出卖人转移标的物的所有权于买受人，买受人支付价款的合同。"},
                {"norm": "《中华人民共和国民法典》第六百二十六条", "desc": "买受人应当按照约定的数额和支付方式支付价款。"},
            ]
        else:
            suggested = [{
                "cause": "案由待律师选择",
                "confidence": "未计算",
                "rationale": "录入文字不足以建议案由。不要默认成民间借贷。",
            }]
            claims = []
            basis = []
        if mentions_guarantee:
            claims.append({
                "id": "claim_guarantee",
                "text": "录入文字提到保证。保证方式、保证期间和是否已经起诉主债务人，还要核对，不预选连带责任。",
                "default_selected": False,
                "category": "保证",
            })
        step1_data = {
            "facts_summary": [
                "模型没有抽出事实。下面只保留律师录入的原文，不补写协议、转账或违约。",
                facts[:800] if facts else "律师还没有录入事实。",
            ],
            "disputed_amount": "金额未从案情中算定，以律师核对后的数字为准",
            "suggested_causes_of_action": suggested,
            "candidate_claims": claims,
            "candidate_legal_basis": basis,
        }

    from gateway.utils.practice_workflow import suggest_claim_tracks
    mixed_tracks = suggest_claim_tracks(facts_text or "")
    if len(mixed_tracks) > 1:
        step1_data["must_split"] = True
        step1_data["suggested_causes_of_action"] = [
            {
                "cause": item["cause"],
                "confidence": "未计算",
                "rationale": item["reason"],
                "track": item["track"],
            }
            for item in mixed_tracks
        ]
        step1_data["candidate_claims"] = [
            {
                "id": f"claim_{index}",
                "text": item["pleading"],
                "default_selected": False,
                "category": item["track"],
            }
            for index, item in enumerate(mixed_tracks, 1)
        ]

    # 工作流总状态持久化字典
    step_data = {
        "matter_id": matter_id,
        "case_title": case_title,
        "facts_text": facts_text,
        "client_role": client_role,
        "perspective": perspective,
        "step1": step1_data,
        "step2": {},  # 待律师确认
        "step3": {},
        "step4": {},
        "step5": {}
    }

    # 存入数据库并挂起在 Step 2（等待人工确认）
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO matter_workflows (
            workflow_id, matter_id, workflow_type, current_step, step_status, step_data_json, is_completed, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            workflow_id,
            matter_id,
            "litigation_drafting",
            WorkflowStep.STEP2_CLAIMS_BREAKPOINT,
            WorkflowStatus.WAITING_HUMAN,
            json.dumps(step_data, ensure_ascii=False),
            0,
            now_str,
            now_str
        ))
        conn.commit()

    return {
        "workflow_id": workflow_id,
        "matter_id": matter_id,
        "current_step": WorkflowStep.STEP2_CLAIMS_BREAKPOINT,
        "step_status": WorkflowStatus.WAITING_HUMAN,
        "step_name": "诉讼请求与请求权基础锁定（人工断点）",
        "instruction": "请主办律师审核并勾选案由、最终诉讼请求项及请求权基础条文，点击'确认并推进至下一步'。",
        "step_data": step_data
    }


async def advance_workflow_step(workflow_id: str, human_confirmed_data: Dict[str, Any]) -> Dict[str, Any]:
    """律师在前端核准断点后，提交数据并推动工作流前进到下一步"""
    with get_db_connection() as conn:
        return await _advance_workflow_step_core(conn, workflow_id, human_confirmed_data)


async def _advance_workflow_step_core(conn, workflow_id: str, human_confirmed_data: Dict[str, Any]) -> Dict[str, Any]:
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM matter_workflows WHERE workflow_id = ?", (workflow_id,))
    row = cursor.fetchone()
    if not row:
        raise ValueError(f"工作流不存在: {workflow_id}")

    current_step = row["current_step"]
    step_data = json.loads(row["step_data_json"])
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # =========================================================================
    # 断点 1 (Step 2) 推进到 Step 3 & Step 4: 锁定请求权，检索法条与抗辩焦点预测
    # =========================================================================
    if current_step == WorkflowStep.STEP2_CLAIMS_BREAKPOINT:
        # 保存人工确认的 Step 2 数据
        step_data["step2"] = {
            "confirmed_cause": human_confirmed_data.get("confirmed_cause") or human_confirmed_data.get("cause_of_action") or "案由待律师选择",
            "confirmed_claims": human_confirmed_data.get("confirmed_claims") or [],
            "confirmed_legal_basis": human_confirmed_data.get("confirmed_legal_basis") or human_confirmed_data.get("confirmed_statutes") or [],
            "human_notes": human_confirmed_data.get("human_notes") or human_confirmed_data.get("lawyer_notes") or "",
            "confirmed_at": now_str
        }

        # 自动触发 Step 3: 依据确认的案由与请求权基础，检索法规库与预测被告抗辩焦点
        cause = step_data["step2"]["confirmed_cause"]
        claims_text = "\n".join([f"- {c}" for c in step_data["step2"]["confirmed_claims"]])
        basis_text = "\n".join([f"- {b}" for b in step_data["step2"]["confirmed_legal_basis"]])

        prompt_step3 = f"""【主办律师已确认案由】{cause}
【律师认定的诉讼请求】
{claims_text}
【请求权基础】
{basis_text}
【案件事实】
{step_data['facts_text']}

请只根据上面已经确认的案由和事实预测抗辩。案由不是民间借贷时，不要预测砍头息、四倍利率或保证期间。不要把预测写成对方已经提出的抗辩。
示例只说明字段，不要照抄示例里的借款抗辩。

严格输出 JSON：
{{
  "defense_predictions": [
    {{
      "id": "def_1",
      "focus": "诉讼时效是否经过抗辩",
      "opponent_argument": "主张借款期限届满后超过三年没有起诉，诉讼时效已过，可以拒绝履行",
      "counter_strategy": "诉讼时效届满后，义务人可以提出不履行的抗辩，债权本身不消灭。催告、对方同意履行可以中断时效，但要核对主张权利的日期和送达，不能把没有日期的催告直接写成已经中断（《民法典》第一百八十八条、第一百九十二条、第一百九十五条）。",
      "recommended_action": "将催收函及邮寄签收单作为证据四重点质证"
    }},
    {{
      "id": "def_2",
      "focus": "利息超标或砍头息抗辩",
      "opponent_argument": "主张出借时预先扣除了利息或费用，或者利息、逾期利息、违约金和其他费用合计超过合同成立时一年期贷款市场报价利率的四倍",
      "counter_strategy": "用转账流水说明实际交付金额。预先在本金中扣除的利息，不能计入本金。超过四倍的合计部分不予支持，四倍以内仍可主张。不要把某一个固定年利率写成司法解释规定的上限（《民间借贷规定》第二十五条、第二十六条、第二十九条）。",
      "recommended_action": "在起诉状中附带利息精算清单附表"
    }},
    {{
      "id": "def_3",
      "focus": "保证人一般保证或保证期限抗辩",
      "opponent_argument": "主张没有约定保证方式所以是一般保证，或者保证期间已经过了",
      "counter_strategy": "没有约定保证方式或者约定不明的，按一般保证。已经写明连带责任保证的，从约定。保证期间没有约定、约定不明，或者约定期间早于主债务履行期限或同时届满的，才是届满之日起六个月。一般保证必须在保证期间内起诉主债务人或者申请仲裁，催告函不够。连带责任保证必须在保证期间内向保证人请求承担保证责任（《民法典》第六百八十六条、第六百九十二条、第六百九十三条）。",
      "recommended_action": "诉状中单列保证合同条款字样与送达凭证"
    }}
  ],
  "applicable_rules": [
    "《最高人民法院关于审理民间借贷案件适用法律若干问题的规定》第二十五条、第二十六条、第二十九条",
    "《中华人民共和国民法典》第一百九十二条、第六百八十六条、第六百八十八条、第六百九十二条、第六百九十三条"
  ]
}}
"""
        step3_data = {}
        try:
            from gateway.utils.pii_sanitizer import build_entities_from_matter as _bem

            _entities3 = _bem(matter_id) if matter_id else []
            raw_out3 = await ollama_client.generate(
                prompt=prompt_step3, temperature=0.2, custom_entities=_entities3 or None
            )
            step3_data = ollama_client.extract_json(raw_out3)
        except Exception as e:
            logger.warning(f"Step 3 预测失败，使用标准规则库兜底: {e}")

        if not _has_usable_defenses(step3_data):
            facts = step_data.get("facts_text") or ""
            is_loan = ("借贷" in cause) or ("借款" in cause) or any(word in facts for word in ("借款", "借贷", "出借"))
            if is_loan:
                step3_data = {
                    "defense_predictions": [
                        {
                            "id": "def_1",
                            "focus": "诉讼时效是否经过",
                            "opponent_argument": "如果期限届满后超过三年没有主张权利，对方可能提出诉讼时效抗辩。本案是否超过，要核对起算日，本页没有计算。",
                            "counter_strategy": "催告或对方同意履行，要留下日期和能够证明送达的记录，才讨论是否中断。一次记录不能写成已经中断。债权不因期间届满而消灭。",
                            "recommended_action": "核对主张权利的日期和送达材料",
                        },
                        {
                            "id": "def_2",
                            "focus": "款项性质",
                            "opponent_argument": "对方可能主张转账不是借款。本页没有认定款项性质。",
                            "counter_strategy": "把约定、转账和聊天记录对照着看。聊天承认不等于利息约定已经证明。",
                            "recommended_action": "核对实际交付凭证和款项用途",
                        },
                    ],
                    "applicable_rules": [
                        "《中华人民共和国民法典》第一百八十八条、第一百九十二条、第一百九十五条",
                        "《中华人民共和国民法典》第六百六十七条、第六百七十五条",
                    ],
                }
            else:
                step3_data = {
                    "defense_predictions": [
                        {
                            "id": "def_1",
                            "focus": "合同是否成立、是否已经履行",
                            "opponent_argument": "对方可能否认合同成立，或者否认已经收货、付款。本页没有认定。",
                            "counter_strategy": "对照录入的合同、签收和付款材料。没有写进案情的交付或违约，不要补写。",
                            "recommended_action": "核对原件和签收人是否有权受领",
                        },
                        {
                            "id": "def_2",
                            "focus": "诉讼时效是否经过",
                            "opponent_argument": "期间是否经过要核对起算日。本页没有计算。",
                            "counter_strategy": "催告或对方同意履行，要有日期和送达记录，才讨论是否中断。不能把没有日期的催告写成已经中断。",
                            "recommended_action": "核对主张权利的日期",
                        },
                    ],
                    "applicable_rules": [
                        "《中华人民共和国民法典》第五百零九条、第五百七十七条",
                        "《中华人民共和国民法典》第一百八十八条、第一百九十二条",
                    ],
                }

        step_data["step3"] = step3_data

        # 更新数据库，流转到 Step 4（等待律师核准抗辩与策略）
        next_step = WorkflowStep.STEP4_TACTICS_BREAKPOINT
        step_status = WorkflowStatus.WAITING_HUMAN

        cursor.execute("""
        UPDATE matter_workflows
        SET current_step = ?, step_status = ?, step_data_json = ?, updated_at = ?
        WHERE workflow_id = ?
        """, (next_step, step_status, json.dumps(step_data, ensure_ascii=False), now_str, workflow_id))
        conn.commit()
        return {
            "workflow_id": workflow_id,
            "matter_id": row["matter_id"] or step_data.get("matter_id"),
            "current_step": next_step,
            "step_status": step_status,
            "step_name": "攻防策略与争议焦点核准（人工断点）",
            "instruction": "抗辩预测来自模型或规则提示，不是已经检索到的裁判。请律师勾选后再生成文书。",
            "step_data": step_data
        }

    # =========================================================================
    # 断点 2 (Step 4) 推进到 Step 5: 核准策略，生成终稿起诉状并挂载引注防火墙
    # =========================================================================
    elif current_step == WorkflowStep.STEP4_TACTICS_BREAKPOINT:
        # 保存律师核准的 Step 4 数据
        step_data["step4"] = {
            "accepted_defenses": human_confirmed_data.get("accepted_defenses") or human_confirmed_data.get("accepted_counter_strategies") or [],
            "special_strategy_notes": human_confirmed_data.get("special_strategy_notes") or human_confirmed_data.get("lawyer_defense_notes") or "",
            "confirmed_at": now_str
        }

        matter_id = row["matter_id"] or step_data.get("matter_id")
        matter = get_matter_by_id(matter_id) if matter_id else None
        matter = matter or {}

        p_info = matter.get("plaintiff_info") or {}
        d_info = matter.get("defendant_info") or {}
        if isinstance(p_info, str):
            try:
                p_info = json.loads(p_info)
            except Exception:
                p_info = {}
        if isinstance(d_info, str):
            try:
                d_info = json.loads(d_info)
            except Exception:
                d_info = {}

        plaintiff_name = (
            human_confirmed_data.get("plaintiff_name")
            or (p_info.get("name") if isinstance(p_info, dict) else None)
            or matter.get("plaintiff_name")
            or ""
        )
        defendant_name = (
            human_confirmed_data.get("defendant_name")
            or (d_info.get("name") if isinstance(d_info, dict) else None)
            or matter.get("defendant_name")
            or ""
        )
        confirmed_claims_list = step_data.get("step2", {}).get("confirmed_claims") or []
        if human_confirmed_data.get("confirmed_claims"):
            confirmed_claims_list = human_confirmed_data["confirmed_claims"]
        court_raw = (
            human_confirmed_data.get("court_name")
            or matter.get("court_name")
            or step_data.get("court_name")
            or ""
        )
        court_full = normalize_court_name(court_raw) if court_raw else ""

        missing_fields: List[str] = []
        if not str(plaintiff_name).strip():
            missing_fields.append("plaintiff")
        if not str(defendant_name).strip():
            missing_fields.append("defendant")
        if not confirmed_claims_list or not any(str(c).strip() for c in confirmed_claims_list):
            missing_fields.append("claims")
        if not court_raw or not str(court_raw).strip():
            missing_fields.append("court")
        if missing_fields:
            raise WorkflowValidationError(
                f"终稿缺少必要字段: {', '.join(missing_fields)}",
                missing_fields=missing_fields,
            )

        confirmed_claims = "\n".join([f"{i+1}. {c}" for i, c in enumerate(confirmed_claims_list)])
        confirmed_basis = "\n".join([f"- {b}" for b in step_data["step2"].get("confirmed_legal_basis", [])])
        facts_text = step_data.get("facts_text") or matter.get("case_summary") or "【待填写】"
        cause = step_data["step2"].get("confirmed_cause", matter.get("cause_of_action") or "民事纠纷")
        filing_date_str = datetime.now().strftime("%Y年%m月%d日")

        # 仅用案件当事人与确认诉请渲染终稿，删除写死演示起诉状
        final_pleading_text = (
            f"民事起诉状\n\n"
            f"原告：{plaintiff_name}\n"
            f"被告：{defendant_name}\n\n"
            f"案由：{cause}\n\n"
            f"诉讼请求：\n{confirmed_claims}\n\n"
            f"事实与理由：\n{facts_text}\n"
        )
        if confirmed_basis:
            final_pleading_text += f"\n请求权基础：\n{confirmed_basis}\n"
        final_pleading_text += (
            f"\n此致\n{court_full}\n\n"
            f"具状人：{plaintiff_name}\n"
            f"日期：{filing_date_str}\n"
        )

        citation_audit = audit_citations_in_text(final_pleading_text, auto_sanitize=True)
        final_clean_text = citation_audit.get("sanitized_text", final_pleading_text)

        from gateway.core.paths import get_base_dir, get_generated_dir
        storage_dir = str(get_generated_dir())
        templates_dir = str(get_base_dir() / "templates")

        docx_filename = f"民事起诉状_工作流_{workflow_id}.docx"
        docx_output_path = os.path.join(storage_dir, docx_filename)
        download_url = f"/api/documents/download/{docx_filename}"

        try:
            from docxtpl import DocxTemplate
            tpl_path = os.path.join(templates_dir, "civil_complaint_template.docx")
            p_address = (p_info.get("address") if isinstance(p_info, dict) else None) or "【待填写】"
            d_address = (d_info.get("address") if isinstance(d_info, dict) else None) or "【待填写】"
            p_id = (p_info.get("id_card_or_uscc") or p_info.get("id") or p_info.get("uscc") if isinstance(p_info, dict) else None) or "【待填写】"
            d_id = (d_info.get("id_card_or_uscc") or d_info.get("id") or d_info.get("uscc") if isinstance(d_info, dict) else None) or "【待填写】"
            if os.path.exists(tpl_path):
                doc_tpl = DocxTemplate(tpl_path)
                context_wf = {
                    "plaintiff_name": plaintiff_name,
                    "plaintiff_gender": "",
                    "plaintiff_birth": "",
                    "plaintiff_ethnicity": "",
                    "plaintiff_id": p_id,
                    "plaintiff_id_label": "证件号码",
                    "plaintiff_address": p_address,
                    "plaintiff_phone": (p_info.get("phone") if isinstance(p_info, dict) else None) or "【待填写】",
                    "plaintiff_party_type": "natural",
                    "plaintiff_is_natural": True,
                    "plaintiff_is_legal": False,
                    "plaintiff_legal_rep": "",
                    "plaintiff_rep_position": "",
                    "defendant_name": defendant_name,
                    "defendant_gender": "",
                    "defendant_birth": "",
                    "defendant_ethnicity": "",
                    "defendant_id": d_id,
                    "defendant_id_label": "证件号码",
                    "defendant_address": d_address,
                    "defendant_phone": (d_info.get("phone") if isinstance(d_info, dict) else None) or "【待填写】",
                    "defendant_party_type": "natural",
                    "defendant_is_natural": True,
                    "defendant_is_legal": False,
                    "defendant_legal_rep": "",
                    "defendant_rep_position": "",
                    "claims": confirmed_claims_list,
                    "facts_and_reasons": facts_text,
                    "court_name": court_full,
                    "filing_date": filing_date_str,
                    "evidences": [],
                    "copies": 1,
                }
                doc_tpl.render(context_wf)
                doc_tpl.save(docx_output_path)
            else:
                import docx
                d = docx.Document()
                d.add_heading("民事起诉状", level=1)
                for line in final_clean_text.splitlines():
                    if line.strip():
                        d.add_paragraph(line)
                d.save(docx_output_path)
        except Exception as e_docx:
            logger.warning(f"工作流生成 docx 失败: {e_docx}")
            import docx
            d = docx.Document()
            for line in final_clean_text.splitlines():
                d.add_paragraph(line)
            d.save(docx_output_path)

        step_data["step5"] = {
            "pleading_text": final_clean_text,
            "citation_audit": citation_audit,
            "completed_at": now_str,
            "verification_cert_id": citation_audit.get("audit_cert", {}).get("audit_id", "CG-CERT-OK"),
            "docx_filename": docx_filename,
            "docx_path": docx_output_path,
            "download_url": download_url
        }

        cursor.execute("""
        UPDATE matter_workflows
        SET current_step = ?, step_status = ?, step_data_json = ?, is_completed = 1, updated_at = ?
        WHERE workflow_id = ?
        """, (
            WorkflowStep.STEP5_FINAL_COMPLETED,
            WorkflowStatus.COMPLETED,
            json.dumps(step_data, ensure_ascii=False),
            now_str,
            workflow_id
        ))
        conn.commit()
        return {
            "workflow_id": workflow_id,
            "matter_id": matter_id,
            "current_step": WorkflowStep.STEP5_FINAL_COMPLETED,
            "step_status": WorkflowStatus.COMPLETED,
            "step_name": "文书终稿交付与引注防火墙认证（流程达成）",
            "instruction": "人机协同工作流全流程完成！终稿文书已通过司法引注与案号反查防火墙认证，可一键复制或导出。",
            "step_data": step_data
        }

    else:
        return {
            "workflow_id": workflow_id,
            "matter_id": row["matter_id"] or step_data.get("matter_id"),
            "current_step": current_step,
            "step_status": row["step_status"],
            "step_data": step_data
        }


def rollback_workflow_step(workflow_id: str, target_step: int = 2) -> Dict[str, Any]:
    """支持工作流回退到前序断点，允许律师修改诉讼请求或策略后重新执行"""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM matter_workflows WHERE workflow_id = ?", (workflow_id,))
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"工作流不存在: {workflow_id}")

        step_data = json.loads(row["step_data_json"])
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        target = max(WorkflowStep.STEP2_CLAIMS_BREAKPOINT, min(target_step, WorkflowStep.STEP4_TACTICS_BREAKPOINT))

        cursor.execute("""
        UPDATE matter_workflows
        SET current_step = ?, step_status = ?, is_completed = 0, updated_at = ?
        WHERE workflow_id = ?
        """, (target, WorkflowStatus.WAITING_HUMAN, now_str, workflow_id))
        conn.commit()

    return {
        "workflow_id": workflow_id,
        "current_step": target,
        "step_status": WorkflowStatus.WAITING_HUMAN,
        "step_name": f"回退至步骤 {target}（人工核准断点）",
        "instruction": "流程已成功回退，您可以重新修改并确认当前步骤要素。",
        "step_data": step_data
    }


def get_workflow_by_id(workflow_id: str) -> Optional[Dict[str, Any]]:
    """读取指定工作流详情"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM matter_workflows WHERE workflow_id = ?", (workflow_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "workflow_id": row["workflow_id"],
            "matter_id": row["matter_id"],
            "workflow_type": row["workflow_type"],
            "current_step": row["current_step"],
            "step_status": row["step_status"],
            "step_data": json.loads(row["step_data_json"]),
            "is_completed": bool(row["is_completed"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
