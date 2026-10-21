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

from gateway.core.ollama_client import ollama_client, PROVIDER_PRESETS

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


class PIIScanReq(BaseModel):
    text: str = Field(..., description="待检测个人敏感信息的文本")
    custom_entities: Optional[list] = Field(default=None, description="自定义实体清单")


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
    test_cfg = {
        "provider": req.provider,
        "cloud_preset": req.cloud_preset,
        "api_key": req.api_key.strip() if req.api_key else ollama_client.settings.get("api_key", ""),
        "base_url": req.base_url.strip() if req.base_url else "",
        "model": req.model.strip() if req.model else "",
        "ollama_base_url": req.ollama_base_url.strip() if req.ollama_base_url else "http://127.0.0.1:11434"
    }

    # 若未提供 base_url 则根据 preset 填充
    if not test_cfg["base_url"] and req.cloud_preset in PROVIDER_PRESETS:
        test_cfg["base_url"] = PROVIDER_PRESETS[req.cloud_preset]["base_url"]
    if not test_cfg["model"] and req.cloud_preset in PROVIDER_PRESETS:
        test_cfg["model"] = PROVIDER_PRESETS[req.cloud_preset]["default_model"]

    res = await ollama_client.test_connection(test_cfg)
    return res


@router.post("/llm", summary="保存大模型配置并即时热生效")
async def save_llm_settings(req: LLMConfigReq):
    new_cfg: Dict[str, Any] = {
        "provider": req.provider,
        "cloud_preset": req.cloud_preset,
        "ollama_model": req.ollama_model.strip() if req.ollama_model else "gemma4:12b",
        "ollama_base_url": req.ollama_base_url.strip() if req.ollama_base_url else "http://127.0.0.1:11434"
    }

    if req.pii_shield_enabled is not None:
        new_cfg["pii_shield_enabled"] = bool(req.pii_shield_enabled)

    # 只有用户输入了非空 API Key 才覆盖更新，避免前端回显脱敏值覆盖真实密钥
    if req.api_key and not req.api_key.startswith("****"):
        new_cfg["api_key"] = req.api_key.strip()

    if req.base_url:
        new_cfg["base_url"] = req.base_url.strip().rstrip("/")
    elif req.cloud_preset in PROVIDER_PRESETS:
        new_cfg["base_url"] = PROVIDER_PRESETS[req.cloud_preset]["base_url"]

    if req.model:
        new_cfg["model"] = req.model.strip()
    elif req.cloud_preset in PROVIDER_PRESETS:
        new_cfg["model"] = PROVIDER_PRESETS[req.cloud_preset]["default_model"]

    # 持久化保存
    sanitized = ollama_client.save_settings(new_cfg)
    # 重置探测缓存
    ollama_client._active_ollama_url = None
    health = await ollama_client.check_health()

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
