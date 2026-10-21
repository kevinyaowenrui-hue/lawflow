"""
LawFlow 智律工作台 - 阶段五：权威法典与子母法图谱检索中枢 API 路由
集成：
1. 全景法源库运行状态与指标总览 (GET /api/v1/statutes/overview)
2. 法规列表与特定法规全文条目 (GET /api/v1/statutes/laws, GET /api/v1/statutes/law/{law_id})
3. 单条法条与子母法双向穿透图谱详情 (GET /api/v1/statutes/article/{article_id})
4. 三路混合检索（精确条号直达 + 复合短语 + FTS5 全文索引 + 子母法连带召回） (POST /api/v1/statutes/search)
5. 律所自定义法规/高院指引原子切片导入 (POST /api/v1/statutes/import)
6. 手工建立子母法图谱关联 (POST /api/v1/statutes/link)
"""

import logging
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from gateway.utils.statute_db import (
    get_statute_database_stats,
    get_db_connection,
    search_statutes_hybrid,
    get_article_details_with_graph,
    import_custom_statute,
    init_statute_database
)

logger = logging.getLogger("lawflow.phase5_statutes")
router = APIRouter(prefix="/api/v1/statutes", tags=["阶段五：权威法典与子母法图谱中枢"])


# ==============================================================================
# 请求与响应模型定义
# ==============================================================================
class StatuteSearchRequest(BaseModel):
    query: str = Field(..., description="检索词（支持条号如'民法典 585'、法言法语如'套取贷款'、'刺破公司面纱'、'违约金调减'）")
    domain: Optional[str] = Field(default="全部", description="部门法领域筛选（全部、民商、合同、公司、劳动、刑事、民诉程序）")
    hierarchy: Optional[int] = Field(default=None, description="效力位阶筛选（1:基本法律, 2:司法解释, 3:行政法规, 4:裁判指引）")
    status: str = Field(default="VALID", description="效力状态（VALID现行有效, ALL含已废止）")
    include_linked: bool = Field(default=True, description="是否自动双向穿透召回子法司法解释与上位母法")
    limit: int = Field(default=15, ge=1, le=50, description="返回结果上限")


class StatuteImportRequest(BaseModel):
    law_id: str = Field(..., description="唯一标识符，如 beijing_high_court_labor_2023")
    full_name: str = Field(..., description="法规全称，如《北京市高级人民法院关于审理劳动争议案件法律适用问题的解答》")
    short_name: str = Field(..., description="法规简称，如 北京高院劳动争议解答")
    hierarchy: int = Field(default=4, description="位阶：1:基本法律, 2:司法解释, 3:行政法规, 4:地方高院指南/纪要")
    promulgated_by: str = Field(..., description="制定机关，如 北京市高级人民法院")
    effective_date: str = Field(..., description="施行日期，格式 YYYY-MM-DD")
    domain: str = Field(default="民商", description="部门法领域")
    raw_text: str = Field(..., description="法规全文原始文本（需包含'第X条'格式，系统将自动进行编章节条款原子切片）")
    summary: Optional[str] = Field(default="", description="法规概要说明")


class LinkCreationRequest(BaseModel):
    parent_article_id: str = Field(..., description="上位母法条文ID，如 civil_code_2021:art_585")
    child_article_id: str = Field(..., description="下位司法解释条文ID，如 contract_interp_2023:art_65")
    relation_type: str = Field(..., description="关联关系类型：细化裁量标准、程序衔接、举证责任分配、追诉门槛标准等")
    notes: Optional[str] = Field(default="", description="实务办案批注或裁判要点")


# ==============================================================================
# API 路由实现
# ==============================================================================

@router.get("/overview", summary="全景法源库与引擎指标总览")
async def get_overview():
    try:
        stats = get_statute_database_stats()
        return {
            "status": "success",
            "data": stats
        }
    except Exception as e:
        logger.error(f"获取法规库概览失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/laws", summary="获取法规法典全景目录列表")
