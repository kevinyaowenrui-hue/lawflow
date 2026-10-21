"""
LawFlow 智律工作台 - 阶段六：律所级风控合规与执业护城河 (phase6_compliance)
核心功能：
1. 利益冲突穿透排查中枢 (Conflict of Interest Check & Anti-Conflict Barrier):
   - 依据《律师法》第39条及中华全国律协《律师执业行为规范》第50/51条
   - 查验直接代理冲突、常年法律顾问冲突、同案双方代理、关联企业穿透冲突、已结案历史承办冲突
   - 签发 SHA-256 利益冲突数字无冲突验讫证书 (Clearance Certificate)
   - 支持排查底档库查询与新案登记
2. 大模型生成后法条强制反查与防幻觉熔断网关 (Zero-Hallucination Statute Circuit Breaker):
   - 针对大模型生成的文书、辩护词、提纲，自动正则抽取引用的所有法条
   - 废止法律熔断探测（合同法、物权法、担保法、民法通则等，自动给出民法典替代条文）
   - 现行法典条号真实性与捏造条号越界探测（民法典 1260 条、民诉法 300 条等上限与具体条文核验）
   - 出具《零幻觉司法引注体检报告单》及自动净化文本 (Sanitized Text)
"""

import logging
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from gateway.utils.conflict_checker import (
    check_conflict_of_interest,
    list_conflict_registry_cases,
    register_new_conflict_case
)
from gateway.utils.citation_guard import (
    audit_citations_in_text,
    verify_single_citation,
    verify_single_case_number
)

logger = logging.getLogger("lawflow.phase6")
router = APIRouter(prefix="/api/v1", tags=["阶段六：律所风控合规与法条防幻觉熔断"])

# ==============================================================================
# 数据模型定义
# ==============================================================================
class ConflictCheckReq(BaseModel):
    client_name: str = Field(..., description="拟委托当事人/客户名称")
    opposing_party: str = Field(..., description="相对方/被告/被申请人名称")
    client_id_or_code: Optional[str] = Field("", description="客户身份证号或统一社会信用代码")
    opposing_id_or_code: Optional[str] = Field("", description="相对方身份证号或统一社会信用代码")
    related_entities: Optional[List[str]] = Field(default=[], description="关联方/母子公司/实际控制人")
    case_subject: Optional[str] = Field("", description="涉案由或争议标的")

class ConflictRegisterReq(BaseModel):
    case_name: str = Field(..., description="案件名称")
    case_no: str = Field(..., description="案号/档案号")
    client_name: str = Field(..., description="委托人名称")
    opposing_party: str = Field(..., description="相对方名称")
    status: Optional[str] = Field("ACTIVE", description="案件状态: ACTIVE / CLOSED / RETAINER")
    related_entities: Optional[List[str]] = Field(default=[], description="关联实体列表")
    handling_lawyer: Optional[str] = Field("主办律师", description="承办律师")
    notes: Optional[str] = Field("", description="备注说明")

class CitationAuditReq(BaseModel):
    text: str = Field(..., description="需要核验法条与司法案号真伪与现行有效性的文本")
    auto_sanitize: Optional[bool] = Field(True, description="是否自动修正已废止法律条文为现行民法典条文")

class CitationVerifySingleReq(BaseModel):
    law_name: str = Field(..., description="法律名称，如《民法典》")
    article_num: int = Field(..., description="条号阿拉伯数字，如 585")
    original_citation: Optional[str] = Field("", description="原始引注文本")

class CaseNumberVerifyReq(BaseModel):
    case_number: str = Field(..., description="司法裁判案号，如（2023）最高法民终123号")

# ==============================================================================
# 接口实现
# ==============================================================================
@router.post("/conflict/check", summary="律所级利益冲突穿透排查与合规熔断")
async def api_check_conflict(req: ConflictCheckReq):
    try:
        res = check_conflict_of_interest(
            client_name=req.client_name,
            opposing_party=req.opposing_party,
            client_id_or_code=req.client_id_or_code or "",
            opposing_id_or_code=req.opposing_id_or_code or "",
            related_entities=req.related_entities or [],
            case_subject=req.case_subject or ""
        )
        return res
    except Exception as e:
        logger.error(f"利益冲突排查失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"利益冲突排查计算异常: {str(e)}")


@router.get("/conflict/registry", summary="获取律所在办/历史顾问案件冲突底档清单")
async def api_list_conflict_registry():
    try:
        cases = list_conflict_registry_cases()
        return {
            "status": "success",
            "count": len(cases),
            "registry": cases
        }
    except Exception as e:
        logger.error(f"查询底档库失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"查询底档库异常: {str(e)}")


@router.post("/conflict/register-case", summary="录入案件至律所利冲底档库")
async def api_register_conflict_case(req: ConflictRegisterReq):
    try:
        res = register_new_conflict_case(
            case_name=req.case_name,
            case_no=req.case_no,
            client_name=req.client_name,
            opposing_party=req.opposing_party,
            status=req.status or "ACTIVE",
            related_entities=req.related_entities or [],
            handling_lawyer=req.handling_lawyer or "主办律师",
            notes=req.notes or ""
        )
        return res
    except Exception as e:
        logger.error(f"录入底档库失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"录入底档库异常: {str(e)}")


@router.post("/guard/audit-citations", summary="文本全量司法法条与裁判案号引用真伪与废止探测")
async def api_audit_citations(req: CitationAuditReq):
    try:
        report = audit_citations_in_text(text=req.text, auto_sanitize=req.auto_sanitize)
        return report
    except Exception as e:
        logger.error(f"法条与案号防幻觉审查失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"审查异常: {str(e)}")


@router.post("/guard/verify-single", summary="单个法条真实性与现行有效性探测")
async def api_verify_single_citation(req: CitationVerifySingleReq):
    try:
        res = verify_single_citation(
            law_name=req.law_name,
            article_num=req.article_num,
            original_citation=req.original_citation or ""
        )
        return res
    except Exception as e:
        logger.error(f"单法条校验失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"校验异常: {str(e)}")


@router.post("/guard/verify-case-number", summary="单个司法审判裁判文书案号真伪与标准规范核验")
async def api_verify_case_number(req: CaseNumberVerifyReq):
    try:
        res = verify_single_case_number(req.case_number)
        return res
    except Exception as e:
        logger.error(f"案号核验失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"核验异常: {str(e)}")
