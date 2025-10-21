"""
Simulate Agent

Responsibility
--------------
- Accept a pandapipes network (as code or serialized form) and simulation
  options, run a hydraulic/thermal simulation, and return structured
  results for downstream agents (KPI, diagnostics, optimize).

Design notes
------------
- I/O is via Pydantic models to keep contracts explicit and robust.
- Actual pandapipes logic is marked as TODO; this keeps the module lean
  and import-safe in environments without pandapipes installed.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
import time
import json

# If you want optional imports, do it inside functions to avoid hard deps:
# import pandapipes as pp  # TODO: add when wiring real simulation.


class SimulationOptions(BaseModel):
    """Options that alter how the simulation is executed."""
    max_iter: int = Field(20, description="Maximum solver iterations")
    tol: float = Field(1e-6, description="Convergence tolerance")
    thermal: bool = Field(False, description="Include temperature modeling if True")
    seed: Optional[int] = Field(None, description="Random seed (if applicable)")
    extra: Dict[str, Any] = Field(default_factory=dict, description="Backend-specific knobs")


class SimulationRequest(BaseModel):
    """Input to the simulation agent."""
    network_code: str = Field(..., description="Source code or serialized string to build a pandapipes network")
    options: SimulationOptions = Field(default_factory=SimulationOptions)


class NodeResult(BaseModel):
    """Per-node outputs of interest (example, adapt to your data)."""
    node_id: str
    pressure_bar: float
    temperature_k: Optional[float] = None


class EdgeResult(BaseModel):
    """Per-edge outputs of interest (example)."""
    edge_id: str
    mass_flow_kg_s: float
    velocity_m_s: Optional[float] = None


class SimulationResult(BaseModel):
    """Structured output of a simulation run."""
    status: str
    runtime_s: float
    iterations: int
    converged: bool
    nodes: List[NodeResult] = Field(default_factory=list)
    edges: List[EdgeResult] = Field(default_factory=list)
    logs: List[str] = Field(default_factory=list)
    raw_backend_payload: Optional[Dict[str, Any]] = Field(
        None, description="Optional raw dict of backend outputs for advanced use"
    )


def _fake_solve(req: SimulationRequest) -> SimulationResult:
    """
    Placeholder solver so developers can test end-to-end plumbing
    without pandapipes installed. Deterministic & small.
    """
    t0 = time.time()
    logs: List[str] = ["Starting fake simulation."]
    iterations = min(5, req.options.max_iter)
    for i in range(iterations):
        # pretend to iterate
        pass
    converged = True
    logs.append("Converged in placeholder solver.")
    runtime = time.time() - t0

    # Return tiny synthetic network results
    nodes = [
        NodeResult(node_id="n1", pressure_bar=4.9, temperature_k=293.15 if req.options.thermal else None),
        NodeResult(node_id="n2", pressure_bar=4.2, temperature_k=293.15 if req.options.thermal else None),
    ]
    edges = [
        EdgeResult(edge_id="e1", mass_flow_kg_s=1.2, velocity_m_s=2.5),
        EdgeResult(edge_id="e2", mass_flow_kg_s=0.8, velocity_m_s=1.9),
    ]
    return SimulationResult(
        status="ok",
        runtime_s=runtime,
        iterations=iterations,
        converged=converged,
        nodes=nodes,
        edges=edges,
        logs=logs,
        raw_backend_payload={"note": "placeholder"},
    )


def run_simulation(network_code: str, options: Dict[str, Any]) -> Dict[str, Any]:
    """
    Functional entrypoint expected by the supervisor/orchestrator.

    Returns a dict to keep a consistent pattern with other agents. The
    dict is validated by the SimulationResult model for safety.
    """
    req = SimulationRequest(network_code=network_code, options=SimulationOptions(**(options or {})))
    # TODO: Replace with real pandapipes build/run:
    # 1) exec(network_code) safely to construct a pandapipes network OR
    #    parse a JSON schema you define for networks.
    # 2) Run pp.pipeflow(net, **solver_args)
    # 3) Extract node & edge results into NodeResult / EdgeResult
    result = _fake_solve(req)
    return json.loads(result.json())


# ---- Registration into Supervisor Registry (optional convenience) ----
try:
    # Only import if supervisor is available (keeps loose coupling).
    from .supervisor import REGISTRY, ToolSpec, SupervisorRequest, SupervisorResponse  # noqa: F401

    class _SimInput(BaseModel):
        network_code: str
        options: Dict[str, Any] = Field(default_factory=dict)

    class _SimOutput(SimulationResult):
        pass

    REGISTRY.register(
        ToolSpec(
            name="simulate.run_simulation",
            description="Run a pandapipes network simulation and return structured results.",
            input_model=_SimInput,
            output_model=_SimOutput,
            func=lambda i: run_simulation(i.network_code, i.options),
        )
    )
except Exception:
    # Silently skip if registry isn't importable at module load time.
    pass
