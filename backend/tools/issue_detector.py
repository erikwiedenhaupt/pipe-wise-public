# backend/tools/issue_detector.py
"""
Detect issues from artifacts and simple thresholds; produce suggestions via suggestor.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from .suggestor import get_tool as get_suggestor_tool  # local SuggestorTool


def detect_issues_from_artifacts(artifacts: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    design = (artifacts or {}).get("design", {})
    results = (artifacts or {}).get("results", {})
    junctions = results.get("junction", [])
    pipes = results.get("pipe", [])
    junctions_design = {str(r.get("index")): r for r in (design.get("junction") or [])}

    issues: List[Dict[str, Any]] = []

    # Low pressure vs pn_bar
    for jr in junctions:
        jid = str(jr.get("index"))
        p = jr.get("p_bar")
        pn = (junctions_design.get(jid) or {}).get("pn_bar")
        if p is None or pn is None:
            continue
        if p < 0.95 * pn:
            sev = "warn" if p >= 0.9 * pn else "error"
            issues.append({
                "id": f"P_LOW::{jid}",
                "severity": sev,
                "component_ref": jid,
                "description": f"Node pressure {p:.3f} bar below 95% of design pn {pn:.3f} bar",
                "code": "P_LOW",
                "location": jid,
            })

    # High velocity
    for pr in pipes:
        pid = str(pr.get("index"))
        v = pr.get("v_mean_m_per_s")
        if v is None:
            continue
        if v > 15.0:
            sev = "warn" if v <= 25.0 else "error"
            issues.append({
                "id": f"VEL_HIGH::{pid}",
                "severity": sev,
                "component_ref": pid,
                "description": f"Pipe velocity {v:.3f} m/s above recommended 15 m/s",
                "code": "VEL_HIGH",
                "location": pid,
            })

    # Low Reynolds
    for pr in pipes:
        pid = str(pr.get("index"))
        re = pr.get("reynolds")
        if re is None:
            continue
        if re < 2300:
            issues.append({
                "id": f"RE_LOW::{pid}",
                "severity": "warn",
                "component_ref": pid,
                "description": f"Reynolds number {re:.1f} indicates laminar/transition",
                "code": "RE_LOW",
                "location": pid,
            })

    # Suggestions via suggestor tool
    Suggestor = get_suggestor_tool()
    # Re-map for suggestor's simple schema
    simple_issues = []
    for it in issues:
        simple_issues.append({
            "id": it["id"],
            "code": it["code"],
            "message": it["description"],
            "severity": it["severity"],
            "location": it.get("location"),
        })
    suggestions_models = Suggestor.run(simple_issues)
    # Convert to plain dict
    suggestions: List[Dict[str, Any]] = []
    for s in suggestions_models:
        try:
            suggestions.append(s.model_dump())
        except Exception:
            try:
                suggestions.append(dict(s))
            except Exception:
                pass

    # Normalize Issues to API shape
    norm_issues: List[Dict[str, Any]] = []
    for it in issues:
        norm_issues.append({
            "id": it["id"],
            "severity": it["severity"],
            "component_ref": it.get("component_ref"),
            "description": it["description"],
            "kpis": [],
        })

    # Normalize Suggestions to API shape
    norm_suggestions: List[Dict[str, Any]] = []
    for s in suggestions:
        norm_suggestions.append({
            "id": s.get("id"),
            "title": s.get("action"),
            "detail": s.get("rationale") or "",
            "estimated_impact": {},
            "actions": [s.get("details") and {"type": s.get("action"), **(s.get("details") or {})}] if s.get("action") else [],
        })

    return norm_issues, norm_suggestions