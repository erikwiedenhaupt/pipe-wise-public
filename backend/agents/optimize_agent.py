"""
Optimize Agent

Responsibility
--------------
- Explore parameter sweeps or run simple optimization loops using the
  simulate_agent to evaluate candidates. Return best configurations and
  a small Pareto/frontier-like summary if available.

Design notes
------------
- Keep the optimizer pluggable: start with a grid/random sweep; you can
  swap in Bayesian or gradient-based methods later.
- The agent depends on the simulate_agent entrypoint only via its public
  function, not by importing internals. This simplifies testing.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Callable, Tuple
from pydantic import BaseModel, Field
import itertools
import random
import json
import math


# We call the public function to avoid tight coupling
from .simulate_agent import run_simulation


class SweepParam(BaseModel):
    """One parameter to sweep over."""
    name: str
    values: List[float]


class ObjectiveSpec(BaseModel):
    """
    Defines the scalar objective to minimize.
    name can be a KPI name (e.g., 'max_edge_velocity') or a lambda alias.
    """
    name: str = Field(..., description="Objective label (for reporting).")
    # For simplicity we support a few canned objectives; extend as needed.
    type: str = Field("max_velocity", description="Objective type: max_velocity|min_pressure_deficit|custom")
    weight: float = Field(1.0, description="Weight for (future) multi-objective aggregation.")
    # TODO: Support real custom callables via a safe registry.


class OptimizationOptions(BaseModel):
    strategy: str = Field("grid", description="grid|random")
    random_trials: int = Field(20, description="Used for random strategy")
    max_candidates: int = Field(200, description="Safety cap")
    thermal: bool = Field(False, description="Forwarded to simulation options")
    # Map to simulation options
    sim_options: Dict[str, Any] = Field(default_factory=dict)


class OptimizationRequest(BaseModel):
    network_code: str
    sweep: List[SweepParam]
    objective: ObjectiveSpec
    options: OptimizationOptions = Field(default_factory=OptimizationOptions)


class CandidateResult(BaseModel):
    params: Dict[str, float]
    objective_value: float
    simulation_result: Dict[str, Any]


class OptimizationReport(BaseModel):
    status: str
    best: Optional[CandidateResult] = None
    candidates: List[CandidateResult] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


def _evaluate_objective(sim: Dict[str, Any], spec: ObjectiveSpec) -> float:
    edges = sim.get("edges", [])
    nodes = sim.get("nodes", [])
    if spec.type == "max_velocity":
        return max((e.get("velocity_m_s", 0.0) for e in edges), default=float("inf"))
    if spec.type == "min_pressure_deficit":
        min_p = min((n.get("pressure_bar", float("inf")) for n in nodes), default=float("inf"))
        target = 4.0  # TODO: make configurable
        return max(0.0, target - float(min_p))
    # Fallback
    return float("inf")


def _grid_points(sweep: List[SweepParam], cap: int) -> List[Dict[str, float]]:
    grids = [ [(p.name, v) for v in p.values] for p in sweep ]
    combos = list(itertools.product(*grids))
    points = [ dict(t) for t in combos ]
    return points[:cap]


def _random_points(sweep: List[SweepParam], trials: int) -> List[Dict[str, float]]:
    points: List[Dict[str, float]] = []
    for _ in range(trials):
        params = {p.name: random.choice(p.values) for p in sweep}
        points.append(params)
    return points


def _apply_params_to_network_code(network_code: str, params: Dict[str, float]) -> str:
    """
    Extremely simple placeholder that injects params as a header comment.
    In real use, you should define a templating scheme (e.g., Jinja2) or
    a JSON network schema and apply the params structurally.
    """
    header = "# OPTIMIZATION PARAMS: " + json.dumps(params) + "\n"
    if network_code.startswith("# OPTIMIZATION PARAMS:"):
        # Replace existing header
        _, _, rest = network_code.partition("\n")
        return header + rest
    return header + network_code


def run_optimization(network_code: str, sweep: List[Dict[str, Any]], objective: Dict[str, Any],
                     options: Dict[str, Any]) -> Dict[str, Any]:
    """
    Functional entrypoint.

    - Builds candidate parameter sets
    - Runs simulations per candidate
    - Scores with objective
    """
    req = OptimizationRequest(
        network_code=network_code,
        sweep=[SweepParam(**s) for s in (sweep or [])],
        objective=ObjectiveSpec(**objective),
        options=OptimizationOptions(**(options or {})),
    )

    notes: List[str] = []
    # Candidate generation
    if req.options.strategy == "grid":
        candidates = _grid_points(req.sweep, cap=req.options.max_candidates)
        notes.append(f"Grid strategy with {len(candidates)} candidates.")
    else:
        candidates = _random_points(req.sweep, trials=req.options.random_trials)
        notes.append(f"Random strategy with {len(candidates)} candidates.")

    results: List[CandidateResult] = []
    for params in candidates:
        nc = _apply_params_to_network_code(req.network_code, params)
        sim_opts = dict(req.options.sim_options)
        sim_opts["thermal"] = req.options.thermal
        sim = run_simulation(nc, sim_opts)  # dict
        score = _evaluate_objective(sim, req.objective)
        results.append(CandidateResult(params=params, objective_value=float(score), simulation_result=sim))

    # Pick best (min objective)
    best = min(results, key=lambda c: c.objective_value) if results else None
    report = OptimizationReport(status="ok", best=best, candidates=results, notes=notes)
    return json.loads(report.json())


# ---- Registration into Supervisor Registry (optional convenience) ----
try:
    from .supervisor import REGISTRY, ToolSpec  # noqa: F401
    from pydantic import BaseModel

    class _OptInput(BaseModel):
        network_code: str
        sweep: List[Dict[str, Any]] = Field(default_factory=list)
        objective: Dict[str, Any]
        options: Dict[str, Any] = Field(default_factory=dict)

    class _OptOutput(OptimizationReport):
        pass

    REGISTRY.register(
        ToolSpec(
            name="optimize.run_optimization",
            description="Run parameter sweeps or simple optimization against simulations.",
            input_model=_OptInput,
            output_model=_OptOutput,
            func=lambda i: run_optimization(i.network_code, i.sweep, i.objective, i.options),
        )
    )
except Exception:
    pass
