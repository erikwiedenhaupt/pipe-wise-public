"""
Diagnostics Agent

Responsibility
--------------
- Inspect simulation results and detect issues (low pressures, high
  velocities, convergence problems, etc.). Suggest concrete remedies
  that the user or optimizer can act upon.

Design notes
------------
- Keep rules human-readable and testable.
- Return structured findings to feed UI and optimization agent.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Literal
from pydantic import BaseModel, Field
import json


class Finding(BaseModel):
    """A single diagnostic finding."""
    id: str
    severity: Literal["info", "warn", "error"]
    message: str
    suggested_actions: List[str] = Field(default_factory=list)
    impacted_elements: List[str] = Field(default_factory=list)


class DiagnosticsReport(BaseModel):
    """Collection of findings with overall status."""
    status: str
    findings: List[Finding] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class DiagnosticsRequest(BaseModel):
    """Input payload containing the simulation result."""
    simulation_result: Dict[str, Any]


def _run_rules(sim: Dict[str, Any]) -> DiagnosticsReport:
    nodes = sim.get("nodes", [])
    edges = sim.get("edges", [])
    logs: List[str] = []
    findings: List[Finding] = []

    # Rule 1: Low node pressure
    for n in nodes:
        p = n.get("pressure_bar")
        if p is not None and p < 4.0:
            findings.append(Finding(
                id=f"low_pressure::{n.get('node_id', '?')}",
                severity="warn" if p > 3.0 else "error",
                message=f"Node {n.get('node_id')} has low pressure ({p:.2f} bar).",
                suggested_actions=[
                    "Increase upstream pressure setpoint.",
                    "Reduce demand at downstream nodes.",
                    "Check for partially closed valves or bottlenecks.",
                ],
                impacted_elements=[n.get("node_id", "?")]
            ))

    # Rule 2: High edge velocity
    for e in edges:
        v = e.get("velocity_m_s")
        if v is not None and v > 3.0:
            findings.append(Finding(
                id=f"high_velocity::{e.get('edge_id', '?')}",
                severity="warn",
                message=f"Edge {e.get('edge_id')} velocity is high ({v:.2f} m/s).",
                suggested_actions=[
                    "Increase pipe diameter for this section.",
                    "Reduce flow by rebalancing or throttling non-critical branches.",
                ],
                impacted_elements=[e.get("edge_id", "?")]
            ))

    # Rule 3: Convergence
    if not sim.get("converged", True):
        findings.append(Finding(
            id="solver_convergence",
            severity="error",
            message="Solver did not converge.",
            suggested_actions=[
                "Relax solver tolerances or reduce time step.",
                "Provide better initial conditions.",
                "Check for ill-conditioned components or unrealistic parameters.",
            ],
            impacted_elements=[]
        ))

    status = "ok"
    if any(f.severity == "error" for f in findings):
        status = "error"
    elif any(f.severity == "warn" for f in findings):
        status = "warn"

    logs.append("Heuristic diagnostics run complete.")
    return DiagnosticsReport(status=status, findings=findings, notes=logs)


def run_diagnostics(simulation_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Functional entrypoint. Accepts simulation_result dict and returns
    a structured diagnostics report.
    """
    req = DiagnosticsRequest(simulation_result=simulation_result)
    rep = _run_rules(req.simulation_result)
    return json.loads(rep.json())


# ---- Registration into Supervisor Registry (optional convenience) ----
try:
    from .supervisor import REGISTRY, ToolSpec  # noqa: F401
    from pydantic import BaseModel

    class _DiagInput(BaseModel):
        simulation_result: Dict[str, Any]

    class _DiagOutput(DiagnosticsReport):
        pass

    REGISTRY.register(
        ToolSpec(
            name="diagnostics.run_diagnostics",
            description="Run rule-based checks on simulation results and suggest fixes.",
            input_model=_DiagInput,
            output_model=_DiagOutput,
            func=lambda i: run_diagnostics(i.simulation_result),
        )
    )
except Exception:
    pass
