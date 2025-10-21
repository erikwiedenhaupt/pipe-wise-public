# tools/scenario_engine.py
"""
Minimal scenario engine:
- Supports diameter sweeps: applies set_diameter mutation for each value and runs pandapipes.
- Returns a simple list of results with summaries.
"""

from __future__ import annotations

from typing import Any, Dict, List

from .base import BaseTool, DEFAULT_TOOL_LIMITS
from .network_mutations import NetworkMutationsTool
from .pandapipes_runner import run_pandapipes_code


class ScenarioEngineTool(BaseTool):
    name = "scenario_engine"
    description = "Run simple parameter sweeps over pandapipes code (diameter only for now)."

    # tools/scenario_engine.py
    def run(self, code: str, parameters: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Supports up to 2 parameters with selectors:
        parameters = [
        {"name":"pipe.diameter_m","selector":{"type":"pipe","id":0},"values":[0.05,0.06]},
        {"name":"ext_grid.p_bar","selector":{"type":"ext_grid","id":0},"values":[1.0,1.1]}
        ]
        """
        from .kpi_calculator import compute_kpis_from_artifacts  # lazy import
        combos: List[Dict[str, Any]] = []

        # Limit to first 2 parameters to avoid explosion
        params = (parameters or [])[:2]
        # Build Cartesian product
        value_lists: List[List[Dict[str, Any]]] = []
        for p in params:
            name = (p.get("name") or "").strip()
            sel = p.get("selector") or {}
            values = p.get("values") or []
            entries = [{"name": name, "selector": sel, "value": v} for v in values]
            value_lists.append(entries)
        if not value_lists:
            return {"results": [], "design_space_size": 0}

        import itertools
        for combo in itertools.product(*value_lists):
            # collapse list of dicts to dict with composite key -> value
            param_state: Dict[str, Any] = {}
            for e in combo:
                key = f'{e["name"]}@{(e["selector"] or {}).get("type","").lower()}[{(e["selector"] or {}).get("id","*")}]'
                param_state[key] = e["value"]
            combos.append({"_entries": list(combo), "params": param_state})

        mutator = NetworkMutationsTool()
        results: List[Dict[str, Any]] = []

        def _action_for_entry(e: Dict[str, Any]) -> Dict[str, Any]:
            name = (e.get("name") or "").lower()
            sel = e.get("selector") or {}
            ctype = (sel.get("type") or "").lower()
            cid = sel.get("id")
            val = e.get("value")
            # map to mutation actions (best-effort; unsupported actions are no-ops in mutator)
            if name == "pipe.diameter_m" and ctype == "pipe" and cid is not None:
                return {"type": "set_diameter", "selector": {"pipe_ids": [cid]}, "to": val}
            if name == "valve.diameter_m" and ctype == "valve" and cid is not None:
                return {"type": "set_valve_diameter", "selector": {"valve_ids": [cid]}, "to": val}
            if name == "junction.pn_bar" and ctype == "junction" and cid is not None:
                return {"type": "set_junction_pn", "selector": {"junction_ids": [cid]}, "to": val}
            if name == "ext_grid.p_bar" and ctype == "ext_grid":
                # accept id hint if present
                return {"type": "set_ext_grid_pressure", "selector": {"ext_grid_ids": [cid]} if cid is not None else None, "to": val}
            if name == "sink.mdot_kg_per_s" and ctype == "sink" and cid is not None:
                return {"type": "set_sink_mdot", "selector": {"sink_ids": [cid]}, "to": val}
            if name == "source.mdot_kg_per_s" and ctype == "source" and cid is not None:
                return {"type": "set_source_mdot", "selector": {"source_ids": [cid]}, "to": val}
            # fallback: no-op
            return {"type": "noop", "to": val}

        for c in combos:
            actions = [_action_for_entry(e) for e in c["_entries"]]
            mutated = mutator.run(code, actions).get("modified_code", code)
            rr = run_pandapipes_code(mutated, limits=self.limits, timeout=60)
            art = (rr.get("artifacts") or {})
            summary = art.get("summary") or {}
            kpis = compute_kpis_from_artifacts(art)
            results.append({
                "params": c["params"],
                "ok": rr.get("ok"),
                "summary": summary,
                "kpis": kpis,
                "wall_time": rr.get("wall_time"),
            })

        return {"results": results, "design_space_size": len(combos)}

def get_tool(**options: Any) -> ScenarioEngineTool:
    return ScenarioEngineTool().configure(**options)