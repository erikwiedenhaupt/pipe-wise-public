# api/routes_network.py
"""
Pipewise API – Network operations (real simulate + artifacts + graph + mutations + sweep)
"""

from __future__ import annotations

import uuid
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import ast

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from core.models import AnalysisRun, AnalysisStatus  # type: ignore
from tools.pandapipes_runner import run_pandapipes_code  # type: ignore
from tools.network_mutations import NetworkMutationsTool  # type: ignore
from tools.scenario_engine import ScenarioEngineTool  # type: ignore
from core.security import validate_pandapipes_code

router = APIRouter(tags=["network"], prefix="")

# Request/Response DTOs
class ValidationMessage(BaseModel):
    level: str
    text: str
    where: Optional[Dict[str, int]] = None  # allow {"line": int, "col": int}


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


@router.post("/validate", response_model=ValidateRes, summary="Validate safe Pandapipes code")
def validate(body: ValidateReq) -> ValidateRes:
    res = validate_pandapipes_code(body.code or "")
    msgs = []
    for m in (res.get("messages") or []):
        where = m.get("where")
        if isinstance(where, dict):
            # normalize to ints if available
            w = {}
            if "line" in where:
                try: w["line"] = int(where["line"])
                except Exception: pass
            if "col" in where:
                try: w["col"] = int(where["col"])
                except Exception: pass
            where = w or None
        msgs.append(ValidationMessage(level=m.get("level"), text=m.get("text"), where=where))
    inferred = res.get("inferred") or {"fluid": None, "components": {}}
    return ValidateRes(ok=bool(res.get("ok")), messages=msgs, inferred=inferred)

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

    vres = validate_pandapipes_code(code)
    if (not vres.get("ok")) or any((m.get("level", "").lower() == "blocked") for m in (vres.get("messages") or [])):
        raise HTTPException(status_code=400, detail={"error": "validation_failed", "messages": vres.get("messages", [])})
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




from starlette.concurrency import run_in_threadpool  # add if not present
import asyncio  # add if not present

# backend/api/routes_network.py
@router.post("/simulate", response_model=SimulateRes, summary="Simulate and create a run")
async def simulate(body: SimulateReq, request: Request) -> SimulateRes:
    storage = request.app.state.storage
    rid = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    channel = body.project_id or "adhoc"

    async def _emit(evtype: str, data: Dict[str, Any]):
        try:
            mgr = getattr(request.app.state, "debug_ws", None)
            if mgr:
                await mgr.broadcast(channel, {"type": evtype, **data})
        except Exception:
            pass

    # Resolve code
    code = (body.code or "").strip()
    if not code:
        code = _load_code_from_version(request, body.project_id, body.version_id) or ""

    vres = validate_pandapipes_code(code)
    blocked = (not vres.get("ok")) or any((m.get("level", "").lower() == "blocked") for m in (vres.get("messages") or []))
    if blocked:
        msgs = vres.get("messages") or []
        failure_reason = "; ".join([f"{m.get('level')}: {m.get('text')}" for m in msgs])
        log_lines = "\n".join([f"- {m.get('level')}: {m.get('text')}" for m in msgs])

        run = AnalysisRun(
            id=rid,
            project_id=body.project_id or "adhoc",
            network_version_id=body.version_id or "adhoc",
            started_at=now,
            finished_at=now,
            status=AnalysisStatus.FAILED,
            executor="simulate",
            metadata={
                "reason": "validation_failed",
                "failure_reason": failure_reason,
                "inferred": vres.get("inferred") or {},
            },
            logs=f"Validation failed:\n{log_lines}",
            kpis=[], issues=[], suggestions=[],
        )
        storage.save_analysis_run(run)
        await _emit("sim.end", {"run_id": rid, "ok": False, "reason": "validation_failed"})
        return SimulateRes(run_id=rid, status="failed")

    # Optional: notify start
    await _emit("sim.start", {"run_id": rid})

    # Run pandapipes in threadpool
    def _do_run():
        return run_pandapipes_code(code)

    result = await run_in_threadpool(_do_run)
    status_ok = bool(result.get("ok"))

    artifacts = result.get("artifacts") or {}
    try:
        artifacts["source_code"] = code
    except Exception:
        pass

    # Save artifacts
    artifacts_path = storage.payload_dir / f"artifacts_{rid}.json"
    try:
        with open(artifacts_path, "w", encoding="utf8") as fh:
            json.dump(artifacts, fh, indent=2)
    except Exception:
        pass

    # Emit stderr into debug
    stderr_txt = (result.get("stderr") or "").strip()
    if stderr_txt:
        await _emit("sim.stderr", {"run_id": rid, "stderr": stderr_txt[:4000]})

    # Persist run row
    run = AnalysisRun(
        id=rid,
        project_id=body.project_id or "adhoc",
        network_version_id=body.version_id or "adhoc",
        started_at=now,
        finished_at=datetime.now(timezone.utc),
        status=AnalysisStatus.SUCCESS if status_ok else AnalysisStatus.FAILED,
        executor="simulate",
        metadata={
            "artifacts_path": str(artifacts_path),
            "options": body.options or {},
            "failure_reason": result.get("reason"),
        },
        logs=(result.get("logs") or "") + (("\nSTDERR:\n" + stderr_txt) if stderr_txt else ""),
        kpis=[], issues=[], suggestions=[],
    )
    storage.save_analysis_run(run)

    await _emit("sim.end", {"run_id": rid, "ok": status_ok, "reason": result.get("reason")})
    return SimulateRes(run_id=rid, status="succeeded" if status_ok else "failed")


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
    
    val = validate_pandapipes_code(code)
    if (not val.get("ok")) or any(m.get("level") in ("blocked", "error") for m in (val.get("messages") or [])):
        raise HTTPException(status_code=400, detail="validation_failed")
    
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

# backend/api/routes_network.py
@router.get("/sweeps/{run_id}", summary="Get scenario sweep results")
def get_sweep_results(run_id: str, request: Request) -> Dict[str, Any]:
    storage = request.app.state.storage
    path = storage.payload_dir / f"sweep_{run_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="sweep_not_found")
    try:
        with open(path, "r", encoding="utf8") as fh:
            return json.load(fh)
    except Exception:
        raise HTTPException(status_code=500, detail="failed_to_read_sweep")