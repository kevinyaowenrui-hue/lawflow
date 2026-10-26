# -*- coding: utf-8 -*-
"""
LawFlow 外部服务可用性探测（Stirling-PDF / Ollama）。
启动或首次使用时探测一次，结果缓存 TTL（默认 60 秒），探测超时 1 秒。
不可用时调用方应直接走本地兜底，避免逐地址长时间等待。
"""
from __future__ import annotations

import logging
import os
import sqlite3
import time
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger("lawflow.service_probe")

_cache: Dict[str, Any] = {
    "stirling": None,
    "stirling_at": 0.0,
    "ollama": None,
    "ollama_at": 0.0,
    
}


def _ttl_seconds() -> float:
    try:
        return float(os.getenv("LAWFLOW_SERVICE_PROBE_TTL", "60"))
    except ValueError:
        return 60.0


def _probe_timeout() -> float:
    try:
        return float(os.getenv("LAWFLOW_SERVICE_PROBE_TIMEOUT", "1.0"))
    except ValueError:
        return 1.0


def reset_probe_cache() -> None:
    """测试或强制刷新时清空缓存。"""
    _cache["stirling"] = None
    _cache["stirling_at"] = 0.0
    _cache["ollama"] = None
    _cache["ollama_at"] = 0.0
    _cache["health_diag"] = None
    _cache["health_diag_at"] = 0.0


def stirling_pdf_url() -> str:
    return os.getenv("STIRLING_PDF_URL", "http://127.0.0.1:8081").rstrip("/")


def ollama_base_url() -> str:
    return os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")


def probe_stirling_pdf(force: bool = False) -> bool:
    """探测配置的唯一 STIRLING_PDF_URL 是否可达。"""
    now = time.time()
    ttl = _ttl_seconds()
    if (
        not force
        and _cache["stirling"] is not None
        and (now - float(_cache["stirling_at"])) < ttl
    ):
        return bool(_cache["stirling"])

    url = stirling_pdf_url()
    ok = False
    try:
        with httpx.Client(timeout=_probe_timeout()) as client:
            # 轻量 GET；部分环境可能 404，只要端口通就算可达
            resp = client.get(f"{url}/")
            ok = resp.status_code < 500
    except Exception as e:
        logger.debug("Stirling-PDF 探测失败 (%s): %s", url, e)
        ok = False

    _cache["stirling"] = ok
    _cache["stirling_at"] = now
    return ok


def probe_ollama(force: bool = False) -> bool:
    """探测 Ollama /api/tags。"""
    now = time.time()
    ttl = _ttl_seconds()
    if (
        not force
        and _cache["ollama"] is not None
        and (now - float(_cache["ollama_at"])) < ttl
    ):
        return bool(_cache["ollama"])

    url = ollama_base_url()
    ok = False
    try:
        with httpx.Client(timeout=_probe_timeout()) as client:
            resp = client.get(f"{url}/api/tags")
            ok = resp.status_code == 200
    except Exception as e:
        logger.debug("Ollama 探测失败 (%s): %s", url, e)
        ok = False

    _cache["ollama"] = ok
    _cache["ollama_at"] = now
    return ok


def is_stirling_available(force: bool = False) -> bool:
    return probe_stirling_pdf(force=force)


def is_ollama_available(force: bool = False) -> bool:
    return probe_ollama(force=force)


def get_engine_status(*, pdf_engine: Optional[str] = None, llm_mode: Optional[str] = None) -> Dict[str, str]:
    """
    供接口返回的 engine_status。
    pdf: stirling / local_pymupdf / libreoffice
    llm: ollama / cloud / rule_fallback
    """
    pdf = pdf_engine
    if pdf is None:
        pdf = "stirling" if is_stirling_available() else "local_pymupdf"
    llm = llm_mode or ("ollama" if is_ollama_available() else "rule_fallback")
    return {"pdf": pdf, "llm": llm}


def warm_up_probes() -> Dict[str, bool]:
    """应用启动时可调用，预热缓存。"""
    return {
        "stirling": probe_stirling_pdf(force=True),
        "ollama": probe_ollama(force=True),
    }


