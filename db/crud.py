import sqlite3
from typing import Optional
from db import get_connection

SCHEMA_PATH = "db/schema.sql"


def init_db():
    with open(SCHEMA_PATH) as f:
        schema = f.read()
    conn = get_connection()
    conn.executescript(schema)
    conn.commit()
    conn.close()


# ── Users ────────────────────────────────────────────────

def register_user(user_id: int, username: str, full_name: str):
    conn = get_connection()
    conn.execute(
        "INSERT OR IGNORE INTO users (user_id, username, full_name) VALUES (?, ?, ?)",
        (user_id, username, full_name),
    )
    conn.commit()
    conn.close()


def get_user_by_username(username: str) -> Optional[dict]:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM users WHERE username = ?", (username.lstrip("@"),)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_user(user_id: int) -> Optional[dict]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


# ── Tasks ────────────────────────────────────────────────

def add_task(
    title: str,
    assignee: str,
    deadline: str,
    description: str = "",
    assignee_id: Optional[int] = None,
) -> int:
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO tasks (title, description, assignee, assignee_id, deadline) VALUES (?, ?, ?, ?, ?)",
        (title, description, assignee, assignee_id, deadline),
    )
    conn.commit()
    task_id = cur.lastrowid
    conn.close()
    return task_id


def get_task(task_id: int) -> Optional[dict]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def list_tasks(include_done: bool = False, user_id: Optional[int] = None) -> list[dict]:
    conn = get_connection()
    if user_id:
        if include_done:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE assignee_id = ? ORDER BY deadline",
                (user_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE assignee_id = ? AND status != 'done' ORDER BY deadline",
                (user_id,),
            ).fetchall()
    else:
        if include_done:
            rows = conn.execute("SELECT * FROM tasks ORDER BY deadline").fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE status != 'done' ORDER BY deadline"
            ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_task_status(task_id: int, status: str) -> bool:
    conn = get_connection()
    cur = conn.execute(
        "UPDATE tasks SET status = ? WHERE id = ?", (status, task_id)
    )
    conn.commit()
    updated = cur.rowcount > 0
    conn.close()
    return updated


def update_task_field(task_id: int, field: str, value: str) -> bool:
    allowed = {"title", "description", "assignee", "assignee_id", "deadline", "status", "calendar_event_id"}
    if field not in allowed:
        raise ValueError(f"Field '{field}' is not allowed")
    conn = get_connection()
    cur = conn.execute(
        f"UPDATE tasks SET {field} = ? WHERE id = ?", (value, task_id)
    )
    conn.commit()
    updated = cur.rowcount > 0
    conn.close()
    return updated


def delete_task(task_id: int) -> bool:
    conn = get_connection()
    cur = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted


def list_overdue(user_id: Optional[int] = None) -> list[dict]:
    conn = get_connection()
    if user_id:
        rows = conn.execute(
            "SELECT * FROM tasks WHERE status = 'overdue' AND assignee_id = ? ORDER BY deadline",
            (user_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM tasks WHERE status = 'overdue' ORDER BY deadline"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def list_pending_approval() -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM tasks WHERE status = 'pending_approval' ORDER BY deadline"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
