"""
LawFlow 智律工作台 - 模型引擎与全局系统配置路由 (Settings Router)
支持：
- 云端 API 密钥与服务商（DeepSeek / 千问 / 智谱等）热配置与持久化
- 连接连通性测速探针
- 工作模式无缝热切换 (云端 / 本地 Ollama / 专家规则兜底)
"""

import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from gateway.core.ollama_client import (
    ollama_client,
    PROVIDER_PRESETS,
    validate_cloud_base_url,
    validate_ollama_base_url,
)

logger = logging.getLogger("lawflow.settings")
router = APIRouter(prefix="/api/v1/settings", tags=["系统与模型引擎配置"])


class LLMConfigReq(BaseModel):
    provider: str = Field(default="auto", description="auto / cloud / ollama / rule_engine")
    cloud_preset: Optional[str] = Field(default="deepseek")
    api_key: Optional[str] = Field(default="")
    base_url: Optional[str] = Field(default="")
    model: Optional[str] = Field(default="")
    ollama_model: Optional[str] = Field(default="gemma4:12b")
    ollama_base_url: Optional[str] = Field(default="http://127.0.0.1:11434")
    pii_shield_enabled: Optional[bool] = Field(default=None, description="是否启用本地 PII 自动脱敏网关")
    cloud_consent: Optional[bool] = Field(default=None, description="是否同意脱敏后向第三方云端发送案情文本")


class PIIScanReq(BaseModel):
    text: str = Field(..., description="待检测个人敏感信息的文本")
    custom_entities: Optional[list] = Field(default=None, description="自定义实体清单")


def _resolve_base_url(req: LLMConfigReq) -> str:
    if req.base_url and req.base_url.strip():
        return req.base_url.strip().rstrip("/")
    if req.cloud_preset and req.cloud_preset in PROVIDER_PRESETS:
        return PROVIDER_PRESETS[req.cloud_preset]["base_url"].rstrip("/")
    return ""


@router.get("/llm", summary="获取当前大模型引擎配置与健康状态")
async def get_llm_settings():
    sanitized = ollama_client.get_sanitized_settings()
    health = await ollama_client.check_health()
    return {
        "status": "success",
        "settings": sanitized,
        "health": health,
        "presets": PROVIDER_PRESETS
    }


@router.post("/test-llm", summary="即时测试大模型连接可用性与网络延迟")
async def test_llm_connection(req: LLMConfigReq):
    base_url = _resolve_base_url(req)
    ollama_url = (req.ollama_base_url or "http://127.0.0.1:11434").strip().rstrip("/")
    provided_key = (req.api_key or "").strip()

    # 校验 URL
    if req.provider in ("cloud", "auto") and base_url and not base_url.startswith("http://127.") and "localhost" not in base_url:
        # 云端地址走 https 白名单；本机 ollama 风格地址交由 ollama 校验
        if PROVIDER_PRESETS.get(req.cloud_preset or "", {}).get("type") == "cloud" or (
            req.provider == "cloud" or (provided_key or base_url)
        ):
            if base_url.startswith("https://") or base_url.startswith("http://"):
                # 对明显云端 / 任意非本机地址做校验
                host_is_local = False
                try:
                    from urllib.parse import urlparse
                    h = (urlparse(base_url).hostname or "").lower()
                    host_is_local = h in ("127.0.0.1", "localhost", "::1")
                except Exception:
                    host_is_local = False
                if not host_is_local:
                    validate_cloud_base_url(base_url)

    if req.provider in ("ollama", "auto") or req.ollama_base_url:
        validate_ollama_base_url(ollama_url)

    saved_base = (ollama_client.settings.get("base_url") or "").rstrip("/")
    if not provided_key:
        # 不再无条件回落 Key：仅当 base_url 与已保存完全相同时允许使用已存 Key
        if base_url and saved_base and base_url != saved_base:
            raise HTTPException(
                status_code=400,
                detail="测试新的服务地址必须重新填写 API Key",
            )
        api_key = ollama_client.settings.get("api_key", "")
    else:
        api_key = provided_key

    test_cfg = {
        "provider": req.provider,
        "cloud_preset": req.cloud_preset,
        "api_key": api_key,
        "base_url": base_url,
        "model": req.model.strip() if req.model else "",
        "ollama_base_url": ollama_url,
    }

    if not test_cfg["model"] and req.cloud_preset in PROVIDER_PRESETS:
        test_cfg["model"] = PROVIDER_PRESETS[req.cloud_preset]["default_model"]

    res = await ollama_client.test_connection(test_cfg)
    return res


