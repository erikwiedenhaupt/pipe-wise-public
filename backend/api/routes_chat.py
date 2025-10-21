# backend/api/routes_chat.py
# (drop-in replacement for the whole file)

from __future__ import annotations

import os
import json
import asyncio
import uuid
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from core.ws_manager import DebugWSManager
from core.models import AnalysisRun
from core.security import validate_pandapipes_code

from tools.pandapipes_runner import run_pandapipes_code  # type: ignore
from tools.kpi_calculator import compute_kpis_from_artifacts  # type: ignore
from tools.issue_detector import detect_issues_from_artifacts  # type: ignore
from tools.network_mutations import NetworkMutationsTool  # type: ignore

from core.eval import compute_run_score  # type: ignore
from core.costs import estimate_network_build_cost  # type: ignore

try:
    from openai import AzureOpenAI  # type: ignore
    from openai import BadRequestError  # type: ignore
except Exception:
    AzureOpenAI = None  # type: ignore

    class BadRequestError(Exception):  # type: ignore
        pass

router = APIRouter(tags=["chat"], prefix="/chat")

AZURE_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
# IMPORTANT: Align with your .env (AZURE_OPENAI_KEY)
AZURE_API_KEY = os.getenv("AZURE_OPENAI_KEY")
AZURE_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION")
AZURE_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT")

TRUNC_CODE = None
TRUNC_DIFF = 2000

# -------------------------
# Debug WS helper
# -------------------------
async def _dbg(request: Request, channel: str, event: dict) -> None:
    try:
        mgr: DebugWSManager | None = getattr(request.app.state, "debug_ws", None)
        if mgr:
            await mgr.broadcast(channel, event)
    except Exception:
        pass


@router.websocket("/ws/debug/{channel}")
async def chat_debug_ws_path(websocket: WebSocket, channel: str):
    await websocket.accept()
    mgr: DebugWSManager | None = getattr(websocket.app.state, "debug_ws", None)
    if not mgr:
        await websocket.send_json({"at": None, "event": {"type": "error", "message": "debug manager not available"}})
        await websocket.close()
        return
    await mgr.connect(channel or "adhoc", websocket)
    try:
        await websocket.send_json({"at": datetime.now(timezone.utc).isoformat(), "event": {"type": "debug.ready", "channel": channel}})
        while True:
            await asyncio.sleep(30)
            await websocket.send_json({"at": datetime.now(timezone.utc).isoformat(), "event": {"type": "debug.heartbeat"}})
    except Exception:
        pass
    finally:
        await mgr.disconnect(websocket)

# -------------------------
# Azure client
# -------------------------
def _make_client():
    if AzureOpenAI is None:
        return None
    if not (AZURE_ENDPOINT and AZURE_API_KEY and AZURE_API_VERSION and AZURE_DEPLOYMENT):
        return None
    try:
        return AzureOpenAI(
            azure_endpoint=AZURE_ENDPOINT,
            api_key=AZURE_API_KEY,
            api_version=AZURE_API_VERSION,
        )
    except Exception:
        return None

# -------------------------
# Schemas
# -------------------------
class ChatRequest(BaseModel):
    project_id: Optional[str] = None
    version_id: Optional[str] = None
    run_id: Optional[str] = None
    message: str
    context: Optional[Dict[str, Any]] = None


class ChatHttpResponse(BaseModel):
    assistant: str
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list)
    references: Dict[str, Any] = Field(default_factory=dict)

# -------------------------
# Prompts
# -------------------------
SYSTEM_PROMPT_BASE = """You are Pipewise, a network analysis assistant for pandapipes models.
You can call tools to: simulate, fetch KPIs or issues, modify code, and fix problems.
- Always call tools to obtain fresh KPIs and issues when needed before answering.
- Produce a natural-language analysis tailored to the audience.
Audience mode:
{STYLE}
Output guidelines:
- Be concrete and actionable about problems and fixes.
- If issues exist, list top problems with severity and specific remedies.
- If no issues, mention near-limits (e.g., velocities, Reynolds).
- If user asks to fix, call fix_issues, then summarize what changed and the new status.
- For cost questions about building the network, call estimate_cost and summarize low/mid/high EUR and main assumptions.
"""

STYLE_NOVICE = """Novice:
- Explain concepts briefly (pressure drop, Reynolds, velocity limits).
- Use plain language, short paragraphs, and bullet points.
- Include “How to fix” steps with why it helps.
- Avoid jargon; define terms when first used."""
STYLE_EXPERT = """Expert:
- Concise, data-driven bullets; include numbers/thresholds/assumptions.
- Focus on hotspots and high-ROI fixes; avoid over-explaining basics."""

