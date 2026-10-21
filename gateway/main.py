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
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

# 确保项目根路径进入 sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from gateway.core.ollama_client import ollama_client
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

# 日志规范配置
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("lawflow.gateway")

FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
STORAGE_DIR = os.path.join(BASE_DIR, "storage")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

# 启动生命周期管理
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=== [LawFlow 智律工作台] 正在启动统一编排网关 ===")
    logger.info(f"项目基准目录: {BASE_DIR}")
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
    import sqlite3
    db_path = os.path.join(BASE_DIR, "storage", "cn_laws_kb.db")
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        ensure_court_precedents_table(conn)
        conn.close()
        logger.info("司法审判案号（指导判例）底库校验就绪！")
    init_matter_vault_db()
    logger.info("案件独立空间数据库 (storage/matter_vault.db) 校验就绪！")
    init_review_tables_schema()
    logger.info("矩阵式批量阅卷表数据库 (matter_review_tables) 校验就绪！")
    init_agent_task_db()
    logger.info("08 智律 AI 语音中枢与任务看板数据表 (agent_tasks) 校验就绪！")
    yield
    logger.info("=== [LawFlow 智律工作台] 网关已安全下线 ===")


app = FastAPI(
    title="LawFlow 智律工作台 API",
    description="面向中国执业律师的本地私有化办案提效系统，基于本地大模型 gemma4:12b",
    version="1.0.0",
    lifespan=lifespan
)

# 允许跨域（方便本地与宿主机调用）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/health", summary="全局网关健康检查探针")
@app.get("/api/health", summary="全局网关健康检查探针")
@app.get("/api/v1/health", summary="全局网关健康检查探针")
async def health_check():
    ollama_info = await ollama_client.check_health()
    port = int(os.getenv("GATEWAY_PORT", "5221"))
    return {
        "status": "healthy",
        "system": "LawFlow Workspace (LawFlow 智律工作台)",
        "version": "1.0.0",
        "gateway_port": port,
        "ollama": ollama_info,
        "features": {
            "phase1_litigation": True,
            "phase2_evidence": True,
            "phase3_rag_sign": True,
            "phase4_deep_matrix": True,
            "phase5_statutes_kb": True,
            "phase6_compliance": True,
            "matter_vault": True,
            "workflow_state_machine": True,
            "review_tables": True,
            "version_comparator": True,
            "source_grounding": True,
            "phase8_ai_copilot": True,
            "offline_file_converter": True
        }
    }


@app.get("/", response_class=HTMLResponse, summary="工作台 Web UI 首页")
async def serve_index():
    index_file = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return HTMLResponse("<h2>LawFlow 智律工作台初始化中... 请稍后刷新。</h2>")


@app.get("/favicon.ico", include_in_schema=False)
async def serve_favicon():
    ico_file = os.path.join(BASE_DIR, "resources", "lawflow.ico")
    if os.path.exists(ico_file):
        return FileResponse(ico_file, media_type="image/x-icon")
    return HTMLResponse("")


if __name__ == "__main__":
    import uvicorn
    import threading

    host = os.getenv("GATEWAY_HOST", "127.0.0.1")
    primary_port = int(os.getenv("GATEWAY_PORT", "5221"))
    legacy_port = 8000 if primary_port != 8000 else None

    if legacy_port:
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


