# tools/base.py
"""
Base utilities for Pipewise tools:
- BaseTool: common interface for tools (configure/run).
- Sandbox helpers to run Python snippets and extract a sentinel JSON result.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from core.sandbox import run_python_snippet, RunResult  # type: ignore
from core.security import ResourceLimits  # type: ignore


SENTINEL = "PIPEWISE_RESULT_JSON::"

# Conservative defaults; tweak per tool via .configure(limits=...)
DEFAULT_TOOL_LIMITS = ResourceLimits(
    cpu_time_seconds=30,
    wall_time_seconds=60,
    memory_bytes=2 * 1024 * 1024 * 1024,  # 2 GiB
)


class BaseTool:
    """
    Minimal base class for in-process tools.

    Subclasses should:
      - set `name` and `description`
      - implement `run(...)` returning a Python object (dict/list/scalar)
      - optionally accept `.configure(**options)` to override defaults (e.g. limits)
    """

    name: str = "base_tool"
    description: str = "Base tool"
    version: str = "0.0.1"

    # Default per-tool resource limits (if the tool uses sandboxed execution)
    default_limits: ResourceLimits = DEFAULT_TOOL_LIMITS

    def __init__(self) -> None:
        self.options: Dict[str, Any] = {}
        self.limits: ResourceLimits = self.default_limits

    def configure(self, **options: Any) -> "BaseTool":
        """
        Store options and allow overriding resource limits:
          - limits: ResourceLimits or dict(cpu_time_seconds=..., wall_time_seconds=..., memory_bytes=...)
        """
        self.options.update(options or {})
        lim = self.options.get("limits")
        if lim is not None:
            if isinstance(lim, ResourceLimits):
                self.limits = lim
            elif isinstance(lim, dict):
                self.limits = ResourceLimits(
                    cpu_time_seconds=lim.get("cpu_time_seconds", self.limits.cpu_time_seconds),
                    wall_time_seconds=lim.get("wall_time_seconds", self.limits.wall_time_seconds),
                    memory_bytes=lim.get("memory_bytes", self.limits.memory_bytes),
                )
        return self

    def run(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("Tool must implement run(...)")

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self.run(*args, **kwargs)

    def to_metadata(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "options": self.options,
        }


@dataclass
class ToolRun:
    ok: bool
    result: Optional[Dict[str, Any]]
    logs: str
    stderr: str
    returncode: Optional[int]
    timed_out: bool
    wall_time: float
    raw: RunResult


def _parse_sentinel_json(stdout: str) -> Tuple[Optional[Dict[str, Any]], str]:
    """
    Parse stdout lines; extract the last JSON object following the sentinel.
    Returns (result_json, remaining_logs_str).
    """
    if not stdout:
        return None, ""
    result_obj: Optional[Dict[str, Any]] = None
    logs: list[str] = []
    for line in stdout.splitlines():
        if line.startswith(SENTINEL):
            payload = line[len(SENTINEL):].strip()
            try:
                result_obj = json.loads(payload)
            except Exception:
                # Ignore malformed sentinel payloads; keep scanning
                pass
        else:
            logs.append(line)
    return result_obj, "\n".join(logs)


def run_snippet_with_result(
    snippet: str,
    *,
    limits: Optional[ResourceLimits] = None,
    timeout: Optional[int] = None,
) -> ToolRun:
    """
    Run a Python snippet in the sandbox and extract the sentinel JSON result.
    The snippet must print a line starting with SENTINEL followed by a JSON object.
    """
    rr = run_python_snippet(snippet, limits=limits or DEFAULT_TOOL_LIMITS, timeout=timeout)
    result_json, cleaned_logs = _parse_sentinel_json(rr.stdout or "")
    ok = (rr.returncode == 0) and (not rr.timed_out) and (result_json is not None)
    return ToolRun(
        ok=ok,
        result=result_json,
        logs=cleaned_logs,
        stderr=rr.stderr or "",
        returncode=rr.returncode,
        timed_out=rr.timed_out,
        wall_time=rr.wall_time,
        raw=rr,
    )