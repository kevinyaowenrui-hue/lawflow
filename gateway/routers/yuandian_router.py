# -*- coding: utf-8 -*-
"""元典检索与引用核对。密钥只通过设置接口写入本机，接口响应不回传明文。"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from gateway.utils.yuandian import YuandianError, yuandian

logger = logging.getLogger("lawflow.yuandian")
router = APIRouter(tags=["元典法律检索"])


class YuandianKeyReq(BaseModel):
    api_key: str = Field(default="")


class YuandianSearchReq(BaseModel):
    kind: str = Field(description="law / case / company / securities")
    query: str = ""
    limit: int = Field(default=8, ge=1, le=20)


class YuandianCheckReq(BaseModel):
    text: str = ""


class YuandianCallReq(BaseModel):
    server: str
    tool: str
    arguments: Dict[str, Any] = Field(default_factory=dict)


class CompanyProfileReq(BaseModel):
    company_id: str = ""
    uscc: str = ""


def _fail(exc: YuandianError) -> None:
    message = str(exc)
    status = 400 if any(word in message for word in ("API Key", "请", "未知")) else 502
    raise HTTPException(status_code=status, detail=message)


@router.get("/api/v1/settings/yuandian", summary="元典是否已配置")
def get_yuandian_settings():
    return {"status": "success", "settings": yuandian.status()}


@router.post("/api/v1/settings/yuandian", summary="保存元典 API Key")
def save_yuandian_settings(req: YuandianKeyReq):
    try:
        settings = yuandian.save_api_key(req.api_key)
    except YuandianError as exc:
        _fail(exc)
    return {"status": "success", "message": "元典密钥已保存", "settings": settings}


@router.post("/api/v1/settings/yuandian/test", summary="测试元典连接并查询余额")
def test_yuandian_settings(req: Optional[YuandianKeyReq] = None):
    incoming = ((req.api_key if req else "") or "").strip()
    if incoming:
        try:
            yuandian.save_api_key(incoming)
        except YuandianError as exc:
            _fail(exc)
    if not yuandian.configured():
        raise HTTPException(status_code=400, detail="尚未配置元典 API Key")
    try:
        balance = yuandian.balance()
    except YuandianError as exc:
        _fail(exc)
    return {"status": "success", "message": "元典已连通", "balance": balance}


@router.get("/api/v1/yuandian/status", summary="元典连接状态")
def yuandian_status():
    return {"status": "success", **yuandian.status()}


@router.post("/api/v1/yuandian/search", summary="按场景检索法条、案例、企业或证券法规")
def yuandian_search(req: YuandianSearchReq):
    query = (req.query or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="请输入检索内容")
    kind = (req.kind or "").strip()
    try:
        if kind == "law":
            found = yuandian.search_articles(query, req.limit)
        elif kind == "case":
            found = yuandian.search_cases(query, req.limit)
        elif kind == "company":
            found = yuandian.search_companies(query, req.limit)
        elif kind == "securities":
            found = yuandian.search_securities(query, req.limit)
        else:
            raise HTTPException(status_code=400, detail="检索类型应为 law、case、company 或 securities")
    except YuandianError as exc:
        _fail(exc)
    return {
        "status": "success",
        "source": "yuandian",
        "kind": found["kind"],
        "items": found["items"],
    }


@router.post("/api/v1/yuandian/check", summary="用元典核对文本中的法条和案号")
def yuandian_check(req: YuandianCheckReq):
    try:
        result = yuandian.check_text(req.text)
    except YuandianError as exc:
        _fail(exc)
    return {"status": "success", "result": result}


@router.post("/api/v1/yuandian/companies/profile", summary="查询企业基本信息")
def yuandian_company_profile(req: CompanyProfileReq):
    try:
        result = yuandian.company_profile(req.company_id, req.uscc)
    except YuandianError as exc:
        _fail(exc)
    return {"status": "success", "result": result}


@router.post("/api/v1/yuandian/call", summary="调用指定元典工具")
def yuandian_call(req: YuandianCallReq):
    try:
        result = yuandian.call_tool(req.server, req.tool, req.arguments)
    except YuandianError as exc:
        _fail(exc)
    return {"status": "success", "result": result}
