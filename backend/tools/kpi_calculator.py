# backend/tools/kpi_calculator.py
"""
Compute KPIs from pandapipes artifacts produced by pandapipes_runner.
Returns shape compatible with /runs/{id}/kpis:
{ "global": [...], "per_node": {...}, "per_pipe": {...} }
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple, Optional


def _index_map(records: List[Dict[str, Any]], id_key: str = "index") -> Dict[str, Dict[str, Any]]:
    out = {}
    for r in records or []:
        k = r.get(id_key)
        if k is None:
            continue
        out[str(k)] = r
    return out


def _status_from_thresholds(value: Optional[float], low: Optional[float], high: Optional[float]) -> str:
    if value is None:
        return "WARN"
    if low is not None and value < low:
        return "FAIL"
    if high is not None and value > high:
        return "WARN"
    return "OK"


def compute_kpis_from_artifacts(artifacts: Dict[str, Any]) -> Dict[str, Any]:
    design = (artifacts or {}).get("design", {})
    results = (artifacts or {}).get("results", {})

    junctions = results.get("junction", [])
    pipes = results.get("pipe", [])
    junctions_design = design.get("junction", [])
    pipes_design = design.get("pipe", [])

    jmap = _index_map(junctions)            # "index" -> res row with p_bar
    jmap_design = _index_map(junctions_design)
    pmap = _index_map(pipes)                # "index" -> res row with v_mean_m_per_s, reynolds
    pmap_design = _index_map(pipes_design)

    pressures = [r.get("p_bar") for r in junctions if r.get("p_bar") is not None]
    min_p = min(pressures) if pressures else None
    max_p = max(pressures) if pressures else None
    total_dp = (max_p - min_p) if (min_p is not None and max_p is not None) else None

    # Velocity stats
    velocities = [r.get("v_mean_m_per_s") for r in pipes if r.get("v_mean_m_per_s") is not None]
    max_v = max(velocities) if velocities else None

    # Violations (simple defaults)
    v_ok_max = 15.0  # m/s default target max
    v_warn_max = 25.0
    vel_viol_cnt = sum(1 for v in velocities if v is not None and v > v_ok_max)

    # Pressure violations if pn_bar exists in design
    pv_cnt = 0
    for jid, jres in jmap.items():
        p = jres.get("p_bar")
        pn = (jmap_design.get(jid) or {}).get("pn_bar")
        if p is not None and pn is not None:
            if p < 0.95 * pn:
                pv_cnt += 1

    # Global KPIs
    global_kpis = [
        {"key": "min_node_pressure", "value": min_p, "unit": "bar", "status": _status_from_thresholds(min_p, None, None), "context": {}},
        {"key": "max_node_pressure", "value": max_p, "unit": "bar", "status": _status_from_thresholds(max_p, None, None), "context": {}},
        {"key": "total_network_pressure_drop", "value": total_dp, "unit": "bar", "status": _status_from_thresholds(total_dp, None, None), "context": {}},
        {"key": "max_velocity", "value": max_v, "unit": "m/s", "status": "OK" if (max_v is not None and max_v <= v_ok_max) else ("WARN" if (max_v is not None and max_v <= v_warn_max) else "FAIL"), "context": {}},
        {"key": "velocity_violations", "value": vel_viol_cnt, "unit": "", "status": "OK" if vel_viol_cnt == 0 else "WARN", "context": {"threshold_m_per_s": v_ok_max}},
        {"key": "pressure_violations", "value": pv_cnt, "unit": "", "status": "OK" if pv_cnt == 0 else "WARN", "context": {"min_fraction_of_pn": 0.95}},
    ]

    # Per-node KPIs (pressure vs pn if available)
    per_node = {}
    for jid, jres in jmap.items():
        p = jres.get("p_bar")
        pn = (jmap_design.get(jid) or {}).get("pn_bar")
        status = "OK"
        if p is not None and pn is not None and p < 0.95 * pn:
            status = "WARN" if p >= 0.9 * pn else "FAIL"
        per_node[jid] = [{"key": "pressure", "value": p, "unit": "bar", "status": status, "context": {"pn_bar": pn}}]

    # Per-pipe KPIs (velocity + Reynolds)
    per_pipe = {}
    for pid, pres in pmap.items():
        v = pres.get("v_mean_m_per_s")
        re = pres.get("reynolds")
        v_status = "OK" if (v is not None and v <= v_ok_max) else ("WARN" if (v is not None and v <= v_warn_max) else ("FAIL" if v is not None else "WARN"))
        re_status = "OK" if (re is not None and re >= 2300) else ("WARN" if re is not None else "WARN")
        per_pipe[pid] = [
            {"key": "velocity", "value": v, "unit": "m/s", "status": v_status, "context": {"max_ok": v_ok_max, "max_warn": v_warn_max}},
            {"key": "reynolds", "value": re, "unit": "", "status": re_status, "context": {"min_turbulent": 2300}},
        ]

    return {"global": global_kpis, "per_node": per_node, "per_pipe": per_pipe}