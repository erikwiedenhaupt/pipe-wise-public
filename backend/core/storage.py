# core/storage.py
from __future__ import annotations
import json
import os
import threading
import sqlite3
from typing import Optional, List, Dict, Any
from datetime import datetime
from pathlib import Path

from . import models

_BASE_DIR = Path(os.getenv("PIPEWISE_STORAGE_PATH", "/tmp/pipewise_storage"))
_DB_PATH = _BASE_DIR / "pipewise.db"
_PAYLOAD_DIR = _BASE_DIR / "payloads"

os.makedirs(_PAYLOAD_DIR, exist_ok=True)
_DB_PATH.parent.mkdir(parents=True, exist_ok=True)


class StorageError(Exception):
    pass


class Storage:
    def __init__(self, db_path: Optional[str] = None, payload_dir: Optional[str] = None):
        self.db_path = db_path or str(_DB_PATH)
        self.payload_dir = Path(payload_dir or str(_PAYLOAD_DIR))
        self.lock = threading.RLock()
        self._init_db()

    def _init_db(self) -> None:
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT,
                    created_at TEXT,
                    metadata TEXT
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS network_versions (
                    id TEXT PRIMARY KEY,
                    project_id TEXT,
                    version_tag TEXT,
                    created_at TEXT,
                    payload_ref TEXT,
                    author TEXT,
                    notes TEXT
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS analysis_runs (
                    id TEXT PRIMARY KEY,
                    project_id TEXT,
                    network_version_id TEXT,
                    started_at TEXT,
                    finished_at TEXT,
                    status TEXT,
                    executor TEXT,
                    metadata TEXT,
                    logs TEXT
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS tools (
                    id TEXT PRIMARY KEY,
                    name TEXT,
                    spec_json TEXT
                )
                """
            )
            conn.commit()

    def _get_conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path, check_same_thread=False)

    def save_project(self, project: models.Project) -> None:
        with self.lock, self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO projects (id, name, created_at, metadata)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                   name=excluded.name,
                   created_at=excluded.created_at,
                   metadata=excluded.metadata
                """,
                (project.id, project.name, project.created_at.isoformat(), json.dumps(project.metadata)),
            )
            conn.commit()

    def get_project(self, project_id: str) -> Optional[models.Project]:
        with self.lock, self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id, name, created_at, metadata FROM projects WHERE id = ?", (project_id,))
            row = cur.fetchone()
            if not row:
                return None
            id_, name, created_at, metadata = row
            return models.Project(
                id=id_,
                name=name,
                created_at=datetime.fromisoformat(created_at),
                metadata=json.loads(metadata or "{}"),
            )

    def save_network_version(self, nv: models.NetworkVersion, payload: Optional[Dict[str, Any]] = None) -> None:
        with self.lock, self._get_conn() as conn:
            cur = conn.cursor()
            payload_ref = nv.payload_ref
            if payload is not None:
                filename = f"{nv.id}.json"
                path = self.payload_dir / filename
                with open(path, "w", encoding="utf8") as fh:
                    json.dump(payload, fh, default=str, indent=2)
                payload_ref = str(path)
            cur.execute(
                """
                INSERT INTO network_versions (id, project_id, version_tag, created_at, payload_ref, author, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    project_id=excluded.project_id,
                    version_tag=excluded.version_tag,
                    created_at=excluded.created_at,
                    payload_ref=excluded.payload_ref,
                    author=excluded.author,
                    notes=excluded.notes
                """,
                (nv.id, nv.project_id, nv.version_tag, nv.created_at.isoformat(), payload_ref, nv.author, nv.notes),
            )
            conn.commit()

    def get_network_version(self, nv_id: str) -> Optional[models.NetworkVersion]:
        with self.lock, self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, project_id, version_tag, created_at, payload_ref, author, notes FROM network_versions WHERE id = ?",
                (nv_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            id_, project_id, version_tag, created_at, payload_ref, author, notes = row
            return models.NetworkVersion(
                id=id_,
                project_id=project_id,
                version_tag=version_tag,
                created_at=datetime.fromisoformat(created_at),
                payload_ref=payload_ref,
                author=author,
                notes=notes,
            )

    def load_network_payload(self, nv: models.NetworkVersion) -> Optional[Dict[str, Any]]:
        if not nv.payload_ref:
            return None
        path = Path(nv.payload_ref)
        if not path.exists():
            return None
        with open(path, "r", encoding="utf8") as fh:
            return json.load(fh)

    def save_analysis_run(self, run: models.AnalysisRun) -> None:
        with self.lock, self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO analysis_runs (id, project_id, network_version_id, started_at, finished_at, status, executor, metadata, logs)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                   project_id=excluded.project_id,
                   network_version_id=excluded.network_version_id,
                   started_at=excluded.started_at,
                   finished_at=excluded.finished_at,
                   status=excluded.status,
                   executor=excluded.executor,
                   metadata=excluded.metadata,
                   logs=excluded.logs
                """,
                (
                    run.id,
                    run.project_id,
                    run.network_version_id,
                    run.started_at.isoformat() if run.started_at else None,
                    run.finished_at.isoformat() if run.finished_at else None,
                    run.status.value,
                    run.executor,
                    json.dumps(run.metadata or {}),
                    run.logs,
                ),
            )
            conn.commit()
            payload = {
                "kpis": [k.dict() for k in run.kpis],
                "issues": [i.dict() for i in run.issues],
                "suggestions": [s.dict() for s in run.suggestions],
            }
            path = self.payload_dir / f"analysis_{run.id}.json"
            with open(path, "w", encoding="utf8") as fh:
                json.dump(payload, fh, default=str, indent=2)

    def get_analysis_run(self, run_id: str) -> Optional[models.AnalysisRun]:
        with self.lock, self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, project_id, network_version_id, started_at, finished_at, status, executor, metadata, logs FROM analysis_runs WHERE id = ?",
                (run_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            id_, project_id, network_version_id, started_at, finished_at, status, executor, metadata, logs = row
            payload_path = self.payload_dir / f"analysis_{id_}.json"
            kpis, issues, suggestions = [], [], []
            if payload_path.exists():
                try:
                    with open(payload_path, "r", encoding="utf8") as fh:
                        pl = json.load(fh)
                        kpis = [models.Kpi(**k) for k in pl.get("kpis", [])]
                        issues = [models.Issue(**i) for i in pl.get("issues", [])]
                        suggestions = [models.Suggestion(**s) for s in pl.get("suggestions", [])]
                except Exception:
                    pass
            return models.AnalysisRun(
                id=id_,
                project_id=project_id,
                network_version_id=network_version_id,
                started_at=datetime.fromisoformat(started_at) if started_at else None,
                finished_at=datetime.fromisoformat(finished_at) if finished_at else None,
                status=models.AnalysisStatus(status),
                executor=executor,
                metadata=json.loads(metadata or "{}"),
                logs=logs,
                kpis=kpis,
                issues=issues,
                suggestions=suggestions,
            )

    def register_tool(self, tool: models.ToolSpec) -> None:
        with self.lock, self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO tools (id, name, spec_json)
                VALUES (?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                   name=excluded.name,
                   spec_json=excluded.spec_json
                """,
                (tool.id, tool.name, json.dumps(tool.dict(), default=str)),
            )
            conn.commit()

    def get_tool(self, tool_id: str) -> Optional[models.ToolSpec]:
        with self.lock, self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT spec_json FROM tools WHERE id = ?", (tool_id,))
            row = cur.fetchone()
            if not row:
                return None
            spec = json.loads(row[0])
            return models.ToolSpec(**spec)

    def list_tools(self) -> List[models.ToolSpec]:
        with self.lock, self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT spec_json FROM tools")
            rows = cur.fetchall()
            out: List[models.ToolSpec] = []
            for (spec_json,) in rows:
                try:
                    out.append(models.ToolSpec(**json.loads(spec_json)))
                except Exception:
                    continue
            return out

    def list_projects(self) -> List[models.Project]:
        with self.lock, self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id, name, created_at, metadata FROM projects")
            rows = cur.fetchall()
            out: List[models.Project] = []
            for id_, name, created_at, metadata in rows:
                out.append(
                    models.Project(
                        id=id_, name=name, created_at=datetime.fromisoformat(created_at), metadata=json.loads(metadata or "{}")
                    )
                )
            return out