"""
LawFlow 智律工作台 - 08 智律 AI 语音中枢与全模块联动编排网关 (Phase 8 AI Copilot Router)
核心接口：
1. POST /api/v1/copilot/converse: 接收口述语音转录文本或输入指令，LLM 意图解析 + 跨模块联动 + 自动任务整理
2. GET /api/v1/copilot/tasks: 办案任务看板查询与状态过滤
3. POST /api/v1/copilot/tasks: 手动/语音追加新办案任务
4. PUT /api/v1/copilot/tasks/{task_id}: 更新任务详情与流转状态
5. DELETE /api/v1/copilot/tasks/{task_id}: 删除指定任务
6. POST /api/v1/copilot/tasks/batch-status: 批量修改任务状态（全部标记已完成/待办）
7. GET /api/v1/copilot/dialogues: 读取近期对话流水
"""

import os
import re
import json
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

import cn2an
from gateway.core.ollama_client import ollama_client
from gateway.utils.agent_task_db import (
    init_agent_task_db,
    get_agent_tasks,
    create_agent_task,
    update_agent_task,
    delete_agent_task,
    batch_update_task_status,
    save_agent_dialogue,
    get_recent_dialogues
)
from gateway.utils.cn_legal_calc import (
    calculate_court_fees,
    calculate_lpr_interest,
    calculate_labor_compensation,
    calculate_statute_of_limitations,
    rmb_to_capital
)
from gateway.utils.statute_db import search_statutes_hybrid

logger = logging.getLogger("lawflow.copilot")
router = APIRouter(prefix="/api/v1/copilot", tags=["08 智律 AI 语音中枢与全模块联动"])


# ==============================================================================
# 金额智能解析与防自激回声过滤器
# ==============================================================================

def extract_chinese_amount(text: str) -> Optional[float]:
    """
    智能提取语音输入中的中英文混合标的/本金金额
    支持：'一百万'、'100万'、'一百万元'、'这是改为一百万元'、'85万'、'500000元'、'标的五千万'
    严格排除法条序号（如'第667条'）与量词（如'一个任务'、'三项待办'）
    """
    text_clean = text.replace("，", "").replace("。", "").replace(" ", "")

    # 1. 先过滤掉常见的非金额数字：如第XX条、X个任务、X项待办
    masked_text = re.sub(r'第\s*\d+\s*条', '', text_clean)
    masked_text = re.sub(r'[一二两三四五六七八九十0-9]+\s*(?:个任务|项任务|个待办|项待办|次开庭|份起诉状|页材料|个模块)', '', masked_text)

    # 2. 优先匹配具有明确货币单位（万、万元、元、块、亿元、亿）的数值
    m_unit = re.search(r'(?:改为|调整为|调为|变更为|本金|标的|金额|欠款|借款)?\s*([0-9零一二两三四五六七八九十百千万亿]+(?:\.[0-9零一二两三四五六七八九]+)?)\s*(万元|万|元|块|亿元|亿)', masked_text)
    if m_unit:
        raw_num = m_unit.group(1)
        unit = m_unit.group(2)
        try:
            val = float(cn2an.cn2an(raw_num, 'smart'))
            if '万' in unit and '万' not in raw_num and '亿' not in raw_num:
                val *= 10000
            elif '亿' in unit and '亿' not in raw_num:
                val *= 100000000
            return val
        except Exception:
            pass

    # 3. 匹配明确带有金额动作前缀（改为/调整为/标的/本金/借款）的汉字数词（如：改为一百万、标的五十万、本金1000000）
    m_prefix = re.search(r'(?:改为|调整为|调为|变更为|本金|标的|金额|欠款|借款)\s*[:：=]?\s*([0-9零一二两三四五六七八九十百千万亿]+(?:\.[0-9零一二两三四五六七八九]+)?)', masked_text)
    if m_prefix:
        raw_num = m_prefix.group(1)
        if any(c in "万千百亿" for c in raw_num) or (raw_num.isdigit() and len(raw_num) >= 3):
            try:
                val = float(cn2an.cn2an(raw_num, 'smart'))
                return val
            except Exception:
                pass

    return None


