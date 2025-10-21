# backend/agents/toolsmith_agent.py
"""
Toolsmith Agent

- Generates simple tools from a schema and registers them into REGISTRY.
- Pydantic v2-friendly dynamic model creation.
"""

from __future__ import annotations

from typing import Any, Dict, Callable, Optional, List
from pydantic import BaseModel, Field, ValidationError
import json
import traceback

from .supervisor import REGISTRY, ToolSpec


class ToolSpecRequest(BaseModel):
    name: str = Field(..., description="Unique tool name, e.g., 'utils.compute_pressure_drop'")
    description: str = Field(..., description="One-line summary of what the tool does.")
    input_fields: Dict[str, str] = Field(default_factory=dict)
    output_fields: Dict[str, str] = Field(default_factory=dict)
    test_case: Dict[str, Any] = Field(default_factory=dict)


class ToolsmithResult(BaseModel):
    status: str
    tool_name: Optional[str] = None
    registered: bool = False
    logs: List[str] = Field(default_factory=list)
    error: Optional[str] = None


def _build_model_class(name: str, fields: Dict[str, str]) -> type:
    """
    Dynamically create a Pydantic model class for tool I/O.

    Important: in Pydantic v2, define __annotations__ + class attrs (Field(...)).
    Do NOT assign (type, Field(...)) tuples.
    """
    namespace: Dict[str, Any] = {}
    annotations: Dict[str, Any] = {}
    for k, t in fields.items():
        t_norm = (t or "").strip().lower()
        py_type = {
            "str": str, "string": str,
            "int": int,
            "float": float,
            "bool": bool,
            "dict": dict,
            "list": list,
            "any": Any,
        }.get(t_norm, Any)
        annotations[k] = py_type
        namespace[k] = Field(...)  # required field
    namespace["__annotations__"] = annotations
    return type(name, (BaseModel,), namespace)


def _model_field_names(model_cls: type) -> List[str]:
    # Pydantic v2: model_fields; v1: __fields__
    fields = getattr(model_cls, "model_fields", None)
    if fields is None:
        fields = getattr(model_cls, "__fields__", {})
    return list(fields.keys())


def _generate_function(name: str, input_model: type, output_model: type) -> Callable[..., Dict[str, Any]]:
    """
    Create a simple function that:
    - Accepts the input model instance
    - Returns a dict matching output_model
    - Contains placeholder logic
    """
    fn_name = name.split(".")[-1]
    out_keys = _model_field_names(output_model)
    in_keys = _model_field_names(input_model)

    def _fn(input_obj):
        output: Dict[str, Any] = {}
        first_out = out_keys[0] if out_keys else "value"
        # Placeholder: copy first numeric input to first output
        for key in in_keys:
            val = getattr(input_obj, key, None)
            if isinstance(val, (int, float)):
                output[first_out] = float(val)
                break
        # Ensure all required output keys exist
        for k in out_keys:
            output.setdefault(k, 0.0 if isinstance(output.get(k, None), (int, float)) or k not in output else output[k])
        return output

    _fn.__name__ = fn_name
    _fn.__doc__ = "Auto-generated tool function (placeholder)."
    return _fn


def generate_and_register_tool(spec: Dict[str, Any]) -> Dict[str, Any]:
    logs: List[str] = []
    try:
        req = ToolSpecRequest(**spec)
        tool_name = req.name

        InputModel = _build_model_class("AutoInputModel", req.input_fields)
        OutputModel = _build_model_class("AutoOutputModel", req.output_fields)
        logs.append("Pydantic models generated.")

        func = _generate_function(tool_name, InputModel, OutputModel)
        logs.append("Function stub generated.")

        # Smoke test
        try:
            input_obj = InputModel(**(req.test_case or {}))
        except ValidationError as ve:
            raise ValueError(f"Test case does not satisfy input schema: {ve}")

        raw = func(input_obj)
        OutputModel(**raw)  # validate output
        logs.append("Smoke test passed; output validated.")

        REGISTRY.register(
            ToolSpec(
                name=tool_name,
                description=req.description,
                input_model=InputModel,
                output_model=OutputModel,
                func=lambda i, _f=func: _f(i),
            )
        )
        logs.append(f"Registered tool '{tool_name}'.")
        return ToolsmithResult(status="ok", tool_name=tool_name, registered=True, logs=logs).dict()
    except Exception:
        return ToolsmithResult(
            status="error",
            tool_name=spec.get("name") if isinstance(spec, dict) else None,
            registered=False,
            logs=logs,
            error=traceback.format_exc(),
        ).dict()


# ---- Registration into Supervisor Registry ----
try:
    class _TSInput(BaseModel):
        spec: Dict[str, Any]

    class _TSOutput(ToolsmithResult):
        pass

    REGISTRY.register(
        ToolSpec(
            name="toolsmith.generate_and_register_tool",
            description="Autogenerate a new tool from a schema, smoke-test it, and register it.",
            input_model=_TSInput,
            output_model=_TSOutput,
            func=lambda i: generate_and_register_tool(i.spec),
        )
    )
except Exception:
    pass