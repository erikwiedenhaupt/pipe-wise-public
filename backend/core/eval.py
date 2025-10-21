# backend/core/eval.py
from __future__ import annotations
from typing import Dict, Any, Optional

def _kv_from_global(kpis: Dict[str, Any]) -> Dict[str, Any]:
    items = kpis.get("global", []) if isinstance(kpis, dict) else []
    out = {}
    for it in items:
        k = it.get("key")
        if k:
            out[k] = it.get("value")
    return out

def compute_run_score(kpis: Dict[str, Any], issues: Optional[Dict[str, Any]] = None) -> float:
    """
    Scalar score: lower is better.
    score = 10*pressure_violations + 5*velocity_violations + 0.2*max_velocity - 0.2*min_node_pressure
    """
    kv = _kv_from_global(kpis or {})
    pv = float(kv.get("pressure_violations") or 0.0)
    vv = float(kv.get("velocity_violations") or 0.0)
    max_v = float(kv.get("max_velocity") or 0.0)
    min_p = float(kv.get("min_node_pressure") or 0.0)
    return 10.0 * pv + 5.0 * vv + 0.2 * max_v - 0.2 * min_p

def estimate_cost_eur_from_usage(usage: Dict[str, Any],
                                 in_per_1k_eur: float,
                                 out_per_1k_eur: float) -> float:
    pt = float(usage.get("prompt_tokens") or 0.0)
    ct = float(usage.get("completion_tokens") or 0.0)
    return round((pt / 1000.0) * in_per_1k_eur + (ct / 1000.0) * out_per_1k_eur, 6)