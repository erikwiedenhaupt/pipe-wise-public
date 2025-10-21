# tools/network_mutations.py
"""
Code-level network mutations (text-based):
- set_diameter: set all diameter_m=... to a given value (meters)
- scale_diameter: multiply all diameter_m=... by a factor (>0)
- set_fluid: set fluid in create_empty_network(fluid="...")
- set_roughness: set k_mm=... roughness across code
- set_ext_grid_pressure: set p_bar=... in pp.create_ext_grid(...)
- bump_ext_grid_pressure: add delta_bar to p_bar in pp.create_ext_grid(...)
- set_valve_diameter: set diameter_m=... in pp.create_valve(...)
- set_junction_pn: set pn_bar=... in pp.create_junction(...)
- set_sink_mdot: set mdot_kg_per_s=... in pp.create_sink(...)
- set_source_mdot: set mdot_kg_per_s=... in pp.create_source(...)
"""

from __future__ import annotations

import re
import difflib
from typing import Any, Dict, List

from .base import BaseTool

def _to_meters(val: Any) -> float:
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().lower()
    try:
        if s.endswith("mm"):
            return float(s[:-2].strip()) / 1000.0
        if s.endswith("cm"):
            return float(s[:-2].strip()) / 100.0
        if s.endswith("m"):
            return float(s[:-1].strip())
        return float(s)
    except Exception:
        return 0.0

def _make_diff(before: str, after: str) -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(True),
            after.splitlines(True),
            fromfile="original",
            tofile="modified",
        )
    )

def _set_diameter_all(code: str, to_m: float) -> str:
    pat = re.compile(r"(diameter_m\s*=\s*)([0-9]*\.?[0-9]+)")
    return pat.sub(lambda m: f"{m.group(1)}{to_m:.6f}", code)

def _scale_diameter_all(code: str, factor: float) -> str:
    if factor <= 0:
        return code
    pat = re.compile(r"(diameter_m\s*=\s*)([0-9]*\.?[0-9]+)")
    def repl(m):
        try:
            val = float(m.group(2))
            return f"{m.group(1)}{val * factor:.6f}"
        except Exception:
            return m.group(0)
    return pat.sub(repl, code)

def _set_fluid(code: str, fluid: str) -> str:
    pat = re.compile(r"(create_empty_network\s*\(\s*fluid\s*=\s*)([\"'])(.*?)(\2)")
    return pat.sub(lambda m: f"{m.group(1)}\"{fluid}\"", code)

def _set_roughness_all(code: str, k_mm: float) -> str:
    pat = re.compile(r"(k_mm\s*=\s*)([0-9]*\.?[0-9]+)")
    return pat.sub(lambda m: f"{m.group(1)}{k_mm:.6f}", code)

def _set_ext_grid_pressure(code: str, to_bar: float) -> str:
    pat = re.compile(r"(create_ext_grid\s*\([^)]*?p_bar\s*=\s*)([0-9]*\.?[0-9]+)")
    return pat.sub(lambda m: f"{m.group(1)}{to_bar:.6f}", code)

def _bump_ext_grid_pressure(code: str, delta_bar: float) -> str:
    pat = re.compile(r"(create_ext_grid\s*\([^)]*?p_bar\s*=\s*)([0-9]*\.?[0-9]+)")
    def repl(m):
        try:
            cur = float(m.group(2))
            return f"{m.group(1)}{cur + float(delta_bar):.6f}"
        except Exception:
            return m.group(0)
    return pat.sub(repl, code)

# NEW: targeted setters (global apply; selectors ignored for now)
def _set_valve_diameter_all(code: str, to_m: float) -> str:
    pat = re.compile(r"(create_valve\s*\([^)]*?diameter_m\s*=\s*)([0-9]*\.?[0-9]+)")
    return pat.sub(lambda m: f"{m.group(1)}{to_m:.6f}", code)

def _set_junction_pn_all(code: str, to_bar: float) -> str:
    pat = re.compile(r"(create_junction\s*\([^)]*?pn_bar\s*=\s*)([0-9]*\.?[0-9]+)")
    return pat.sub(lambda m: f"{m.group(1)}{to_bar:.6f}", code)

def _set_sink_mdot_all(code: str, to_kg_s: float) -> str:
    pat = re.compile(r"(create_sink\s*\([^)]*?mdot_kg_per_s\s*=\s*)([0-9]*\.?[0-9]+)")
    return pat.sub(lambda m: f"{m.group(1)}{to_kg_s:.6f}", code)

def _set_source_mdot_all(code: str, to_kg_s: float) -> str:
    pat = re.compile(r"(create_source\s*\([^)]*?mdot_kg_per_s\s*=\s*)([0-9]*\.?[0-9]+)")
    return pat.sub(lambda m: f"{m.group(1)}{to_kg_s:.6f}", code)

class NetworkMutationsTool(BaseTool):
    name = "network_mutations"
    description = "Apply textual mutations to pandapipes code."

    def run(self, code: str, actions: List[Dict[str, Any]]) -> Dict[str, Any]:
        before = code
        current = code
        for act in actions or []:
            t = (act.get("type") or "").strip().lower()
            if t == "set_diameter":
                to = act.get("to")
                to_m = _to_meters(to)
                current = _set_diameter_all(current, to_m)
            elif t == "scale_diameter":
                factor = float(act.get("factor") or 1.0)
                if factor > 0 and abs(factor - 1.0) > 1e-6:
                    current = _scale_diameter_all(current, factor)
            elif t == "set_fluid":
                fluid = str(act.get("to") or "").strip()
                if fluid:
                    current = _set_fluid(current, fluid)
            elif t == "set_roughness":
                to = act.get("to")
                k_mm = float(to) if isinstance(to, (int, float)) else _to_meters(to) * 1000.0
                current = _set_roughness_all(current, k_mm)
            elif t == "set_ext_grid_pressure":
                to = act.get("to")
                if to is not None:
                    current = _set_ext_grid_pressure(current, float(to))
            elif t == "bump_ext_grid_pressure":
                delta = float(act.get("delta") or 0.1)
                current = _bump_ext_grid_pressure(current, delta)
            elif t == "set_valve_diameter":
                to = act.get("to")
                to_m = _to_meters(to)
                current = _set_valve_diameter_all(current, to_m)
            elif t == "set_junction_pn":
                to = act.get("to")
                if to is not None:
                    current = _set_junction_pn_all(current, float(to))
            elif t == "set_sink_mdot":
                to = act.get("to")
                if to is not None:
                    current = _set_sink_mdot_all(current, float(to))
            elif t == "set_source_mdot":
                to = act.get("to")
                if to is not None:
                    current = _set_source_mdot_all(current, float(to))
            else:
                # ignore unknown action
                continue
        return {"modified_code": current, "diff": _make_diff(before, current)}

def get_tool(**options: Any) -> NetworkMutationsTool:
    return NetworkMutationsTool().configure(**options)