# -*- coding: utf-8 -*-
"""本所公函函号：律师填写的前缀 + 年度流水号。

没有前缀时函号写「【待填写函号前缀】」，不自动生成示例字号。
流水存在 LAWFLOW_STORAGE_DIR/letter_sequence.db 的 letter_sequence 表。
"""
from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Iterator

from gateway.core.paths import get_storage_dir

MISSING_LETTER_NO = "【待填写函号前缀】"
FORBIDDEN_PREFIX = "京律函字"
_PREFIX_RE = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]{1,20}")


def _db_path():
    return get_storage_dir() / "letter_sequence.db"


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=5, isolation_level=None)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("BEGIN IMMEDIATE")
        try:
            _ensure(conn)
            yield conn
            conn.execute("COMMIT")
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
    finally:
        conn.close()


def _ensure(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS letter_sequence (
            kind TEXT NOT NULL,
            year INTEGER NOT NULL,
            prefix TEXT NOT NULL DEFAULT '',
            last_no INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (kind, year)
        )
        """
    )


def normalize_letter_prefix(prefix: str) -> str:
    """空字符串表示尚未设置。示例字号不能存成前缀。"""
    text = re.sub(r"[\s\u3000]+", "", str(prefix or ""))
    if not text:
        return ""
    if FORBIDDEN_PREFIX in text or "待填写" in text:
        raise ValueError(
            "函号前缀不能使用示例字号「京律函字」。请填写本所自己的前缀；没有就留空。"
        )
    if not _PREFIX_RE.fullmatch(text):
        raise ValueError("函号前缀请用 20 个字以内的中文或字母，例如「京师函」。")
    return text


def get_letter_prefix() -> str:
    with _connect() as conn:
        row = conn.execute(
            "SELECT prefix FROM letter_sequence WHERE kind = 'config' AND year = 0"
        ).fetchone()
        if row is None:
            return ""
        return str(row["prefix"] or "").strip()


def set_letter_prefix(prefix: str) -> str:
    text = normalize_letter_prefix(prefix)
    with _connect() as conn:
        existing = conn.execute(
            "SELECT 1 FROM letter_sequence WHERE kind = 'config' AND year = 0"
        ).fetchone()
        if existing is None:
            conn.execute(
                """
                INSERT INTO letter_sequence (kind, year, prefix, last_no)
                VALUES ('config', 0, ?, 0)
                """,
                (text,),
            )
        else:
            conn.execute(
                """
                UPDATE letter_sequence
                   SET prefix = ?
                 WHERE kind = 'config' AND year = 0
                """,
                (text,),
            )
    return text


def _stored_prefix(conn: sqlite3.Connection) -> str:
    row = conn.execute(
        "SELECT prefix FROM letter_sequence WHERE kind = 'config' AND year = 0"
    ).fetchone()
    if row is None:
        return ""
    text = str(row["prefix"] or "").strip()
    if not text or FORBIDDEN_PREFIX in text:
        return ""
    return text


def next_letter_number(year: int | None = None) -> str:
    """取出下一号。没有前缀时不占流水号。"""
    current_year = int(year or datetime.now().year)
    with _connect() as conn:
        prefix = _stored_prefix(conn)
        if not prefix:
            return MISSING_LETTER_NO
        row = conn.execute(
            "SELECT last_no FROM letter_sequence WHERE kind = 'counter' AND year = ?",
            (current_year,),
        ).fetchone()
        if row is None:
            seq = 1
            conn.execute(
                """
                INSERT INTO letter_sequence (kind, year, prefix, last_no)
                VALUES ('counter', ?, '', 1)
                """,
                (current_year,),
            )
        else:
            seq = int(row["last_no"]) + 1
            conn.execute(
                """
                UPDATE letter_sequence
                   SET last_no = ?
                 WHERE kind = 'counter' AND year = ?
                """,
                (seq, current_year),
            )
    return f"{prefix}〔{current_year}〕第{seq}号"
