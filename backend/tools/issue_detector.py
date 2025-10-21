# backend/tools/issue_detector.py
"""
Detect issues from artifacts and simple thresholds; produce suggestions via suggestor.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from .suggestor import get_tool as get_suggestor_tool  # local SuggestorTool

# backend/tools/issue_detector.py
def detect_issues_from_artifacts(artifacts: Dict[str, Any], thresholds: Dict[str, Any] | None = None) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    design = (artifacts or {}).get("design", {})
    results = (artifacts or {}).get("results", {}) or {}
    junctions = results.get("junction") or []
    pipes = results.get("pipe") or []
    j_design = {str(r.get("index")): r for r in (design.get("junction") or [])}

    t = thresholds or {}
    v_ok = float(t.get("velocity_ok_max", 15.0))
    v_warn = float(t.get("velocity_warn_max", 25.0))
    min_frac = float(t.get("min_p_fraction", 0.95))
    min_warn_frac = max(min_frac - 0.05, 0.0)
    re_min = float(t.get("re_min_turbulent", 2300.0))
    dp_ok = float(t.get("dp_ok_max_bar", 0.30))
    dp_warn = float(t.get("dp_warn_max_bar", 0.60))
    temp_min = float(t.get("temp_min_k", 273.15))
    temp_max = float(t.get("temp_max_k", 373.15))

    def _pick_temp(r):
        for key in ("t_k", "temperature_k", "tfluid_k"):
            if key in r and r[key] is not None:
                return float(r[key])
        return None

    # Build pressure map for dp calc
    jmap = {str(r.get("index")): r for r in (results.get("junction") or [])}
    dp_per_pipe: Dict[str, float] = {}
    for pr in pipes:
        pid = str(pr.get("index"))
        fj, tj = pr.get("from_junction"), pr.get("to_junction")
        pf = (jmap.get(str(fj)) or {}).get("p_bar")
        pt = (jmap.get(str(tj)) or {}).get("p_bar")
        if pf is None or pt is None:
            continue
        dp_per_pipe[pid] = max(float(pf) - float(pt), 0.0)

    issues: List[Dict[str, Any]] = []

    # Low node pressure
    for jr in junctions:
        jid = str(jr.get("index"))
        p = jr.get("p_bar")
        pn = (j_design.get(jid) or {}).get("pn_bar")
        if p is None or pn is None:
            continue
        p = float(p); pn = float(pn)
        if p < min_frac * pn:
            sev = "warn" if p >= (min_warn_frac * pn) else "error"
            issues.append({"id": f"P_LOW::{jid}", "severity": sev, "component_ref": jid, "description": f"Node pressure {p:.3f} bar below {min_frac:.0%} of design pn {pn:.3f} bar", "code": "P_LOW", "location": jid})

    # High velocity
    for pr in pipes:
        pid = str(pr.get("index"))
        v = pr.get("v_mean_m_per_s")
        if v is None:
            continue
        v = float(v)
        if v > v_ok:
            sev = "warn" if v <= v_warn else "error"
            issues.append({"id": f"VEL_HIGH::{pid}", "severity": sev, "component_ref": pid, "description": f"Pipe velocity {v:.3f} m/s above {v_ok:.1f} m/s", "code": "VEL_HIGH", "location": pid})

    # Low Reynolds
    for pr in pipes:
        pid = str(pr.get("index"))
        re = pr.get("reynolds")
        if re is None:
            continue
        re = float(re)
        if re < re_min:
            issues.append({"id": f"RE_LOW::{pid}", "severity": "warn", "component_ref": pid, "description": f"Reynolds number {re:.0f} below {re_min:.0f}", "code": "RE_LOW", "location": pid})

    # High segment dp
    for pid, dp in dp_per_pipe.items():
        if dp > dp_ok:
            sev = "warn" if dp <= dp_warn else "error"
            issues.append({"id": f"DP_HIGH::{pid}", "severity": sev, "component_ref": pid, "description": f"Pipe Δp {dp:.3f} bar above {dp_ok:.3f} bar", "code": "DP_HIGH", "location": pid})

    # Temperature out of range
    for jr in junctions:
        jid = str(jr.get("index"))
        tval = _pick_temp(jr)
        if tval is None:
            continue
        if tval < temp_min or tval > temp_max:
            issues.append({"id": f"TEMP_OUT_OF_RANGE::{jid}", "severity": "warn", "component_ref": jid, "description": f"Temperature {tval:.1f} K out of [{temp_min:.1f}, {temp_max:.1f}] K", "code": "TEMP_OUT_OF_RANGE", "location": jid})

    # Suggestions
    Suggestor = get_suggestor_tool()
    simple = [{"id": it["id"], "code": it["code"], "message": it["description"], "severity": it["severity"], "location": it.get("location")} for it in issues]
    suggestions_models = Suggestor.run(simple)
    suggestions: List[Dict[str, Any]] = []
    for s in suggestions_models:
        try:
            suggestions.append(s.model_dump())
        except Exception:
            try:
                suggestions.append(dict(s))
            except Exception:
                pass

    # Normalize
    norm_issues: List[Dict[str, Any]] = []
    for it in issues:
        norm_issues.append({"id": it["id"], "severity": it["severity"], "component_ref": it.get("component_ref"), "description": it["description"], "kpis": []})
    norm_suggestions: List[Dict[str, Any]] = []
    for s in suggestions:
        norm_suggestions.append({"id": s.get("id"), "title": s.get("action"), "detail": s.get("rationale") or "", "estimated_impact": {}, "actions": [s.get("details") and {"type": s.get("action"), **(s.get("details") or {})}] if s.get("action") else []})

    return norm_issues, norm_suggestions