# api/routes_network.py
"""
Pipewise API – Network operations (real simulate + artifacts + graph + mutations + sweep)
"""

from __future__ import annotations

import uuid
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from core.models import AnalysisRun, AnalysisStatus  # type: ignore
from tools.pandapipes_runner import run_pandapipes_code  # type: ignore
from tools.network_mutations import NetworkMutationsTool  # type: ignore
from tools.scenario_engine import ScenarioEngineTool  # type: ignore

router = APIRouter(tags=["network"], prefix="")

# Request/Response DTOs
class ValidationMessage(BaseModel):
    level: str  # 'info' | 'warn' | 'error'
    where: Optional[str] = None
    text: str


class ValidateReq(BaseModel):
    code: str


class ValidateRes(BaseModel):
    ok: bool
    messages: List[ValidationMessage] = Field(default_factory=list)
    inferred: Dict[str, Any] = Field(default_factory=dict)


class ParseGraphReq(BaseModel):
    code: str


class Graph(BaseModel):
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]


class ParseGraphRes(BaseModel):
    graph: Graph
    components: Dict[str, Any] = Field(default_factory=dict)


class SimulateReq(BaseModel):
    project_id: Optional[str] = None
    version_id: Optional[str] = None
    code: Optional[str] = None
    options: Dict[str, Any] = Field(default_factory=dict)


class SimulateRes(BaseModel):
    run_id: str
    status: str  # 'queued'|'running'|'succeeded'|'failed'


class ModifySelector(BaseModel):
    pipe_ids: Optional[List[int]] = None
    by_tag: Optional[str] = None


class ModifyAction(BaseModel):
    type: str
    selector: Optional[ModifySelector] = None
    to: Optional[Any] = None


class CodeOrVersion(BaseModel):
    code: Optional[str] = None
    project_id: Optional[str] = None
    version_id: Optional[str] = None


class ModifyReq(BaseModel):
    code_or_version: CodeOrVersion
    actions: List[ModifyAction]


class ModifyRes(BaseModel):
    modified_code: str
    diff: str


class SweepParam(BaseModel):
    name: str
    selector: Optional[Dict[str, Any]] = None
    values: List[Any]


class ScenarioSweepReq(BaseModel):
    code_or_version: CodeOrVersion
    parameters: List[SweepParam]
    objectives: Optional[List[str]] = None
    constraints: Optional[List[Dict[str, Any]]] = None


class ScenarioSweepRes(BaseModel):
    run_id: str
    design_space_size: int
    status: str


@router.post("/validate", response_model=ValidateRes, summary="Validate pasted network code")
def validate(body: ValidateReq) -> ValidateRes:
    messages: List[ValidationMessage] = []
    code = (body.code or "").strip()
    if not code:
        messages.append(ValidationMessage(level="error", text="code is empty"))
        return ValidateRes(ok=False, messages=messages, inferred={})
    if "import pandapipes" not in code:
        messages.append(ValidationMessage(level="warn", text="Missing 'import pandapipes as pp'"))
    if "os" in code:
        messages.append(ValidationMessage(level="blocked", text="Run blocked because of suspicios behaviour'"))
        return ValidateRes(ok=False, messages=messages, inferred={})
    inferred = {"fluid": None, "components": {}, "demands": {}}
    return ValidateRes(ok=True, messages=messages, inferred=inferred)


def _load_code_from_version(request: Request, project_id: Optional[str], version_id: Optional[str]) -> Optional[str]:
    if not version_id:
        return None
    storage = request.app.state.storage
    nv = storage.get_network_version(version_id)
    if not nv or (project_id and nv.project_id != project_id):
        return None
    payload = storage.load_network_payload(nv) or {}
    return payload.get("code")


