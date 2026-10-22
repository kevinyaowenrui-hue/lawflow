"""
LawFlow 智律工作台 - 集中路径常量
所有 storage / frontend / templates / 数据库路径在调用时读取环境变量，便于测试与容器重定向。
不再依赖 main.py 文件所在位置推算。
"""
from __future__ import annotations

import os
from pathlib import Path


def get_base_dir() -> Path:
    """项目根目录（含 gateway/、frontend/、storage/）。可由 LAWFLOW_BASE_DIR 覆盖。"""
    override = os.environ.get("LAWFLOW_BASE_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).resolve().parent.parent.parent


def get_storage_dir() -> Path:
    """
    数据目录：优先环境变量 LAWFLOW_STORAGE_DIR，否则 <BASE_DIR>/storage。
    每次调用重新读取，保证测试可在导入后重定向。
    """
    override = os.environ.get("LAWFLOW_STORAGE_DIR")
    if override:
        path = Path(override).expanduser().resolve()
    else:
        path = get_base_dir() / "storage"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_frontend_dir() -> Path:
    """前端静态资源目录：LAWFLOW_FRONTEND_DIR 或 <BASE_DIR>/frontend。"""
    override = os.environ.get("LAWFLOW_FRONTEND_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return get_base_dir() / "frontend"


def get_templates_dir() -> Path:
    """文书模板目录：LAWFLOW_TEMPLATES_DIR 或 <BASE_DIR>/templates。"""
    override = os.environ.get("LAWFLOW_TEMPLATES_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return get_base_dir() / "templates"


def get_fonts_dir() -> Path:
    """中文字体目录：LAWFLOW_FONTS_DIR 或 <BASE_DIR>/fonts。"""
    override = os.environ.get("LAWFLOW_FONTS_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return get_base_dir() / "fonts"


def get_cjk_font_candidates() -> list[str]:
    """
    CJK 字体候选路径：优先 LAWFLOW_FONTS_DIR 下常见文件，再回退系统字体。
    不硬编码开发者本机盘符。
    """
    fonts_dir = get_fonts_dir()
    candidates: list[str] = []
    if fonts_dir.is_dir():
        for name in (
            "msyh.ttc",
            "simsun.ttc",
            "simhei.ttf",
            "NotoSansSC-Regular.otf",
            "NotoSansCJK-Regular.ttc",
            "SourceHanSansSC-Regular.otf",
        ):
            p = fonts_dir / name
            if p.exists():
                candidates.append(str(p.resolve()))
        for p in sorted(fonts_dir.glob("*.*")):
            if p.suffix.lower() in {".ttf", ".ttc", ".otf"} and str(p.resolve()) not in candidates:
                candidates.append(str(p.resolve()))

    windir = os.environ.get("WINDIR") or os.environ.get("SystemRoot")
    if windir:
        win_fonts = Path(windir) / "Fonts"
        for name in ("msyh.ttc", "simsun.ttc", "simhei.ttf"):
            p = win_fonts / name
            if p.exists():
                candidates.append(str(p.resolve()))

    candidates.extend(
        [
            "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
            "/usr/share/fonts/wqy-microhei/wqy-microhei.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/custom/NotoSansCJK-Regular.ttc",
        ]
    )
    # 去重并保持顺序
    seen: set[str] = set()
    out: list[str] = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def get_generated_dir() -> Path:
    path = get_storage_dir() / "generated"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_uploads_dir() -> Path:
    path = get_storage_dir() / "uploads"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_laws_db_path() -> Path:
    return get_storage_dir() / "cn_laws_kb.db"


def get_vault_db_path() -> Path:
    return get_storage_dir() / "matter_vault.db"


# 兼容旧代码中的模块级别名风格（仍为函数，避免导入时固化路径）
def BASE_DIR() -> str:
    return str(get_base_dir())


def STORAGE_DIR() -> str:
    return str(get_storage_dir())


def GENERATED_DIR() -> str:
    return str(get_generated_dir())


def UPLOADS_DIR() -> str:
    return str(get_uploads_dir())


def LAWS_DB_PATH() -> str:
    return str(get_laws_db_path())


def VAULT_DB_PATH() -> str:
    return str(get_vault_db_path())


def FRONTEND_DIR() -> str:
    return str(get_frontend_dir())


def TEMPLATES_DIR() -> str:
    return str(get_templates_dir())