def probe_libreoffice() -> Dict[str, Any]:
    """探测司法级 Word 转换排版引擎 LibreOffice (soffice)。"""
    soffice_path: Optional[str] = None
    try:
        from gateway.routers.phase1_litigation import _find_soffice
        soffice_path = _find_soffice()
    except Exception as e:
        logger.debug("LibreOffice 探测异常: %s", e)
        soffice_path = None

    if soffice_path:
        return {
            "status": "OK",
            "path": soffice_path,
            "version": "installed",
            "remediation": "LibreOffice (soffice) 正常就绪，支持法庭文书原格式高保真转 PDF。",
        }
    return {
        "status": "MISSING",
        "path": None,
        "remediation": "未检测到 LibreOffice (soffice)。若需完美还原复杂的 Word 排版及法庭文书，可下载安装 LibreOffice 7.x/24.x 并添加至系统 PATH；未安装时系统自动降级使用内置 PyMuPDF 纯代码分页引擎（保障 100% 可用）。",
    }


def probe_ollama_service(force: bool = False) -> Dict[str, Any]:
    """探测本地私有化大模型服务 Ollama (11434)。"""
    url = ollama_base_url()
    online = False
    try:
        online = is_ollama_available(force=force)
    except Exception as e:
        logger.debug("Ollama is_ollama_available 探测异常: %s", e)
        online = False

    if not online:
        return {
            "status": "MISSING",
            "endpoint": url,
            "installed_models": [],
            "active_model": None,
            "remediation": "本地 11434 端口未启动。若需完全离线断网大模型，请运行 'ollama serve'；若无需本地模型，可配置云端 API Key 或使用内置专家规则引擎。",
        }

    # 在线状态下查询已安装模型列表
    installed_models: list[str] = []
    try:
        with httpx.Client(timeout=_probe_timeout()) as client:
            resp = client.get(f"{url}/api/tags")
            if resp.status_code == 200:
                raw_models = resp.json().get("models", [])
                installed_models = [
                    m.get("name") for m in raw_models if isinstance(m, dict) and m.get("name")
                ]
    except Exception as e:
        logger.debug("Ollama /api/tags 查询异常: %s", e)

    if installed_models:
        return {
            "status": "OK",
            "endpoint": url,
            "installed_models": installed_models,
            "active_model": installed_models[0],
            "remediation": f"本地 Ollama 服务已在线，已加载 {len(installed_models)} 个模型 (当前可用: {installed_models[0]})。",
        }
    return {
        "status": "DEGRADED",
        "endpoint": url,
        "installed_models": [],
        "active_model": None,
        "remediation": "本地 Ollama 服务已在线，但未检测到已下载模型。请在终端执行 'ollama pull gemma4:12b' 或在模型设置中切换至云端 API。",
    }


def probe_cn_laws_kb() -> Dict[str, Any]:
    """探测权威法典与图谱底库 (cn_laws_kb.db)。"""
    try:
        from gateway.core.paths import get_laws_db_path
        db_path = get_laws_db_path()
    except Exception as e:
        return {
            "status": "MISSING",
            "path": None,
            "laws_count": 0,
            "articles_count": 0,
            "remediation": f"无法解析权威法典库路径: {e}",
        }

    if not db_path.is_file():
        return {
            "status": "MISSING",
            "path": str(db_path),
            "laws_count": 0,
            "articles_count": 0,
            "remediation": "未找到 cn_laws_kb.db 数据库文件，请检查 storage 目录读写权限并重启网关自动初始化。",
        }

    try:
        laws_count = 0
        articles_count = 0
        with sqlite3.connect(str(db_path), timeout=2.0) as conn:
            cur = conn.cursor()
            cur.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='laws'")
            has_laws = cur.fetchone()[0] > 0
            cur.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='articles'")
            has_articles = cur.fetchone()[0] > 0

            if has_laws:
                cur.execute("SELECT count(*) FROM laws")
                laws_count = cur.fetchone()[0]
            if has_articles:
                cur.execute("SELECT count(*) FROM articles")
                articles_count = cur.fetchone()[0]

        if laws_count > 0 and articles_count > 0:
            return {
                "status": "OK",
                "path": str(db_path),
                "laws_count": laws_count,
                "articles_count": articles_count,
                "remediation": f"权威法典库正常就绪，收录 {laws_count} 部法规与 {articles_count} 条法条全文检索索引。",
            }
        return {
            "status": "DEGRADED",
            "path": str(db_path),
            "laws_count": laws_count,
            "articles_count": articles_count,
            "remediation": "权威法典库表为空，请重启网关执行 init_statute_database() 从 data/legal/*.json 初始化重建。",
        }
    except Exception as e:
        logger.warning("cn_laws_kb 探测失败: %s", e)
        return {
            "status": "DEGRADED",
            "path": str(db_path),
            "laws_count": 0,
            "articles_count": 0,
            "remediation": f"权威法典库访问异常 ({e})，请排查文件锁或修复数据库。",
        }