# -------------------------
# Tools spec
# -------------------------
TOOLS_SPEC = [
    {
        "type": "function",
        "function": {
            "name": "simulate",
            "description": "Create a new simulation run. Provide code, or project_id+version_id or run_id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "string"},
                    "version_id": {"type": "string"},
                    "run_id": {"type": "string"},
                    "code": {"type": "string"},
                    "options": {"type": "object"},
                },
                "required": [],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_kpis",
            "description": "Get KPIs for a run",
            "parameters": {"type": "object", "properties": {"run_id": {"type": "string"}}, "required": ["run_id"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_issues",
            "description": "Get issues and suggestions for a run",
            "parameters": {"type": "object", "properties": {"run_id": {"type": "string"}}, "required": ["run_id"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "validate_code",
            "description": "Validate pandapipes code (or by version_id)",
            "parameters": {
                "type": "object",
                "properties": {"code": {"type": "string"}, "project_id": {"type": "string"}, "version_id": {"type": "string"}},
                "required": [],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_tools",
            "description": "List registered tools",
            "parameters": {"type": "object", "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 100}}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "modify_code",
            "description": "Apply code mutations. If no 'code' given, use version_id or run_id.",
            "parameters": {
                "type": "object",
                "properties": {"project_id": {"type": "string"}, "version_id": {"type": "string"}, "run_id": {"type": "string"}, "code": {"type": "string"}, "actions": {"type": "array", "items": {"type": "object"}}},
                "required": ["actions"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fix_issues",
            "description": "Iteratively modify code and re-simulate until issues resolve or max_iter.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "string"},
                    "version_id": {"type": "string"},
                    "run_id": {"type": "string"},
                    "code": {"type": "string"},
                    "target_velocity": {"type": "number", "default": 12.0},
                    "max_iter": {"type": "integer", "default": 3, "minimum": 1, "maximum": 10},
                },
                "required": [],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "estimate_cost",
            "description": "Estimate build cost (EUR) for the network based on run artifacts (eu context)",
            "parameters": {
                "type": "object",
                "properties": {
                    "run_id": {"type": "string"},
                    "region": {"type": "string", "description": "EU region code (EU, DE, EU_EAST)"},
                    "context": {"type": "string", "description": "urban or rural"},
                    "profile": {"type": "string", "description": "distribution or transmission"},
                    "valve_spacing_m": {"type": "number", "minimum": 50, "maximum": 2000},
                },
                "required": [],
                "additionalProperties": False,
            },
        },
    },
]

# -------------------------
# Settings and helpers
# -------------------------
def _settings_from_body(body: ChatRequest) -> Dict[str, Any]:
    ctx = body.context or {}
    s = (ctx.get("settings") or {}) if isinstance(ctx.get("settings"), dict) else {}
    allowed_models = {"gpt-5-mini-2025-08-07", "gpt-5-nano-2025-08-07", "gpt-5-2025-08-07"}
    model = s.get("model") if s.get("model") in allowed_models else None
    try:
        token_limit = int(s.get("tokenLimit") or 1200)
        token_limit = max(200, min(4000, token_limit))
    except Exception:
        token_limit = 1200
    length = (s.get("length") or "standard").lower()
    length_hint = (s.get("lengthHint") or "").strip()

    profile = (s.get("kpiProfile") or "standard").lower()
    if profile == "strict":
        thresholds = {"velocity_ok_max": 10.0, "velocity_warn_max": 15.0, "min_p_fraction": 0.98, "re_min_turbulent": 4000.0,
                      "dp_ok_max_bar": 0.20, "dp_warn_max_bar": 0.40, "temp_min_k": 273.15, "temp_max_k": 353.15}
    elif profile == "loose":
        thresholds = {"velocity_ok_max": 20.0, "velocity_warn_max": 30.0, "min_p_fraction": 0.90, "re_min_turbulent": 2000.0,
                      "dp_ok_max_bar": 0.50, "dp_warn_max_bar": 0.80, "temp_min_k": 263.15, "temp_max_k": 383.15}
    elif profile == "custom":
        t = s.get("thresholds") or {}
        thresholds = {
            "velocity_ok_max": float(t.get("velocity_ok_max") or 15.0),
            "velocity_warn_max": float(t.get("velocity_warn_max") or 25.0),
            "min_p_fraction": float(t.get("min_p_fraction") or 0.95),
            "re_min_turbulent": float(t.get("re_min_turbulent") or 2300.0),
            "dp_ok_max_bar": float(t.get("dp_ok_max_bar") or 0.30),
            "dp_warn_max_bar": float(t.get("dp_warn_max_bar") or 0.60),
            "temp_min_k": float(t.get("temp_min_k") or 273.15),
            "temp_max_k": float(t.get("temp_max_k") or 373.15),
        }
    else:
        thresholds = {"velocity_ok_max": 15.0, "velocity_warn_max": 25.0, "min_p_fraction": 0.95, "re_min_turbulent": 2300.0,
                      "dp_ok_max_bar": 0.30, "dp_warn_max_bar": 0.60, "temp_min_k": 273.15, "temp_max_k": 373.15}
    return {"model": model, "token_limit": token_limit, "length": length, "length_hint": length_hint, "thresholds": thresholds}

def _length_style_instructions(length: str, custom_hint: str = "") -> str:
    if length == "strict":
        return "Be sehr knapp: höchstens 5 Stichpunkte, je ≤ 12 Wörter. Zahlen und Ergebnisse, kein Fluff."
    if length == "loose":
        return "Gib mehr Details: bis zu ~12 Stichpunkte oder 4–6 kurze Absätze. Zahlen priorisieren."
    if length == "custom" and custom_hint:
        return custom_hint
    # standard
    return "Ausbalanciert: 5–8 kurze Stichpunkte oder 2–4 kurze Absätze. Prägnant, mit Zahlen."

def _num(x):
    try:
        return float(x)
    except Exception:
        return None

def _topn_by_value_map(d: Dict[str, Any], n=3, reverse=True):
    items = []
    for k, v in (d or {}).items():
        vn = _num(v)
        if vn is not None:
            items.append((vn, k))
    items.sort(key=lambda t: t[0], reverse=reverse)
    return [(k, v) for v, k in items[:n]]

def _extract_metric_map_from_kpis(per_map: Any, metric_key: str) -> Dict[str, float]:
    out: Dict[str, float] = {}
    if isinstance(per_map, dict):
        for id_, items in per_map.items():
            if isinstance(items, list):
                for it in items:
                    if not isinstance(it, dict):
                        continue
                    if (it.get("key") or it.get("name")) == metric_key:
                        v = _num(it.get("value"))
                        if v is not None:
                            out[str(id_)] = v
                            break
            elif isinstance(items, dict):
                v = _num(items.get(metric_key))
                if v is not None:
                    out[str(id_)] = v
    elif isinstance(per_map, list):
        for it in per_map:
            if not isinstance(it, dict):
                continue
            id_ = str(it.get("id") or it.get("index") or "")
            v = _num(it.get(metric_key))
            if id_ and v is not None:
                out[id_] = v
    return out

def _global_map_from_list(g: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if isinstance(g, list):
        for it in g:
            if not isinstance(it, dict):
                continue
            k = it.get("key") or it.get("name")
            v = it.get("value")
            if not k:
                continue
            if isinstance(v, (int, float)):
                out[k] = v
            elif isinstance(v, str):
                out[k] = v if len(v) <= 50 else v[:47] + "..."
    elif isinstance(g, dict):
        for k, v in g.items():
            if isinstance(v, (int, float)) or (isinstance(v, str) and len(v) <= 50):
                out[k] = v
    return out

def _compact_kpis(k: Dict[str, Any], max_items: int = 5) -> Dict[str, Any]:
    if not isinstance(k, dict):
        return {}
    g_map = _global_map_from_list(k.get("global"))
    per_node = k.get("per_node") or {}
    per_pipe = k.get("per_pipe") or {}

    nodes_count = len(per_node) if isinstance(per_node, dict) else (len(per_node) if isinstance(per_node, list) else 0)
    pipes_count = len(per_pipe) if isinstance(per_pipe, dict) else (len(per_pipe) if isinstance(per_pipe, list) else 0)

    node_pressure = _extract_metric_map_from_kpis(per_node, "pressure")
    pipe_velocity = _extract_metric_map_from_kpis(per_pipe, "velocity")
    pipe_reynolds = _extract_metric_map_from_kpis(per_pipe, "reynolds")

    extremes: Dict[str, Any] = {}
    if pipe_velocity:
        top = _topn_by_value_map(pipe_velocity, n=3, reverse=True)
        extremes["top_velocity"] = [{"id": id_, "velocity": pipe_velocity[id_]} for id_, _v in top]
    if pipe_reynolds:
        top_re = _topn_by_value_map(pipe_reynolds, n=3, reverse=True)
        extremes["top_reynolds"] = [{"id": id_, "reynolds": pipe_reynolds[id_]} for id_, _v in top_re]
    if node_pressure:
        low = _topn_by_value_map(node_pressure, n=3, reverse=False)
        extremes["lowest_pressure"] = [{"id": id_, "pressure": node_pressure[id_]} for id_, _v in low]

    return {"counts": {"nodes": nodes_count, "pipes": pipes_count}, "global": g_map, "extremes": extremes, "run_id": k.get("run_id")}

def _compact_issues(x: Dict[str, Any], max_items: int = 5) -> Dict[str, Any]:
    if not isinstance(x, dict):
        return {"issues": [], "suggestions": [], "counts": {"issues": 0, "suggestions": 0}}
    issues = x.get("issues") or []
    sugg = x.get("suggestions") or []
    def _fmt_issue(it):
        if isinstance(it, dict):
            sid = it.get("id") or it.get("code") or "issue"
            sev = it.get("severity") or it.get("level")
            msg = it.get("description") or it.get("message") or it.get("text") or ""
            if isinstance(msg, str) and len(msg) > 90:
                msg = msg[:87] + "..."
            return {"id": sid, "severity": sev, "message": msg}
        return {"message": str(it)[:90]}
    def _fmt_sugg(it):
        if isinstance(it, dict):
            txt = it.get("title") or it.get("text") or it.get("message") or it.get("action") or ""
            if isinstance(txt, str) and len(txt) > 90:
                txt = txt[:87] + "..."
            return {"text": txt}
        return {"text": str(it)[:90]}
    return {"counts": {"issues": len(issues), "suggestions": len(sugg)}, "issues": [_fmt_issue(it) for it in issues[:max_items]], "suggestions": [_fmt_sugg(it) for it in sugg[:max_items]], "run_id": x.get("run_id")}

def _format_compact_for_prompt(kc: Optional[Dict[str, Any]], ic: Optional[Dict[str, Any]], run_id: Optional[str]) -> str:
    lines = []
    if run_id:
        lines.append(f"run_id: {run_id}")
    if kc:
        cnt = kc.get("counts", {})
        lines.append(f"nodes: {cnt.get('nodes', 0)}, pipes: {cnt.get('pipes', 0)}")
        g = kc.get("global") or {}
        if g:
            gk = ", ".join([f"{k}={g[k]}" for k in list(g.keys())[:6]])
            lines.append(f"global: {gk}")
        ex = kc.get("extremes") or {}
        if ex.get("top_velocity"):
            tv = ex["top_velocity"][0]
            lines.append(f"max velocity: {tv.get('velocity')} (pipe {tv.get('id')})")
        if ex.get("lowest_pressure"):
            lp = ex["lowest_pressure"][0]
            lines.append(f"min node pressure: {lp.get('pressure')} (node {lp.get('id')})")
    if ic:
        ci = ic.get("counts", {})
        lines.append(f"issues: {ci.get('issues', 0)}, suggestions: {ci.get('suggestions', 0)}")
        if ic.get("issues"):
            lines.append("top issues: " + "; ".join([i.get("id") or i.get("message", "") for i in ic["issues"][:3]]))
    text = "\n".join([ln for ln in lines if ln])
    return text[:1500]

def _audience(body: ChatRequest) -> str:
    mode = ((body.context or {}).get("audience") or "").strip().lower()
    if mode in ("novice", "unexperienced", "beginner"):
        return "novice"
    return "expert"

def _get_hist_store(request: Request) -> Dict[str, List[Dict[str, str]]]:
    store = getattr(request.app.state, "chat_hist", None)
    if store is None:
        store = {}
        setattr(request.app.state, "chat_hist", store)
    return store

def _history_key(body: "ChatRequest") -> str:
    return body.project_id or "adhoc"

def _append_history(request: Request, body: "ChatRequest", role: str, content: str) -> None:
    store = _get_hist_store(request)
    key = _history_key(body)
    hist = store.setdefault(key, [])
    hist.append({"role": role, "content": content})
    if len(hist) > 50:
        store[key] = hist[-50:]

def _truncate(text: str, max_chars: Optional[int] = TRUNC_CODE) -> str:
    if not isinstance(text, str):
        return ""
    if max_chars is None or len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n# ... [truncated]"

# -------------------------
# Storage helpers
# -------------------------
def _load_code_from_version(request: Request, project_id: Optional[str], version_id: Optional[str]) -> Optional[str]:
    if not version_id:
        return None
    storage = request.app.state.storage
    nv = storage.get_network_version(version_id)
    if not nv or (project_id and nv.project_id != project_id):
        return None
    payload = storage.load_network_payload(nv) or {}
    return payload.get("code")

def _save_artifacts(request: Request, run_id: str, artifacts: Dict[str, Any]) -> Optional[str]:
    storage = request.app.state.storage
    path = storage.payload_dir / f"artifacts_{run_id}.json"
    try:
        with open(path, "w", encoding="utf8") as fh:
            json.dump(artifacts, fh, indent=2)
        return str(path)
    except Exception:
        return None

def _load_artifacts(request: Request, run_id: str) -> Dict[str, Any]:
    storage = request.app.state.storage
    path = storage.payload_dir / f"artifacts_{run_id}.json"
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf8") as fh:
            return json.load(fh)
    except Exception:
        return {}

def _load_code_from_run(request: Request, run_id: Optional[str]) -> Optional[str]:
    if not run_id:
        return None
    art = _load_artifacts(request, run_id)
    src = (art or {}).get("source_code")
    return src if isinstance(src, str) and src.strip() else None

def _load_latest_code_for_project(request: Request, project_id: Optional[str]) -> Optional[str]:
    if not project_id:
        return None
    storage = request.app.state.storage
    try:
        with storage._get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT id FROM network_versions WHERE project_id = ? ORDER BY datetime(created_at) DESC LIMIT 1",
                (project_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            latest_vid = row[0]
        return _load_code_from_version(request, project_id, latest_vid)
    except Exception:
        return None

def _design_component_counts(request: Request, run_id: Optional[str]) -> Dict[str, int]:
    if not run_id:
        return {}
    art = _load_artifacts(request, run_id)
    design = (art or {}).get("design", {}) or {}
    def _count(key: str) -> int:
        v = design.get(key) or []
        return len(v) if isinstance(v, list) else 0
    return {
        "junctions": _count("junction"),
        "pipes": _count("pipe"),
        "sinks": _count("sink"),
        "sources": _count("source"),
        "ext_grids": _count("ext_grid"),
        "valves": _count("valve"),
        "compressors": _count("compressor"),
    }

def _get_latest_run_id_for_project(request: Request, project_id: Optional[str]) -> Optional[str]:
    if not project_id:
        return None
    storage = request.app.state.storage
    try:
        with storage._get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT id FROM analysis_runs WHERE project_id = ? ORDER BY datetime(started_at) DESC LIMIT 1",
                (project_id,),
            )
            row = cur.fetchone()
            return row[0] if row else None
    except Exception:
        return None

def _resolve_code_for_action(request: Request, args: Dict[str, Any]) -> Optional[str]:
    code = (args.get("code") or "").strip()
    if code:
        return code
    rid = (args.get("run_id") or "").strip() or None
    if rid:
        code = _load_code_from_run(request, rid)
        if code:
            return code
    vid = (args.get("version_id") or "").strip() or None
    pid = (args.get("project_id") or "").strip() or None
    if vid:
        code = _load_code_from_version(request, pid, vid)
        if code:
            return code
    if pid:
        return _load_latest_code_for_project(request, pid)
    return None

def _overwrite_version_code(request: Request, project_id: Optional[str], version_id: Optional[str], new_code: str) -> Tuple[bool, Optional[str]]:
    """
    Overwrite the existing version payload's 'code'. Returns (overwritten, version_id_used).
    """
    storage = request.app.state.storage
    vid = version_id
    # if version_id missing, pick latest for project
    if not vid and project_id:
        try:
            with storage._get_conn() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT id FROM network_versions WHERE project_id = ? ORDER BY datetime(created_at) DESC LIMIT 1",
                    (project_id,),
                )
                row = cur.fetchone()
                vid = row[0] if row else None
        except Exception:
            vid = None
    if not vid:
        return (False, None)
    try:
        nv = storage.get_network_version(vid)
        payload = storage.load_network_payload(nv) or {}
        payload["code"] = new_code
        # Try common save methods
        if hasattr(storage, "save_network_payload"):
            storage.save_network_payload(nv, payload)
        elif hasattr(storage, "write_network_payload"):  # fallback name
            storage.write_network_payload(nv, payload)  # type: ignore
        else:
            # As a last resort, try a generic save method if present
            if hasattr(storage, "save_payload"):
                storage.save_payload(nv, payload)  # type: ignore
            else:
                return (False, vid)
        return (True, vid)
    except Exception:
        return (False, vid)

# -------------------------
# Tool handlers
# -------------------------
def _tool_simulate(args: Dict[str, Any], request: Request) -> Dict[str, Any]:
    project_id = args.get("project_id") or "adhoc"
    version_id = args.get("version_id") or None
    code = _resolve_code_for_action(request, args) or ""

    vr = validate_pandapipes_code(code)
    if not vr.get("ok"):
        return {"error": "validation_failed", "detail": vr}

    rid = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    result = run_pandapipes_code(code)
    artifacts = result.get("artifacts") or {}
    try:
        artifacts["source_code"] = code
    except Exception:
        pass
    _save_artifacts(request, rid, artifacts)

    status_ok = bool(result.get("ok"))
    # Build readable logs
    base_logs = (result.get("logs") or "").strip()
    stderr = (result.get("stderr") or "").strip()
    if stderr:
        base_logs = (base_logs + ("\n\nSTDERR:\n" + stderr)).strip()
    if not status_ok:
        reason = result.get("reason")
        tips = result.get("tips") or []
        if reason:
            base_logs += f"\n\nReason: {reason}"
        if tips:
            for t in tips:
                base_logs += f"\nTip: {t}"

    request.app.state.storage.save_analysis_run(
        AnalysisRun(
            id=rid,
            project_id=project_id,
            network_version_id=version_id or "adhoc",
            started_at=now,
            finished_at=now,
            status="success" if status_ok else "failed",
            executor="chat:simulate",
            metadata={"via": "chat", "options": args.get("options") or {}, "failure_reason": result.get("reason"), "tips": result.get("tips") or []},
            logs=base_logs,
            kpis=[], issues=[], suggestions=[],
        )
    )
    return {
        "run_id": rid,
        "status": "succeeded" if status_ok else "failed",
        "summary": artifacts.get("summary") or {},
        "reason": result.get("reason"),
        "tips": result.get("tips") or [],
    }

def _tool_get_kpis(args: Dict[str, Any], request: Request) -> Dict[str, Any]:
    rid = args.get("run_id")
    if not rid:
        return {"error": "missing run_id"}
    artifacts = _load_artifacts(request, rid)
    if not artifacts:
        return {"global": [], "per_node": {}, "per_pipe": {}, "run_id": rid}
    k = compute_kpis_from_artifacts(artifacts)
    k["run_id"] = rid
    return k

def _tool_get_issues(args: Dict[str, Any], request: Request) -> Dict[str, Any]:
    rid = args.get("run_id")
    thresholds = args.get("thresholds") or None
    if not rid:
        return {"error": "missing run_id"}
    artifacts = _load_artifacts(request, rid)
    if not artifacts:
        return {"issues": [], "suggestions": [], "run_id": rid}
    issues, suggestions = detect_issues_from_artifacts(artifacts, thresholds=thresholds)
    return {"issues": issues, "suggestions": suggestions, "run_id": rid}

def _tool_validate_code(args: Dict[str, Any], request: Request) -> Dict[str, Any]:
    code = _resolve_code_for_action(request, args) or ""
    return validate_pandapipes_code(code)

def _tool_list_tools(args: Dict[str, Any], request: Request) -> Dict[str, Any]:
    registry = request.app.state.tools
    tools = [t.dict() for t in registry.list()]
    limit = args.get("limit") or 20
    try:
        limit = int(limit)
    except Exception:
        limit = 20
    limit = max(1, min(100, limit))
    return {"count": len(tools), "tools": tools[:limit]}

def _tool_modify_code(args: Dict[str, Any], request: Request) -> Dict[str, Any]:
    code = _resolve_code_for_action(request, args) or ""
    actions = args.get("actions") or []
    tool = NetworkMutationsTool()
    res = tool.run(code, actions)
    # Overwrite version code immediately if we know where to write
    try:
        ok, vid_used = _overwrite_version_code(
            request,
            project_id=args.get("project_id") or None,
            version_id=args.get("version_id") or None,
            new_code=res.get("modified_code") or "",
        )
        res["overwritten"] = bool(ok)
        if vid_used:
            res["version_id"] = vid_used
    except Exception:
        res["overwritten"] = False
    return res

def _sanitize_messages_for_openai(messages: list[dict]) -> list[dict]:
    """
    - If there is no assistant message with tool_calls, strip any 'tool' role messages.
    - Also drop malformed 'tool' messages missing tool_call_id.
    """
    has_tool_driver = any(
        (m.get("role") == "assistant") and bool(m.get("tool_calls"))
        for m in messages
    )
    if not has_tool_driver:
        return [m for m in messages if m.get("role") != "tool"]

    clean = []
    for m in messages:
        if m.get("role") == "tool" and not m.get("tool_call_id"):
            # malformed: missing required tool_call_id
            continue
        clean.append(m)
    return clean

def _velocity_factor(artifacts: Dict[str, Any], target_v: float) -> float:
    pipes = (artifacts.get("results") or {}).get("pipe") or []
    vmax = None
    for r in pipes:
        v = r.get("v_mean_m_per_s")
        if v is not None:
            vmax = v if vmax is None else max(vmax, v)
    if vmax is None or vmax <= target_v:
        return 1.0
    f = math.sqrt(float(vmax) / float(target_v))
    return min(1.5, max(1.02, f))

def _tool_fix_issues(args: Dict[str, Any], request: Request) -> Dict[str, Any]:
    code = _resolve_code_for_action(request, args) or ""
    if not code:
        return {"error": "no_code", "detail": "Provide code, run_id, or a valid project/version with saved code."}
    current = code
    val = validate_pandapipes_code(current)
    if not val["ok"]:
        return {"error": "validation_failed", "detail": val}

    target_v = float(args.get("target_velocity") or 12.0)
    max_iter = int(args.get("max_iter") or 3)

    mut = NetworkMutationsTool()
    changes: List[Dict[str, Any]] = []
    rid_final: Optional[str] = None
    k_final: Dict[str, Any] = {}
    i_final: Dict[str, Any] = {"issues": [], "suggestions": []}

    for it in range(max_iter):
        rr = run_pandapipes_code(current)
        artifacts = rr.get("artifacts") or {}
        k = compute_kpis_from_artifacts(artifacts)
        issues, suggestions = detect_issues_from_artifacts(artifacts)

        vmax = None
        for pr in (artifacts.get("results") or {}).get("pipe") or []:
            v = pr.get("v_mean_m_per_s")
            if v is not None:
                vmax = v if vmax is None else max(vmax, v)

        need_velocity_fix = (vmax is not None) and (float(vmax) > target_v)
        has_p_low = any(j.get("id", "").startswith("P_LOW::") for j in issues)

        if not need_velocity_fix and not has_p_low:
            rid = str(uuid.uuid4())
            try:
                artifacts["source_code"] = current
            except Exception:
                pass
            _save_artifacts(request, rid, artifacts)
            rid_final = rid
            k_final = k
            i_final = {"issues": issues, "suggestions": suggestions}
            break

        actions = []
        if need_velocity_fix and vmax is not None:
            f = math.sqrt(float(vmax) / float(target_v))
            if f > 1.01:
                actions.append({"type": "scale_diameter", "factor": f})
                changes.append({"iter": it + 1, "change": f"Scaled all diameters by x{f:.3f} to target vmax {target_v:.2f} m/s"})
        if has_p_low:
            actions.append({"type": "bump_ext_grid_pressure", "delta": 0.1})
            changes.append({"iter": it + 1, "change": "Bumped ext_grid p_bar by +0.10 bar"})

        if not actions:
            rid = str(uuid.uuid4())
            try:
                artifacts["source_code"] = current
            except Exception:
                pass
            _save_artifacts(request, rid, artifacts)
            rid_final = rid
            k_final = k
            i_final = {"issues": issues, "suggestions": suggestions}
            break

        res = mut.run(current, actions)
        current = res["modified_code"]

    if rid_final is None:
        rr = run_pandapipes_code(current)
        artifacts = rr.get("artifacts") or {}
        rid_final = str(uuid.uuid4())
        try:
            artifacts["source_code"] = current
        except Exception:
            pass
        _save_artifacts(request, rid_final, artifacts)
        k_final = compute_kpis_from_artifacts(artifacts)
        i2, s2 = detect_issues_from_artifacts(artifacts)
        i_final = {"issues": i2, "suggestions": s2}

    import difflib
    diff = "".join(
        difflib.unified_diff(
            code.splitlines(True),
            current.splitlines(True),
            fromfile="original",
            tofile="modified",
        )
    )

    # Persist AnalysisRun for the fix
    try:
        storage = request.app.state.storage
        now = datetime.now(timezone.utc)
        log_lines = [c["change"] for c in (changes or [])]
        logs = "[fix_issues] " + ("; ".join(log_lines) if log_lines else "no changes")
        storage.save_analysis_run(
            AnalysisRun(
                id=rid_final,
                project_id=args.get("project_id") or "adhoc",
                network_version_id=args.get("version_id") or "adhoc",
                started_at=now,
                finished_at=now,
                status="success",
                executor="chat:fix_issues",
                metadata={"via": "chat", "iterations": len(changes), "target_velocity": target_v},
                logs=logs,
                kpis=[],
                issues=[],
                suggestions=[],
            )
        )
    except Exception:
        pass

    # Overwrite current code in storage if we know where to write
    overwritten = False
    vid_used = args.get("version_id")
    try:
        overwritten, vid_used = _overwrite_version_code(
            request,
            project_id=args.get("project_id") or None,
            version_id=args.get("version_id") or None,
            new_code=current,
        )
    except Exception:
        overwritten = False

    return {
        "modified_code": current,
        "diff": diff,
        "run_id": rid_final,
        "iterations": len(changes),
        "changes": changes,
        "kpis": k_final,
        "issues": i_final,
        "overwritten": bool(overwritten),
        "version_id": vid_used,
    }

def _tool_estimate_cost(args: Dict[str, Any], request: Request) -> Dict[str, Any]:
    rid = args.get("run_id")
    if not rid and isinstance(args.get("project_id"), str):
        rid = _get_latest_run_id_for_project(request, args["project_id"])
    if not rid:
        return {"error": "missing_run", "detail": "Provide run_id or have at least one run in the project"}
    artifacts = _load_artifacts(request, rid)
    if not artifacts:
        return {"error": "no_artifacts", "detail": f"No artifacts for run_id {rid}"}
    est = estimate_network_build_cost(
        artifacts,
        region=args.get("region"),
        context=args.get("context"),
        profile=args.get("profile"),
        valve_spacing_m=args.get("valve_spacing_m"),
    )
    est["run_id"] = rid
    return est

TOOL_HANDLERS = {
    "simulate": _tool_simulate,
    "get_kpis": _tool_get_kpis,
    "get_issues": _tool_get_issues,
    "validate_code": _tool_validate_code,
    "list_tools": _tool_list_tools,
    "modify_code": _tool_modify_code,
    "fix_issues": _tool_fix_issues,
    "estimate_cost": _tool_estimate_cost,
}

# -------------------------
# Memory integration
# -------------------------
def _get_lessons_text(request: Request, project_id: Optional[str]) -> str:
    mem = getattr(request.app.state, "memory", None)
    if not mem:
        return ""
    try:
        lessons = mem.list_top_lessons(project_id, top_k=int(os.getenv("MEMORY_TOP_K", "5")))
        useful = [l for l in lessons if float(l.get("weight") or 0.0) >= float(os.getenv("MEMORY_MIN_WEIGHT", "0.0"))]
        if not useful:
            prefs = mem.get_preferences(project_id, top_k=3)
            pref_txt = ", ".join([f"{t}(avgΔ={d:+.3f})" for t, d in prefs]) if prefs else ""
            return ("Project Memory:\n(none)\n" + (f"Tool preferences: {pref_txt}\n" if pref_txt else ""))
        lines = [f"- {l['title']}: {l['body']}" for l in useful]
        prefs = mem.get_preferences(project_id, top_k=3)
        pref_txt = ", ".join([f"{t}(avgΔ={d:+.3f})" for t, d in prefs]) if prefs else ""
        return "Project Memory:\n" + "\n".join(lines) + (f"\nTool preferences: {pref_txt}\n" if pref_txt else "\n")
    except Exception:
        return ""

async def _reflect_and_learn(client, request: Request, project_id: Optional[str],
                             user_goal: str, tool_calls: List[Dict[str, Any]],
                             k_cache: Optional[Dict[str, Any]], i_cache: Optional[Dict[str, Any]],
                             prev_score: Optional[float], new_score: Optional[float]) -> Dict[str, Any]:
    mem = getattr(request.app.state, "memory", None)
    out: Dict[str, Any] = {"last_score": prev_score, "new_score": new_score, "delta": None, "lesson_title": None}
    if client is None or mem is None:
        return out
    delta = None
    if (prev_score is not None) and (new_score is not None):
        delta = new_score - prev_score
    out["delta"] = delta

    sys = "You are Pipewise Critic. Evaluate the last step and produce a short general lesson to improve future plans. Reply as JSON: {\"lesson\": {\"title\": str, \"body\": str, \"tags\": [str], \"weight\": number}}."
    prompt = {
        "goal": user_goal,
        "tool_calls": tool_calls,
        "kpis": k_cache or {},
        "issues": i_cache or {},
        "prev_score": prev_score,
        "new_score": new_score,
        "delta": delta,
    }
    try:
        resp = client.chat.completions.create(
            model=AZURE_DEPLOYMENT,
            messages=[{"role": "system", "content": sys},
                      {"role": "user", "content": json.dumps(prompt)}],
            temperature=0.2,
            max_completion_tokens=256,
        )
        txt = (resp.choices[0].message.content or "").strip()
        obj = None
        try:
            obj = json.loads(txt)
        except Exception:
            try:
                start = txt.rfind("{")
                end = txt.rfind("}") + 1
                if start >= 0 and end > start:
                    obj = json.loads(txt[start:end])
            except Exception:
                obj = None
        if isinstance(obj, dict):
            lesson = obj.get("lesson") or {}
            title = (lesson.get("title") or "Lesson from run").strip()[:140]
            body = (lesson.get("body") or "").strip()[:800]
            tags = lesson.get("tags") or ["critic"]
            weight = float(lesson.get("weight") or 1.0)
            try:
                mem.add_lesson(project_id, title, body, tags=tags, weight=weight)
                out["lesson_title"] = title
            except Exception:
                pass
        # Update tool stats
        if delta is not None and tool_calls:
            for t in tool_calls:
                tname = t.get("name") or t.get("function") or "unknown"
                try:
                    mem.update_tool_stats(project_id, tname, delta)
                except Exception:
                    pass
    except Exception:
        pass
    return out

# -------------------------
# Build messages (with memory injection)
# -------------------------
def _build_history_messages(body: ChatRequest, request: Request) -> List[Dict[str, Any]]:
    audience = _audience(body)
    style = STYLE_NOVICE if audience == "novice" else STYLE_EXPERT
    s = _settings_from_body(body)
    length_guide = _length_style_instructions(s["length"], s.get("length_hint") or "")

    ctx = []
    if body.project_id: ctx.append(f"project_id={body.project_id}")
    if body.version_id: ctx.append(f"version_id={body.version_id}")
    if body.run_id:     ctx.append(f"run_id={body.run_id}")
    context_line = f"Context: {', '.join(ctx)}" if ctx else "Context: none"

    memory_txt = _get_lessons_text(request, body.project_id)
    memory_section = ("\n" + memory_txt) if memory_txt else ""

    system = (
        SYSTEM_PROMPT_BASE.format(STYLE=style)
        + memory_section
        + "\nLength preference:\n"
        + f"{length_guide}\n"
        + "\nRules:\n"
        "- If the user asks general knowledge that doesn't require network data, answer directly (do NOT call tools).\n"
        "- If the user asks about the network, call tools to fetch data. After tool calls, ALWAYS produce a natural-language answer (never 'Done').\n"
        "- After you receive tool results, STOP calling tools and write the answer.\n"
        "- Reference the active run_id when summarizing the network.\n"
        + context_line
    )
    msgs: List[Dict[str, Any]] = [{"role": "system", "content": system}]

    # Inject raw network code context
    code_ctx: Optional[str] = None
    if body.run_id:
        try:
            art = _load_artifacts(request, body.run_id)
            if isinstance(art, dict):
                src = art.get("source_code")
                if isinstance(src, str) and src.strip():
                    code_ctx = src
        except Exception:
            pass
    if not code_ctx and body.version_id:
        try:
            code_ctx = _load_code_from_version(request, body.project_id, body.version_id) or None
        except Exception:
            code_ctx = None
    if code_ctx:
        msgs.append({"role": "system", "content": "Network source code:\n\n" + _truncate(code_ctx) + "\n"})

    # History
    store = getattr(request.app.state, "chat_hist", None) or {}
    key = body.project_id or "adhoc"
    hist = store.get(key, [])
    for m in hist[-12:]:
        if m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str):
            msgs.append({"role": m["role"], "content": m["content"]})

    msgs.append({"role": "user", "content": body.message})
    return msgs

def _compact_tool_message_payload(name: str, result: Any) -> Dict[str, Any]:
    if not isinstance(result, dict):
        return {"result": str(result)[:400]}
    if name == "get_kpis":
        return {"kpis_compact": _compact_kpis(result)}
    if name == "get_issues":
        return {"issues_compact": _compact_issues(result)}
    if name == "simulate":
        return {"simulate": {"run_id": result.get("run_id"), "status": result.get("status"), "summary": result.get("summary")}}
    if name == "list_tools":
        tools = result.get("tools") or []
        names = []
        for t in tools[:12]:
            try:
                names.append((t.get("name") if isinstance(t, dict) else str(t)) or "")
            except Exception:
                continue
        return {"tools": {"count": result.get("count", len(tools)), "names": names}}
    if name == "modify_code":
        return {"modify_code": {"diff": _truncate(result.get("diff") or "", TRUNC_DIFF), "overwritten": bool(result.get("overwritten"))}}
    if name == "fix_issues":
        kc = _compact_kpis(result.get("kpis") or {})
        ic = _compact_issues(result.get("issues") or {})
        return {
            "fix_issues": {
                "run_id": result.get("run_id"),
                "iterations": result.get("iterations"),
                "changes": (result.get("changes") or [])[:3],
                "kpis_compact": kc,
                "issues_compact": ic,
                "diff": _truncate(result.get("diff") or "", TRUNC_DIFF),
                "overwritten": bool(result.get("overwritten")),
            }
        }
    if name == "estimate_cost":
        return {
            "estimate_cost": {
                "mid_eur": result.get("total_mid_eur"),
                "low_eur": result.get("total_low_eur"),
                "high_eur": result.get("total_high_eur"),
            }
        }
    return {"keys": list(result.keys())}

def _is_content_filter(err: Exception) -> bool:
    try:
        data = getattr(err, "response", None)
        payload = data.json() if data is not None and hasattr(data, "json") else None
        if not payload and hasattr(err, "body"):
            payload = err.body  # type: ignore
        if isinstance(payload, dict):
            e = payload.get("error", {})
            if e.get("code") == "content_filter":
                return True
            inner = e.get("innererror") or {}
            if inner.get("code") == "ResponsibleAIPolicyViolation":
                return True
            msg = (e.get("message") or "").lower()
            if "content management policy" in msg or "content_filter" in msg:
                return True
    except Exception:
        pass
    return False

# -------------------------
# Chat engine
# -------------------------
async def _chat_engine(body: ChatRequest, request: Request, client) -> ChatHttpResponse:
    # Memory: user message
    try:
        mem = getattr(request.app.state, "memory", None)
        if mem:
            mem.add_message(body.project_id, "user", body.message, run_id=body.run_id)
    except Exception:
        pass

    # History
    store = getattr(request.app.state, "chat_hist", None)
    if store is None:
        store = {}
        setattr(request.app.state, "chat_hist", store)
    key = body.project_id or "adhoc"
    hist = store.setdefault(key, [])
    hist.append({"role": "user", "content": body.message})
    if len(hist) > 50:
        store[key] = hist[-50:]

    # Settings
    s = _settings_from_body(body)
    model_to_use = s["model"] or AZURE_DEPLOYMENT
    token_cap = int(s["token_limit"] or 1200)
    thresholds = s["thresholds"] or {}
    length_guide = _length_style_instructions(s["length"], s.get("length_hint") or "")

    # Auto-latest run_id if missing and project_id present
    if (not body.run_id) and body.project_id:
        auto_rid = _get_latest_run_id_for_project(request, body.project_id)
        if auto_rid:
            body.run_id = auto_rid

    messages = _build_history_messages(body, request)
    tool_calls_resp: List[Dict[str, Any]] = []
    refs: Dict[str, Any] = {
        "project_id": body.project_id,
        "version_id": body.version_id,
        "run_id": body.run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    initial_run_id = body.run_id or None
    new_run_id: Optional[str] = None
    new_run_reason: Optional[str] = None

    channel = body.project_id or "adhoc"
    await _dbg(request, channel, {"type": "chat.start", "message": body.message, "context": {"project_id": body.project_id, "version_id": body.version_id, "run_id": body.run_id}})

    k_buf: Optional[Dict[str, Any]] = None
    i_buf: Optional[Dict[str, Any]] = None
    auto_fixed_once = False

    max_hops = 3
    for _ in range(max_hops):
        await _dbg(request, channel, {"type": "llm.call", "stage": "first", "tool_choice": "auto", "temp": 1, "tokens": token_cap})
        resp = await asyncio.to_thread(
            client.chat.completions.create,
            model=model_to_use,
            messages=messages,
            tools=TOOLS_SPEC,
            tool_choice="auto",
            temperature=1,
            max_completion_tokens=token_cap,
        )
        choice = resp.choices[0]
        msg = choice.message
        finish_reason = getattr(choice, "finish_reason", None)
        tool_calls = getattr(msg, "tool_calls", None) or []

        await _dbg(request, channel, {"type": "llm.response", "stage": "first", "finish_reason": finish_reason, "content_preview": (msg.content or "")[:240], "tool_calls": [{"name": tc.function.name} for tc in tool_calls]})

        if not tool_calls:
            assistant_text = (msg.content or "").strip()
            if not assistant_text:
                await _dbg(request, channel, {"type": "llm.retry", "reason": "no_tools_and_empty_content"})
                prompt_lines = [
                    "Please provide a concise natural-language answer now.",
                    f"Length guideline: {length_guide}",
                    "If you lack data, state briefly what is missing.",
                    "No further tool use is expected in this turn.",
                ]
                run_hint = refs.get("run_id") or body.run_id
                if run_hint:
                    prompt_lines.append(f"Active run_id: {run_hint}.")
                    try:
                        art = _load_artifacts(request, run_hint)
                        src = art.get("source_code")
                        if isinstance(src, str) and src.strip():
                            prompt_lines.append("Here is the network source code for context:")
                            prompt_lines.append("\n" + _truncate(src) + "\n")
                    except Exception:
                        pass

                messages.append({"role": "user", "content": "\n".join(prompt_lines)})
                resp_retry = await asyncio.to_thread(
                    client.chat.completions.create,
                    model=model_to_use,
                    messages=messages,
                    temperature=1,
                    max_completion_tokens=token_cap,
                )
                assistant_text = (resp_retry.choices[0].message.content or "").strip() or "I executed the model but didn’t receive text. Please try again."
                await _dbg(request, channel, {"type": "llm.response", "stage": "retry_no_tools", "content_preview": assistant_text[:240]})

            hist.append({"role": "assistant", "content": assistant_text})
            if len(hist) > 50:
                store[key] = hist[-50:]

            # Learning summary
            learning: Dict[str, Any] = {}
            try:
                mem = getattr(request.app.state, "memory", None)
                last_score = mem.get_last_score(body.project_id) if mem else None
                new_score = compute_run_score(k_buf or {}, i_buf or {}) if (k_buf is not None) else None
                if mem and new_score is not None:
                    rid_for_score = refs.get("run_id") or f"adhoc-{uuid.uuid4().hex}"
                    mem.record_run_score(body.project_id, rid_for_score, new_score, components={"kpis": k_buf or {}, "issues": i_buf or {}})
                critic_refs = await _reflect_and_learn(client, request, body.project_id, user_goal=body.message, tool_calls=tool_calls_resp, k_cache=k_buf, i_cache=i_buf, prev_score=last_score, new_score=new_score)
                prefs = mem.get_preferences(body.project_id, top_k=3) if mem else []
                learning = {**critic_refs, "tool_preferences": prefs}
            except Exception:
                learning = {}

            if new_run_id:
                refs["new_run_id"] = new_run_id
                refs["should_switch_run"] = True
                if new_run_reason:
                    refs["switch_reason"] = new_run_reason
            if learning:
                refs["learning"] = learning

            await _dbg(request, channel, {"type": "chat.end", "status": "ok"})
            # Memory: assistant message
            try:
                mem = getattr(request.app.state, "memory", None)
                if mem:
                    mem.add_message(body.project_id, "assistant", assistant_text, run_id=refs.get("run_id"))
            except Exception:
                pass

            return ChatHttpResponse(assistant=assistant_text, tool_calls=tool_calls_resp, references=refs)

        messages.append({
            "role": "assistant",
            "content": None,
            "tool_calls": [{"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments or "{}"}} for tc in tool_calls],
        })
        await _dbg(request, channel, {"type": "tools.batch", "count": len(tool_calls), "names": [tc.function.name for tc in tool_calls]})

        for tc in tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except Exception:
                args = {}

            if body.project_id and "project_id" not in args:
                args["project_id"] = body.project_id
            if body.version_id and "version_id" not in args:
                args["version_id"] = body.version_id
            if body.run_id and "run_id" not in args and name in ("get_kpis", "get_issues", "simulate", "fix_issues", "estimate_cost"):
                args["run_id"] = body.run_id
            if name == "get_issues":
                args["thresholds"] = thresholds

            await _dbg(request, channel, {"type": "tool.call", "name": name, "args": args})
            handler = TOOL_HANDLERS.get(name)
            if not handler:
                result: Any = {"error": f"Unknown tool '{name}'"}
            else:
                try:
                    result = await asyncio.to_thread(handler, args, request)
                except Exception as e:
                    result = {"error": f"{type(e).__name__}: {e}"}

            # Track run switching
            if isinstance(result, dict) and result.get("run_id"):
                refs["run_id"] = result["run_id"]
                body.run_id = result["run_id"]
                if (not initial_run_id) or (result["run_id"] != initial_run_id):
                    new_run_id = result["run_id"]
                    new_run_reason = name
                    await _dbg(request, channel, {"type": "ui.switch_run", "run_id": new_run_id, "reason": new_run_reason, "project_id": body.project_id})

            if isinstance(result, dict) and name == "get_kpis":
                k_buf = result
            if isinstance(result, dict) and name == "get_issues":
                i_buf = result
            if isinstance(result, dict) and name == "fix_issues":
                if isinstance(result.get("kpis"), dict):
                    k_buf = result.get("kpis")
                if isinstance(result.get("issues"), dict):
                    i_buf = result.get("issues")
            if isinstance(result, dict) and name == "estimate_cost":
                # keep short summary for references
                refs["cost"] = {
                    "total_low_eur": result.get("total_low_eur"),
                    "total_mid_eur": result.get("total_mid_eur"),
                    "total_high_eur": result.get("total_high_eur"),
                    "assumptions": result.get("assumptions"),
                }

            compact_payload = _compact_tool_message_payload(name, result)
            messages.append({"role": "tool", "tool_call_id": tc.id, "name": name, "content": json.dumps(compact_payload)})

            tool_calls_resp.append({"name": name, "args": args, "result": result if name in ("modify_code", "fix_issues", "estimate_cost") else {"keys": list(result.keys()) if isinstance(result, dict) else []}})
            # derive ok and valid flags
            derived_ok = True
            if isinstance(result, dict):
                if "error" in result:
                    derived_ok = False
                elif name == "validate_code":
                    derived_ok = bool(result.get("ok"))
            await _dbg(request, channel, {
                "type": "tool.result",
                "name": name,
                "ok": derived_ok,
                "valid": (bool(result.get("ok")) if (name == "validate_code" and isinstance(result, dict)) else None),
                "result_keys": list(result.keys()) if isinstance(result, dict) else []
            })

            # Memory: tool trace
            try:
                mem = getattr(request.app.state, "memory", None)
                if mem:
                    mem.add_message(body.project_id, "tool", json.dumps({"name": name, "args": args, "result_keys": list(result.keys()) if isinstance(result, dict) else []}), run_id=refs.get("run_id"), tool_name=name)
            except Exception:
                pass

            # Auto-simulate after modify_code, also ensure overwrite was attempted in tool
            if name == "modify_code" and isinstance(result, dict) and result.get("modified_code"):
                sim_args = {
                    "project_id": args.get("project_id") or body.project_id or "adhoc",
                    "version_id": args.get("version_id") or body.version_id,
                    "code": result["modified_code"],
                }
                await _dbg(request, channel, {"type": "tool.call", "name": "simulate (auto)", "args": sim_args})
                valm = validate_pandapipes_code(sim_args["code"])
                if not valm["ok"]:
                    tool_calls_resp.append({"name": "simulate", "args": sim_args, "result": {"error": "validation_failed", "detail": valm}})
                    
                    continue
                sim_res = _tool_simulate(sim_args, request)
                await _dbg(request, channel, {"type": "tool.result", "name": "simulate (auto)", "ok": "error" not in sim_res, "result_keys": list(sim_res.keys())})
                tool_calls_resp.append({"name": "simulate", "args": sim_args, "result": {"keys": list(sim_res.keys())}})
                rid = sim_res.get("run_id")
                if rid:
                    refs["run_id"] = rid
                    body.run_id = rid
                    new_run_id = rid
                    new_run_reason = "modify_code_auto_simulate"
                    await _dbg(request, channel, {"type": "ui.switch_run", "run_id": rid, "reason": new_run_reason, "project_id": body.project_id})
                    k_buf = _tool_get_kpis({"run_id": rid}, request)
                    i_buf = _tool_get_issues({"run_id": rid, "thresholds": thresholds}, request)

            # Auto-fix if simulate failed or issues exist (once per turn)
            if not auto_fixed_once:
                if name == "simulate" and isinstance(result, dict) and result.get("status") == "failed":
                    fx_args = {
                        "project_id": args.get("project_id") or body.project_id,
                        "version_id": args.get("version_id") or body.version_id,
                        "run_id": result.get("run_id") or body.run_id,
                        "target_velocity": thresholds.get("velocity_ok_max", 12.0),
                        "max_iter": 3,
                    }
                    await _dbg(request, channel, {"type": "tool.call", "name": "fix_issues (auto_after_failed_simulate)", "args": fx_args})
                    fx_res = _tool_fix_issues(fx_args, request)
                    auto_fixed_once = True
                    compact_fx = _compact_tool_message_payload("fix_issues", fx_res)
                    
                    tool_calls_resp.append({"name": "fix_issues", "args": fx_args, "result": fx_res})
                    if isinstance(fx_res, dict) and fx_res.get("run_id"):
                        refs["run_id"] = fx_res["run_id"]
                        body.run_id = fx_res["run_id"]
                        new_run_id = fx_res["run_id"]
                        new_run_reason = "auto_fix_after_failed_simulate"
                        await _dbg(request, channel, {"type": "ui.switch_run", "run_id": new_run_id, "reason": new_run_reason, "project_id": body.project_id})
                    if isinstance(fx_res, dict):
                        if isinstance(fx_res.get("kpis"), dict):
                            k_buf = fx_res["kpis"]
                        if isinstance(fx_res.get("issues"), dict):
                            i_buf = fx_res["issues"]

                elif name == "get_issues" and isinstance(result, dict) and (len(result.get("issues") or []) > 0):
                    fx_args = {
                        "project_id": args.get("project_id") or body.project_id,
                        "version_id": args.get("version_id") or body.version_id,
                        "run_id": args.get("run_id") or body.run_id,
                        "target_velocity": thresholds.get("velocity_ok_max", 12.0),
                        "max_iter": 3,
                    }
                    await _dbg(request, channel, {"type": "tool.call", "name": "fix_issues (auto_after_issues)", "args": fx_args})
                    fx_res = _tool_fix_issues(fx_args, request)
                    auto_fixed_once = True
                    compact_fx = _compact_tool_message_payload("fix_issues", fx_res)
                    
                    tool_calls_resp.append({"name": "fix_issues", "args": fx_args, "result": fx_res})
                    if isinstance(fx_res, dict) and fx_res.get("run_id"):
                        refs["run_id"] = fx_res["run_id"]
                        body.run_id = fx_res["run_id"]
                        new_run_id = fx_res["run_id"]
                        new_run_reason = "auto_fix_after_issues"
                        await _dbg(request, channel, {"type": "ui.switch_run", "run_id": new_run_id, "reason": new_run_reason, "project_id": body.project_id})
                    if isinstance(fx_res, dict):
                        if isinstance(fx_res.get("kpis"), dict):
                            k_buf = fx_res["kpis"]
                        if isinstance(fx_res.get("issues"), dict):
                            i_buf = fx_res["issues"]

        run_hint = refs.get("run_id") or body.run_id
        audience = (_audience(body) or "expert")
        prompt_lines = [
            "You now have the necessary data from the tool results above.",
            f"Please provide a concise natural-language answer for the user (audience: {audience}).",
            f"Length guideline: {length_guide}",
            "No further tool use is expected in this turn.",
        ]
        if run_hint:
            prompt_lines.append(f"Active run_id: {run_hint}.")
            try:
                art = _load_artifacts(request, run_hint)
                src = art.get("source_code")
                if isinstance(src, str) and src.strip():
                    prompt_lines.append("Here is the network source code for context:")
                    prompt_lines.append("\n" + _truncate(src) + "\n")
            except Exception:
                pass
            comps = _design_component_counts(request, run_hint)
            if comps:
                prompt_lines.append("Component counts:")
                prompt_lines.append(", ".join([f"{k}={v}" for k, v in comps.items()]))

        kc = _compact_kpis(k_buf) if k_buf is not None else None
        ic = _compact_issues(i_buf) if i_buf is not None else None
        if kc is not None or ic is not None:
            prompt_lines.append("Data summary to use in your answer (do not echo raw JSON):")
            prompt_lines.append(_format_compact_for_prompt(kc, ic, run_hint))

        messages.append({"role": "user", "content": "\n".join(prompt_lines)})

        await _dbg(request, channel, {"type": "llm.call", "stage": "forced_final", "tool_choice": "none", "temp": 1, "tokens": token_cap, "run_id": run_hint})
        try:
            resp2 = await asyncio.to_thread(
                client.chat.completions.create,
                model=model_to_use,
                messages=messages,
                temperature=1,
                max_completion_tokens=token_cap,
            )
        except BadRequestError as e:
            if _is_content_filter(e):
                await _dbg(request, channel, {"type": "llm.content_filter", "stage": "forced_final", "action": "fallback"})
                fallback_msgs = [
                    {"role": "system", "content": "You are a helpful engineering assistant summarizing network KPIs and issues. Provide a concise, safe summary."},
                    {"role": "user", "content": "Summarize the following data for a non-technical audience:\n" + (_format_compact_for_prompt(kc, ic, run_hint) if (kc or ic) else "(no data)")},
                ]
                # sanitize messages before final call; keeps valid tool message groups only
                messages = _sanitize_messages_for_openai(messages)
                resp2 = await asyncio.to_thread(
                    client.chat.completions.create,
                    model=model_to_use,
                    messages=messages,
                    temperature=1,
                    max_completion_tokens=token_cap,
                )
            else:
                raise

        choice2 = resp2.choices[0]
        final_text = (choice2.message.content or "").strip()
        finish_reason2 = getattr(choice2, "finish_reason", None)

        await _dbg(request, channel, {"type": "llm.response", "stage": "forced_final", "finish_reason": finish_reason2, "len_text": len(final_text or ""), "content_preview": (final_text or "")[:240]})

        if final_text:
            hist.append({"role": "assistant", "content": final_text})
            if len(hist) > 50:
                store[key] = hist[-50:]

            # Learning summary
            learning: Dict[str, Any] = {}
            try:
                mem = getattr(request.app.state, "memory", None)
                last_score = mem.get_last_score(body.project_id) if mem else None
                new_score = compute_run_score(k_buf or {}, i_buf or {}) if (k_buf is not None) else None
                if mem and new_score is not None:
                    rid_for_score = refs.get("run_id") or f"adhoc-{uuid.uuid4().hex}"
                    mem.record_run_score(body.project_id, rid_for_score, new_score, components={"kpis": k_buf or {}, "issues": i_buf or {}})
                critic_refs = await _reflect_and_learn(client, request, body.project_id, user_goal=body.message, tool_calls=tool_calls_resp, k_cache=k_buf, i_cache=i_buf, prev_score=last_score, new_score=new_score)
                prefs = mem.get_preferences(body.project_id, top_k=3) if mem else []
                learning = {**critic_refs, "tool_preferences": prefs}
            except Exception:
                learning = {}

            if new_run_id:
                refs["new_run_id"] = new_run_id
                refs["should_switch_run"] = True
                if new_run_reason:
                    refs["switch_reason"] = new_run_reason
            if learning:
                refs["learning"] = learning

            await _dbg(request, channel, {"type": "chat.end", "status": "ok"})
            # Memory: assistant message
            try:
                mem = getattr(request.app.state, "memory", None)
                if mem:
                    mem.add_message(body.project_id, "assistant", final_text, run_id=refs.get("run_id"))
            except Exception:
                pass

            return ChatHttpResponse(assistant=final_text, tool_calls=tool_calls_resp, references=refs)

    assistant_text = "I executed tools but didn’t produce a final answer. Please try again."
    hist.append({"role": "assistant", "content": assistant_text})
    if len(hist) > 50:
        store[key] = hist[-50:]
    if new_run_id:
        refs["new_run_id"] = new_run_id
        refs["should_switch_run"] = True
        if new_run_reason:
            refs["switch_reason"] = new_run_reason
    await _dbg(request, channel, {"type": "chat.end", "status": "empty_final"})
    # Memory: assistant message
    try:
        mem = getattr(request.app.state, "memory", None)
        if mem:
            mem.add_message(body.project_id, "assistant", assistant_text, run_id=refs.get("run_id"))
    except Exception:
        pass
    return ChatHttpResponse(assistant=assistant_text, tool_calls=tool_calls_resp, references=refs)

# -------------------------
# Public routes
# -------------------------
@router.post("", response_model=ChatHttpResponse, summary="Chat (Azure OpenAI, tools, history, learning)")
async def chat_post(body: ChatRequest, request: Request) -> ChatHttpResponse:
    client = _make_client()
    if client is None:
        return ChatHttpResponse(
            assistant="Azure OpenAI is not configured (AZURE_OPENAI_*).",
            tool_calls=[],
            references={"project_id": body.project_id, "version_id": body.version_id, "run_id": body.run_id, "timestamp": datetime.now(timezone.utc).isoformat()},
        )
    return await _chat_engine(body, request, client)

@router.websocket("/ws/chat")
async def chat_ws(websocket: WebSocket):
    await websocket.accept()
    try:
        await websocket.receive_json()
        text = "Use HTTP /api/chat for full tool-calling. WS streaming will be added next."
        for ch in text:
            await websocket.send_json({"token": ch, "done": False})
            await asyncio.sleep(0.003)
        await websocket.send_json({"token": "", "done": True})
    except WebSocketDisconnect:
        return
    except Exception as exc:
        await websocket.send_json({"token": f"[error] {type(exc).__name__}: {exc}", "done": True})
        await websocket.close()