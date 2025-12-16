import hashlib
import sqlite3
from datetime import datetime


def hash_user_id(user_id: str, salt: str) -> str:
    raw = (salt + ":" + user_id).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _today() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d")


def ensure_session(db_path: str, session_id: str, user_id_hash: str) -> None:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT session_id FROM sessions WHERE session_id = ?", (session_id,))
    row = cur.fetchone()
    if row is None:
        cur.execute(
            "INSERT INTO sessions (session_id, user_id_hash, created_at, question_count) VALUES (?, ?, ?, 0)",
            (session_id, user_id_hash, datetime.utcnow().isoformat()),
        )
    conn.commit()
    conn.close()


def check_and_increment(
    db_path: str,
    user_id_hash: str,
    session_id: str,
    q_limit_day: int,
    q_limit_session: int,
) -> tuple[bool, str]:
    today = _today()
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Daily usage
    cur.execute(
        "SELECT question_count FROM daily_usage WHERE usage_date = ? AND user_id_hash = ?",
        (today, user_id_hash),
    )
    row = cur.fetchone()
    daily_count = row[0] if row else 0
    if daily_count >= q_limit_day:
        conn.close()
        return False, "QUESTION_LIMIT_PER_DAY"

    # Session usage
    cur.execute("SELECT question_count FROM sessions WHERE session_id = ?", (session_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return False, "SESSION_NOT_INITIALIZED"
    session_count = row[0]
    if session_count >= q_limit_session:
        conn.close()
        return False, "QUESTION_LIMIT_PER_SESSION"

    cur.execute(
        """
        INSERT INTO daily_usage (usage_date, user_id_hash, question_count)
        VALUES (?, ?, 1)
        ON CONFLICT(usage_date, user_id_hash)
        DO UPDATE SET question_count = question_count + 1
    """,
        (today, user_id_hash),
    )

    cur.execute(
        "UPDATE sessions SET question_count = question_count + 1 WHERE session_id = ?",
        (session_id,),
    )
    conn.commit()
    conn.close()
    return True, "OK"
