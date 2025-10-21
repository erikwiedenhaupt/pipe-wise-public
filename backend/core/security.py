# backend/core/security.py
"""
Security and sandboxing helpers.

This module provides helper functions for validating paths, sanitizing inputs,
and constructing resource limits. Heavy lifting (actual enforcement) is performed
in sandbox.py where processes are spawned.

Functions:
- is_safe_path: ensure file paths live under allowed root
- sanitize_filename: basic sanitization for filenames
- resource_limits_for_run: convenience factory for CPU/time/memory limits

Plus:
- get_allowed_pandapipes_functions: whitelist of allowed pandapipes callables
- validate_pandapipes_code: centralized validator (imports, calls, counts, fluid inference)
"""

from __future__ import annotations
from typing import Optional, Tuple, Any, Dict, List
import os
import re
from dataclasses import dataclass

# ---------- existing helpers ----------
# Default allowed storage root for payloads and artifacts
DEFAULT_ALLOWED_ROOT = os.path.abspath(os.getenv("PIPEWISE_ALLOWED_ROOT", "/tmp/pipewise_storage"))


class SecurityError(Exception):
    pass


_filename_re = re.compile(r"^[A-Za-z0-9_.\-]+$")


def sanitize_filename(name: str, fallback: str = "payload.json") -> str:
    base = os.path.basename(name)
    if _filename_re.match(base):
        return base
    cleaned = re.sub(r"[^A-Za-z0-9_.\-]", "_", base)
    return cleaned or fallback


def is_safe_path(path: str, allowed_root: str = DEFAULT_ALLOWED_ROOT) -> bool:
    try:
        allowed_root = os.path.abspath(allowed_root)
        real_path = os.path.abspath(path)
        return os.path.commonpath([real_path, allowed_root]) == allowed_root
    except Exception:
        return False


@dataclass
class ResourceLimits:
    cpu_time_seconds: Optional[int] = None
    memory_bytes: Optional[int] = None
    wall_time_seconds: Optional[int] = None


def resource_limits_for_run(cpu_seconds: Optional[int] = 10, memory_mb: Optional[int] = 512, wall_seconds: Optional[int] = 30) -> ResourceLimits:
    return ResourceLimits(
        cpu_time_seconds=cpu_seconds,
        memory_bytes=(memory_mb * 1024 * 1024) if memory_mb else None,
        wall_time_seconds=wall_seconds,
    )

def static_scan(code: str) -> List[Tuple[str, int]]:
    """
    Very small static scan for obviously dangerous patterns in user code.
    Returns a list of (pattern, line_number).
    """
    import re
    patterns = [
        r"\bimport\s+os\b",
        r"\bimport\s+sys\b",
        r"\bimport\s+subprocess\b",
        r"\bfrom\s+subprocess\s+import\b",
        r"\bopen\s*\(",
        r"\beval\s*\(",
        r"\bexec\s*\(",
        r"\bsocket\b",
        r"\bshutil\b",
    ]
    findings: List[Tuple[str, int]] = []
    lines = code.splitlines()
    for i, ln in enumerate(lines, start=1):
        low = ln.strip()
        for pat in patterns:
            try:
                if re.search(pat, low):
                    findings.append((pat, i))
            except Exception:
                continue
    return findings

# ---------- NEW: pandapipes validation utilities ----------

import ast
import inspect
import pandapipes  # centralizes dependency (previously imported in routes)

# Build a whitelist of allowed pandapipes function names (top-level)
def get_allowed_pandapipes_functions() -> set[str]:
    allowed: set[str] = set()
    for name, obj in inspect.getmembers(pandapipes):
        if inspect.isfunction(obj):
            allowed.add(name)
    return allowed


_ALLOWED_FUNCS = get_allowed_pandapipes_functions()


