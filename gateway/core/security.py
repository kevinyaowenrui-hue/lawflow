"""
LawFlow 智律工作台 - 安全与鉴权工具
- API Token 校验（X-LawFlow-Token）
- 路径安全拼接 / 文件名消毒 / 落盘 UUID 名
- 上传大小与魔数校验
"""

from __future__ import annotations

import hmac
import logging
import os
import re
import secrets
import uuid
from typing import Iterable, Optional, Sequence, Set

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("lawflow.security")

API_TOKEN: str = os.getenv("LAWFLOW_API_TOKEN") or secrets.token_urlsafe(32)

AUTH_EXEMPT_EXACT: Set[str] = {
    "/",
    "/favicon.ico",
    "/health",
    "/api/health",
    "/api/v1/health",
    "/api/system/health",
    # DocuSeal / 演示签署回调：使用 DOCUSEAL_WEBHOOK_SECRET，不用 X-LawFlow-Token
    "/api/v1/phase3/signing-webhook",
}

AUTH_EXEMPT_PREFIXES: tuple = (
    "/static/",
    # 当事人 sign-view：仅靠 view_token，无律师 Token
    "/api/v1/phase3/sign-view/",
)

# 默认单文件 / 单次总量上限（MB）
DEFAULT_MAX_UPLOAD_MB = 50
DEFAULT_MAX_UPLOAD_TOTAL_MB = 200

# 常见魔数
_MAGIC_PREFIXES = {
    ".pdf": (b"%PDF",),
    ".png": (b"\x89PNG",),
    ".jpg": (b"\xff\xd8",),
    ".jpeg": (b"\xff\xd8",),
    ".docx": (b"PK\x03\x04",),
    ".xlsx": (b"PK\x03\x04",),
}


def get_api_token() -> str:
    return API_TOKEN


def is_auth_exempt(path: str, method: str = "GET") -> bool:
    if method.upper() == "OPTIONS":
        return True
    clean_path = path.rstrip("/") or "/"
    if clean_path in AUTH_EXEMPT_EXACT:
        return True
    for prefix in AUTH_EXEMPT_PREFIXES:
        if path.startswith(prefix):
            return True
    return False


DOWNLOAD_TOKEN_PREFIXES: tuple = (
    "/api/documents/download/",
    "/api/v1/phase1/package/",
)


def extract_request_token(request: Request) -> Optional[str]:
    token = request.headers.get("X-LawFlow-Token")
    if token:
        return token
    path = request.url.path
    if request.method.upper() == "GET" and any(path.startswith(prefix) for prefix in DOWNLOAD_TOKEN_PREFIXES):
        return request.query_params.get("token")
    return None


def token_matches(provided: Optional[str]) -> bool:
    if not provided:
        return False
    return hmac.compare_digest(provided, API_TOKEN)


async def require_token(request: Request) -> None:
    """FastAPI 依赖：校验 X-LawFlow-Token（下载接口额外接受 ?token=）。"""
    if is_auth_exempt(request.url.path, request.method):
        return
    if not request.url.path.startswith("/api/"):
        return
    if not token_matches(extract_request_token(request)):
        raise HTTPException(status_code=401, detail={"error_code": "AUTH_REQUIRED"})


def auth_failure_response() -> JSONResponse:
    return JSONResponse(status_code=401, content={"error_code": "AUTH_REQUIRED"})


def safe_join(base_dir: str, *parts: str) -> str:
    """将路径拼接到 base_dir 内；穿越则 400。"""
    base = os.path.realpath(base_dir)
    # 拒绝以盘符/根起始的路径部件直接覆盖 base
    cleaned_parts = []
    for p in parts:
        if p is None:
            continue
        s = str(p)
        if os.path.isabs(s) or (len(s) >= 2 and s[1] == ":"):
            raise HTTPException(status_code=400, detail="非法路径：不允许以根或盘符起始的路径")
        if ".." in s.replace("\\", "/").split("/"):
            raise HTTPException(status_code=400, detail="非法路径：不允许 ..")
        cleaned_parts.append(s)
    candidate = os.path.realpath(os.path.join(base, *cleaned_parts))
    try:
        common = os.path.commonpath([base, candidate])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="非法路径") from exc
    if common != base:
        raise HTTPException(status_code=400, detail="非法路径：越出存储目录")
    return candidate


def sanitize_filename(name: Optional[str], default: str = "文书") -> str:
    """取 basename，拒绝 ..，只保留中文/字母数字/_-.（）()，最长 80。"""
    if not name or not str(name).strip():
        return default
    raw = str(name).replace("\\", "/")
    base = raw.split("/")[-1]
    if ".." in base:
        base = base.replace("..", "")
    cleaned = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9_\-.（）()]", "", base)
    cleaned = cleaned[:80].strip("._-")
    return cleaned or default


def storage_name(ext: str) -> str:
    """生成 uuid4 落盘文件名。"""
    e = (ext or "").strip().lower()
    if e and not e.startswith("."):
        e = f".{e}"
    return f"{uuid.uuid4().hex}{e}"


def max_upload_bytes() -> int:
    mb = int(os.getenv("LAWFLOW_MAX_UPLOAD_MB", str(DEFAULT_MAX_UPLOAD_MB)))
    return max(1, mb) * 1024 * 1024


def max_upload_total_bytes() -> int:
    mb = int(os.getenv("LAWFLOW_MAX_UPLOAD_TOTAL_MB", str(DEFAULT_MAX_UPLOAD_TOTAL_MB)))
    return max(1, mb) * 1024 * 1024


def extension_of(filename: Optional[str]) -> str:
    if not filename:
        return ""
    base = os.path.basename(filename.replace("\\", "/"))
    _, ext = os.path.splitext(base)
    return ext.lower()


def assert_allowed_extension(filename: Optional[str], allowed: Sequence[str]) -> str:
    ext = extension_of(filename)
    normalized = {a.lower() if a.startswith(".") else f".{a.lower()}" for a in allowed}
    if ext not in normalized:
        raise HTTPException(status_code=415, detail=f"不允许的文件类型: {ext or '(无扩展名)'}")
    return ext


def validate_magic_bytes(data: bytes, ext: str) -> None:
    """按扩展名校验文件头魔数；无规则的类型跳过。"""
    e = ext.lower() if ext.startswith(".") else f".{ext.lower()}"
    prefixes = _MAGIC_PREFIXES.get(e)
    if not prefixes:
        return
    if not data or not any(data.startswith(p) for p in prefixes):
        raise HTTPException(status_code=415, detail="文件内容与扩展名不符（魔数校验失败）")


def enforce_size_limit(size: int, *, limit: Optional[int] = None) -> None:
    cap = limit if limit is not None else max_upload_bytes()
    if size > cap:
        raise HTTPException(status_code=413, detail=f"单文件超过上限 {cap // (1024 * 1024)}MB")


async def read_upload_bounded(upload, *, max_bytes: Optional[int] = None) -> bytes:
    """读取 UploadFile，超出上限返回 413。"""
    cap = max_bytes if max_bytes is not None else max_upload_bytes()
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > cap:
            raise HTTPException(status_code=413, detail=f"单文件超过上限 {cap // (1024 * 1024)}MB")
        chunks.append(chunk)
    return b"".join(chunks)


def validate_plain_filename(name: str) -> str:
    """redact-sensitive 等：只接受不含路径分隔符的纯文件名。"""
    if not name or not str(name).strip():
        raise HTTPException(status_code=400, detail="文件名不能为空")
    s = str(name).strip()
    if "/" in s or "\\" in s or ".." in s or os.path.isabs(s) or (len(s) >= 2 and s[1] == ":"):
        raise HTTPException(status_code=400, detail="非法文件名：不允许路径分隔符或以根起始的路径")
    return s


def validate_download_filename(filename: str) -> str:
    """下载接口：含 / \\ .. 或解码后含这些 → 400。"""
    from urllib.parse import unquote

    raw = filename or ""
    decoded = unquote(raw)
    for candidate in (raw, decoded):
        if "/" in candidate or "\\" in candidate or ".." in candidate:
            raise HTTPException(status_code=400, detail="非法下载文件名")
        if os.path.isabs(candidate) or (len(candidate) >= 2 and candidate[1] == ":"):
            raise HTTPException(status_code=400, detail="非法下载文件名")
    return decoded
