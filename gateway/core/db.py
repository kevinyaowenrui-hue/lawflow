"""
LawFlow 智律工作台 - SQLite 连接上下文管理器
确保任意异常路径都会 rollback + close，避免锁库。
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional, Union


@contextmanager
def connect(
    path: Union[str, Path],
    *,
    row_factory: Optional[type] = sqlite3.Row,
) -> Iterator[sqlite3.Connection]:
    """
    打开 SQLite 连接：foreign_keys / busy_timeout / WAL；
    正常结束 commit，异常 rollback 后重新抛出，finally 一定 close。
    """
    db_path = Path(path)
    parent = db_path.parent
    if str(parent) and str(parent) != ".":
        os.makedirs(parent, exist_ok=True)

    conn = sqlite3.connect(str(db_path), timeout=5)
    try:
        if row_factory is not None:
            conn.row_factory = row_factory
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA journal_mode=WAL")
        yield conn
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()