async def list_laws(
    domain: Optional[str] = Query(default=None, description="部门法筛选"),
    hierarchy: Optional[int] = Query(default=None, description="位阶筛选"),
    status: Optional[str] = Query(default="VALID", description="状态筛选")
):
    try:
        init_statute_database()
        conn = get_db_connection()
        cursor = conn.cursor()

        sql = "SELECT * FROM laws WHERE 1=1"
        params: List[Any] = []
        if domain and domain != "全部":
            sql += " AND domain = ?"
            params.append(domain)
        if hierarchy:
            sql += " AND hierarchy = ?"
            params.append(hierarchy)
        if status and status != "ALL":
            sql += " AND status = ?"
            params.append(status)

        sql += " ORDER BY hierarchy ASC, effective_date DESC"
        cursor.execute(sql, params)
        laws = [dict(r) for r in cursor.fetchall()]
        conn.close()

        return {
            "status": "success",
            "total": len(laws),
            "laws": laws
        }
    except Exception as e:
        logger.error(f"获取法规列表失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/law/{law_id}", summary="获取单部法律详情及其所有法条清单")
async def get_law_detail(law_id: str):
    try:
        init_statute_database()
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM laws WHERE id = ?", (law_id,))
        law_row = cursor.fetchone()
        if not law_row:
            conn.close()
            raise HTTPException(status_code=404, detail=f"未找到指定的法律: {law_id}")

        law_info = dict(law_row)

        cursor.execute("""
        SELECT id, law_id, part_name, chapter_name, section_name, article_no_cn, article_no_int,
               content, has_proviso, key_terms, claim_basis_type
        FROM articles
        WHERE law_id = ?
        ORDER BY article_no_int ASC, id ASC
        """, (law_id,))
        articles = [dict(r) for r in cursor.fetchall()]
        conn.close()

        return {
            "status": "success",
            "law": law_info,
            "articles": articles
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取法规详情失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/article/{article_id:path}", summary="获取单条法条详情及其完整的子母法关联网")
async def get_article_detail(article_id: str):
    try:
        detail = get_article_details_with_graph(article_id)
        if not detail:
            raise HTTPException(status_code=404, detail=f"未找到法条: {article_id}")
        return {
            "status": "success",
            "article": detail
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取法条详情失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/search", summary="三路混合检索（精确条号 + 复合短语 + FTS5 + 子母法图谱）")
async def search_statutes(req: StatuteSearchRequest):
    try:
        hits = search_statutes_hybrid(
            query=req.query,
            domain=req.domain,
            hierarchy=req.hierarchy,
            status=req.status,
            include_linked=req.include_linked,
            limit=req.limit
        )
        return {
            "status": "success",
            "query": req.query,
            "total_hits": len(hits),
            "results": hits
        }
    except Exception as e:
        logger.error(f"法典检索异常: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/import", summary="律所私有新法规/地方审判指引一键切片导入")
async def import_statute(req: StatuteImportRequest):
    try:
        result = import_custom_statute(
            law_id=req.law_id,
            full_name=req.full_name,
            short_name=req.short_name,
            hierarchy=req.hierarchy,
            promulgated_by=req.promulgated_by,
            effective_date=req.effective_date,
            domain=req.domain,
            raw_text=req.raw_text,
            summary=req.summary or ""
        )
        return {
            "status": "success",
            "message": f"法规《{req.full_name}》切片入库成功！共解析导入 {result['articles_imported']} 条法条。",
            "data": result
        }
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"导入法规失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/link", summary="手动绑定或拓展母法与司法解释子母关联图谱")
async def create_link(req: LinkCreationRequest):
    try:
        init_statute_database()
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
        INSERT OR REPLACE INTO parent_child_links (parent_article_id, child_article_id, relation_type, notes)
        VALUES (?, ?, ?, ?)
        """, (req.parent_article_id, req.child_article_id, req.relation_type, req.notes))
        conn.commit()
        conn.close()

        return {
            "status": "success",
            "message": f"成功建立子母法图谱关联: {req.parent_article_id} ➔ {req.child_article_id}"
        }
    except Exception as e:
        logger.error(f"建立子母法图谱失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reseed", summary="强制重置并重新灌装权威核心法典全集")
async def reseed_database():
    try:
        init_statute_database(force_reseed=True)
        stats = get_statute_database_stats()
        return {
            "status": "success",
            "message": "法典库与子母法图谱已全量重新灌装！",
            "stats": stats
        }
    except Exception as e:
        logger.error(f"重置法规库失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
