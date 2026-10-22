"""
LawFlow 智律工作台 - 司法级全格式离线转码引擎 (Filee CLI 增强 + 本地原生快速回退)
特点：
1. 100% 离线隐私保护：不上传任何第三方云端，恪守《律师执业行为规范》与涉案信息保密红线。
2. 双轨架构：
   - 优先探测并调度 Filee CLI (C# .NET 开源引擎)，支持 180+ ~ 244 种多媒体及工业文档格式；
   - 缺省无感回退至 LawFlow 内置原生司法转码器，原生支持 iPhone HEIC/HEIF、TIFF、微信截图、
     多图合并法院 A4 举证册（加盖贝茨码）、Word 文档、CSV/Excel 银行流水与标准音频流。
"""

import os
import sys
import shutil
import subprocess
import logging
import time
import uuid
from typing import List, Dict, Any, Optional
from PIL import Image, ImageOps


class AudioConversionUnavailable(Exception):
    """未安装 pydub/ffmpeg 时抛出，路由映射为 HTTP 501。"""


def _transcode_output_name(base_name: str, ext: str) -> str:
    """输出文件名：可读前缀 + uuid，避免同一秒覆盖。"""
    safe_base = (base_name or "file").strip() or "file"
    e = ext.lstrip(".").lower()
    return f"{safe_base}_转码_{uuid.uuid4().hex[:8]}.{e}"

# 注册 HEIC/HEIF 解码支持
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    HEIF_SUPPORTED = True
except Exception:
    HEIF_SUPPORTED = False

import pymupdf as fitz

from gateway.core.paths import get_base_dir, get_generated_dir, get_uploads_dir

logger = logging.getLogger("lawflow.converter")


