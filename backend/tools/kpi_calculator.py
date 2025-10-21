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

# backend/tools/kpi_calculator.py
def compute_kpis_from_artifacts(artifacts: Dict[str, Any]) -> Dict[str, Any]:
    design = (artifacts or {}).get("design", {})
    results = (artifacts or {}).get("results", {}) or {}

    j_rows = results.get("junction") or []
    p_rows = results.get("pipe") or []

    def _idx_map(rows):
        m = {}
        for r in rows or []:
            k = r.get("index")
            if k is not None:
                m[str(k)] = r
        return m

    jmap = _idx_map(j_rows)                      # result junctions (have p_bar)
    pmap_res = _idx_map(p_rows)                  # result pipes (have velocity/reynolds)
    j_design = _idx_map(design.get("junction") or [])
    p_design = _idx_map(design.get("pipe") or [])  # design pipes (have from/to junction)

    # Junction pressures
    pressures = [r.get("p_bar") for r in j_rows if r.get("p_bar") is not None]
    min_p = min(pressures) if pressures else None
    max_p = max(pressures) if pressures else None
    avg_p = (sum(pressures) / len(pressures)) if pressures else None
    total_dp = (max_p - min_p) if (min_p is not None and max_p is not None) else None

    # Junction temperatures
    def _pick_temp(r):
        for key in ("t_k", "temperature_k", "tfluid_k"):
            if key in r and r[key] is not None:
                return r[key]
        return None
    temps = [(_pick_temp(r)) for r in j_rows if _pick_temp(r) is not None]
    min_t = min(temps) if temps else None
    max_t = max(temps) if temps else None
    avg_t = (sum(temps) / len(temps)) if temps else None

    # Pipe velocities/Reynolds (from results)
    velocities = [r.get("v_mean_m_per_s") for r in p_rows if r.get("v_mean_m_per_s") is not None]
    max_v = max(velocities) if velocities else None
    mean_v = (sum(velocities) / len(velocities)) if velocities else None
    reynolds = [r.get("reynolds") for r in p_rows if r.get("reynolds") is not None]
    max_re = max(reynolds) if reynolds else None
    mean_re = (sum(reynolds) / len(reynolds)) if reynolds else None

    # dp per pipe: use design to get from/to junction, then read pressures from result junctions
    dp_per_pipe: Dict[str, float] = {}
    for pid, d in (p_design or {}).items():
        fj = d.get("from_junction")
        tj = d.get("to_junction")
        if fj is None or tj is None:
            continue
        pf = (jmap.get(str(fj)) or {}).get("p_bar")
        pt = (jmap.get(str(tj)) or {}).get("p_bar")
        if pf is None or pt is None:
            continue
        dp_per_pipe[pid] = max(float(pf) - float(pt), 0.0)

    max_dp = max(dp_per_pipe.values()) if dp_per_pipe else None
    avg_dp = (sum(dp_per_pipe.values()) / len(dp_per_pipe)) if dp_per_pipe else None

    # Design-based flows
    sink_rows = design.get("sink") or []
    source_rows = design.get("source") or []
    total_sink_mdot = sum((s.get("mdot_kg_per_s") or 0.0) for s in sink_rows)
    total_source_mdot = sum((s.get("mdot_kg_per_s") or 0.0) for s in source_rows)

    # Simple default thresholds for status marking
    v_ok_max = 15.0
    v_warn_max = 25.0

    vel_viol_cnt = sum(1 for v in velocities if v is not None and v > v_ok_max)

    # Pressure violations vs pn_bar
    pv_cnt = 0
    for jid, jres in jmap.items():
        p = jres.get("p_bar")
        pn = (j_design.get(jid) or {}).get("pn_bar")
        if p is not None and pn is not None:
            if float(p) < 0.95 * float(pn):
                pv_cnt += 1

    # Global KPIs
    global_kpis = [
        {"key": "min_node_pressure", "value": min_p, "unit": "bar", "status": "OK" if min_p is not None else "WARN", "context": {}},
        {"key": "avg_node_pressure", "value": avg_p, "unit": "bar", "status": "OK" if avg_p is not None else "WARN", "context": {}},
        {"key": "max_node_pressure", "value": max_p, "unit": "bar", "status": "OK" if max_p is not None else "WARN", "context": {}},
        {"key": "total_network_pressure_drop", "value": total_dp, "unit": "bar", "status": "OK" if total_dp is not None else "WARN", "context": {}},

        {"key": "max_velocity", "value": max_v, "unit": "m/s", "status": "OK" if (max_v is not None and max_v <= v_ok_max) else ("WARN" if (max_v is not None and max_v <= v_warn_max) else ("FAIL" if max_v is not None else "WARN")), "context": {"threshold_m_per_s": v_ok_max}},
        {"key": "mean_velocity", "value": mean_v, "unit": "m/s", "status": "OK" if mean_v is not None else "WARN", "context": {}},

        {"key": "max_reynolds", "value": max_re, "unit": "", "status": "OK" if max_re is not None else "WARN", "context": {}},
        {"key": "mean_reynolds", "value": mean_re, "unit": "", "status": "OK" if mean_re is not None else "WARN", "context": {}},

        {"key": "max_pipe_dp_bar", "value": max_dp, "unit": "bar", "status": "OK" if max_dp is not None else "WARN", "context": {}},
        {"key": "avg_pipe_dp_bar", "value": avg_dp, "unit": "bar", "status": "OK" if avg_dp is not None else "WARN", "context": {}},

        {"key": "min_node_temperature_k", "value": min_t, "unit": "K", "status": "OK" if min_t is not None else "WARN", "context": {}},
        {"key": "avg_node_temperature_k", "value": avg_t, "unit": "K", "status": "OK" if avg_t is not None else "WARN", "context": {}},
        {"key": "max_node_temperature_k", "value": max_t, "unit": "K", "status": "OK" if max_t is not None else "WARN", "context": {}},

        {"key": "total_sink_mdot_kg_per_s", "value": total_sink_mdot, "unit": "kg/s", "status": "OK", "context": {}},
        {"key": "total_source_mdot_kg_per_s", "value": total_source_mdot, "unit": "kg/s", "status": "OK", "context": {}},

        {"key": "velocity_violations", "value": vel_viol_cnt, "unit": "", "status": "OK" if vel_viol_cnt == 0 else "WARN", "context": {"threshold_m_per_s": v_ok_max}},
        {"key": "pressure_violations", "value": pv_cnt, "unit": "", "status": "OK" if pv_cnt == 0 else "WARN", "context": {"min_fraction_of_pn": 0.95}},
    ]

    # Per-node KPIs
    per_node: Dict[str, List[Dict[str, Any]]] = {}
    for jid, jres in jmap.items():
        p = jres.get("p_bar")
        pn = (j_design.get(jid) or {}).get("pn_bar")
        temp = _pick_temp(jres)
        status = "OK"
        if p is not None and pn is not None and float(p) < 0.95 * float(pn):
            status = "WARN" if float(p) >= 0.9 * float(pn) else "FAIL"
        items = [{"key": "pressure", "value": p, "unit": "bar", "status": status, "context": {"pn_bar": pn}}]
        items.append({"key": "temperature_k", "value": temp, "unit": "K", "status": "OK" if temp is not None else "WARN", "context": {}})
        per_node[jid] = items

    # Per-pipe KPIs
    per_pipe: Dict[str, List[Dict[str, Any]]] = {}
    for pid, pres in pmap_res.items():
        v = pres.get("v_mean_m_per_s")
        re = pres.get("reynolds")
        dp = dp_per_pipe.get(pid)

        drow = (p_design or {}).get(pid) or {}
        D = drow.get("diameter_m")
        k_mm = drow.get("k_mm")
        rel_eps = None
        if D and k_mm is not None:
            try:
                rel_eps = (float(k_mm) / 1000.0) / float(D)
            except Exception:
                rel_eps = None

        f = None
        try:
            if re and rel_eps and re > 0:
                import math
                inv_sqrt_f = -1.8 * math.log10(((rel_eps / 3.7) ** 1.11) + (6.9 / float(re)))
                f = (1.0 / (inv_sqrt_f ** 2))
        except Exception:
            f = None

        v_status = "OK" if (v is not None and v <= v_ok_max) else ("WARN" if (v is not None and v <= v_warn_max) else ("FAIL" if v is not None else "WARN"))
        re_status = "OK" if (re is not None and re >= 2300) else ("WARN" if re is not None else "WARN")
        items = [
            {"key": "velocity", "value": v, "unit": "m/s", "status": v_status, "context": {"max_ok": v_ok_max, "max_warn": v_warn_max}},
            {"key": "reynolds", "value": re, "unit": "", "status": re_status, "context": {"min_turbulent": 2300}},
            {"key": "dp_bar", "value": dp, "unit": "bar", "status": "OK" if dp is not None else "WARN", "context": {}},
            {"key": "relative_roughness", "value": rel_eps, "unit": "", "status": "OK" if rel_eps is not None else "WARN", "context": {}},
            {"key": "friction_factor", "value": f, "unit": "", "status": "OK" if f is not None else "WARN", "context": {}},
        ]
        per_pipe[pid] = items

    return {"global": global_kpis, "per_node": per_node, "per_pipe": per_pipe}