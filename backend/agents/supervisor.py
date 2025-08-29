# backend/agents/supervisor.py
"""
Supervisor Agent (central planner)

- Tools (agents) self-register here at import time.
- Registry is idempotent (overwrites on reload) for smoother dev.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Type
from pydantic import BaseModel, Field, validator
import json
import traceback


class ToolSpec(BaseModel):
    """
    Minimal specification of a callable tool (agent entrypoint).
    """
    name: str = Field(..., description="Unique tool name")
    description: str = Field(..., description="Human-readable summary")
    input_model: Type[BaseModel]  # Pydantic input model class
    output_model: Type[BaseModel]  # Pydantic output model class
    func: Callable[..., Any] = Field(..., description="Entrypoint callable")


class SupervisorRequest(BaseModel):
    intent: str = Field(..., description="simulate | kpi | diagnose | optimize | toolsmith (or a direct tool name)")
    payload: Dict[str, Any] = Field(default_factory=dict)
    context: Dict[str, Any] = Field(default_factory=dict)

    @validator("intent")
    def normalize_intent(cls, v: str) -> str:
        return v.strip().lower()


class SupervisorResponse(BaseModel):
    status: str
    chosen_tool: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    logs: List[str] = Field(default_factory=list)
    error: Optional[str] = None


class ToolRegistry:
    """
    Process-local registry mapping tool names to ToolSpec.
    """

    def __init__(self) -> None:
        self._tools: Dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        # Idempotent for dev reloads: override if already present
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec:
        if name not in self._tools:
            raise KeyError(f"Unknown tool '{name}'.")
        return self._tools[name]

    def list(self) -> List[ToolSpec]:
        return list(self._tools.values())

    def has(self, name: str) -> bool:
        return name in self._tools


# Global registry for agent self-registration
REGISTRY = ToolRegistry()


def _try_build_langchain_agent():
    try:
        import langchain  # noqa: F401
        return None
    except Exception:
        return None


class Supervisor:
    """
    Planner:
    - If LC agent available, could delegate (not wired yet).
    - Else rules-based routing by 'intent'.
    """

    def __init__(self, registry: ToolRegistry | None = None) -> None:
        self.registry = registry or REGISTRY
        self._lc_agent = _try_build_langchain_agent()

    def plan_and_execute(self, request: SupervisorRequest) -> SupervisorResponse:
        logs: List[str] = []
        try:
            if self._lc_agent is not None:
                logs.append("Using LangChain agent for planning (stub).")
                pass  # fallback below

            intent = request.intent
            logs.append(f"Routing by intent='{intent}'.")

            intent_to_tool = {
                "simulate": "simulate.run_simulation",
                "kpi": "kpi.compute_kpis",
                "diagnose": "diagnostics.run_diagnostics",
                "optimize": "optimize.run_optimization",
                "toolsmith": "toolsmith.generate_and_register_tool",
            }

            if intent in intent_to_tool:
                tool_name = intent_to_tool[intent]
            elif self.registry.has(intent):
                tool_name = intent
            else:
                raise ValueError(f"Unknown intent '{intent}'. Known intents: {list(intent_to_tool.keys())}")

            logs.append(f"Chosen tool: {tool_name}")
            spec = self.registry.get(tool_name)

            input_obj = spec.input_model(**request.payload)
            logs.append(f"Validated payload for tool '{tool_name}'.")

            raw = spec.func(input_obj)
            output_obj = spec.output_model(**raw) if isinstance(raw, dict) else raw
            result = json.loads(output_obj.json())
            logs.append(f"Tool '{tool_name}' executed successfully.")

            return SupervisorResponse(status="ok", chosen_tool=tool_name, result=result, logs=logs)
        except Exception as e:
            return SupervisorResponse(
                status="error",
                chosen_tool=None,
                result=None,
                logs=logs + [f"Error: {e}"],
                error=traceback.format_exc(),
            )


def run_supervisor(intent: str, payload: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    sup = Supervisor()
    req = SupervisorRequest(intent=intent, payload=payload, context=context or {})
    resp = sup.plan_and_execute(req)
    return json.loads(resp.json())