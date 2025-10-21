# backend/core/memory.py
from __future__ import annotations
import sqlite3
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime
import json
import os

GLOBAL_PROJECT_ID = "GLOBAL"

class MemoryStore:
    def __init__(self, db_path: Optional[str] = None):
        # Reuse the same DB the Storage uses (pipewise.db)
        self.db_path = db_path or os.path.abspath(os.getenv("PIPEWISE_STORAGE_PATH", "/tmp/pipewise_storage/pipewise.db"))
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path, check_same_thread=False)

    def _init_db(self) -> None:
        with self._conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS memory_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT,
                    run_id TEXT,
                    role TEXT,
                    content TEXT,
                    tool_name TEXT,
                    tokens INTEGER,
                    meta_json TEXT,
                    created_at TEXT
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS memory_lessons (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT,
                    title TEXT,
                    body TEXT,
                    tags TEXT,
                    weight REAL DEFAULT 1.0,
                    embedding_json TEXT,
                    created_at TEXT
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS run_scores (
                    run_id TEXT PRIMARY KEY,
                    project_id TEXT,
                    score REAL,
                    components_json TEXT,
                    created_at TEXT
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS tool_stats (
                    project_id TEXT,
                    tool_name TEXT,
                    calls INTEGER,
                    avg_delta REAL,
                    last_used TEXT,
                    PRIMARY KEY(project_id, tool_name)
                )
            """)
            conn.commit()

    # ---- Messages ----
    def add_message(self, project_id: Optional[str], role: str, content: str,
                    *, run_id: Optional[str] = None, tool_name: Optional[str] = None,
                    tokens: Optional[int] = None, meta: Optional[Dict[str, Any]] = None) -> int:
        with self._conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO memory_messages (project_id, run_id, role, content, tool_name, tokens, meta_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                project_id or GLOBAL_PROJECT_ID,
                run_id,
                role,
                content,
                tool_name,
                tokens or 0,
                json.dumps(meta or {}, default=str),
                datetime.utcnow().isoformat()
            ))
            conn.commit()
            return cur.lastrowid

    # ---- Lessons ----
    def add_lesson(self, project_id: Optional[str], title: str, body: str,
                   *, tags: Optional[List[str]] = None, weight: float = 1.0,
                   embedding: Optional[List[float]] = None) -> int:
        with self._conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO memory_lessons (project_id, title, body, tags, weight, embedding_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                project_id or GLOBAL_PROJECT_ID,
                title,
                body,
                ",".join(tags or []),
                float(weight),
                json.dumps(embedding) if embedding is not None else None,
                datetime.utcnow().isoformat()
            ))
            conn.commit()
            return cur.lastrowid

    def list_top_lessons(self, project_id: Optional[str], top_k: int = 5) -> List[Dict[str, Any]]:
        pid = project_id or GLOBAL_PROJECT_ID
        with self._conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT title, body, tags, weight
                FROM memory_lessons
                WHERE project_id IN (?, ?)
                ORDER BY weight DESC, created_at DESC
                LIMIT ?
            """, (pid, GLOBAL_PROJECT_ID, top_k))
            out: List[Dict[str, Any]] = []
            for title, body, tags, weight in cur.fetchall():
                out.append({"title": title, "body": body, "tags": (tags or "").split(",") if tags else [], "weight": weight})
            return out

    def bump_lessons(self, project_id: Optional[str], tags_like: Optional[str], delta: float = 0.1) -> None:
        # Simple global reinforcement by tag substring
        pid = project_id or GLOBAL_PROJECT_ID
        if not tags_like:
            return
        with self._conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE memory_lessons SET weight = weight + ?
                WHERE project_id IN (?, ?) AND tags LIKE ?
            """, (delta, pid, GLOBAL_PROJECT_ID, f"%{tags_like}%"))
            conn.commit()

    # ---- Scores ----
    def record_run_score(self, project_id: Optional[str], run_id: str, score: float,
                         components: Optional[Dict[str, Any]] = None) -> None:
        with self._conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO run_scores (run_id, project_id, score, components_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                   project_id=excluded.project_id,
                   score=excluded.score,
                   components_json=excluded.components_json,
                   created_at=excluded.created_at
            """, (
                run_id,
                project_id or GLOBAL_PROJECT_ID,
                float(score),
                json.dumps(components or {}, default=str),
                datetime.utcnow().isoformat()
            ))
            conn.commit()

    def get_last_score(self, project_id: Optional[str]) -> Optional[float]:
        pid = project_id or GLOBAL_PROJECT_ID
        with self._conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT score FROM run_scores
                WHERE project_id = ?
                ORDER BY created_at DESC
                LIMIT 1
            """, (pid,))
            row = cur.fetchone()
            return float(row[0]) if row else None

    def get_best_score(self, project_id: Optional[str]) -> Optional[float]:
        pid = project_id or GLOBAL_PROJECT_ID
        with self._conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT MIN(score) FROM run_scores
                WHERE project_id = ?
            """, (pid,))
            row = cur.fetchone()
            return float(row[0]) if (row and row[0] is not None) else None

    # ---- Tool stats (simple bandit features) ----
    def update_tool_stats(self, project_id: Optional[str], tool_name: str, delta: float) -> None:
        pid = project_id or GLOBAL_PROJECT_ID
        with self._conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO tool_stats (project_id, tool_name, calls, avg_delta, last_used)
                VALUES (?, ?, 1, ?, ?)
                ON CONFLICT(project_id, tool_name) DO UPDATE SET
                   calls = tool_stats.calls + 1,
                   avg_delta = ((tool_stats.avg_delta * (tool_stats.calls) + ?) / (tool_stats.calls + 1)),
                   last_used = excluded.last_used
            """, (pid, tool_name, float(delta), datetime.utcnow().isoformat(), float(delta)))
            conn.commit()

    def get_preferences(self, project_id: Optional[str], top_k: int = 3) -> List[Tuple[str, float]]:
        pid = project_id or GLOBAL_PROJECT_ID
        with self._conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT tool_name, avg_delta FROM tool_stats
                WHERE project_id IN (?, ?)
                ORDER BY avg_delta ASC, calls DESC
                LIMIT ?
            """, (pid, GLOBAL_PROJECT_ID, top_k))
            return [(t, float(d)) for t, d in cur.fetchall()]