@router.post("/llm", summary="保存大模型配置并即时热生效")
async def save_llm_settings(req: LLMConfigReq):
    ollama_url = (req.ollama_base_url or "http://127.0.0.1:11434").strip().rstrip("/")
    validate_ollama_base_url(ollama_url)

    base_url = ""
    if req.base_url and req.base_url.strip():
        base_url = req.base_url.strip().rstrip("/")
    elif req.cloud_preset in PROVIDER_PRESETS:
        base_url = PROVIDER_PRESETS[req.cloud_preset]["base_url"].rstrip("/")

    # 云端 base_url 校验（非本机）
    if base_url:
        from urllib.parse import urlparse
        h = (urlparse(base_url).hostname or "").lower()
        if h not in ("127.0.0.1", "localhost", "::1"):
            validate_cloud_base_url(base_url)

    new_cfg: Dict[str, Any] = {
        "provider": req.provider,
        "cloud_preset": req.cloud_preset,
        "ollama_model": req.ollama_model.strip() if req.ollama_model else "gemma4:12b",
        "ollama_base_url": ollama_url,
    }

    if req.pii_shield_enabled is not None:
        new_cfg["pii_shield_enabled"] = bool(req.pii_shield_enabled)

    if req.cloud_consent is not None:
        new_cfg["cloud_consent"] = bool(req.cloud_consent)
    elif req.provider == "cloud":
        # 显式切换云端但未传 consent 时保持原值；未同意则不允许静默开通
        pass

    # 只有用户输入了非空 API Key 才覆盖更新，避免前端回显脱敏值覆盖真实密钥
    if req.api_key and not req.api_key.startswith("****"):
        new_cfg["api_key"] = req.api_key.strip()

    if base_url:
        new_cfg["base_url"] = base_url

    if req.model:
        new_cfg["model"] = req.model.strip()
    elif req.cloud_preset in PROVIDER_PRESETS:
        new_cfg["model"] = PROVIDER_PRESETS[req.cloud_preset]["default_model"]

    sanitized = ollama_client.save_settings(new_cfg)
    ollama_client._active_ollama_url = None
    health = await ollama_client.check_health()
    try:
        from gateway.utils.matter_vault_db import record_audit_log
        record_audit_log(action="settings_update", target="llm_settings")
        if req.provider:
            record_audit_log(action="cloud_toggle_change", target=f"provider={req.provider}")
    except Exception as audit_err:
        logger.warning(f"记录设置审计日志失败: {audit_err}")

    return {
        "status": "success",
        "message": "配置已保存并即时生效",
        "settings": sanitized,
        "health": health
    }


@router.post("/pii/scan", summary="本地快速扫描并脱敏文本中的 PII 实体")
async def scan_pii_endpoint(req: PIIScanReq):
    from gateway.utils.pii_sanitizer import pii_sanitizer
    masked_text, mapping, stats = pii_sanitizer.mask(req.text, req.custom_entities)
    scanned_entities = pii_sanitizer.scan_pii(req.text)
    return {
        "status": "success",
        "original_length": len(req.text),
        "masked_text": masked_text,
        "mapping": mapping,
        "stats": stats,
        "detected_entities": scanned_entities
    }