@router.post("/parse-graph", response_model=ParseGraphRes, summary="Parse graph from code")
def parse_graph(body: ParseGraphReq, request: Request) -> ParseGraphRes:
    code = (body.code or "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="code is required")
    # Reuse sandbox runner to get design artifacts
    rr = run_pandapipes_code(code)
    artifacts = rr.get("artifacts") or {}
    design = artifacts.get("design") or {}
    junc = design.get("junction") or []
    pipes = design.get("pipe") or []
    valves = design.get("valve") or []
    comps = design.get("compressor") or []

    # Nodes from junctions
    nodes = []
    for r in junc:
        nodes.append({
            "id": str(r.get("index")),
            "type": "junction",
            "name": r.get("name"),
            "pn_bar": r.get("pn_bar"),
        })

    # Edges from pipes/valves/compressors
    edges: List[Dict[str, Any]] = []
    def _edge_rows(rows, typ: str):
        for r in rows or []:
            u = r.get("from_junction")
            v = r.get("to_junction")
            if u is None or v is None:
                continue
            edges.append({
                "id": str(r.get("index")),
                "u": str(u),
                "v": str(v),
                "type": typ,
                "diameter_m": r.get("diameter_m"),
                "length_km": r.get("length_km"),
                "k_mm": r.get("k_mm"),
                "name": r.get("name"),
            })
    _edge_rows(pipes, "pipe")
    _edge_rows(valves, "valve")
    _edge_rows(comps, "compressor")

    components = {
        "junctions": len(junc),
        "pipes": len(pipes),
        "valves": len(valves),
        "compressors": len(comps),
    }
    return ParseGraphRes(graph=Graph(nodes=nodes, edges=edges), components=components)


# backend/api/routes_network.py
@router.post("/simulate", response_model=SimulateRes, summary="Simulate and create a run")
def simulate(body: SimulateReq, request: Request) -> SimulateRes:
    storage = request.app.state.storage
    rid = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    code = (body.code or "").strip()
    if not code:
        code = _load_code_from_version(request, body.project_id, body.version_id) or ""

    if not code:
        run = AnalysisRun(
            id=rid,
            project_id=body.project_id or "adhoc",
            network_version_id=body.version_id or "adhoc",
            started_at=now,
            finished_at=now,
            status=AnalysisStatus.FAILED,
            executor="simulate",
            metadata={"reason": "no_code"},
            logs="No code provided and version not found.",
        )
        storage.save_analysis_run(run)
        return SimulateRes(run_id=rid, status="failed")

    result = run_pandapipes_code(code)
    status = "succeeded" if result.get("ok") else "failed"

    artifacts = result.get("artifacts") or {}
    # IMPORTANT: embed source code so chat tools can resolve code from run_id later
    try:
        artifacts["source_code"] = code
    except Exception:
        pass

    artifacts_path = storage.payload_dir / f"artifacts_{rid}.json"
    try:
        with open(artifacts_path, "w", encoding="utf8") as fh:
            json.dump(artifacts, fh, indent=2)
    except Exception:
        pass

    run = AnalysisRun(
        id=rid,
        project_id=body.project_id or "adhoc",
        network_version_id=body.version_id or "adhoc",
        started_at=now,
        finished_at=now,
        status=AnalysisStatus.SUCCESS if status == "succeeded" else AnalysisStatus.FAILED,
        executor="simulate",
        metadata={"artifacts_path": str(artifacts_path), "options": body.options or {}},
        logs=(result.get("logs") or "") + ("\nSTDERR:\n" + (result.get("stderr") or "") if result.get("stderr") else ""),
        kpis=[],
        issues=[],
        suggestions=[],
    )
    storage.save_analysis_run(run)
    return SimulateRes(run_id=rid, status=status)


@router.post("/modify", response_model=ModifyRes, summary="Apply code modifications")
def modify(body: ModifyReq) -> ModifyRes:
    base_code = (body.code_or_version.code or "").strip()
    if not base_code:
        return ModifyRes(modified_code="# no code", diff="")
    tool = NetworkMutationsTool()
    res = tool.run(base_code, [a.model_dump() for a in (body.actions or [])])
    return ModifyRes(modified_code=res["modified_code"], diff=res["diff"])


@router.post("/scenario-sweep", response_model=ScenarioSweepRes, summary="Run scenario sweep")
def scenario_sweep(body: ScenarioSweepReq, request: Request) -> ScenarioSweepRes:
    storage = request.app.state.storage
    rid = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    code = (body.code_or_version.code or "").strip()
    if not code:
        code = _load_code_from_version(request, body.code_or_version.project_id, body.code_or_version.version_id) or ""
    if not code:
        raise HTTPException(status_code=400, detail="Provide code or a valid project_id+version_id")

    engine = ScenarioEngineTool()
    payload = engine.run(code, [p.model_dump() for p in (body.parameters or [])])
    # persist sweep results
    results_path = storage.payload_dir / f"sweep_{rid}.json"
    try:
        with open(results_path, "w", encoding="utf8") as fh:
            json.dump(payload, fh, indent=2)
    except Exception:
        pass

    run = AnalysisRun(
        id=rid,
        project_id=body.code_or_version.project_id or "adhoc",
        network_version_id=body.code_or_version.version_id or "adhoc",
        started_at=now,
        finished_at=now,
        status=AnalysisStatus.SUCCESS,
        executor="scenario-sweep",
        metadata={"design_space_size": payload.get("design_space_size"), "results_path": str(results_path)},
        logs="[sweep] completed",
        kpis=[],
        issues=[],
        suggestions=[],
    )
    storage.save_analysis_run(run)
    return ScenarioSweepRes(run_id=rid, design_space_size=int(payload.get("design_space_size") or 0), status="succeeded")