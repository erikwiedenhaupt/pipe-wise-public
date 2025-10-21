# backend/api/routes_runs.py
"""
Pipewise API – Runs & Artifacts (now loads real artifacts and computes KPIs/issues)
"""

from __future__ import annotations

import os
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Path, Request
from pydantic import BaseModel, Field

from tools.kpi_calculator import compute_kpis_from_artifacts  # type: ignore
from tools.issue_detector import detect_issues_from_artifacts  # type: ignore

router = APIRouter(tags=["runs"], prefix="")

# DTOs aligned with API plan
class RunGetRes(BaseModel):
    status: str
    logs: Optional[str] = None
    artifacts: Dict[str, Any] = Field(default_factory=dict)


class KpiItem(BaseModel):
    key: str
    value: float | int | str | Dict[str, Any] | None
    unit: Optional[str] = None
    target_range: Optional[List[float]] = None
    status: str = "OK"
    context: Dict[str, Any] = Field(default_factory=dict)


class KpisRes(BaseModel):
    global_: List[KpiItem] = Field(default_factory=list, alias="global")
    per_node: Dict[str, List[KpiItem]] = Field(default_factory=dict)
    per_pipe: Dict[str, List[KpiItem]] = Field(default_factory=dict)

    class Config:
        populate_by_name = True


class IssueItem(BaseModel):
    id: str
    severity: str
    component_ref: Optional[str] = None
    description: str
    evidence: Optional[Dict[str, Any]] = None
    kpis: Optional[List[str]] = None


class SuggestionItem(BaseModel):
    id: str
    title: str
    detail: str
    estimated_impact: Optional[Dict[str, Any]] = None
    actions: List[Dict[str, Any]] = Field(default_factory=list)


class IssuesRes(BaseModel):
    issues: List[IssueItem]
    suggestions: List[SuggestionItem]


class RunListItem(BaseModel):
    id: str
    status: str
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class RunListRes(BaseModel):
    items: List[RunListItem]
    total: int


def _load_artifacts_for_run(request: Request, run_id: str) -> Dict[str, Any]:
    storage = request.app.state.storage
    path = storage.payload_dir / f"artifacts_{run_id}.json"
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf8") as fh:
            return json.load(fh)
    except Exception:
        return {}


@router.get("/runs/{run_id}", response_model=RunGetRes, summary="Get run details")
def get_run(run_id: str = Path(...), request: Request = None) -> RunGetRes:
    storage = request.app.state.storage
    run = storage.get_analysis_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    artifacts = _load_artifacts_for_run(request, run_id)

    # Sanitize noisy logs
    def _clean_noise(s: Optional[str]) -> str:
        if not s:
            return ""
        out = []
        for ln in s.splitlines():
            low = ln.lower()
            # matplotlib noise
            if "matplotlib" in low and ("not a writable directory" in low or "created a temporary cache directory" in low or "mplconfigdir" in low):
                continue
            if "mplconfigdir" in low:
                continue
            # generic worker-dir noise
            if "is not a writable directory" in low and ("pipewise_worker" in low or "pipewise_storage" in low):
                continue
            out.append(ln)
        return "\n".join(out).strip()

    cleaned_logs = _clean_noise(run.logs or "")

    node_table = (artifacts.get("results") or {}).get("junction") or []
    pipe_table = (artifacts.get("results") or {}).get("pipe") or []
    pressures = [r.get("p_bar") for r in node_table if r.get("p_bar") is not None]
    velocities = [r.get("v_mean_m_per_s") for r in pipe_table if r.get("v_mean_m_per_s") is not None]

    view: Dict[str, Any] = {
        "pressures": pressures[:2000],
        "flows": velocities[:2000],
        "node_table": node_table,
        "pipe_table": pipe_table,
    }

    # Failure details (reason/tips from metadata) + user code line from artifacts
    reason = (run.metadata or {}).get("failure_reason")
    tips = (run.metadata or {}).get("tips") or []
    code_line = artifacts.get("user_error_line") if artifacts.get("user_code_error") else None
    code_msg = artifacts.get("user_error") if artifacts.get("user_code_error") else None
    if reason or tips or code_line or code_msg:
        failure = {"reason": reason, "tips": tips}
        if code_line:
            failure["code_line"] = code_line
        if code_msg:
            failure["code_message"] = code_msg
        view["failure"] = failure

    return RunGetRes(status=run.status.value, logs=cleaned_logs, artifacts=view)

@router.get("/runs/{run_id}/kpis", response_model=KpisRes, summary="Get run KPIs")
def get_run_kpis(run_id: str = Path(...), request: Request = None) -> KpisRes:
    storage = request.app.state.storage
    run = storage.get_analysis_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    artifacts = _load_artifacts_for_run(request, run_id)
    if not artifacts:
        # no artifacts yet
        return KpisRes(**{"global": []}, per_node={}, per_pipe={})
    k = compute_kpis_from_artifacts(artifacts)
    # Normalize to KpisRes
    global_items = [KpiItem(**g) for g in k.get("global", [])]
    per_node = {k: [KpiItem(**it) for it in v] for k, v in (k.get("per_node", {}) or {}).items()}
    per_pipe = {k: [KpiItem(**it) for it in v] for k, v in (k.get("per_pipe", {}) or {}).items()}
    return KpisRes(**{"global": global_items}, per_node=per_node, per_pipe=per_pipe)


@router.get("/runs/{run_id}/issues", response_model=IssuesRes, summary="Get run issues")
def get_run_issues(run_id: str = Path(...), request: Request = None) -> IssuesRes:
    storage = request.app.state.storage
    run = storage.get_analysis_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    artifacts = _load_artifacts_for_run(request, run_id)
    if not artifacts:
        return IssuesRes(issues=[], suggestions=[])
    issues, suggestions = detect_issues_from_artifacts(artifacts)
    # Validate shapes
    issues_items = [IssueItem(**i) for i in issues]
    sugg_items = [SuggestionItem(**s) for s in suggestions]
    return IssuesRes(issues=issues_items, suggestions=sugg_items)


@router.get("/projects/{project_id}/runs", response_model=RunListRes, summary="List project runs")
def list_project_runs(project_id: str, request: Request) -> RunListRes:
    storage = request.app.state.storage
    items: List[RunListItem] = []
    try:
        with storage._get_conn() as conn:  # scaffold access
            cur = conn.cursor()
            cur.execute(
                "SELECT id, status, started_at, finished_at FROM analysis_runs WHERE project_id = ? ORDER BY started_at DESC",
                (project_id,),
            )
            for rid, status, started, finished in cur.fetchall():
                items.append(
                    RunListItem(
                        id=rid,
                        status=status,
                        started_at=datetime.fromisoformat(started) if started else None,
                        finished_at=datetime.fromisoformat(finished) if finished else None,
                    )
                )
    except Exception:
        pass
    return RunListRes(items=items, total=len(items))


@router.delete("/runs/{run_id}", summary="Delete a run", status_code=204)
def delete_run(run_id: str, request: Request):
    storage = request.app.state.storage
    # Delete DB row
    try:
        with storage._get_conn() as conn:  # scaffold access
            cur = conn.cursor()
            cur.execute("DELETE FROM analysis_runs WHERE id = ?", (run_id,))
            conn.commit()
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to delete run")
    # Delete artifacts
    try:
        path = storage.payload_dir / f"artifacts_{run_id}.json"
        if path.exists():
            path.unlink(missing_ok=True)  # type: ignore[arg-type]
    except Exception:
        pass
    return