def is_self_echo_or_noise(text: str) -> bool:
    """过滤麦克风误收录的电脑自身扬声器播报声或极短杂音"""
    t = text.strip()
    if len(t) < 2:
        return True
    if t in ["嗯", "啊", "哦", "好的", "对", "好", "呃", "喂", "...", "并同步", "好的。"]:
        return True
    echo_signatures = [
        "已为您将诉讼标的",
        "已更新标的金额为",
        "核算LPR利息暂计为",
        "已挂载实体法条依据",
        "已在办案看板整理出",
        "已在办案看板中归纳了",
        "已收到指令并同步",
        "智律 AI 协同总控",
        "智律 AI 协同编排简报",
        "并同步全局在办案情",
        "跨模块自动化执行链",
        "所有计算结果与法条依据已实时回填",
        "指令已执行完成",
        "我是智律 AI 协同助手",
        "智能办案总控中枢"
    ]
    for sig in echo_signatures:
        if sig in t:
            return True
    return False


# ==============================================================================
# Pydantic Models
# ==============================================================================

class CopilotConverseReq(BaseModel):
    user_input: str = Field(..., description="用户口述转录或输入的自然语言指令")
    matter_id: Optional[str] = Field("default", description="当前绑定案件ID")
    current_tab: Optional[str] = Field("tab-copilot", description="当前所处模块ID")
    case_context: Optional[Dict[str, Any]] = Field(None, description="前端全局在办案件上下文快照")
    mode: Optional[str] = Field("voice", description="语音模式 voice 或文字模式 text")


_TASK_ISO_DATE_PATTERN = re.compile(r'^\d{4}-\d{2}-\d{2}(?:[T\s]\d{2}:\d{2}(?::\d{2})?)?$')

def _check_task_due_date_iso(val: Optional[str]) -> Optional[str]:
    if not val:
        return None
    val = val.strip()
    if not val or val in ("待定", "none", "null"):
        return None
    if not _TASK_ISO_DATE_PATTERN.match(val):
        raise ValueError(f"任务截止时间必须是 ISO 格式日期 (YYYY-MM-DD 或带时间)，非法值: '{val}'")
    return val

class TaskCreateReq(BaseModel):
    title: str = Field(..., description="任务名称")
    description: Optional[str] = Field("", description="任务详情与办案备注")
    stage: Optional[str] = Field("立案", description="办案阶段")
    priority: Optional[str] = Field("medium", description="优先级 high/medium/low")
    status: Optional[str] = Field("todo", description="状态 todo/in_progress/done")
    due_date: Optional[str] = Field(None, description="截止时限 (ISO 格式)")

    @field_validator("due_date")
    @classmethod
    def validate_due_date(cls, v):
        return _check_task_due_date_iso(v)
    linked_module: Optional[str] = Field("phase1_litigation", description="联动模块标识")
    action_payload: Optional[Dict[str, Any]] = Field(default_factory=dict, description="预填或动作载荷")
    matter_id: Optional[str] = Field("default", description="关联案件ID")


