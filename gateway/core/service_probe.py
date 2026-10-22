# -*- coding: utf-8 -*-
"""
LawFlow 外部服务可用性探测（Stirling-PDF / Ollama）。
启动或首次使用时探测一次，结果缓存 TTL（默认 60 秒），探测超时 1 秒。
不可用时调用方应直接走本地兜底，避免逐地址长时间等待。
"""
from __future__ import annotations

import logging
import os
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
