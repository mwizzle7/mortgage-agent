from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_column(cur: sqlite3.Cursor, table: str, column: str, definition: str) -> None:
    cur.execute(f"PRAGMA table_info({table})")
    columns = {row[1] for row in cur.fetchall()}
    if column not in columns:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db(db_path: str) -> None:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute(
        """
    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        event_type TEXT NOT NULL,
        request_id TEXT,
        session_id TEXT,
        user_id_hash TEXT,
        payload_json TEXT NOT NULL
    )
    """
    )

    cur.execute(
        """
    CREATE TABLE IF NOT EXISTS sessions (
        session_id TEXT PRIMARY KEY,
        user_id_hash TEXT NOT NULL,
        created_at TEXT NOT NULL,
        question_count INTEGER NOT NULL DEFAULT 0
    )
    """
    )

    cur.execute(
        """
    CREATE TABLE IF NOT EXISTS daily_usage (
        usage_date TEXT NOT NULL,
        user_id_hash TEXT NOT NULL,
        question_count INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (usage_date, user_id_hash)
    )
    """
    )

    cur.execute(
        """
    CREATE TABLE IF NOT EXISTS documents (
        doc_id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        page_title TEXT,
        source_name TEXT NOT NULL,
        source_url TEXT,
        source_domain TEXT,
        jurisdiction TEXT,
        published_date TEXT,
        retrieved_date TEXT NOT NULL,
        corpus_version TEXT NOT NULL,
        content_type TEXT,
        is_approved INTEGER NOT NULL DEFAULT 1
    )
    """
    )
    _ensure_column(cur, "documents", "content_type", "TEXT")
    _ensure_column(cur, "documents", "page_title", "TEXT")
    _ensure_column(cur, "documents", "source_domain", "TEXT")

    cur.execute(
        """
    CREATE TABLE IF NOT EXISTS chunks (
        chunk_id TEXT PRIMARY KEY,
        doc_id TEXT NOT NULL,
        chunk_index INTEGER NOT NULL,
        text TEXT NOT NULL,
        embedding_index INTEGER NOT NULL,
        FOREIGN KEY (doc_id) REFERENCES documents(doc_id)
    )
    """
    )

    conn.commit()
    conn.close()


def log_event(
    db_path: str,
    event_type: str,
    request_id: str | None,
    session_id: str | None,
    user_id_hash: str | None,
    payload: dict,
) -> None:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO events (timestamp, event_type, request_id, session_id, user_id_hash, payload_json) VALUES (?, ?, ?, ?, ?, ?)",
        (
            _utc_now(),
            event_type,
            request_id,
            session_id,
            user_id_hash,
            json.dumps(payload, ensure_ascii=False),
        ),
    )
    conn.commit()
    conn.close()
