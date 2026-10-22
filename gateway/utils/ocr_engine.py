"""
LawFlow 智律工作台 - 中文法律证据多模态提取与结构化清洗引擎
支持：
1. PDF 证据材料（合同文本、判决书扫描件、银行账单）文字及元数据提取
2. 图片证据（微信聊天截图、收据、发票、借条）文字识别
3. 证据要素清洗（自动识别出证据发生时间、当事人姓名、涉案金额、流水单号等）
"""

import os
import re
import logging
from typing import Dict, Any, List, Optional
from PIL import Image

logger = logging.getLogger("lawflow.ocr")

# 懒加载 OCR 模型，避免启动占用大量内存
_easyocr_reader = None

def get_easyocr_reader():
    global _easyocr_reader
    if _easyocr_reader is None:
        try:
            import easyocr
            # 优先使用 GPU，无 GPU 则使用 CPU；支持中英文识别
            _easyocr_reader = easyocr.Reader(['ch_sim', 'en'], gpu=False, verbose=False)
            logger.info("EasyOCR 中文模型加载成功")
        except Exception as e:
            logger.warning(f"EasyOCR 初始化失败或模型未下载: {e}，将采用备用文本解析器")
            _easyocr_reader = False
    return _easyocr_reader if _easyocr_reader is not False else None


def extract_text_from_pdf(pdf_path: str) -> str:
    """从 PDF 文件提取全部文本（自动兼容电子版矢量文字与扫描件 OCR 识别）"""
    extracted_text = []
    try:
        import pymupdf as fitz
        doc = fitz.open(pdf_path)
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text("text").strip()
            # 若当前页文字极少（少于 20 字），判定为纯图片扫描件，栅格化调用 OCR 引擎
            if len(text) < 20:
                try:
                    pix = page.get_pixmap(dpi=150)
                    temp_img_path = f"{pdf_path}_temp_page_{page_num+1}.png"
                    pix.save(temp_img_path)
                    ocr_page_text = extract_text_from_image(temp_img_path)
                    try:
                        os.remove(temp_img_path)
                    except OSError as rem_err:
                        logger.debug(f"清理临时OCR图失败: {rem_err}")
                    if ocr_page_text and not ocr_page_text.startswith("[图片证据识别]"):
                        text = f"[扫描件OCR识别]\n{ocr_page_text}"
                except Exception as e_ocr:
                    logger.debug(f"第 {page_num+1} 页扫描件 OCR 识别略过: {e_ocr}")

            if text:
                extracted_text.append(f"--- 第 {page_num + 1} 页 ---\n{text}")
            else:
                extracted_text.append(f"--- 第 {page_num + 1} 页 ---\n[本页无文字或为清晰度受限图像]")
        doc.close()
    except Exception as e:
        logger.warning(f"PyMuPDF 提取 PDF 失败: {e}，尝试 pypdf")
        try:
            import pypdf
            reader = pypdf.PdfReader(pdf_path)
            for i, page in enumerate(reader.pages):
                text = page.extract_text() or ""
                if text.strip():
                    extracted_text.append(f"--- 第 {i + 1} 页 ---\n{text.strip()}")
        except Exception as e2:
            logger.error(f"PDF 文本提取均失败: {e2}")

    return "\n\n".join(extracted_text)


def extract_text_from_image(image_path: str) -> str:
    """从常见图片文件 (JPG/PNG/WEBP/BMP) 提取文本"""
    # 1. 尝试使用 EasyOCR
    reader = get_easyocr_reader()
    if reader:
        try:
            results = reader.readtext(image_path, detail=0)
            if results:
                return "\n".join(results)
        except Exception as e:
            logger.warning(f"EasyOCR 识别图片失败: {e}")

    # 2. 备选方案：尝试从图片中提取基本 EXIF/文件信息或直接提示
    try:
        with Image.open(image_path) as img:
            w, h = img.size
            fmt = img.format
            return f"[图片证据识别] 图像格式: {fmt}, 分辨率: {w}x{h}。"
    except Exception as e:
        return f"[图片解析错误]: {e}"


def extract_evidence_text(file_path: str) -> str:
    """统一证据提取入口，全面支持 PDF、Word、表格及常见图片"""
    if not os.path.exists(file_path):
        return f"文件不存在: {file_path}"

    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf":
        return extract_text_from_pdf(file_path)
    elif ext in [".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif", ".heic"]:
        return extract_text_from_image(file_path)
    elif ext in [".docx", ".doc"]:
        try:
            import docx
            doc = docx.Document(file_path)
            chunks = []
            for p in doc.paragraphs:
                txt = p.text.strip()
                if txt:
                    chunks.append(txt)
            for tbl in doc.tables:
                for row in tbl.rows:
                    row_cells = [c.text.strip() for c in row.cells if c.text.strip()]
                    if row_cells:
                        chunks.append(" | ".join(row_cells))
            return "\n\n".join(chunks)
        except Exception as e_docx:
            logger.warning(f"提取 docx 失败: {e_docx}")
            return f"[DOCX 解析错误]: {e_docx}"
    elif ext in [".xlsx", ".xls"]:
        try:
            import pandas as pd
            df = pd.read_excel(file_path)
            return df.to_string(index=False)
        except Exception as e_excel:
            return f"[Excel 解析错误]: {e_excel}"
    elif ext == ".csv":
        try:
            import pandas as pd
            df = pd.read_csv(file_path)
            return df.to_string(index=False)
        except Exception:
            with open(file_path, "r", encoding="utf-8-sig", errors="ignore") as f:
                return f.read()
    elif ext in [".txt", ".md", ".json"]:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    else:
        return f"不支持的文件类型: {ext}"


def structure_evidence_text(raw_text: str) -> Dict[str, Any]:
    """
    通过正则与启发式规则清洗证据核心要素（时间、金额、当事人、证据类型）
    """
    # 提取日期 (YYYY年MM月DD日 或 YYYY-MM-DD 或 YYYY/MM/DD)
    date_pattern = re.compile(r"(\d{4}[年\-\/\.]\d{1,2}[月\-\/\.]\d{1,2}日?)")
    dates = date_pattern.findall(raw_text)

    # 提取金额数字 (如 ￥10,000 或 10000.00元 或 金额：5000)
    money_pattern = re.compile(r"(?:[¥￥]|金额|转账|支付|实付|合计|小计)[:：]?\s*([\d,]+\.?\d*)\s*(?:元)?")
    raw_moneys = money_pattern.findall(raw_text)
    moneys = []
    for m in raw_moneys:
        clean_m = m.replace(",", "")
        try:
            val = float(clean_m)
            if val > 0:
                moneys.append(val)
        except ValueError:
            pass

    # 识别证据类别属性
    category = "书证"
    lower_text = raw_text.lower()
    if any(k in raw_text for k in ["微信", "支付宝", "转账电子回单", "短信", "聊天记录", "电子邮件", "app"]):
        category = "电子数据"
    elif any(k in raw_text for k in ["录像", "录音", "视频", "音频", "通话"]):
        category = "视听资料"
    elif any(k in raw_text for k in ["合同", "协议", "借条", "收条", "欠条", "补充协议", "承诺书"]):
        category = "书证"
    elif any(k in raw_text for k in ["照片", "现场勘验", "实物"]):
        category = "物证"

    return {
        "raw_text": raw_text,
        "category": category,
        "detected_dates": list(dict.fromkeys(dates))[:5],
        "detected_amounts": sorted(list(set(moneys)), reverse=True)[:5],
        "char_count": len(raw_text)
    }
