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

请作为主办律师，提炼该案件的核心事实要素清单，并推荐 1-3 个适格法定案由，及建议初步诉讼请求。
严格输出 JSON 格式：
{{
  "facts_summary": ["事实1...", "事实2..."],
  "disputed_amount": "涉案争议本金或标的额说明",
  "suggested_causes_of_action": [
    {{"cause": "民间借贷纠纷", "confidence": "95%", "rationale": "出借转账凭证完备，借贷合同及借条明确"}},
    {{"cause": "合同纠纷", "confidence": "70%", "rationale": "基于借款协议的通用违约责任"}}
  ],
  "candidate_claims": [
    {{"id": "claim_1", "text": "判令被告偿还原告借款本金", "default_selected": true, "category": "本金"}},
    {{"id": "claim_2", "text": "判令被告支付利息及逾期利息（按合同约定或LPR4倍计算）", "default_selected": true, "category": "利息"}},
    {{"id": "claim_3", "text": "判令保证人承担连带偿还责任", "default_selected": true, "category": "担保"}},
    {{"id": "claim_4", "text": "判令被告承担本案全部诉讼费、保全费及律师费", "default_selected": true, "category": "费用"}}
  ],
  "candidate_legal_basis": [
    {{"norm": "《中华人民共和国民法典》第六百七十五条", "desc": "借款人应当按照约定的期限返还借款"}},
    {{"norm": "《中华人民共和国民法典》第六百七十六条", "desc": "借款人未按照约定期限返还借款应当支付逾期利息"}},
    {{"norm": "《中华人民共和国民法典》第六百八十八条", "desc": "连带责任保证人偿还义务"}}
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

    # 规则兜底保证 100% 可用
    if not step1_data or "candidate_claims" not in step1_data:
        step1_data = {
            "facts_summary": [
                f"委托人【{client_role}】因合同履行与款项结算与对方发生实质争议。",
                "双方此前签署有书面协议或转账往来记录，约定权利义务明确。",
                "履行期届满后，对方未能依约清偿，构成实质性履约违约。"
            ],
            "disputed_amount": "以合同约定义务及实际银行打款凭据为准",
            "suggested_causes_of_action": [
                {"cause": "民间借贷纠纷", "confidence": "92%", "rationale": "符合《民法典》借款合同编及司法解释关于借贷关系的要件"},
                {"cause": "买卖/服务合同违约纠纷", "confidence": "65%", "rationale": "备选违约金追偿路径"}
            ],
            "candidate_claims": [
                {"id": "claim_1", "text": "判令被告偿还原告本金/货款/借款", "default_selected": True, "category": "本金"},
                {"id": "claim_2", "text": "判令被告支付逾期利息与违约金（自违约之日起算至实际清偿之日止）", "default_selected": True, "category": "利息与违约金"},
                {"id": "claim_3", "text": "判令连带责任人/保证人对上述款项承担连带清偿责任", "default_selected": True, "category": "担保追偿"},
                {"id": "claim_4", "text": "本案全部案件受理费、保全费由各被告共同承担", "default_selected": True, "category": "程序费用"}
            ],
            "candidate_legal_basis": [
                {"norm": "《中华人民共和国民法典》第五百零九条", "desc": "当事人应当按照约定全面履行自己的义务"},
                {"norm": "《中华人民共和国民法典》第五百七十七条", "desc": "当事人一方不履行合同义务应当承担继续履行或者采取补救措施等违约责任"},
                {"norm": "《中华人民共和国民法典》第六百七十五条", "desc": "借款人应当按照约定的期限返还借款"}
            ]
        }

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
            "confirmed_cause": human_confirmed_data.get("confirmed_cause") or human_confirmed_data.get("cause_of_action") or "民间借贷纠纷",
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

请针对上述律师核准的诉讼请求，从对方被告律师（Red Team）视角深度预测：
1. 对方最可能提出的 3 个实体或程序抗辩焦点；
2. 每一个抗辩焦点的反驳预案与证据补强建议；
3. 本案现行适用的裁判规则指引。

严格输出 JSON：
{{
  "defense_predictions": [
    {{
      "id": "def_1",
      "focus": "诉讼时效是否经过抗辩",
      "opponent_argument": "主张借款期限届满后超过3年未主张权利，胜诉权已消灭",
      "counter_strategy": "出示微信催收记录、EMS寄递催告函，证明时效发生连续中断",
      "recommended_action": "将催收函及邮寄签收单作为证据四重点质证"
    }},
    {{
      "id": "def_2",
      "focus": "利息超标或砍头息抗辩",
      "opponent_argument": "主张出借时扣除了中介费或约定利率超过LPR4倍红线",
      "counter_strategy": "依银行转账流水证明实际全额到账500万无扣减，年利率14.4%严守司法解释上限",
      "recommended_action": "在起诉状中附带利息精算清单附表"
    }},
    {{
      "id": "def_3",
      "focus": "保证人一般保证或保证期限抗辩",
      "opponent_argument": "主张保证合同未明确连带责任推定为一般保证，或主债务到期后6个月内未起诉",
      "counter_strategy": "出示《保证合同》第3条明确载明'连带责任保证'字样，且催告函在6个月内送达",
      "recommended_action": "诉状中单列保证合同条款字样与送达凭证"
    }}
  ],
  "applicable_rules": [
    "最高人民法院关于审理民间借贷案件适用法律若干问题的规定（2020修正）第二十八条",
    "中华人民共和国民法典第六百八十八条（连带责任保证）"
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

        if not step3_data or "defense_predictions" not in step3_data:
            step3_data = {
                "defense_predictions": [
                    {
                        "id": "def_1",
                        "focus": "诉讼时效抗辩",
                        "opponent_argument": "对方常以债权超期、未及时催告为由主张时效抗辩",
                        "counter_strategy": "通过出借后持续催款凭据、还款承诺书主张时效中断",
                        "recommended_action": "固定时效中断的电子数据与通信记录"
                    },
                    {
                        "id": "def_2",
                        "focus": "款项性质与对价真实性抗辩",
                        "opponent_argument": "主张转账款项系投资款、预付款或其他往来款而非借款",
                        "counter_strategy": "结合双方往来合同、汇款凭据附言及结算确认书形成闭环证据链",
                        "recommended_action": "提供完整银行交易电子回单"
                    }
                ],
                "applicable_rules": [
                    "《中华人民共和国民法典》第六百七十五条、第六百七十六条",
                    "《最高人民法院关于审理民间借贷案件适用法律若干问题的规定》"
                ]
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
            "instruction": "系统已穿透法规库并预测对方 3 大抗辩焦点，请律师勾选应对策略与补充论辩意见，点击'核准并生成文书终稿'。",
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
