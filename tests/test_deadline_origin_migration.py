# -*- coding: utf-8 -*-
"""期限表 origin 列：空库和已有库都能初始化，连续两次不报 duplicate column。"""
from __future__ import annotations

import sqlite3


def _origin_columns(db_path) -> list:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("PRAGMA table_info(matter_deadlines)").fetchall()
    finally:
        conn.close()
    return [row[1] for row in rows if str(row[1]).lower() == "origin"]


def test_empty_dir_init_twice_does_not_duplicate_origin(tmp_path, monkeypatch):
    storage = tmp_path / "empty-vault"
    monkeypatch.setenv("LAWFLOW_STORAGE_DIR", str(storage))
    monkeypatch.delenv("LAWFLOW_SEED_DEMO", raising=False)

    from gateway.core.paths import get_vault_db_path
    from gateway.utils.matter_vault_db import init_matter_vault_db

    init_matter_vault_db()
    init_matter_vault_db()

    assert _origin_columns(get_vault_db_path()) == ["origin"]


def test_existing_db_without_origin_then_second_init(tmp_path, monkeypatch):
    storage = tmp_path / "legacy-vault"
    monkeypatch.setenv("LAWFLOW_STORAGE_DIR", str(storage))
    monkeypatch.delenv("LAWFLOW_SEED_DEMO", raising=False)
    storage.mkdir()
    db_path = storage / "matter_vault.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE matter_deadlines (
            id TEXT PRIMARY KEY,
            matter_id TEXT,
            kind TEXT NOT NULL,
            due_date TEXT NOT NULL,
            source TEXT,
            note TEXT,
            done INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        INSERT INTO matter_deadlines
            (id, matter_id, kind, due_date, source, note, done, created_at)
        VALUES ('DL-old', NULL, 'hearing', '2026-12-01', '', '', 0, '2026-01-01 00:00:00')
        """
    )
    conn.commit()
    conn.close()

    from gateway.utils.matter_vault_db import init_matter_vault_db

    init_matter_vault_db()
    init_matter_vault_db()

    assert _origin_columns(db_path) == ["origin"]
    conn = sqlite3.connect(db_path)
    try:
        origin = conn.execute(
            "SELECT origin FROM matter_deadlines WHERE id = 'DL-old'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert origin == "lawyer_note"


def test_existing_origin_column_is_not_altered_again(tmp_path, monkeypatch):
    storage = tmp_path / "already-origin"
    monkeypatch.setenv("LAWFLOW_STORAGE_DIR", str(storage))
    monkeypatch.delenv("LAWFLOW_SEED_DEMO", raising=False)
    storage.mkdir()
    db_path = storage / "matter_vault.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE matter_deadlines (
            id TEXT PRIMARY KEY,
            matter_id TEXT,
            kind TEXT NOT NULL,
            due_date TEXT NOT NULL,
            source TEXT,
            note TEXT,
            done INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            origin TEXT NOT NULL DEFAULT 'lawyer_note'
        )
        """
    )
    conn.commit()
    conn.close()

    from gateway.utils.matter_vault_db import init_matter_vault_db

    init_matter_vault_db()
    init_matter_vault_db()

    assert _origin_columns(db_path) == ["origin"]
