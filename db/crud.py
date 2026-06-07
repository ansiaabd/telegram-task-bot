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


def add_task(title: str, assignee: str, deadline: str, description: str = "") -> int:
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO tasks (title, description, assignee, deadline) VALUES (?, ?, ?, ?)",
        (title, description, assignee, deadline),
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


def list_tasks(include_done: bool = False) -> list[dict]:
    conn = get_connection()
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
    allowed = {"title", "description", "assignee", "deadline", "status", "calendar_event_id"}
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