def probe_matter_vault() -> Dict[str, Any]:
    """探测案件独立空间数据库 (matter_vault.db)。"""
    try:
        from gateway.core.paths import get_vault_db_path
        vault_path = get_vault_db_path()
    except Exception as e:
        return {
            "status": "MISSING",
            "path": None,
            "matters_count": 0,
            "remediation": f"无法解析案件空间数据库路径: {e}",
        }

    if not vault_path.is_file():
        return {
            "status": "MISSING",
            "path": str(vault_path),
            "matters_count": 0,
            "remediation": "未检测到 matter_vault.db，首次建立案件或重启网关时将自动初始化。",
        }

    try:
        matters_count = 0
        with sqlite3.connect(str(vault_path), timeout=2.0) as conn:
            cur = conn.cursor()
            cur.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='matters'")
            has_matters = cur.fetchone()[0] > 0
            if has_matters:
                cur.execute("SELECT count(*) FROM matters")
                matters_count = cur.fetchone()[0]
            else:
                return {
                    "status": "DEGRADED",
                    "path": str(vault_path),
                    "matters_count": 0,
                    "remediation": "案件空间数据库表结构未建立，重启网关时将自动补全 schema。",
                }

        return {
            "status": "OK",
            "path": str(vault_path),
            "matters_count": matters_count,
            "remediation": f"案件空间数据库正常就绪，当前在册案件 {matters_count} 件。",
        }
    except Exception as e:
        logger.warning("matter_vault 探测失败: %s", e)
        return {
            "status": "DEGRADED",
            "path": str(vault_path),
            "matters_count": 0,
            "remediation": f"案件空间数据库访问异常 ({e})，请检查文件权限或从备份恢复。",
        }


def probe_pdf_engine() -> Dict[str, Any]:
    """探测 PDF 渲染与格式转换引擎矩阵 (PyMuPDF / Stirling-PDF / LibreOffice)。"""
    has_pymupdf = False
    try:
        import pymupdf  # noqa: F401
        has_pymupdf = True
    except Exception:
        try:
            import fitz  # noqa: F401
            has_pymupdf = True
        except Exception:
            has_pymupdf = False

    has_stirling = False
    try:
        has_stirling = is_stirling_available()
    except Exception:
        has_stirling = False

    has_soffice = False
    soffice_path: Optional[str] = None
    try:
        from gateway.routers.phase1_litigation import _find_soffice
        soffice_path = _find_soffice()
        has_soffice = bool(soffice_path)
    except Exception:
        has_soffice = False

    available_engines = []
    if has_soffice:
        available_engines.append("libreoffice")
    if has_stirling:
        available_engines.append("stirling")
    if has_pymupdf:
        available_engines.append("local_pymupdf")

    if has_soffice:
        active_engine = "libreoffice"
        status = "OK"
        remediation = "司法级排版引擎 (LibreOffice) 在线，支持法庭文书原格式高保真转 PDF。"
    elif has_stirling:
        active_engine = "stirling"
        status = "OK"
        remediation = "Stirling-PDF 微服务在线，支持高精度文书转码。"
    elif has_pymupdf:
        active_engine = "local_pymupdf"
        status = "DEGRADED"
        remediation = "未检测到外部高保真排版转换器（LibreOffice / Stirling-PDF），当前降级为内置 PyMuPDF 纯代码分页引擎，基础生成功能正常。"
    else:
        active_engine = "none"
        status = "MISSING"
        remediation = "未检测到可用 PDF 引擎，请安装 PyMuPDF 或 LibreOffice。"

    return {
        "status": status,
        "active_engine": active_engine,
        "available_engines": available_engines,
        "has_soffice": has_soffice,
        "has_stirling": has_stirling,
        "has_pymupdf": has_pymupdf,
        "remediation": remediation,
    }


