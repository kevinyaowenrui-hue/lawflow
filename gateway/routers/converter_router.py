"""
LawFlow 智律工作台 - 司法级全格式离线转码 API 路由 (converter_router)
集成：
1. GET  /api/v1/converter/status: 探测 Filee CLI 及内置司法转码引擎就绪状态
2. POST /api/v1/converter/convert: 统一文件转码入口（支持 HEIC/TIFF/PDF/Word/Excel/音视频）
3. POST /api/v1/converter/batch-merge-bates: 多证据图批量合卷为标准法院 A4 举证册（加盖贝茨码）
"""

import os
import time
import shutil
import logging
from typing import List, Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse

from gateway.utils.file_converter_engine import (
    get_converter_status,
    convert_file_unified,
    convert_images_to_court_pdf,
    convert_pdf_to_images,
    UPLOADS_DIR,
    STORAGE_DIR
)

logger = logging.getLogger("lawflow.converter_router")
router = APIRouter(prefix="/api/v1/converter", tags=["司法离线全格式转码中枢 (Filee 协同)"])


@router.get("/status", summary="获取离线转码引擎状态与格式支持列表")
async def api_get_converter_status():
    """探测 Filee CLI 路径、内置司法引擎及支持的全部文件格式"""
    return get_converter_status()


@router.post("/convert", summary="单文件/多文件统一离线转码")
async def api_convert_file(
    file: UploadFile = File(..., description="待转换的原始文件 (如 HEIC照片、录音、表格、Word等)"),
    target_format: str = Form("pdf", description="目标格式：pdf, jpg, png, mp3, wav 等"),
    bates_prefix: Optional[str] = Form("证据", description="加盖贝茨码前缀，默认'证据'"),
    stamp_bates: bool = Form(True, description="是否在右上角加盖红色法院标准贝茨页码")
):
    """
    单文件离线格式转换：
    - 支持手机 HEIC/HEIF 照片转为法院标准 A4 PDF
    - 支持多媒体音频转为司法规范 MP3/WAV
    - 支持 PDF 各页拆解为高清图片
    - 优先调度 Filee CLI 离线引擎，缺省无感回退至内置原生司法引擎
    """
    start_time = time.time()
    timestamp = int(start_time)
    safe_filename = f"upload_{timestamp}_{file.filename}"
    temp_path = os.path.join(UPLOADS_DIR, safe_filename)

    try:
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        result = convert_file_unified(
            file_path=temp_path,
            target_format=target_format,
            bates_prefix=bates_prefix,
            stamp_bates=stamp_bates
        )

        result["elapsed_ms"] = int((time.time() - start_time) * 1000)
        result["original_filename"] = file.filename
        return result

    except Exception as e:
        logger.error(f"转码失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"离线转码失败: {str(e)}")

    finally:
        # 清理原始上传临时文件（保留转换好的成品于 storage/generated）
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass


@router.post("/batch-merge-bates", summary="多源证据图批量合卷为单一 A4 举证册 (加盖贝茨码)")
async def api_batch_merge_evidence(
    files: List[UploadFile] = File(..., description="多张微信截图、手机拍照(HEIC/JPG)、扫描件"),
    evidence_label: str = Form("原告证据", description="贝茨编码前缀，如'原告证据一'或'证据1'"),
    stamp_bates: bool = Form(True, description="是否右上角加盖贝茨页码")
):
    """
    批量接收手机拍照 (含 HEIC/HEIF/TIFF/PNG/JPG/WEBP):
    1. 自动矫正手机 EXIF 拍摄方向；
    2. 按等比缩放规范置入标准 A4 页面；
    3. 在每页右上角自动生成红色法院贝茨页码（如：原告证据一 - 第 1 页）；
    4. 导出为符合各级人民法院立案与质证标准的单一合卷 PDF。
    """
    start_time = time.time()
    timestamp = int(start_time)
    saved_paths = []

    try:
        for idx, f in enumerate(files, 1):
            tmp_name = f"batch_{timestamp}_{idx}_{f.filename}"
            tmp_p = os.path.join(UPLOADS_DIR, tmp_name)
            with open(tmp_p, "wb") as buf:
                shutil.copyfileobj(f.file, buf)
            saved_paths.append(tmp_p)

        merged_pdf_name = f"合卷举证册_{evidence_label}_{timestamp}.pdf"
        result = convert_images_to_court_pdf(
            input_paths=saved_paths,
            output_filename=merged_pdf_name,
            bates_prefix=evidence_label,
            stamp_bates=stamp_bates
        )

        result["elapsed_ms"] = int((time.time() - start_time) * 1000)
        result["input_files_count"] = len(files)
        return result

    except Exception as e:
        logger.error(f"多图合卷失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"合卷制作失败: {str(e)}")

    finally:
        for p in saved_paths:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass
