"""
LawFlow 智律工作台 - 核心统一 API 网关与服务入口
集成：
- 阶段一：诉讼立案文书流水线与本土计算器 (phase1_litigation)
- 阶段二：证据清洗、目录生成与庭审提纲 Agent (phase2_evidence)
- 阶段三：私有类案 RAG 检索与 DocuSeal 电子签约 (phase3_rag_sign)
- 前端静态工作台挂载与健康检查
"""

import os
import sys
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# 确保项目根路径进入 sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)


def bootstrap_env_and_logging(env_file: str | Path | None = None) -> int:
    """
    加载 .env（仅文件存在时；不覆盖已设置的环境变量），并按 LOG_LEVEL 配置根日志级别。
    返回解析后的 logging 级别整数值。
    """
    from dotenv import load_dotenv

    if env_file is None:
        env_file = os.environ.get("LAWFLOW_DOTENV_FILE") or str(Path(BASE_DIR) / ".env")
    env_path = Path(env_file)
    if env_path.is_file():
        # override=False：不覆盖进程中已存在的环境变量
        load_dotenv(dotenv_path=str(env_path), override=False)

    level_name = (os.getenv("LOG_LEVEL") or "INFO").strip().upper()
    level = getattr(logging, level_name, None)
    if not isinstance(level, int):
        level = logging.INFO
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(
            level=level,
            format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    root.setLevel(level)
    logging.getLogger("lawflow.gateway").setLevel(level)
    return level


_RESOLVED_LOG_LEVEL = bootstrap_env_and_logging()

from gateway.core.ollama_client import ollama_client
from gateway.core.security import (
    API_TOKEN,
    auth_failure_response,
    extract_request_token,
    is_auth_exempt,
    token_matches,
)
from gateway.routers.phase1_litigation import router as phase1_router
from gateway.routers.phase2_evidence import router as phase2_router
from gateway.routers.phase3_rag_sign import router as phase3_router
from gateway.routers.settings_router import router as settings_router
from gateway.routers.phase4_deep_matrix import router as deep_matrix_router
from gateway.routers.phase5_statutes_kb import router as phase5_statutes_router
from gateway.routers.phase6_compliance import router as phase6_compliance_router
from gateway.routers.matter_vault import router as matter_vault_router
from gateway.routers.review_and_diff import router as review_and_diff_router
from gateway.routers.phase8_ai_copilot import router as copilot_router
from gateway.routers.converter_router import router as converter_router
from gateway.utils.matter_vault_db import init_matter_vault_db
from gateway.utils.review_table_engine import init_review_tables_schema
from gateway.utils.agent_task_db import init_agent_task_db

logger = logging.getLogger("lawflow.gateway")
logger.setLevel(_RESOLVED_LOG_LEVEL)

from gateway.core.paths import get_base_dir, get_frontend_dir, get_laws_db_path


def _frontend_dir() -> str:
    return str(get_frontend_dir())


def _parse_csv_env(name: str, default: str) -> list:
    raw = os.getenv(name, default)
    return [x.strip() for x in raw.split(",") if x.strip()]


# 启动生命周期管理
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=== [LawFlow 智律工作台] 正在启动统一编排网关 ===")
    logger.info(f"项目基准目录: {get_base_dir()}")
    # 迁移旧版仓库内 LLM 配置（如有）
    try:
        ollama_client.migrate_legacy_settings_if_needed()
    except Exception as e:
        logger.warning(f"LLM 配置迁移检查失败: {e}")
    # 检查大模型状态
    health = await ollama_client.check_health()
    logger.info(f"Ollama 引擎连接探测: {health.get('status')} | 目标模型: {health.get('target_model')} (就绪: {health.get('model_ready')})")
    # 初始化/校验权威法典数据库
    from gateway.utils.statute_db import init_statute_database
    init_statute_database()
    logger.info("权威法典与子母法图谱数据库 (SQLite FTS5) 校验就绪！")
    from gateway.utils.conflict_checker import init_conflict_database
    init_conflict_database()
    logger.info("利益冲突穿透排查底档库 (conflict_case_registry) 校验就绪！")
    from gateway.utils.citation_guard import ensure_court_precedents_table
    from gateway.core.db import connect
    with connect(get_laws_db_path()) as conn:
        ensure_court_precedents_table(conn)
    logger.info("司法审判案号（指导判例）底库校验就绪！")
    init_matter_vault_db()
    logger.info("案件独立空间数据库 (storage/matter_vault.db) 校验就绪！")
    init_review_tables_schema()
    logger.info("矩阵式批量阅卷表数据库 (matter_review_tables) 校验就绪！")
    init_agent_task_db()
    logger.info("08 智律 AI 语音中枢与任务看板数据表 (agent_tasks) 校验就绪！")
    if not os.getenv("LAWFLOW_API_TOKEN"):
        logger.warning(
            "未设置环境变量 LAWFLOW_API_TOKEN，已在内存生成一次性 Token。"
            "同源前端可通过首页 meta[name=lawflow-token] 自动携带；"
            "外部调用请设置 LAWFLOW_API_TOKEN 并在请求头加入 X-LawFlow-Token。"
        )
    try:
        from gateway.utils.cn_legal_calc import check_lpr_data_freshness
        check_lpr_data_freshness()
    except Exception as e:
        logger.warning(f"LPR 数据新鲜度检查失败: {e}")
    yield
    logger.info("=== [LawFlow 智律工作台] 网关已安全下线 ===")


app = FastAPI(
    title="LawFlow 智律工作台 API",
    description="面向中国执业律师的本地私有化办案提效系统，基于本地大模型 gemma4:12b",
    version="1.0.0",
    lifespan=lifespan
)

# CORS：默认仅本机来源；凭证关闭
_allowed_origins = _parse_csv_env(
    "LAWFLOW_ALLOWED_ORIGINS",
    "http://127.0.0.1:5221,http://localhost:5221",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-LawFlow-Token"],
)

# TrustedHost：防 DNS rebinding（testserver 供 TestClient）
_allowed_hosts = _parse_csv_env(
    "LAWFLOW_ALLOWED_HOSTS",
    "127.0.0.1,localhost,testserver",
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=_allowed_hosts)


@app.middleware("http")
async def api_token_middleware(request: Request, call_next):
    path = request.url.path
    if is_auth_exempt(path, request.method):
        return await call_next(request)
    if path.startswith("/api/"):
        if not token_matches(extract_request_token(request)):
            return auth_failure_response()
    return await call_next(request)


# 分析/计算/文书等 JSON 业务响应统一注入免责声明（健康检查等除外）
_DISCLAIMER_SKIP_PREFIXES = (
    "/health",
    "/api/health",
    "/api/v1/health",
    "/api/documents/download/",
    "/static",
)


@app.middleware("http")
async def disclaimer_middleware(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if any(path.startswith(p) for p in _DISCLAIMER_SKIP_PREFIXES):
        return response
    if not path.startswith("/api/"):
        return response
    content_type = (response.headers.get("content-type") or "").lower()
    if "application/json" not in content_type:
        return response

    body = b""
    async for chunk in response.body_iterator:
        body += chunk if isinstance(chunk, (bytes, bytearray)) else chunk.encode("utf-8")

    import json as _json
    from starlette.responses import Response as StarletteResponse
    from gateway.utils.disclaimer import DISCLAIMER, add_disclaimer

    headers = {k: v for k, v in response.headers.items() if k.lower() != "content-length"}
    try:
        data = _json.loads(body.decode("utf-8"))
    except Exception:
        return StarletteResponse(
            content=body,
            status_code=response.status_code,
            headers=headers,
            media_type=content_type,
        )

    if isinstance(data, dict):
        data["disclaimer"] = DISCLAIMER
        add_disclaimer(data)
        return JSONResponse(
            content=data,
            status_code=response.status_code,
            headers=headers,
            media_type="application/json",
        )

    return StarletteResponse(
        content=body,
        status_code=response.status_code,
        headers=headers,
        media_type=content_type,
    )


# 挂载各业务阶段路由
app.include_router(phase1_router)
app.include_router(phase2_router)
app.include_router(phase3_router)
app.include_router(settings_router)
app.include_router(deep_matrix_router)
app.include_router(phase5_statutes_router)
app.include_router(phase6_compliance_router)
app.include_router(matter_vault_router)
app.include_router(review_and_diff_router)
app.include_router(copilot_router)
app.include_router(converter_router)

# 挂载静态资源
if os.path.exists(_frontend_dir()):
    app.mount("/static", StaticFiles(directory=_frontend_dir()), name="static")


@app.get("/health", summary="全局网关健康检查探针")
@app.get("/api/health", summary="全局网关健康检查探针")
@app.get("/api/v1/health", summary="全局网关健康检查探针")
async def health_check():
    """健康检查：含实际 llm_mode 与 model_ready；规则兜底时 model_ready 为 false。"""
    health = await ollama_client.check_health()
    llm_mode = health.get("llm_mode") or health.get("mode") or "rule_fallback"
    if llm_mode in ("rule_engine", "fallback"):
        llm_mode = "rule_fallback"
    model_ready = bool(health.get("model_ready"))
    if llm_mode == "rule_fallback":
        model_ready = False
    return {
        "status": "healthy",
        "app": "LawFlow",
        "llm_mode": llm_mode,
        "model_ready": model_ready,
    }


# Content-Security-Policy：同源默认；内联脚本暂保留 unsafe-inline（批次 17 A-09 拆分前端后去除）
_CSP_HEADER = (
    "default-src 'self'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "frame-ancestors 'none'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; "
    "connect-src 'self'; "
    "font-src 'self' data:"
)


@app.middleware("http")
async def csp_middleware(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    ctype = (response.headers.get("content-type") or "").lower()
    if (
        path == "/"
        or path.startswith("/static")
        or path.endswith(".html")
        or path.endswith(".js")
        or "text/html" in ctype
    ):
        response.headers["Content-Security-Policy"] = _CSP_HEADER
    return response


@app.get("/", response_class=HTMLResponse, summary="工作台 Web UI 首页")
async def serve_index():
    index_file = os.path.join(_frontend_dir(), "index.html")
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            html = f.read()
        meta = f'<meta name="lawflow-token" content="{API_TOKEN}">'
        if "</head>" in html:
            html = html.replace("</head>", f"  {meta}\n</head>", 1)
        else:
            html = meta + html
        return HTMLResponse(html, headers={"Content-Security-Policy": _CSP_HEADER})
    return HTMLResponse(
        "<h2>LawFlow 智律工作台初始化中... 请稍后刷新。</h2>",
        headers={"Content-Security-Policy": _CSP_HEADER},
    )


@app.get("/favicon.ico", include_in_schema=False)
async def serve_favicon():
    from fastapi.responses import FileResponse
    ico_file = str(get_base_dir() / "resources" / "lawflow.ico")
    if os.path.exists(ico_file):
        return FileResponse(ico_file, media_type="image/x-icon")
    return HTMLResponse("")


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("GATEWAY_HOST", "127.0.0.1")
    primary_port = int(os.getenv("GATEWAY_PORT", "5221"))
    # A-14：默认不再绑定 8000；仅当显式设置 LAWFLOW_LEGACY_PORT 时启动兼容端口
    legacy_port_env = os.getenv("LAWFLOW_LEGACY_PORT", "").strip()
    legacy_port = int(legacy_port_env) if legacy_port_env.isdigit() else None

    if legacy_port and legacy_port != primary_port:
        import threading

        def run_legacy_server():
            try:
                logger.info(f"同时启动兼容端口服务: http://{host}:{legacy_port}")
                config = uvicorn.Config(app, host=host, port=legacy_port, log_level="warning")
                server = uvicorn.Server(config)
                server.run()
            except Exception as e:
                logger.warning(f"兼容端口 {legacy_port} 绑定跳过: {e}")

        t = threading.Thread(target=run_legacy_server, daemon=True)
        t.start()

    logger.info(f"LawFlow 统一网关即将启动，监听主地址: http://{host}:{primary_port}")
    uvicorn.run(app, host=host, port=primary_port, log_level="info")
