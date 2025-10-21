# backend/core/agent_orchestrator.py
"""
Orchestrator for LangChain-like supervisor/subagents.

This module provides a lightweight orchestrator interface that:
- accepts an AnalysisRun request
- uses registered tools to perform sub-tasks (via registry)
- can spawn sandboxed workers (via sandbox.run_python_snippet) to isolate work
- collects logs, KPIs, issues, and suggestions and persists via Storage

This is intentionally lightweight and dependency-free: it does not import LangChain.
Instead, it models interactions and provides extension points for injecting
real agent frameworks later.

Main class: AgentOrchestrator
"""

from __future__ import annotations
from typing import Optional, Dict, Any, List
import uuid
import logging
import json
import threading

from . import models
from .storage import Storage
from .tool_registry import ToolRegistry
from .sandbox import run_python_snippet, run_command, RunResult
from .security import resource_limits_for_run, ResourceLimits

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class OrchestratorError(Exception):
    pass


class AgentOrchestrator:
    """
    High-level orchestrator.

    Responsibilities:
    - coordinate tool usage
    - spawn sandboxed workers for heavy computations
    - assemble results into AnalysisRun objects and persist via Storage

    This class is intentionally synchronous for clarity. In production you might
    run asynchronous workers and event streams.
    """

    def __init__(self, storage: Storage, tool_registry: ToolRegistry):
        self.storage = storage
        self.tools = tool_registry
        self._lock = threading.RLock()

    def _generate_run_id(self) -> str:
        return f"run-{uuid.uuid4().hex}"

    def start_analysis_run(self, project_id: str, network_version_id: str, executor_hint: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> models.AnalysisRun:
        """
        Create and start a new AnalysisRun. This spawns a sandboxed Python snippet
        that acts as a worker; in a real system the worker would be a dedicated
        binary or container.

        Returns the saved AnalysisRun (may be in RUNNING state).
        """
        run_id = self._generate_run_id()
        run = models.AnalysisRun(
            id=run_id,
            project_id=project_id,
            network_version_id=network_version_id,
            started_at=None,
            finished_at=None,
            status=models.AnalysisStatus.PENDING,
            executor=executor_hint,
            metadata=metadata or {},
        )
        # persist initial run
        self.storage.save_analysis_run(run)

        # spawn the worker synchronously (blocking). In future switch to async/background queue.
        try:
            self._execute_run_sync(run)
        except Exception as e:
            logger.exception("Analysis run failed")
            run.status = models.AnalysisStatus.FAILED
            run.finished_at = __import__("datetime").datetime.utcnow()
            run.logs = f"Failed to schedule/execute: {e}"
            self.storage.save_analysis_run(run)
        return run

    def _execute_run_sync(self, run: models.AnalysisRun) -> None:
        """
        Execute a simple worker that:
        - loads the network payload from storage
        - performs a tiny sample KPI computation (dummy)
        - returns results as JSON written to stdout which we parse
        """
        # mark running
        run.started_at = __import__("datetime").datetime.utcnow()
        run.status = models.AnalysisStatus.RUNNING
        self.storage.save_analysis_run(run)

        # Load network payload - may be None
        nv = self.storage.get_network_version(run.network_version_id)
        payload = None
        if nv:
            payload = self.storage.load_network_payload(nv)

        # Build a small python snippet to run in the sandbox that simulates KPI computation.
        snippet = self._build_worker_snippet(run.id, payload)

        # Resource limits reasonable for KPI jobs
        limits = resource_limits_for_run(cpu_seconds=10, memory_mb=256, wall_seconds=20)

        result: RunResult = run_python_snippet(snippet, limits=limits, timeout=limits.wall_time_seconds)

        # Collect logs and decode output
        logs = f"stdout:\n{result.stdout}\n\nstderr:\n{result.stderr}"
        run.logs = logs

        if result.returncode != 0 or result.timed_out or result.killed:
            run.status = models.AnalysisStatus.FAILED
            run.finished_at = __import__("datetime").datetime.utcnow()
            run.kpis = []
            run.issues = []
            run.suggestions = []
            self.storage.save_analysis_run(run)
            return

        # Expect the worker to output a JSON blob on stdout with keys 'kpis','issues','suggestions'
        try:
            parsed = json.loads(result.stdout.strip() or "{}")
        except Exception:
            parsed = {}

        # Parse KPIs
        kpis = []
        for k in parsed.get("kpis", []):
            try:
                kpi = models.Kpi(**k)
                kpis.append(kpi)
            except Exception:
                # best-effort: wrap raw dict
                kpis.append(models.Kpi(id=str(uuid.uuid4()), run_id=run.id, name=k.get("name", "unknown"), type=models.KpiType.CUSTOM, value=float(k.get("value", 0.0)), status=models.StatusEnum.UNKNOWN))
        issues = []
        for i in parsed.get("issues", []):
            try:
                issue = models.Issue(**i)
                issues.append(issue)
            except Exception:
                issues.append(models.Issue(id=str(uuid.uuid4()), run_id=run.id, title=i.get("title", "issue"), description=i.get("description")))

        suggestions = []
        for s in parsed.get("suggestions", []):
            try:
                sug = models.Suggestion(**s)
                suggestions.append(sug)
            except Exception:
                suggestions.append(models.Suggestion(id=str(uuid.uuid4()), run_id=run.id, title=s.get("title", "suggestion"), description=s.get("description")))

        run.kpis = kpis
        run.issues = issues
        run.suggestions = suggestions
        run.status = models.AnalysisStatus.SUCCESS
        run.finished_at = __import__("datetime").datetime.utcnow()
        self.storage.save_analysis_run(run)

    def _build_worker_snippet(self, run_id: str, payload: Optional[Dict[str, Any]]) -> str:
        """
        Build a Python snippet that acts as a worker. It should be small and
        deterministic — producing JSON to stdout describing kpis/issues/suggestions.

        NOTE: This is a stub implementation. Replace with a real worker in production.
        """
        # escape payload safely for embedding (best-effort)
        safe_payload = json.dumps(payload or {}, default=str)
        snippet = f"""
import json, time, uuid
# Worker snippet for run {run_id}
payload = json.loads({safe_payload!r})

# Simulated KPI computation delay
time.sleep(0.5)

kpis = [
    {{
        "id": str(uuid.uuid4()),
        "run_id": "{run_id}",
        "name": "avg_pressure",
        "type": "pressure",
        "value": 3.14,
        "unit": "bar",
        "status": "OK"
    }}
]

issues = []
# Very naive check: if payload contains key 'leak' mark an issue
if isinstance(payload, dict) and payload.get("leak"):
    issues.append({{
        "id": str(uuid.uuid4()),
        "run_id": "{run_id}",
        "title": "Detected leak risk",
        "description": "Payload signalled a leak",
        "severity": "high",
        "status": "WARN",
        "node_refs": payload.get("leak_nodes", [])
    }})

suggestions = []
if issues:
    suggestions.append({{
        "id": str(uuid.uuid4()),
        "issue_id": issues[0].get("id"),
        "run_id": "{run_id}",
        "suggestion_type": "repair",
        "title": "Isolate section and inspect",
        "description": "Suggested manual inspection and pressure reduction",
        "confidence": 0.9
    }})

out = {{
    "kpis": kpis,
    "issues": issues,
    "suggestions": suggestions
}}

print(json.dumps(out))
"""
        return snippet