def _infer_counts_and_fluid(tree: ast.AST) -> Dict[str, Any]:
    counts = {
        "junctions": 0,
        "pipes": 0,
        "sinks": 0,
        "sources": 0,
        "ext_grids": 0,
        "valves": 0,
        "compressors": 0,
        "pumps": 0,
        "heat_exchangers": 0,
    }
    fluid: Optional[str] = None

    def _fname(node: ast.AST) -> Optional[str]:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr
        return None

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = _fname(node.func)  # 'create_junction', 'create_pipe_from_parameters', ...
            if fn is None:
                continue

            # Fluid detection in create_empty_network(...)
            if fn == "create_empty_network":
                # look for keyword 'fluid'
                for kw in node.keywords or []:
                    if kw.arg == "fluid":
                        try:
                            if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                                fluid = kw.value.value
                            # also handle simple name assignment like fluid=FLUID_NAME (skip evaluating)
                        except Exception:
                            pass

            # Count common components
            if fn == "create_junction":
                counts["junctions"] += 1
            elif fn in ("create_pipe_from_parameters", "create_pipe"):
                counts["pipes"] += 1
            elif fn == "create_sink":
                counts["sinks"] += 1
            elif fn == "create_source":
                counts["sources"] += 1
            elif fn == "create_ext_grid":
                counts["ext_grids"] += 1
            elif fn == "create_valve":
                counts["valves"] += 1
            elif fn == "create_compressor":
                counts["compressors"] += 1
            elif fn == "create_pump":
                counts["pumps"] += 1
            elif fn == "create_heat_exchanger":
                counts["heat_exchangers"] += 1

    return {"fluid": fluid, "components": counts}

def validate_pandapipes_code(code: str) -> Dict[str, Any]:
    """
    Central validator for pandapipes user code:
    - allow only pandapipes imports
    - flag disallowed calls on pp/pandapipes.*
    - block dunder attribute access (except __version__)
    Returns: {"ok": bool, "messages": [{level, text, where}], "inferred": {...}}
    where = {"line": int, "col": int} when available.
    Collects ALL issues; ok=false if any level in {"blocked","error"} present.
    """
    msgs: List[Dict[str, Any]] = []
    code_str = (code or "")
    code_s = code_str.strip()
    if not code_s:
        return {"ok": False, "messages": [{"level": "error", "text": "code is empty"}], "inferred": {"fluid": None, "components": {}}}

    if "import pandapipes" not in code_str:
        msgs.append({"level": "warn", "text": "Missing 'import pandapipes as pp'", "where": {"line": 1, "col": 1}})

    import ast
    try:
        tree = ast.parse(code_str)
    except SyntaxError as e:
        msgs.append({"level": "error", "text": f"SyntaxError: {e.msg}", "where": {"line": e.lineno or 1, "col": e.offset or 1}})
        return {"ok": False, "messages": msgs, "inferred": {"fluid": None, "components": {}}}

    # Scan AST (collect all issues)
    for node in ast.walk(tree):
        # Imports
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = (alias.name or "").split(".")[0]
                if root != "pandapipes":
                    msgs.append({"level": "blocked", "text": f"Disallowed import '{alias.name}'", "where": {"line": getattr(node, "lineno", 1), "col": getattr(node, "col_offset", 0) + 1}})
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0] if node.module else ""
            if root != "pandapipes":
                msgs.append({"level": "blocked", "text": f"Disallowed import from '{node.module}'", "where": {"line": getattr(node, "lineno", 1), "col": getattr(node, "col_offset", 0) + 1}})

        # Calls: only police calls on pp.* / pandapipes.* (ignore builtins etc.)
        elif isinstance(node, ast.Call):
            fn_name = None
            allow_check = False
            if isinstance(node.func, ast.Attribute) and isinstance(getattr(node.func, "value", None), ast.Name):
                base = node.func.value.id
                if base in ("pp", "pandapipes"):
                    fn_name = node.func.attr
                    allow_check = True
            elif isinstance(node.func, ast.Attribute) and isinstance(getattr(node.func, "value", None), ast.Attribute):
                # e.g., pandapipes.stdtypes.create_... -> still treat attr name
                base = getattr(node.func.value, "attr", None)
                if base:
                    fn_name = node.func.attr
                    allow_check = True

            if allow_check and fn_name and fn_name not in _ALLOWED_FUNCS:
                msgs.append({"level": "blocked", "text": f"Disallowed function '{fn_name}'", "where": {"line": getattr(node, "lineno", 1), "col": getattr(node, "col_offset", 0) + 1}})

        # Block dunder attribute access
        elif isinstance(node, ast.Attribute):
            if node.attr.startswith("__") and node.attr not in ["__version__"]:
                msgs.append({"level": "blocked", "text": f"Disallowed access to '{node.attr}'", "where": {"line": getattr(node, "lineno", 1), "col": getattr(node, "col_offset", 0) + 1}})

    inferred = _infer_counts_and_fluid(tree)
    ok = not any((m.get("level") in ("blocked", "error")) for m in msgs)
    return {"ok": ok, "messages": msgs, "inferred": inferred}