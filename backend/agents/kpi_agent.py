"""
KPI Agent

Responsibility
--------------
- Consume simulation results and compute domain KPIs (pressure margins,
  energy use proxies, mass balance checks, etc.). Provide a compact,
  structured summary that can be rendered to users or used by other agents.

Design notes
------------
- Keeps business logic separate from simulation.
- KPIs computed here are examples; replace with your validated metrics.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
import json
import math


class KPIRequest(BaseModel):
    """Input: prior simulation result payload."""
    simulation_result: Dict[str, Any]


class KPIItem(BaseModel):
    """Single KPI with value and optional threshold/status."""
    name: str
    value: float
    target: Optional[float] = None
    unit: Optional[str] = None
    status: Optional[str] = Field(None, description="ok / warn / fail")
    explanation: Optional[str] = None


class KPISummary(BaseModel):
    """Collection of KPIs with an overall status."""
    status: str
    kpis: List[KPIItem]
    notes: List[str] = Field(default_factory=list)


def _compute_example_kpis(sim: Dict[str, Any]) -> KPISummary:
    """Very simple heuristic KPIs as a placeholder."""
    nodes = sim.get("nodes", [])
    edges = sim.get("edges", [])
    notes: List[str] = []
    kpis: List[KPIItem] = []

    # Example 1: Minimum node pressure
    min_p = min((n.get("pressure_bar", float("inf")) for n in nodes), default=float("nan"))
    kpis.append(KPIItem(name="min_node_pressure", value=float(min_p), unit="bar", target=4.0,
                        status="ok" if min_p >= 4.0 else "warn",
                        explanation="Minimum pressure across all nodes."))

    # Example 2: Max edge velocity
    max_v = max((e.get("velocity_m_s", float("-inf")) for e in edges), default=float("nan"))
    kpis.append(KPIItem(name="max_edge_velocity", value=float(max_v), unit="m/s", target=3.0,
                        status="ok" if max_v <= 3.0 else "warn",
                        explanation="Peak velocity; exceeding targets can increase losses."))

    # Example 3: Total mass flow (proxy)
    total_flow = sum(e.get("mass_flow_kg_s", 0.0) for e in edges)
    kpis.append(KPIItem(name="total_mass_flow", value=float(total_flow), unit="kg/s",
                        explanation="Total mass flow across all edges (non-directional sum)."))

    # Overall status heuristic
    overall = "ok" if all(k.status in (None, "ok") for k in kpis) else "warn"
    notes.append("Heuristic KPI evaluation. Replace with validated business rules.")
    return KPISummary(status=overall, kpis=kpis, notes=notes)


def compute_kpis(simulation_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Functional entrypoint. Accepts a dict (e.g., from simulate_agent)
    and returns a validated KPI summary dict.
    """
    req = KPIRequest(simulation_result=simulation_result)
    summary = _compute_example_kpis(req.simulation_result)
    return json.loads(summary.json())


# ---- Registration into Supervisor Registry (optional convenience) ----
try:
    from .supervisor import REGISTRY, ToolSpec  # noqa: F401

    class _KPIInput(BaseModel):
        simulation_result: Dict[str, Any]

    class _KPIOutput(KPISummary):
        pass

    REGISTRY.register(
        ToolSpec(
            name="kpi.compute_kpis",
            description="Compute domain KPIs from a simulation result payload.",
            input_model=_KPIInput,
            output_model=_KPIOutput,
            func=lambda i: compute_kpis(i.simulation_result),
        )
    )
except Exception:
    pass
