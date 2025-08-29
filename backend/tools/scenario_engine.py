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

    def run(self, code: str, parameters: List[Dict[str, Any]]) -> Dict[str, Any]:
        # Only support one parameter 'diameter' for now
        combos: List[Dict[str, Any]] = []
        for p in parameters or []:
            if (p.get("name") or "").lower() == "diameter":
                for val in p.get("values") or []:
                    combos.append({"diameter": val})

        results: List[Dict[str, Any]] = []
        mutator = NetworkMutationsTool()

        for combo in combos:
            # Apply diameter mutation
            mutated = mutator.run(code, [{"type": "set_diameter", "to": combo["diameter"]}])["modified_code"]
            rr = run_pandapipes_code(mutated, limits=self.limits, timeout=60)
            summary = (rr.get("artifacts") or {}).get("summary") or {}
            results.append({
                "params": combo,
                "ok": rr.get("ok"),
                "summary": summary,
                "wall_time": rr.get("wall_time"),
            })

        return {"results": results, "design_space_size": len(combos)}


def get_tool(**options: Any) -> ScenarioEngineTool:
    return ScenarioEngineTool().configure(**options)