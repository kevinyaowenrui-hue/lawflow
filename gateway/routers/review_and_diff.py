# -*- coding: utf-8 -*-
"""
LawFlow 智律工作台 - 第三批功能路由：
1. 矩阵式批量阅卷表与单元格局部重刷 (Harvey Review Tables & Cell Refresh)
2. 双栏穿透式原文定位 (Split-Screen Source Grounding)
3. 合同多版本比对与模板偏离度比对 (Multi-Version Clause Alignment & Playbook Deviation)
"""

import os
import re
import base64
import logging
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, Field
import pymupdf as fitz

from gateway.utils.review_table_engine import (
    list_review_tables,
    get_review_table,
    create_review_table,
    add_column_to_table,
    delete_column_from_table,
    add_row_to_table,
    run_single_cell_refresh,
    run_column_refresh,
    run_all_table_extraction,
    export_review_table_to_csv,
    export_review_table_to_xlsx
)
from gateway.utils.version_comparator import (
    compare_contract_versions,
    export_version_diff_docx
)
from gateway.utils.matter_vault_db import get_matter_by_id

logger = logging.getLogger("lawflow.review_and_diff")
router = APIRouter(tags=["第三批：批量阅卷表与多版本对比"])


# ==============================================================================
# Pydantic 请求模型
# ==============================================================================

class ReviewTableCreateReq(BaseModel):
    title: str = Field(..., description="阅卷表名称")
    description: Optional[str] = Field("", description="审查目的说明")
    columns: Optional[List[Dict[str, Any]]] = Field(None, description="自定义初始列")


class ReviewTableAddColumnReq(BaseModel):
    name: str = Field(..., description="列名称/要素名称")
    instruction: str = Field(..., description="该要素的提取 Prompt 指令")
    type: str = Field("text", description="字段类型: text / date / currency")


class ReviewTableAddRowReq(BaseModel):
    doc_title: str = Field(..., description="材料名称")
    doc_type: str = Field("evidence", description="材料类型")
    content_text: str = Field(..., description="材料正文")
    doc_id: Optional[str] = None


class VersionCompareReq(BaseModel):
    base_title: str = Field(default="标准模板/原版本", description="基准版本标题")
    base_text: str = Field(..., description="基准版本合同正文")
    target_title: str = Field(default="对方修改版/新版本", description="目标版本标题")
    target_text: str = Field(..., description="相对方修改版合同正文")


# ==============================================================================
# 1. 矩阵式批量阅卷表 (Harvey Review Tables) 路由
# ==============================================================================

@router.get("/api/v1/vault/matters/{matter_id}/review-tables", summary="获取案件下的全部阅卷表清单")
async def api_list_matter_review_tables(matter_id: str):
    tables = list_review_tables(matter_id)
    return {
        "status": "success",
        "matter_id": matter_id,
        "total": len(tables),
        "tables": tables
    }


@router.get("/api/v1/vault/review-tables/{table_id}", summary="获取单张阅卷表完整数据网格")
async def api_get_review_table_data(table_id: str):
    table = get_review_table(table_id)
    if not table:
        raise HTTPException(status_code=404, detail="阅卷表不存在")
    return {
        "status": "success",
        "table": table
    }


@router.post("/api/v1/vault/matters/{matter_id}/review-tables", summary="为案件创建新阅卷表")
async def api_create_matter_review_table(matter_id: str, req: ReviewTableCreateReq):
    table = create_review_table(
        matter_id=matter_id,
        title=req.title,
        description=req.description or "",
        columns=req.columns
    )
    return {
        "status": "success",
        "message": f"阅卷表【{table['title']}】创建成功，已自动关联案件材料",
        "table": table
    }