class TaskUpdateReq(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    stage: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    due_date: Optional[str] = None

    @field_validator("due_date")
    @classmethod
    def validate_due_date(cls, v):
        return _check_task_due_date_iso(v)
    linked_module: Optional[str] = None
    action_payload: Optional[Dict[str, Any]] = None


class BatchStatusReq(BaseModel):
    task_ids: List[str] = Field(..., description="任务ID列表")
    new_status: str = Field(..., description="目标状态 todo/in_progress/done")


# ==============================================================================
# 专家规则引擎与意图解析器 (兼做离线极速高保真兜底)
# ==============================================================================

def _rule_based_intent_parser(
    text: str,
    case_ctx: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    当大模型断网或未配置时，通过中国民商事实务规则引擎毫秒级精准解析
    """
    case_ctx = case_ctx or {}
    text_clean = text.strip()
    
    context_patch = {}
    task_operations = []
    module_actions = []

    # 1. 提取金额（支持一百万、100万、85万元、500000元等）
    extracted_amount = extract_chinese_amount(text_clean)
    if extracted_amount is not None:
        context_patch["amount"] = extracted_amount

    # 2. 提取起止起息日期（例如：2023年5月1日、2022-08-10、2024.01.01）
    dates = re.findall(r'(\d{4})[年\-\.\/](\d{1,2})[月\-\.\/](\d{1,2})[日]?', text_clean)
    start_date_str = None
    end_date_str = None
    if dates:
        formatted_dates = [f"{int(y):04d}-{int(m):02d}-{int(d):02d}" for y, m, d in dates]
        start_date_str = formatted_dates[0]
        if len(formatted_dates) > 1:
            end_date_str = formatted_dates[1]
        else:
            end_date_str = datetime.now().strftime("%Y-%m-%d")

    # 3. 提取当事人
    p_match = re.search(r'(?:原告|出借人|申请人|甲方)[：:\s]*([\u4e00-\u9fa5]{2,15})', text_clean)
    d_match = re.search(r'(?:被告|借款人|被申请人|乙方)[：:\s]*([\u4e00-\u9fa5]{2,15})', text_clean)
    if p_match:
        context_patch["plaintiff"] = {"name": p_match.group(1)}
    if d_match:
        context_patch["defendant"] = {"name": d_match.group(1)}

    # 4. 判断是否需要执行【01 精算】联动（LPR利息 / 诉讼费 / 劳动仲裁）
    is_calc_req = any(k in text_clean for k in ["算", "计息", "利息", "lpr", "LPR", "诉讼费", "保全费", "核算", "重算"])
    if is_calc_req or extracted_amount is not None or start_date_str is not None:
        principal = extracted_amount if extracted_amount is not None else (case_ctx.get("amount") or 500000.0)
        start = start_date_str or (case_ctx.get("interest_calc") or {}).get("start_date") or "2023-01-01"
        end = end_date_str or (case_ctx.get("interest_calc") or {}).get("end_date") or datetime.now().strftime("%Y-%m-%d")

        try:
            lpr_res = calculate_lpr_interest(principal=principal, start_date=start, end_date=end, term="1Y")
            court_res = calculate_court_fees(claim_amount=principal, case_type="property")
            
            interest_val = lpr_res.get("interest_total", 0.0)
            court_fee_val = court_res.get("fee_amount", 0.0)

            formal_statement = f"自{start}起至实际清偿之日止，以本金{principal:,.2f}元为基数，按同期全国银行间同业拆借中心公布的一年期贷款市场报价利率（LPR）计算至{end}暂计为{interest_val:,.2f}元；"

            calc_patch = {
                "principal": principal,
                "start_date": start,
                "end_date": end,
                "interest_total": interest_val,
                "formal_statement": formal_statement,
                "court_fee": court_fee_val,
                "preservation_fee": court_res.get("preservation_fee", 0.0)
            }
            context_patch["interest_calc"] = calc_patch
            if "amount" not in context_patch:
                context_patch["amount"] = principal

            module_actions.append({
                "module_id": "phase1_calc",
                "module_name": "01 实务精算与核验",
                "action_name": "LPR 利息与诉讼费穿透精算",
                "target_tab": "tab-calc",
                "status": "success",
                "summary": f"已按本金 ¥{principal:,.2f} 重新核算 LPR 利息 ¥{interest_val:,.2f}，诉讼费受理费 ¥{court_fee_val:,.2f}，并写入全案上下文",
                "data": calc_patch
            })
        except Exception as e:
            logger.warning(f"本地规则精算执行异常: {e}")

    # 5. 判断是否需要执行【06 法典穿透】联动
    statute_keywords = ["法条", "民法典", "司法解释", "第", "借款合同", "违约金", "劳动合同", "时效", "利息上限", "保证"]
    if any(k in text_clean for k in statute_keywords):
        query_word = "民间借贷 借款合同 利息"
        if "违约金" in text_clean:
            query_word = "违约金 调减 损失"
        elif "劳动" in text_clean or "补偿" in text_clean:
            query_word = "解除劳动合同 经济补偿金"
        elif "保证" in text_clean or "担保" in text_clean:
            query_word = "连带保证 一般保证"

        try:
            statute_hits = search_statutes_hybrid(query=query_word, limit=3)
            if statute_hits:
                attached_statutes = []
                for s in statute_hits:
                    attached_statutes.append({
                        "id": s.get("id"),
                        "law_name": s.get("law_name"),
                        "article_no": s.get("article_no_cn"),
                        "content": (s.get("content") or "")[:120] + "..."
                    })
                context_patch["statutes"] = attached_statutes
                module_actions.append({
                    "module_id": "phase5_statutes",
                    "module_name": "06 权威法典与子母法图谱",
                    "action_name": "实体法规范与司法解释检索",
                    "target_tab": "tab-statutes",
                    "status": "success",
                    "summary": f"检索命中《{attached_statutes[0]['law_name']}》{attached_statutes[0]['article_no']}等 {len(attached_statutes)} 条实体裁判规范，已挂载至案件请求权依据",
                    "data": {"count": len(attached_statutes), "statutes": attached_statutes}
                })
        except Exception as e:
            logger.warning(f"本地法典检索联动异常: {e}")

    # 6. 判断是否需要【02 文书流水线】联动
    if any(k in text_clean for k in ["起诉状", "文书", "立案材料", "起草", "生成公文"]):
        module_actions.append({
            "module_id": "phase1_litigation",
            "module_name": "02 立案文书流水线",
            "action_name": "文书要素对齐与起诉状草稿装配",
            "target_tab": "tab-litigation",
            "status": "success",
            "summary": "已将最新当事人、诉请本金、LPR 计息明细与法条依据装配至 02 模块，可随时一键生成全套立案公文包",
            "data": {"ready_for_export": True}
        })

    # 7. 任务梳理（Task Operations）
    # 检测是否要求新建/完成/删除任务
    if any(k in text_clean for k in ["完成", "搞定", "做完了", "勾选"]):
        task_operations.append({
            "op": "update_status",
            "target_keyword": text_clean,
            "status": "done",
            "title": "更新关联办案任务为已完成"
        })
    elif any(k in text_clean for k in ["任务", "待办", "整理", "记一下", "加一个", "提醒", "调取", "证据", "核对"]):
        # 提炼任务名称
        task_title = text_clean
        for prefix in ["帮我", "记一下", "加一个任务", "加个待办", "请", "去"]:
            if task_title.startswith(prefix):
                task_title = task_title[len(prefix):].strip("，：: ")
        
        # 截取合适长度作为标题
        short_title = task_title[:35] if len(task_title) > 35 else task_title
        
        stage = "立案"
        linked_mod = "phase1_litigation"
        if any(w in short_title for w in ["流水", "银行", "转账", "公证", "微信", "证明", "证据", "核对"]):
            stage = "证据"
            linked_mod = "phase2_evidence"
        elif any(w in short_title for w in ["算", "利息", "诉讼费", "赔偿", "精算"]):
            stage = "精算"
            linked_mod = "phase1_calc"
        elif any(w in short_title for w in ["法条", "检索", "判例", "案例", "法典"]):
            stage = "检索"
            linked_mod = "phase5_statutes"
        elif any(w in short_title for w in ["开庭", "质证", "辩论", "推演", "抗辩"]):
            stage = "庭审"
            linked_mod = "phase4_deep_matrix"
        elif any(w in short_title for w in ["执行", "查控", "冻结", "拍卖"]):
            stage = "执行"
            linked_mod = "matter_vault"

        task_operations.append({
            "op": "create",
            "title": short_title,
            "description": f"由 AI 语音/指令中枢自动归纳：{text_clean}",
            "stage": stage,
            "priority": "high" if any(w in short_title for w in ["紧急", "保全", "时效", "立刻", "今天"]) else "medium",
            "status": "todo",
            "due_date": "明日 18:00" if "明天" in short_title else ("本周内" if "周" in short_title else "待定"),
            "linked_module": linked_mod
        })

    # 生成自然拟人回复话术
    speech_parts = []
    if context_patch.get("amount"):
        amt_val = context_patch['amount']
        amt_wan = amt_val / 10000
        if amt_wan >= 1:
            amt_text = f"{amt_wan:.2f}".rstrip('0').rstrip('.') + "万元"
        else:
            amt_text = f"{amt_val:,.0f}元"
        speech_parts.append(f"好的，已为您将诉讼标的调整为{amt_text}")
    if any(a["module_id"] == "phase1_calc" for a in module_actions):
        c_patch = context_patch.get("interest_calc", {})
        int_total = c_patch.get('interest_total', 0)
        if int_total > 0:
            speech_parts.append(f"核算LPR利息暂计为{int_total:,.0f}元")
    if any(a["module_id"] == "phase5_statutes" for a in module_actions):
        speech_parts.append("已挂载实体法条依据")
    if task_operations:
        speech_parts.append(f"已在办案看板中归纳了{len(task_operations)}项待办")

    if not speech_parts:
        # 用户仅打招呼或寒暄
        if any(w in text_clean for w in ["你好", "您好", "在吗", "在不在", "嗨", "hello", "hi"]):
            return {
                "speech_reply": "您好！我是智律 AI 助手，已就绪，随时为您调度计算与办案待办整理。",
                "text_reply": """### ⚖️ 智律 AI 协同总控就绪

您好！我是您的智能办案协同助手。您可以直接口述或输入指令：
- *“帮我把借款本金调为100万元，算下从2023年5月1日起算的LPR利息”*
- *“查下民法典第667条借款合同法条”*
- *“记一个调取微信转账记录的任务”*
系统将实时穿透计算并同步全案。""",
                "context_patch": {},
                "task_operations": [],
                "module_actions": []
            }
        
        # 未识别出有效法律要素或交办指令：严禁主动发声朗读，保持静默！
        return {
            "speech_reply": "",
            "text_reply": f"已收到口述记录：「{text_clean}」。当前未检测到明确的案件要素修改、利息计算或待办任务交办指令。若需调整案情或排期待办，请直接说明。",
            "context_patch": {},
            "task_operations": [],
            "module_actions": []
        }

    speech_reply = "，".join(speech_parts) + "。"
    
    text_reply = f"""### ⚖️ 智律 AI 协同编排简报

您口述的案情与交办指令已完成结构化解析：

- **案情要素更新**：{'诉讼标的 ¥{:,.2f}'.format(context_patch.get('amount', 0)) if 'amount' in context_patch else '案情上下文已核验'}
- **跨模块自动化调度**：触发并完成了 **{len(module_actions)}** 项联动（见下方执行进度链）
- **办案任务矩阵**：自动归纳并排期了 **{len(task_operations)}** 项办案工作待办

*所有计算结果与法条依据已实时回填至当前案件总线 `CaseContextStore`。*"""

    return {
        "speech_reply": speech_reply,
        "text_reply": text_reply,
        "context_patch": context_patch,
        "task_operations": task_operations,
        "module_actions": module_actions
    }


# ==============================================================================
# 核心接口实现
# ==============================================================================

@router.get("/tasks", summary="获取办案任务看板列表")
async def list_copilot_tasks(
    matter_id: Optional[str] = Query("default"),
    status: Optional[str] = Query("all"),
    stage: Optional[str] = Query("all")
):
    init_agent_task_db()
    tasks = get_agent_tasks(matter_id=matter_id, status=status, stage=stage)
    
    # 统计各状态计数
    all_tasks = get_agent_tasks(matter_id=matter_id, status='all', stage='all')
    counts = {
        "total": len(all_tasks),
        "todo": sum(1 for t in all_tasks if t.get("status") == "todo"),
        "in_progress": sum(1 for t in all_tasks if t.get("status") == "in_progress"),
        "done": sum(1 for t in all_tasks if t.get("status") == "done")
    }

    return {
        "status": "success",
        "counts": counts,
        "tasks": tasks
    }


@router.post("/tasks", summary="创建新办案任务")
async def create_new_copilot_task(req: TaskCreateReq):
    init_agent_task_db()
    created = create_agent_task(req.dict())
    return {
        "status": "success",
        "task": created
    }


@router.put("/tasks/{task_id}", summary="更新办案任务状态或属性")
async def update_copilot_task_info(task_id: str, req: TaskUpdateReq):
    init_agent_task_db()
    data = {k: v for k, v in req.dict().items() if v is not None}
    updated = update_agent_task(task_id, data)
    if not updated:
        raise HTTPException(status_code=404, detail="未找到目标任务或任务不存在")
    return {
        "status": "success",
        "task": updated
    }


@router.delete("/tasks/{task_id}", summary="删除办案任务")
async def remove_copilot_task(task_id: str):
    init_agent_task_db()
    ok = delete_agent_task(task_id)
    return {
        "status": "success",
        "deleted": ok
    }


@router.post("/tasks/batch-status", summary="批量更新办案任务状态")
async def batch_update_tasks(req: BatchStatusReq):
    init_agent_task_db()
    count = batch_update_task_status(req.task_ids, req.new_status)
    return {
        "status": "success",
        "updated_count": count
    }


@router.get("/dialogues", summary="获取近期对话流水")
async def list_recent_dialogues(
    matter_id: Optional[str] = Query("default"),
    limit: Optional[int] = Query(25)
):
    init_agent_task_db()
    dialogues = get_recent_dialogues(matter_id=matter_id, limit=limit)
    return {
        "status": "success",
        "dialogues": dialogues
    }


@router.post("/converse", summary="智律 AI 语音通话与全模块联动编排中枢")
async def copilot_converse_orchestrate(req: CopilotConverseReq):
    """
    用户通过语音口述或键盘输入指令：
    1. 记下用户发言并存档
    2. 优先调用大模型 UniversalLLMClient 进行复杂意图抽取与工具编排
    3. 若离线或无可用大模型，无缝进入高保真法律实务规则引擎进行深度解析
    4. 执行数据库任务落地与模块动作，并同步全局在办案情
    5. 返回精练语音朗读文案 (TTS)、Markdown 详述及模块联动执行进度链
    """
    init_agent_task_db()

    user_text = req.user_input.strip()
    if not user_text:
        raise HTTPException(status_code=400, detail="输入指令不能为空")

    if is_self_echo_or_noise(user_text):
        logger.info(f"拦截自激回声或无意义杂音: '{user_text}'")
        return {
            "status": "ignored",
            "speech_reply": "",
            "text_reply": "",
            "context_patch": {},
            "module_actions": [],
            "task_operations": [],
            "tasks": get_agent_tasks(matter_id=req.matter_id, status="all")
        }

    # 1. 保存用户对话记录
    save_agent_dialogue(
        role="user",
        content=user_text,
        matter_id=req.matter_id
    )

    # 2. 意图解析：优先通过法律专家规则引擎毫秒级极速解析 (< 5ms)
    rule_result = _rule_based_intent_parser(user_text, req.case_context)

    # 判断规则引擎是否已高置信度命中（标的金额变更/利息精算/法条检索/公文装配/待办记账/问候打招呼等）
    has_rule_hit = (
        bool(rule_result.get("context_patch")) or
        bool(rule_result.get("module_actions")) or
        bool(rule_result.get("task_operations")) or
        bool(rule_result.get("speech_reply"))
    )

    orchestration_result = None
    if has_rule_hit:
        # 命中明确办案动作或问候，毫秒级直接直通，充分消灭数秒等待
        orchestration_result = rule_result
    else:
        # 仅在无规则命中且可能为复杂开放式法理咨询时，尝试异步调用大模型 (超时严控在 2.5 秒)
        has_active_llm = bool(ollama_client.settings.get("api_key")) or (await ollama_client._is_ollama_online())
        if has_active_llm and len(user_text) >= 6:
            try:
                llm_prompt = f"""你是一名资深的中国民商事律师助手与智能办案总控中枢 (LawFlow AI Copilot)。
用户正在通过语音或打字向你交办工作、口述案情或指挥联动 01~07 功能模块。

【当前在办案件上下文】:
{json.dumps(req.case_context or {}, ensure_ascii=False, indent=2)}

【用户指令】:
"{user_text}"

请严格按照以下 JSON Schema 输出结构化执行计划（不得输出除合规 JSON 以外的任何文本或标记）：
{{
  "speech_reply": "简练口语播报文本（专供TTS直接朗读，30字以内，热情干练）",
  "text_reply": "详细的Markdown办案分析与汇报",
  "context_patch": {{
    "amount": 标的金额数值(若有),
    "cause": "法定案由(若有)",
    "plaintiff": {{"name": "原告姓名"}},
    "defendant": {{"name": "被告姓名"}},
    "court": "管辖法院",
    "facts": "核心事实摘要"
  }},
  "task_operations": [
    {{
      "op": "create",
      "title": "任务简明标题",
      "description": "详细要求与法律注意点",
      "stage": "立案|证据|检索|精算|文书|庭审|执行",
      "priority": "high|medium|low",
      "status": "todo",
      "due_date": "期限如 明日18:00",
      "linked_module": "phase1_calc|phase1_litigation|phase2_evidence|phase5_statutes|phase4_deep_matrix"
    }}
  ],
  "module_actions": [
    {{
      "module_id": "phase1_calc",
      "module_name": "01 实务精算与核验",
      "action_name": "执行操作名",
      "target_tab": "tab-calc",
      "status": "success",
      "summary": "执行摘要"
    }}
  ]
}}
"""
                from gateway.utils.pii_sanitizer import build_entities_from_matter

                _copilot_entities = build_entities_from_matter(req.matter_id or "")
                raw_llm_out = await asyncio.wait_for(
                    ollama_client.generate(
                        prompt=llm_prompt,
                        system_prompt="你输出的内容必须是纯 JSON 格式。",
                        temperature=0.1,
                        max_tokens=600,
                        custom_entities=_copilot_entities or None,
                    ),
                    timeout=2.5
                )
                cleaned_json = raw_llm_out.strip()
                if "```json" in cleaned_json:
                    cleaned_json = cleaned_json.split("```json")[1].split("```")[0].strip()
                elif "```" in cleaned_json:
                    cleaned_json = cleaned_json.split("```")[1].split("```")[0].strip()

                parsed = json.loads(cleaned_json)
                if isinstance(parsed, dict) and "speech_reply" in parsed:
                    orchestration_result = parsed
            except Exception as e:
                logger.info(f"大模型解析超时或异常，平滑降级到规则引擎: {e}")

    # 若未命中大模型解析，使用规则引擎
    if not orchestration_result:
        orchestration_result = rule_result

    # 3. 落地任务操作 (Task Operations)
    for op in orchestration_result.get("task_operations", []):
        if op.get("op") == "create":
            create_agent_task({
                "matter_id": req.matter_id,
                "title": op.get("title", "新办案任务"),
                "description": op.get("description", ""),
                "stage": op.get("stage", "立案"),
                "priority": op.get("priority", "medium"),
                "status": op.get("status", "todo"),
                "due_date": op.get("due_date", "待定"),
                "linked_module": op.get("linked_module", "phase1_litigation"),
                "action_payload": {"target_tab": op.get("target_tab", "tab-litigation")}
            })
        elif op.get("op") == "update_status":
            # 找到最匹配的任务并标记状态
            target_kw = op.get("target_keyword", "")
            current_tasks = get_agent_tasks(matter_id=req.matter_id, status="all")
            for t in current_tasks:
                if any(w in t["title"] for w in ["LPR", "利息", "精算", "合同", "起诉状"]):
                    update_agent_task(t["task_id"], {"status": op.get("status", "done")})
                    break

    # 4. 获取最新任务列表以同步回传前端
    latest_tasks = get_agent_tasks(matter_id=req.matter_id, status="all")

    # 5. 保存 AI 助手回复记录
    saved_msg = save_agent_dialogue(
        role="assistant",
        content=orchestration_result.get("text_reply", ""),
        speech_text=orchestration_result.get("speech_reply", ""),
        action_summary={
            "module_actions": orchestration_result.get("module_actions", []),
            "context_patch": orchestration_result.get("context_patch", {})
        },
        matter_id=req.matter_id
    )

    return {
        "status": "success",
        "speech_reply": orchestration_result.get("speech_reply", "指令已执行完成。"),
        "text_reply": orchestration_result.get("text_reply", ""),
        "context_patch": orchestration_result.get("context_patch", {}),
        "module_actions": orchestration_result.get("module_actions", []),
        "task_operations": orchestration_result.get("task_operations", []),
        "tasks": latest_tasks,
        "dialogue_id": saved_msg.get("dialogue_id")
    }