def get_system_health_diagnostics(force: bool = False) -> Dict[str, Any]:
    """
    全量探测系统环境与 5 项运行时依赖。
    严格包裹所有探测项，保证零未捕获异常并返回统一的结构化字典。
    """

    try:
        libreoffice_diag = probe_libreoffice()
    except Exception as e:
        logger.warning("LibreOffice 探测异常: %s", e)
        libreoffice_diag = {
            "status": "MISSING",
            "path": None,
            "remediation": f"LibreOffice 探测异常 ({e})，已降级为内置引擎。",
        }

    try:
        ollama_diag = probe_ollama_service(force=force)
    except Exception as e:
        logger.warning("Ollama 探测异常: %s", e)
        ollama_diag = {
            "status": "MISSING",
            "endpoint": ollama_base_url(),
            "installed_models": [],
            "active_model": None,
            "remediation": f"Ollama 探测异常 ({e})，请检查 11434 端口或运行 'ollama serve'。",
        }

    try:
        cn_laws_kb_diag = probe_cn_laws_kb()
    except Exception as e:
        logger.warning("cn_laws_kb 探测异常: %s", e)
        cn_laws_kb_diag = {
            "status": "MISSING",
            "path": None,
            "laws_count": 0,
            "articles_count": 0,
            "remediation": f"法典库探测异常 ({e})，请检查 storage 目录。",
        }

    try:
        matter_vault_diag = probe_matter_vault()
    except Exception as e:
        logger.warning("matter_vault 探测异常: %s", e)
        matter_vault_diag = {
            "status": "MISSING",
            "path": None,
            "matters_count": 0,
            "remediation": f"案件空间数据库探测异常 ({e})。",
        }

    try:
        pdf_engine_diag = probe_pdf_engine()
    except Exception as e:
        logger.warning("pdf_engine 探测异常: %s", e)
        pdf_engine_diag = {
            "status": "DEGRADED",
            "active_engine": "none",
            "available_engines": [],
            "remediation": f"PDF 引擎探测异常 ({e})。",
        }

    diagnostics = {
        "libreoffice": libreoffice_diag,
        "ollama": ollama_diag,
        "cn_laws_kb": cn_laws_kb_diag,
        "matter_vault": matter_vault_diag,
        "pdf_engine": pdf_engine_diag,
    }

    # 计算 overall_status: "OK" | "DEGRADED" | "MISSING"
    if (cn_laws_kb_diag["status"] == "MISSING" and matter_vault_diag["status"] == "MISSING") or pdf_engine_diag["status"] == "MISSING":
        overall_status = "MISSING"
    elif all(d["status"] == "OK" for d in diagnostics.values()):
        overall_status = "OK"
    else:
        overall_status = "DEGRADED"

    issues = []
    if libreoffice_diag["status"] != "OK":
        issues.append("LibreOffice 未安装 (使用内置排版)")
    if ollama_diag["status"] != "OK":
        issues.append("本地大模型未在线 (支持规则或云端)")
    if cn_laws_kb_diag["status"] != "OK":
        issues.append("权威法典库待完善")
    if matter_vault_diag["status"] != "OK":
        issues.append("案件空间数据库待初始化")
    if pdf_engine_diag["status"] != "OK":
        issues.append("PDF 引擎降级为纯代码分页")

    if overall_status == "OK":
        summary = "所有系统核心与辅助依赖运行就绪，处于最佳就绪状态。"
    elif overall_status == "DEGRADED":
        summary = f"系统基础服务正常运行，部分辅助依赖已降级启用内置兜底 ({'；'.join(issues)})。"
    else:
        summary = f"核心基础存储或渲染引擎缺失 ({'；'.join(issues)})，请按照修复建议进行配置。"

    return {
        "overall_status": overall_status,
        "diagnostics": diagnostics,
        "dependencies": diagnostics,
        "summary": summary,
    }

