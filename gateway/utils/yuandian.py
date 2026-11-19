# -*- coding: utf-8 -*-
"""元典开放平台 MCP 客户端。

律师侧直接调用：

    from gateway.utils.yuandian import yuandian
    yuandian.search_articles("合同解除后的违约金")
    yuandian.search_cases("买卖合同迟延交货")
    yuandian.search_companies("腾讯科技")
    yuandian.check_text("根据《民法典》第五百八十五条……")

密钥只读环境变量 YUANDIAN_API_KEY 或 ~/.lawflow/secrets.json，不写入仓库。
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from gateway.core.ollama_client import BASE_DIR, read_secrets, write_secrets

SERVERS = {
    "law": "https://open.chineselaw.com/mcp/law/stream",
    "case": "https://open.chineselaw.com/mcp/case/stream",
    "company": "https://open.chineselaw.com/mcp/company/stream",
    "securities": "https://open.chineselaw.com/mcp/securities/stream",
    "hallucination": "https://open.chineselaw.com/mcp/hallucination/stream",
}

_LIST_KEYS = (
    "law_article_list",
    "articles",
    "case_list",
    "cases",
    "company_list",
    "companies",
    "list",
    "items",
    "records",
    "rows",
    "data",
    "results",
)


class YuandianError(RuntimeError):
    pass


def dotenv_path() -> Path:
    override = os.getenv("LAWFLOW_DOTENV_FILE", "").strip()
    if override:
        return Path(override)
    return Path(BASE_DIR) / ".env"


def mask_secret(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    if len(text) <= 8:
        return "****"
    return text[:4] + "*" * (len(text) - 8) + text[-4:]


def _upsert_dotenv(key: str) -> None:
    path = dotenv_path()
    line = f"YUANDIAN_API_KEY={key}"
    if path.is_file():
        raw = path.read_text(encoding="utf-8")
        if re.search(r"(?m)^YUANDIAN_API_KEY=", raw):
            raw = re.sub(r"(?m)^YUANDIAN_API_KEY=.*$", line, raw)
        else:
            if raw and not raw.endswith("\n"):
                raw += "\n"
            raw += line + "\n"
        path.write_text(raw, encoding="utf-8")
        return
    path.write_text(
        "# 本文件已被 .gitignore 忽略，不要提交。\n" + line + "\n",
        encoding="utf-8",
    )


def _parse_mcp_body(text: str, content_type: str) -> List[dict]:
    body = text or ""
    if not body.strip():
        return []
    if "text/event-stream" in (content_type or "") or body.lstrip().startswith("data:"):
        messages = []
        for block in body.split("\n\n"):
            data = "\n".join(
                line[5:].strip() for line in block.splitlines() if line.startswith("data:")
            )
            if data and data != "[DONE]":
                messages.append(json.loads(data))
        return messages
    parsed = json.loads(body)
    return [parsed] if isinstance(parsed, dict) else []


def _first(record: dict, *keys: str) -> str:
    for key in keys:
        value = record.get(key)
        if value not in (None, "", [], {}):
            if isinstance(value, (dict, list)):
                continue
            return str(value).strip()
    return ""


def collect_records(payload: Any) -> List[dict]:
    found: List[dict] = []

    def walk(node: Any, depth: int = 0) -> None:
        if found or depth > 5:
            return
        if isinstance(node, list):
            rows = [item for item in node if isinstance(item, dict)]
            if rows:
                found.extend(rows)
            return
        if not isinstance(node, dict):
            return
        for key in _LIST_KEYS:
            if key in node:
                walk(node[key], depth + 1)
                if found:
                    return
        for value in node.values():
            if isinstance(value, (dict, list)):
                walk(value, depth + 1)
                if found:
                    return

    walk(payload)
    return found


def to_items(payload: Any, limit: int = 8) -> List[dict]:
    items = []
    for record in collect_records(payload)[:limit]:
        title = _first(
            record,
            "regulation_name",
            "fgmc",
            "law_name",
            "title",
            "case_name",
            "company_name",
            "name",
            "ah",
            "case_number",
        )
        article = _first(record, "article_number", "ftnum", "tiao", "article_no", "article_no_cn")
        subtitle = _first(record, "court", "court_name", "fayuan", "uscc", "tyshxydm", "validity_status", "sxx")
        snippet = _first(record, "content", "article_content", "highlight", "summary", "snippet", "text")
        if len(snippet) > 500:
            snippet = snippet[:500] + "…"
        items.append(
            {
                "id": _first(record, "article_id", "case_id", "company_id", "id"),
                "title": title or "元典结果",
                "article": article,
                "subtitle": subtitle,
                "snippet": snippet,
            }
        )
    return items


class YuandianClient:
    def api_key(self) -> str:
        env_key = os.getenv("YUANDIAN_API_KEY", "").strip()
        if env_key:
            return env_key
        return (read_secrets().get("yuandian_api_key") or "").strip()

    def configured(self) -> bool:
        return bool(self.api_key())

    def status(self) -> Dict[str, Any]:
        key = self.api_key()
        return {
            "configured": bool(key),
            "key_masked": mask_secret(key),
            "servers": list(SERVERS),
        }

    def save_api_key(self, api_key: str) -> Dict[str, Any]:
        key = (api_key or "").strip()
        if not key:
            raise YuandianError("请填写元典 API Key")
        data = read_secrets()
        data["yuandian_api_key"] = key
        write_secrets(data)
        os.environ["YUANDIAN_API_KEY"] = key
        _upsert_dotenv(key)
        return self.status()

    def call_tool(self, server: str, tool: str, arguments: Optional[dict] = None) -> Any:
        if server not in SERVERS:
            raise YuandianError("未知的元典服务")
        if not re.fullmatch(r"yuandian_[a-z0-9_]+", tool or ""):
            raise YuandianError("未知的元典工具")
        key = self.api_key()
        if not key:
            raise YuandianError("尚未配置元典 API Key")
        url = SERVERS[server]
        headers = {
            "Authorization": f"Bearer {key}",
            "Accept": "application/json, text/event-stream",
        }
        with httpx.Client(timeout=60.0, headers=headers) as client:
            init = client.post(
                url,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {},
                        "clientInfo": {"name": "lawflow", "version": "1.0"},
                    },
                },
            )
            self._raise_for_status(init)
            session_id = init.headers.get("mcp-session-id")
            extra = {"Mcp-Session-Id": session_id} if session_id else {}
            client.post(url, json={"jsonrpc": "2.0", "method": "notifications/initialized"}, headers=extra)
            response = client.post(
                url,
                headers=extra,
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": tool, "arguments": arguments or {}},
                },
            )
        self._raise_for_status(response)
        messages = _parse_mcp_body(response.text, response.headers.get("content-type", ""))
        if not messages:
            raise YuandianError("元典没有返回结果")
        message = messages[-1]
        if message.get("error"):
            err = message["error"]
            detail = err.get("message") if isinstance(err, dict) else str(err)
            raise YuandianError(detail or "元典调用失败")
        result = message.get("result") or {}
        if result.get("isError"):
            raise YuandianError(self._content_text(result) or "元典调用失败")
        text = self._content_text(result)
        if not text:
            return result
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"text": text}

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.status_code in (401, 403):
            raise YuandianError("元典密钥无效或没有权限")
        if response.status_code >= 400:
            raise YuandianError(f"元典服务暂时不可用（{response.status_code}）")

    @staticmethod
    def _content_text(result: dict) -> str:
        chunks = []
        for item in result.get("content") or []:
            if isinstance(item, dict) and item.get("type") == "text":
                chunks.append(item.get("text") or "")
            elif isinstance(item, str):
                chunks.append(item)
        return "\n".join(chunk for chunk in chunks if chunk).strip()

    def search_articles(self, query: str, limit: int = 8) -> Dict[str, Any]:
        payload = self.call_tool(
            "law",
            "yuandian_semantic_search_legal_articles",
            {
                "query": query,
                "limit": limit,
                "law_article_filter": {"validity_status": ["现行有效"], "regions": ["中央"]},
            },
        )
        return {"kind": "law", "items": to_items(payload, limit), "data": payload}

    def article_detail(self, regulation_name: str, article_number: str = "") -> Any:
        args = {"regulation_name": regulation_name}
        if article_number:
            args["article_number"] = article_number
        return self.call_tool("law", "yuandian_get_legal_article_detail", args)

    def search_cases(self, query: str, limit: int = 8) -> Dict[str, Any]:
        payload = self.call_tool(
            "case",
            "yuandian_semantic_search_cases",
            {"query": query, "limit": limit},
        )
        return {"kind": "case", "items": to_items(payload, limit), "data": payload}

    def search_companies(self, company_name: str, limit: int = 8) -> Dict[str, Any]:
        payload = self.call_tool(
            "company",
            "yuandian_search_companies",
            {"company_name": company_name, "top_k": limit},
        )
        return {"kind": "company", "items": to_items(payload, limit), "data": payload}

    def company_profile(self, company_id: str = "", uscc: str = "") -> Any:
        if not company_id and not uscc:
            raise YuandianError("请提供企业 ID 或统一社会信用代码")
        return self.call_tool(
            "company",
            "yuandian_get_company_basic_profile",
            {"company_id": company_id, "uscc": uscc},
        )

    def search_securities(self, query: str, limit: int = 8) -> Dict[str, Any]:
        payload = self.call_tool(
            "securities",
            "yuandian_semantic_search_securities_articles",
            {
                "query": query,
                "limit": limit,
                "law_article_filter": {"validity_status": ["现行有效"]},
            },
        )
        return {"kind": "securities", "items": to_items(payload, limit), "data": payload}

    def check_text(self, text: str) -> Any:
        """把核对原文发到 open.chineselaw.com，最多两万字。

        不经过云端模型的脱敏开关，也不能当成已经脱敏。
        能识别的未成年人信息和病历留在本机；识别不了的不会被写成已经拦住。
        调用方在真正发送前应单独提示用户。
        """
        raw = text or ""
        if not raw.strip():
            raise YuandianError("请输入需要核对的文本")
        from gateway.utils.pii_sanitizer import NETWORK_WITHHELD_MARK, withhold_network_sensitive

        cleaned, _report = withhold_network_sensitive(raw)
        leftover = re.sub(r"[\s。！？；，、：:、]+", "", cleaned.replace(NETWORK_WITHHELD_MARK, ""))
        if not leftover:
            raise YuandianError(
                "能识别的未成年人信息或病历内容已留在本机，没有剩余核对文本可发送。识别不了的内容没有被拦截。"
            )
        return self.call_tool("hallucination", "yuandian_hall_detect", {"text": cleaned[:20000]})

    def balance(self) -> Any:
        return self.call_tool("law", "yuandian_get_user_balance", {})


yuandian = YuandianClient()