def _tools_filee_dir() -> str:
    path = get_base_dir() / "tools" / "filee"
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def find_filee_executable() -> Optional[str]:
    """
    自动多路径探测 Filee CLI 执行程序
    """
    # 1. 显式环境变量
    env_path = os.environ.get("FILEE_PATH")
    if env_path and os.path.isfile(env_path) and os.access(env_path, os.X_OK):
        return env_path

    # 2. tools/filee/ 目录内置
    candidates = [
        os.path.join(_tools_filee_dir(), "Filee.exe"),
        os.path.join(_tools_filee_dir(), "filee.exe"),
        os.path.join(_tools_filee_dir(), "filee"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c

    # 3. 系统 PATH
    which_filee = shutil.which("filee") or shutil.which("Filee")
    if which_filee:
        return which_filee

    # 4. Windows 常见安装位置
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    program_files = os.environ.get("ProgramFiles", "")
    program_files_x86 = os.environ.get("ProgramFiles(x86)", "")
    standard_paths = [
        os.path.join(local_app_data, "Programs", "Filee", "Filee.exe"),
        os.path.join(local_app_data, "Programs", "Filee", "filee.exe"),
        os.path.join(program_files, "Filee", "Filee.exe"),
        os.path.join(program_files_x86, "Filee", "Filee.exe"),
    ]
    for sp in standard_paths:
        if sp and os.path.isfile(sp):
            return sp

    return None


def _pydub_available() -> bool:
    try:
        import pydub  # noqa: F401
        return True
    except Exception:
        return False


def _pandas_available() -> bool:
    try:
        import pandas  # noqa: F401
        return True
    except Exception:
        return False


def get_converter_status() -> Dict[str, Any]:
    """获取当前转码系统的引擎状态与实际可用格式（按依赖探测动态生成）"""
    filee_exe = find_filee_executable()
    has_filee = filee_exe is not None
    has_pydub = _pydub_available()
    has_pandas = _pandas_available()

    native_inputs = ["JPG", "JPEG", "PNG", "WEBP", "BMP", "TIFF", "GIF", "PDF", "DOCX", "TXT", "MD"]
    if HEIF_SUPPORTED:
        native_inputs = ["HEIC", "HEIF"] + native_inputs
    if has_pandas:
        native_inputs.extend(["CSV", "XLSX"])
    if has_pydub:
        native_inputs.extend(["M4A", "MP3", "WAV", "AAC", "AMR"])

    native_outputs = ["PDF", "JPG", "PNG", "WEBP", "TXT"]
    if has_pydub:
        native_outputs.extend(["WAV", "MP3"])

    presets = [
        {"id": "heic_to_pdf", "label": "手机照片(HEIC/TIFF) -> 法院立案PDF", "target": "pdf"},
        {"id": "multi_to_bates_pdf", "label": "多证据图批量合卷 (标准A4+加盖贝茨码)", "target": "pdf"},
        {"id": "txt_to_pdf", "label": "纯文本(TXT/MD) -> 法院A4 PDF", "target": "pdf"},
        {"id": "pdf_to_images", "label": "证据PDF各页一键拆解为高清图片", "target": "png"},
    ]
    if has_pandas:
        presets.append({"id": "table_to_court_pdf", "label": "银行流水(CSV/XLSX) -> 证据对照表格PDF", "target": "pdf"})
    if has_pydub:
        presets.append({"id": "audio_to_court_mp3", "label": "谈话录音(M4A/AMR) -> 司法标准MP3", "target": "mp3"})

    return {
        "filee_installed": has_filee,
        "filee_path": filee_exe,
        "engine_mode": "filee_accelerated" if has_filee else "native_legal",
        "engine_label": "Filee 离线全格式引擎 (244+ 格式)" if has_filee else "LawFlow 司法内置快速转码引擎",
        "heif_supported": HEIF_SUPPORTED,
        "pydub_available": has_pydub,
        "tools_filee_dir": _tools_filee_dir(),
        "supported_inputs": native_inputs + (["180+ 工业/CAD/HWP/音视频 (Filee已解锁)"] if has_filee else []),
        "supported_outputs": native_outputs,
        "quick_presets": presets,
        "setup_guide": "若需转换涉外HWP、工程CAD或生僻音视频，可将 Filee.exe 绿色版解压放入 tools/filee 目录即可无缝增强。音频转换另需 pydub 与 ffmpeg（见 requirements-optional.txt）。"
    }


def convert_images_to_court_pdf(
    input_paths: List[str],
    output_filename: str,
    bates_prefix: Optional[str] = "证据",
    stamp_bates: bool = True
) -> Dict[str, Any]:
    """
    将单张或多张图片（支持 HEIC/HEIF/JPG/PNG/WEBP/TIFF/BMP）按法院标准排版为 A4 页面 PDF，
    并可选在右上角加盖贝茨编码（如：证据1 - 第 1 页）
    """
    merged_doc = fitz.open()
    total_pages = 0
    a4_w, a4_h = 595, 842  # 标准 A4 尺寸 (72 DPI)
    margin = 40

    for idx, path in enumerate(input_paths, 1):
        try:
            with Image.open(path) as raw_img:
                # 自动根据 EXIF 旋转矫正（手机拍照常见 90度/270度 翻转问题）
                img = ImageOps.exif_transpose(raw_img)
                w, h = img.size

                # 临时保存为标准 RGB PNG，供 PyMuPDF 嵌入
                temp_png = os.path.join(str(get_uploads_dir()), f"temp_trans_{uuid.uuid4().hex[:8]}_{idx}.png")
                # 若为 RGBA 或包含透明通道，合成白色底色
                if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                    bg = Image.new("RGB", img.size, (255, 255, 255))
                    bg.paste(img, mask=img.convert("RGBA").split()[3])
                    bg.save(temp_png, "PNG")
                else:
                    img.convert("RGB").save(temp_png, "PNG")

            page = merged_doc.new_page(width=a4_w, height=a4_h)
            avail_w = a4_w - 2 * margin
            avail_h = a4_h - 2 * margin - 35  # 为顶部贝茨码留出空间

            scale = min(avail_w / w, avail_h / h, 1.0)
            target_w = w * scale
            target_h = h * scale
            x0 = margin + (avail_w - target_w) / 2
            y0 = margin + 35 + (avail_h - target_h) / 2

            rect = fitz.Rect(x0, y0, x0 + target_w, y0 + target_h)
            page.insert_image(rect, filename=temp_png)

            total_pages += 1

            if stamp_bates:
                bates_text = f"{bates_prefix} - 第 {total_pages} 页"
                # 法院标准红色贝茨编码，右上角排布
                page.insert_text(
                    fitz.Point(380, 32),
                    bates_text,
                    fontname="china-s",
                    fontsize=11,
                    color=(0.82, 0.12, 0.12)
                )

            # 清理临时转换图
            if os.path.exists(temp_png):
                try:
                    os.remove(temp_png)
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"处理图片 {path} 失败: {e}")
            raise RuntimeError(f"文件 {os.path.basename(path)} 格式解析失败: {e}")

    out_path = os.path.join(str(get_generated_dir()), output_filename)
    merged_doc.save(out_path)
    merged_doc.close()

    file_size = os.path.getsize(out_path) if os.path.exists(out_path) else 0

    return {
        "status": "success",
        "output_filename": output_filename,
        "download_url": f"/api/documents/download/{output_filename}",
        "total_pages": total_pages,
        "file_size": file_size,
        "target_format": "pdf",
        "engine": "native_legal"
    }


def convert_pdf_to_images(pdf_path: str, output_prefix: str, fmt: str = "png") -> Dict[str, Any]:
    """将 PDF 每页渲染为高清晰度法庭质证图片"""
    doc = fitz.open(pdf_path)
    generated_files = []
    batch_tag = uuid.uuid4().hex[:8]

    for pno in range(len(doc)):
        page = doc[pno]
        # 150 DPI 高清渲染（适合法律文书文字阅读，防卡死）
        pix = page.get_pixmap(dpi=150)
        out_name = f"{output_prefix}_page_{pno + 1}_{batch_tag}.{fmt}"
        out_path = os.path.join(str(get_generated_dir()), out_name)
        pix.save(out_path)
        generated_files.append({
            "page": pno + 1,
            "filename": out_name,
            "download_url": f"/api/documents/download/{out_name}"
        })

    doc.close()

    return {
        "status": "success",
        "total_pages": len(generated_files),
        "files": generated_files,
        "target_format": fmt,
        "engine": "native_legal"
    }


def convert_txt_to_court_pdf(txt_path: str, output_filename: str) -> Dict[str, Any]:
    """将 TXT/MD 纯文本按行分页写入法院 A4 PDF（复用批次7分页逻辑思想）。"""
    try:
        with open(txt_path, "r", encoding="utf-8") as f:
            content = f.read()
    except UnicodeDecodeError:
        with open(txt_path, "r", encoding="gbk", errors="replace") as f:
            content = f.read()

    paragraphs = content.splitlines() or [content or "（空文本）"]
    # 复用 phase1 分页渲染
    from gateway.routers.phase1_litigation import _pymupdf_paginated_render

    out_path = os.path.join(str(get_generated_dir()), output_filename)
    ok = _pymupdf_paginated_render(paragraphs, out_path)
    if not ok:
        raise RuntimeError("TXT 转 PDF 失败")
    return {
        "status": "success",
        "output_filename": output_filename,
        "download_url": f"/api/documents/download/{output_filename}",
        "file_size": os.path.getsize(out_path),
        "target_format": "pdf",
        "engine": "native_legal",
    }


def convert_table_to_court_pdf(table_path: str, output_filename: str) -> Dict[str, Any]:
    """
    将银行流水、借贷账目 (CSV / XLSX / XLS) 渲染为规范整洁的法庭证据对照表格 PDF
    """
    import pandas as pd
    ext = os.path.splitext(table_path)[1].lower()
    if ext == ".csv":
        df = pd.read_csv(table_path, encoding="utf-8-sig", on_bad_lines="skip")
    else:
        df = pd.read_excel(table_path)

    # 替换 NaN
    df = df.fillna("")
    # 限制前 200 行，防止巨型文件导致死锁
    df_sample = df.head(200)

    # 用 HTML/CSS 样式排版，再通过 PyMuPDF Story 或直接生成
    doc = fitz.open()
    a4_w, a4_h = 842, 595  # 横向 A4，更适合展示多列财务账目流水
    page = doc.new_page(width=a4_w, height=a4_h)

    # 标题
    title = f"【法庭举证附表】{os.path.splitext(os.path.basename(table_path))[0]}"
    page.insert_text(fitz.Point(30, 35), title, fontname="china-s", fontsize=13, color=(0.1, 0.15, 0.25))

    # 简易表格绘制：横向 A4 适配更多财务列
    headers = [str(c) for c in df_sample.columns][:14]  # 拓展最多前 14 列
    col_width = (a4_w - 60) / max(len(headers), 1)

    y = 65
    # 表头底色
    page.draw_rect(fitz.Rect(30, y - 15, a4_w - 30, y + 5), fill=(0.92, 0.94, 0.96), color=(0.8, 0.85, 0.9))
    for i, h in enumerate(headers):
        page.insert_text(fitz.Point(35 + i * col_width, y), str(h)[:20], fontname="china-s", fontsize=9.0, color=(0.15, 0.2, 0.3))

    y += 18
    for row_idx, row in df_sample.iterrows():
        if y > a4_h - 40:
            page = doc.new_page(width=a4_w, height=a4_h)
            y = 45

        # 斑马纹
        if row_idx % 2 == 1:
            page.draw_rect(fitz.Rect(30, y - 13, a4_w - 30, y + 4), fill=(0.98, 0.98, 0.99))

        for col_idx, h in enumerate(headers):
            val = str(row[h]).strip()
            # 保证银行卡号 (16-19位) 和流水号完整显示，动态调整字号
            f_size = 7.5 if len(val) > 18 else 8.5
            page.insert_text(fitz.Point(35 + col_idx * col_width, y), val[:36], fontname="china-s", fontsize=f_size, color=(0.25, 0.3, 0.35))

        y += 16

    out_path = os.path.join(str(get_generated_dir()), output_filename)
    doc.save(out_path)
    doc.close()

    return {
        "status": "success",
        "output_filename": output_filename,
        "download_url": f"/api/documents/download/{output_filename}",
        "total_rows": len(df_sample),
        "target_format": "pdf",
        "engine": "native_legal"
    }


def execute_filee_cli_conversion(
    input_path: str,
    target_format: str,
    output_dir: str
) -> Optional[str]:
    """
    通过 Filee CLI 执行转码 (若已安装)
    """
    filee_exe = find_filee_executable()
    if not filee_exe:
        return None

    try:
        # Filee CLI 参数: filee <input> -t <target> -o <output_dir>
        cmd = [filee_exe, input_path, "-t", target_format.lower(), "-o", output_dir]
        logger.info(f"调用 Filee CLI 转码: {' '.join(cmd)}")
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if res.returncode == 0:
            # 推测生成的文件名
            base_name = os.path.splitext(os.path.basename(input_path))[0]
            expected_out = os.path.join(output_dir, f"{base_name}.{target_format.lower()}")
            if os.path.exists(expected_out):
                return expected_out
            # 搜索 output_dir 下最新生成的文件
            files = [os.path.join(output_dir, f) for f in os.listdir(output_dir) if f.lower().endswith(f".{target_format.lower()}")]
            if files:
                files.sort(key=os.path.getmtime, reverse=True)
                return files[0]
        else:
            logger.warning(f"Filee CLI 转码返回非零状态: {res.stderr}")
    except Exception as e:
        logger.warning(f"执行 Filee CLI 异常: {e}")

    return None


def convert_file_unified(
    file_path: str,
    target_format: str,
    bates_prefix: Optional[str] = "证据",
    stamp_bates: bool = True
) -> Dict[str, Any]:
    """
    统一入口：双轨自适应转换
    """
    target_format = target_format.lower().strip().replace(".", "")
    src_ext = os.path.splitext(file_path)[1].lower().replace(".", "")
    base_name = os.path.splitext(os.path.basename(file_path))[0]
    out_filename = _transcode_output_name(base_name, target_format)

    # 1. 尝试优先使用 Filee CLI
    filee_exe = find_filee_executable()
    if filee_exe:
        filee_out = execute_filee_cli_conversion(file_path, target_format, str(get_generated_dir()))
        if filee_out and os.path.exists(filee_out):
            # 重命名为带 uuid 的规范文件名，避免覆盖
            dest_name = _transcode_output_name(base_name, target_format)
            dest_path = os.path.join(str(get_generated_dir()), dest_name)
            if os.path.abspath(filee_out) != os.path.abspath(dest_path):
                try:
                    shutil.move(filee_out, dest_path)
                    filee_out = dest_path
                except Exception:
                    dest_name = os.path.basename(filee_out)
            return {
                "status": "success",
                "output_filename": dest_name,
                "download_url": f"/api/documents/download/{dest_name}",
                "file_size": os.path.getsize(filee_out),
                "target_format": target_format,
                "engine": "filee"
            }

    # 2. 本地原生司法转码回退处理
    # 场景 A: 图片 (HEIC/TIFF/JPG/PNG...) 转 法院标准 PDF
    if src_ext in ["heic", "heif", "jpg", "jpeg", "png", "webp", "bmp", "tiff", "gif"] and target_format == "pdf":
        return convert_images_to_court_pdf(
            input_paths=[file_path],
            output_filename=out_filename,
            bates_prefix=bates_prefix,
            stamp_bates=stamp_bates
        )

    # 场景 B: 图片转格式 (如 HEIC -> JPG, TIFF -> PNG)
    elif src_ext in ["heic", "heif", "jpg", "jpeg", "png", "webp", "bmp", "tiff", "gif"] and target_format in ["jpg", "jpeg", "png", "webp"]:
        out_path = os.path.join(str(get_generated_dir()), out_filename)
        with Image.open(file_path) as raw_img:
            img = ImageOps.exif_transpose(raw_img)
            if target_format in ["jpg", "jpeg"] and img.mode in ("RGBA", "LA", "P"):
                bg = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode == "RGBA":
                    bg.paste(img, mask=img.split()[3])
                else:
                    bg.paste(img)
                bg.save(out_path, "JPEG", quality=92)
            else:
                img.save(out_path)
        return {
            "status": "success",
            "output_filename": out_filename,
            "download_url": f"/api/documents/download/{out_filename}",
            "file_size": os.path.getsize(out_path),
            "target_format": target_format,
            "engine": "native_legal"
        }

    # 场景 C: PDF 转各页高清图片 (PDF -> PNG)
    elif src_ext == "pdf" and target_format in ["png", "jpg", "jpeg"]:
        return convert_pdf_to_images(file_path, base_name, target_format)

    # 场景 D: 表格 (CSV/XLSX) 转 法庭证据对照表 PDF
    elif src_ext in ["csv", "xlsx", "xls"] and target_format == "pdf":
        return convert_table_to_court_pdf(file_path, out_filename)

    # 场景 D2: TXT/MD → PDF
    elif src_ext in ["txt", "md"] and target_format == "pdf":
        return convert_txt_to_court_pdf(file_path, out_filename)

    # 场景 E: Word (.docx) 转 PDF / TXT
    elif src_ext == "docx" and target_format == "pdf":
        # 尝试提取段落与表格，使用 PyMuPDF 排版为标准法院文书 PDF
        import docx
        doc_obj = docx.Document(file_path)
        pdf_doc = fitz.open()
        a4_w, a4_h = 595, 842
        page = pdf_doc.new_page(width=a4_w, height=a4_h)
        y = 50
        page.insert_text(fitz.Point(50, y), f"【案件文书】{base_name}", fontname="china-s", fontsize=14, color=(0.1, 0.15, 0.25))
        y += 30

        for para in doc_obj.paragraphs:
            text = para.text.strip()
            if not text:
                continue
            if y > a4_h - 50:
                page = pdf_doc.new_page(width=a4_w, height=a4_h)
                y = 50
            # 自动折行
            rect = fitz.Rect(50, y, a4_w - 50, a4_h - 40)
            page.insert_textbox(rect, text, fontname="china-s", fontsize=11, color=(0.2, 0.2, 0.2))
            y += max(20, int(len(text) / 35 * 18) + 10)

        out_path = os.path.join(str(get_generated_dir()), out_filename)
        pdf_doc.save(out_path)
        pdf_doc.close()

        return {
            "status": "success",
            "output_filename": out_filename,
            "download_url": f"/api/documents/download/{out_filename}",
            "file_size": os.path.getsize(out_path),
            "target_format": "pdf",
            "engine": "native_legal"
        }

    # 场景 F: 音频处理
    elif src_ext in ["m4a", "amr", "wav", "mp3", "aac", "flac"] and target_format in ["mp3", "wav"]:
        out_path = os.path.join(str(get_generated_dir()), out_filename)
        try:
            from pydub import AudioSegment
        except ImportError as e:
            raise AudioConversionUnavailable(
                "音频转换需要安装 pydub 与 ffmpeg（见 requirements-optional.txt）"
            ) from e
        try:
            audio = AudioSegment.from_file(file_path)
            audio.export(out_path, format=target_format)
            return {
                "status": "success",
                "output_filename": out_filename,
                "download_url": f"/api/documents/download/{out_filename}",
                "file_size": os.path.getsize(out_path),
                "duration_seconds": round(len(audio) / 1000.0, 2),
                "target_format": target_format,
                "engine": "native_legal"
            }
        except AudioConversionUnavailable:
            raise
        except Exception as e:
            logger.warning(f"pydub 音频转码失败: {e}")
            if src_ext == target_format:
                shutil.copyfile(file_path, out_path)
                return {
                    "status": "success",
                    "output_filename": out_filename,
                    "download_url": f"/api/documents/download/{out_filename}",
                    "file_size": os.path.getsize(out_path),
                    "target_format": target_format,
                    "engine": "native_legal"
                }
            raise AudioConversionUnavailable(
                "音频转换需要安装 pydub 与 ffmpeg（见 requirements-optional.txt）"
            ) from e

    else:
        raise ValueError(f"暂不支持从 .{src_ext} 直接转换到 .{target_format}。建议将 Filee.exe 放入 tools/filee 解锁 244 种工业格式。")