@router.post("/api/v1/vault/review-tables/{table_id}/columns", summary="动态新增提取要素列")
async def api_add_review_table_column(table_id: str, req: ReviewTableAddColumnReq):
    try:
        updated = add_column_to_table(
            table_id=table_id,
            col_name=req.name,
            instruction=req.instruction,
            col_type=req.type
        )
        return {
            "status": "success",
            "message": f"成功追加提取列【{req.name}】",
            "table": updated
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api/v1/vault/review-tables/{table_id}/columns/{col_id}", summary="删除指定提取列")
async def api_delete_review_table_column(table_id: str, col_id: str):
    try:
        updated = delete_column_from_table(table_id, col_id)
        return {
            "status": "success",
            "message": "提取列删除成功",
            "table": updated
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/vault/review-tables/{table_id}/rows", summary="向阅卷表追加文档行")
async def api_add_review_table_row(table_id: str, req: ReviewTableAddRowReq):
    try:
        updated = add_row_to_table(
            table_id=table_id,
            doc_title=req.doc_title,
            doc_type=req.doc_type,
            content_text=req.content_text,
            doc_id=req.doc_id or ""
        )
        return {
            "status": "success",
            "message": f"案卷【{req.doc_title}】已成功入表",
            "table": updated
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/vault/review-tables/{table_id}/cells/{row_id}/{col_id}/refresh", summary="单元格局部即时重刷")
async def api_refresh_single_cell(table_id: str, row_id: str, col_id: str):
    try:
        res = await run_single_cell_refresh(table_id, row_id, col_id)
        return {
            "status": "success",
            "message": "单元格局部重算完成",
            **res
        }
    except Exception as e:
        logger.error(f"单元格局部重刷失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/vault/review-tables/{table_id}/columns/{col_id}/refresh", summary="列级全局重跑")
async def api_refresh_column(table_id: str, col_id: str):
    try:
        updated = await run_column_refresh(table_id, col_id)
        return {
            "status": "success",
            "message": "该列所有文档要素重刷完成",
            "table": updated
        }
    except Exception as e:
        logger.error(f"列级重跑失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/vault/review-tables/{table_id}/run-all", summary="全表批量并发抽取")
async def api_run_all_review_table(table_id: str):
    try:
        updated = await run_all_table_extraction(table_id)
        return {
            "status": "success",
            "message": "全表要素批量并发抽取完毕",
            "table": updated
        }
    except Exception as e:
        logger.error(f"全表批量抽取失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/vault/review-tables/{table_id}/export/csv", summary="导出阅卷表为 CSV")
async def api_export_review_table_csv(table_id: str):
    csv_text = export_review_table_to_csv(table_id)
    if not csv_text:
        raise HTTPException(status_code=404, detail="阅卷表无数据可导出")
    return Response(
        content=csv_text.encode("utf-8-sig"),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=review_table_{table_id}.csv"}
    )


@router.get("/api/v1/vault/review-tables/{table_id}/export/xlsx", summary="导出阅卷表为规范带样式的 Excel (.xlsx)")
async def api_export_review_table_xlsx(table_id: str):
    xlsx_bytes = export_review_table_to_xlsx(table_id)
    if not xlsx_bytes:
        raise HTTPException(status_code=404, detail="阅卷表无数据可导出")
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=review_table_{table_id}.xlsx"}
    )



# ==============================================================================
# 2. 双栏穿透式原文定位 (Split-Screen Source Grounding) 路由
# ==============================================================================

# ==============================================================================
# 2. 双栏穿透式原文定位与案卷原件高分辨率切片 (Source Grounding & Visual Crop)
# ==============================================================================

def _cjk_font_candidates() -> list:
    """通过 paths 模块解析字体候选，避免写死开发者本机盘符。"""
    from gateway.core.paths import get_cjk_font_candidates
    return get_cjk_font_candidates()



def generate_source_grounding_visual_crop(
    target_doc: Dict[str, Any],
    full_text: str,
    page_no: int = 1,
    highlight_snippet: str = ""
) -> Dict[str, Any]:
    """
    使用 PyMuPDF 对案卷原件 (PDF/扫描图/合成存证页) 进行高分辨率切片与琥珀金高亮加框。
    返回 base64 编码的 PNG 切片图片及严格边界框坐标，让律师无需离开界面即可直视案卷纸质证据！
    """
    file_path = target_doc.get("file_path") or ""
    doc = None
    is_synthesized = False

    # 1. 尝试打开磁盘物理原件
    if file_path and os.path.exists(file_path):
        ext = os.path.splitext(file_path)[1].lower()
        try:
            if ext == ".pdf":
                doc = fitz.open(file_path)
            elif ext in [".png", ".jpg", ".jpeg", ".bmp", ".webp"]:
                img_doc = fitz.open(file_path)
                pdf_bytes = img_doc.convert_to_pdf()
                img_doc.close()
                doc = fitz.open("pdf", pdf_bytes)
        except Exception as e:
            logger.warning(f"打开原件文件失败 ({file_path}): {e}，回退至合成存证页面")

    # 2. 若无磁盘物理原件，合成标准司法公文存证页面
    if doc is None:
        is_synthesized = True
        doc = fitz.open()
        font_path = next((f for f in _cjk_font_candidates() if os.path.exists(f)), None)

        page_marker = f"--- 第 {page_no} 页 ---"
        page_text = full_text
        if page_marker in full_text:
            parts = full_text.split(page_marker)
            if len(parts) > 1:
                page_text = parts[1].split("--- 第 ")[0].strip()

        page = doc.new_page(width=595, height=842)
        font_name = "china-s"
        if font_path:
            font_name = "cjk"
            page.insert_font(fontname="cjk", fontfile=font_path)

        doc_name = target_doc.get("title") or target_doc.get("doc_title", "案卷证据材料")
        page.insert_textbox(
            fitz.Rect(54, 30, 541, 50),
            f"LawFlow 卷宗存证库 · {doc_name}",
            fontsize=9,
            fontname=font_name,
            color=(0.4, 0.45, 0.5)
        )
        page.draw_line(fitz.Point(54, 55), fitz.Point(541, 55), color=(0.82, 0.82, 0.82), width=0.8)
        page.insert_textbox(fitz.Rect(54, 75, 541, 750), page_text, fontsize=11, fontname=font_name, align=0)
        footer_str = f"卷宗存证凭据 · 第 {page_no} 页 · 符合司法审判证据真实性溯源标准"
        page.insert_textbox(fitz.Rect(54, 800, 541, 820), footer_str, fontsize=8, fontname=font_name, align=1, color=(0.5, 0.5, 0.5))

    page_idx = max(0, min(page_no - 1, len(doc) - 1))
    page = doc[page_idx]
    pw = page.rect.width
    ph = page.rect.height

    # 3. 稳健定位检索与跨行折行碎片组合
    rects = []
    clean_h = highlight_snippet.strip() if highlight_snippet else ""
    if clean_h:
        # A. 精确匹配
        rects = list(page.search_for(clean_h))
        # B. 若跨行拆分，按 4 字符滑动检索
        if not rects and len(clean_h) >= 4:
            step = 4
            for i in range(0, min(len(clean_h), 40), step):
                sub = clean_h[i:i+step]
                if len(sub) >= 2:
                    r = page.search_for(sub)
                    if r:
                        rects.extend(r)
        # C. 标点切分主谓短语检索
        if not rects and len(clean_h) >= 6:
            parts = [p.strip() for p in re.split(r'[，。；：\s]+', clean_h) if len(p.strip()) >= 3]
            for p in parts[:3]:
                r = page.search_for(p)
                if r:
                    rects.extend(r)
                    break

    bounding_boxes = []
    for r in rects:
        bounding_boxes.append({
            "x0": round(r.x0, 1),
            "y0": round(r.y0, 1),
            "x1": round(r.x1, 1),
            "y1": round(r.y1, 1),
            "width": round(r.width, 1),
            "height": round(r.height, 1)
        })
        # 绘制半透明琥珀金遮罩 (天平琥珀金 #C58532)
        page.draw_rect(r, color=(0.77, 0.52, 0.2), fill=(1.0, 0.85, 0.4), fill_opacity=0.35, width=1.5)

    if rects:
        rx0 = min(r.x0 for r in rects)
        ry0 = min(r.y0 for r in rects)
        rx1 = max(r.x1 for r in rects)
        ry1 = max(r.y1 for r in rects)

        pad_top = 45
        pad_bottom = 55
        pad_x = 35
        crop_y0 = max(0, ry0 - pad_top)
        crop_y1 = min(ph, ry1 + pad_bottom)
        crop_x0 = max(0, rx0 - pad_x)
        crop_x1 = min(pw, rx1 + pad_x)

        if (crop_y1 - crop_y0) < 140:
            deficit = 140 - (crop_y1 - crop_y0)
            crop_y0 = max(0, crop_y0 - deficit / 2)
            crop_y1 = min(ph, crop_y1 + deficit / 2)

        if (crop_x1 - crop_x0) < 300:
            deficit = 300 - (crop_x1 - crop_x0)
            crop_x0 = max(0, crop_x0 - deficit / 2)
            crop_x1 = min(pw, crop_x1 + deficit / 2)

        crop_rect = fitz.Rect(crop_x0, crop_y0, crop_x1, crop_y1)
    else:
        crop_rect = fitz.Rect(max(0, 54 - 20), 20, min(pw, 541 + 20), min(ph, 380))

    # 4. 高清渲染 (180 DPI Retina 保证文字极度清晰锐利)
    pix = page.get_pixmap(clip=crop_rect, dpi=180)
    png_bytes = pix.tobytes("png")
    b64_str = base64.b64encode(png_bytes).decode("utf-8")
    visual_crop_base64 = f"data:image/png;base64,{b64_str}"

    total_pages = len(doc)
    doc.close()

    return {
        "visual_crop_base64": visual_crop_base64,
        "bounding_boxes": bounding_boxes,
        "crop_rect": {
            "x0": round(crop_rect.x0, 1),
            "y0": round(crop_rect.y0, 1),
            "x1": round(crop_rect.x1, 1),
            "y1": round(crop_rect.y1, 1),
            "width": round(crop_rect.width, 1),
            "height": round(crop_rect.height, 1)
        },
        "page_count": total_pages,
        "highlighted": len(rects) > 0,
        "is_synthesized": is_synthesized
    }


@router.get("/api/v1/vault/matters/{matter_id}/grounding/excerpt", summary="根据文档与切片角标获取原文穿透定位及高分辨率切片")
async def api_get_source_grounding_excerpt(
    matter_id: str,
    doc_title: Optional[str] = Query(None, description="材料名称"),
    page_no: int = Query(1, description="页码"),
    query_text: Optional[str] = Query(None, description="匹配原文片段")
):
    matter = get_matter_by_id(matter_id)
    if not matter:
        raise HTTPException(status_code=404, detail="案件不存在")

    docs = matter.get("documents", [])
    target_doc = None
    if doc_title:
        # 优先全字或双向包含匹配
        target_doc = next((d for d in docs if (doc_title in (d.get("title") or d.get("doc_title") or "") or (d.get("title") or d.get("doc_title") or "") in doc_title or doc_title == d.get("doc_id"))), None)

    if not target_doc:
        return {
            "status": "success",
            "found": False,
            "message": f"当前案件空间中未匹配到名称为【{doc_title}】的案卷原件",
            "doc_title": doc_title or "未知材料",
            "full_content": "暂无原文内容",
            "highlight_snippet": query_text or "",
            "visual_crop_base64": None,
            "bounding_boxes": []
        }

    full_text = target_doc.get("text_content") or target_doc.get("content_text", "")
    highlight = (query_text or "").strip()
    
    # 优先在目标页码范围内高亮
    page_marker = f"--- 第 {page_no} 页 ---"
    start_pos = -1
    if page_marker in full_text and highlight:
        p_idx = full_text.find(page_marker)
        sub_pos = full_text[p_idx:].find(highlight)
        if sub_pos >= 0:
            start_pos = p_idx + sub_pos

    if start_pos < 0 and highlight:
        start_pos = full_text.find(highlight)

    # 生成高分辨率原件视觉切片及严格边界框
    visual_info = generate_source_grounding_visual_crop(
        target_doc=target_doc,
        full_text=full_text,
        page_no=page_no,
        highlight_snippet=highlight
    )

    return {
        "status": "success",
        "found": True,
        "doc_id": target_doc.get("doc_id", ""),
        "doc_title": target_doc.get("title") or target_doc.get("doc_title", ""),
        "doc_type": target_doc.get("doc_type", "evidence"),
        "page_no": page_no,
        "page_count": visual_info["page_count"],
        "full_content": full_text,
        "highlight_snippet": highlight,
        "char_start": start_pos,
        "char_end": start_pos + len(highlight) if start_pos >= 0 else -1,
        "visual_crop_base64": visual_info["visual_crop_base64"],
        "bounding_boxes": visual_info["bounding_boxes"],
        "crop_rect": visual_info["crop_rect"],
        "is_synthesized": visual_info["is_synthesized"]
    }


# ==============================================================================
# 3. 合同多版本比对与模板偏离度分析 (Multi-Version & Deviation) 路由
# ==============================================================================

@router.post("/api/v1/contract/compare-versions", summary="多版本合同条款对齐与偏离度比对")
async def api_compare_contract_versions(req: VersionCompareReq):
    try:
        res = compare_contract_versions(
            base_title=req.base_title,
            base_text=req.base_text,
            target_title=req.target_title,
            target_text=req.target_text
        )
        return {
            "status": "success",
            "message": f"双版本条款对齐与偏离度比对完成！合规指数: {res['stats']['deviation_score']} 分",
            "comparison": res
        }
    except Exception as e:
        logger.error(f"多版本合同比对失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/contract/export-version-diff", summary="导出双版本比对修订版 Word (.docx)")
async def api_export_version_diff(req: VersionCompareReq):
    try:
        comparison = compare_contract_versions(
            base_title=req.base_title,
            base_text=req.base_text,
            target_title=req.target_title,
            target_text=req.target_text
        )
        docx_path = export_version_diff_docx(comparison)
        filename = os.path.basename(docx_path)
        return {
            "status": "success",
            "message": "Word 原生修订模式文档已生成",
            "filename": filename,
            "download_url": f"/static/generated/{filename}",
            "stats": comparison["stats"]
        }
    except Exception as e:
        logger.error(f"导出比对 Word 失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
