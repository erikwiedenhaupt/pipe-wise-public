# backend/tools/pandapipes_runner.py
from __future__ import annotations
from typing import Any, Dict, Optional, List
from .base import run_snippet_with_result, SENTINEL, DEFAULT_TOOL_LIMITS  # type: ignore
from core.security import ResourceLimits  # type: ignore

HARNESS_TEMPLATE = r'''
# ===== Pipewise Pandapipes Harness =====
import os, json, pathlib
# Force Matplotlib to a writable cache + non-interactive backend
os.environ["MPLBACKEND"] = "Agg"
try:
    _mpl = pathlib.Path.cwd() / "mplconfig"
    _mpl.mkdir(parents=True, exist_ok=True)
    os.environ["MPLCONFIGDIR"] = str(_mpl)
except Exception:
    pass

try:
    import pandas as pd
    import numpy as np
    import pandapipes as pp
except Exception as e:
    print("Import error:", e)

# ----- USER CODE START -----
__USER_CODE__
# ----- USER CODE END -----

if 'net' not in globals():
    raise RuntimeError("User code must define a variable named 'net' (pandapipes network).")

# Try to solve; record any pipeflow exception but do not abort extraction
pipeflow_error = None
try:
    pp.pipeflow(net)
except Exception as e:
    pipeflow_error = f"{type(e).__name__}: {e}"

def to_records(df):
    if df is None:
        return []
    try:
        d = df.reset_index().replace({np.nan: None}).to_dict(orient='records')
    except Exception:
        try:
            d = df.reset_index().to_dict(orient='records')
        except Exception:
            d = []
    return d

artifacts = {}
try:
    artifacts['design'] = {
        'junction': to_records(getattr(net, 'junction', None)),
        'pipe': to_records(getattr(net, 'pipe', None)),
        'sink': to_records(getattr(net, 'sink', None)),
        'source': to_records(getattr(net, 'source', None)),
        'ext_grid': to_records(getattr(net, 'ext_grid', None)),
        'valve': to_records(getattr(net, 'valve', None)),
        'compressor': to_records(getattr(net, 'compressor', None)) if hasattr(net,'compressor') else [],
    }
    artifacts['results'] = {
        'junction': to_records(getattr(net, 'res_junction', None)),
        'pipe': to_records(getattr(net, 'res_pipe', None)),
        'sink': to_records(getattr(net, 'res_sink', None)) if hasattr(net, 'res_sink') else [],
        'source': to_records(getattr(net, 'res_source', None)) if hasattr(net, 'res_source') else [],
        'ext_grid': to_records(getattr(net, 'res_ext_grid', None)) if hasattr(net, 'res_ext_grid') else [],
        'valve': to_records(getattr(net, 'res_valve', None)) if hasattr(net, 'res_valve') else [],
        'compressor': to_records(getattr(net,'res_compressor', None)) if hasattr(net,'res_compressor') else [],
    }
    pressures = [r.get('p_bar') for r in artifacts['results']['junction'] if r.get('p_bar') is not None]
    velocities = [r.get('v_mean_m_per_s') for r in artifacts['results']['pipe'] if r.get('v_mean_m_per_s') is not None]
    artifacts['summary'] = {
        'node_count': len(artifacts['design']['junction']),
        'pipe_count': len(artifacts['design']['pipe']),
        'min_p_bar': min(pressures) if pressures else None,
        'max_p_bar': max(pressures) if pressures else None,
        'max_v_m_per_s': max(velocities) if velocities else None,
    }
except Exception as e:
    artifacts = {'error': f'extract_failed: {type(e).__name__}: {e}'}

# carry pipeflow error for the parent to decide success/failure
artifacts['pipeflow_error'] = pipeflow_error

print("__SENTINEL__" + json.dumps(artifacts))
'''

def run_pandapipes_code(
    code: str,
    *,
    limits: Optional[ResourceLimits] = None,
    timeout: Optional[int] = 60,
) -> Dict[str, Any]:
    """
    Stable runner:
    - compiles/executess user code in its own pseudo file 'USER_CODE.py' so we can extract exact line numbers
    - runs pp.pipeflow if user code succeeded
    - extracts design/results/summary (same shape as before)
    - cleans noisy stderr (matplotlib + generic 'is not a writable directory' from worker dirs)
    - returns human-friendly 'reason' and 'tips' on failure
    """
    import json as _json
    HARNESS = r'''
# ===== Pipewise Pandapipes Harness =====
import os, json, pathlib, traceback, re
os.environ["MPLBACKEND"] = "Agg"
try:
    _mpl = pathlib.Path.cwd() / "mplconfig"
    _mpl.mkdir(parents=True, exist_ok=True)
    os.environ["MPLCONFIGDIR"] = str(_mpl)
except Exception:
    pass

# ----- USER CODE (compiled with filename USER_CODE.py) -----
USER_CODE = __USER_CODE_LITERAL__
user_code_error = False
user_error = None
user_traceback = None
user_error_line = None

def _extract_user_line(tb: str, fname: str = "USER_CODE.py"):
    try:
        last = None
        for ln in tb.splitlines():
            m = re.search(r'File "([^"]+)", line (\d+)', ln)
            if m and fname in m.group(1):
                last = int(m.group(2))
        return last
    except Exception:
        return None

try:
    exec(compile(USER_CODE, "USER_CODE.py", "exec"), globals())
    if 'net' not in globals():
        raise NameError("variable 'net' is not defined in user code")
except Exception as e:
    user_code_error = True
    user_error = f"{type(e).__name__}: {e}"
    user_traceback = traceback.format_exc()
    user_error_line = _extract_user_line(user_traceback)

# Try to solve if user code was OK
pipeflow_error = None
if not user_code_error:
    try:
        import pandapipes as pp
        pp.pipeflow(net)
    except Exception as e:
        pipeflow_error = f"{type(e).__name__}: {e}"

def to_records(df):
    try:
        import numpy as np
    except Exception:
        class _N: nan = None
        np = _N()  # type: ignore
    if df is None:
        return []
    try:
        d = df.reset_index().replace({np.nan: None}).to_dict(orient='records')
    except Exception:
        try:
            d = df.reset_index().to_dict(orient='records')
        except Exception:
            d = []
    return d

artifacts = {}
try:
    nd = globals().get('net', object())
    design = {
        'junction': to_records(getattr(nd, 'junction', None)),
        'pipe': to_records(getattr(nd, 'pipe', None)),
        'sink': to_records(getattr(nd, 'sink', None)),
        'source': to_records(getattr(nd, 'source', None)),
        'ext_grid': to_records(getattr(nd, 'ext_grid', None)),
        'valve': to_records(getattr(nd, 'valve', None)),
        'compressor': to_records(getattr(nd, 'compressor', None)) if hasattr(nd,'compressor') else [],
    }
    results = {
        'junction': to_records(getattr(nd, 'res_junction', None)),
        'pipe': to_records(getattr(nd, 'res_pipe', None)),
        'sink': to_records(getattr(nd, 'res_sink', None)) if hasattr(nd, 'res_sink') else [],
        'source': to_records(getattr(nd, 'res_source', None)) if hasattr(nd, 'res_source') else [],
        'ext_grid': to_records(getattr(nd, 'res_ext_grid', None)) if hasattr(nd, 'res_ext_grid') else [],
        'valve': to_records(getattr(nd, 'res_valve', None)) if hasattr(nd, 'res_valve') else [],
        'compressor': to_records(getattr(nd,'res_compressor', None)) if hasattr(nd,'res_compressor') else [],
    }
    pressures = [r.get('p_bar') for r in results['junction'] if r.get('p_bar') is not None]
    velocities = [r.get('v_mean_m_per_s') for r in results['pipe'] if r.get('v_mean_m_per_s') is not None]
    summary = {
        'node_count': len(design['junction']),
        'pipe_count': len(design['pipe']),
        'min_p_bar': min(pressures) if pressures else None,
        'max_p_bar': max(pressures) if pressures else None,
        'max_v_m_per_s': max(velocities) if velocities else None,
    }
    artifacts = {'design': design, 'results': results, 'summary': summary}
except Exception as e:
    artifacts = {'error': f'extract_failed: {type(e).__name__}: {e}'}

# Carry errors forward (used by UI and backend diagnostics)
artifacts['pipeflow_error'] = pipeflow_error
artifacts['user_code_error'] = user_code_error
artifacts['user_error'] = user_error
artifacts['user_error_line'] = user_error_line
artifacts['user_traceback'] = user_traceback

print("PIPEWISE_RESULT_JSON::" + json.dumps(artifacts))
'''
    def _clean_stderr(stderr: Optional[str]) -> str:
        if not stderr:
            return ""
        out: List[str] = []
        for ln in (stderr.splitlines() or []):
            low = ln.lower()
            # Hide matplotlib/mplconfig + generic worker dir noise
            if "matplotlib" in low and ("not a writable directory" in low or "created a temporary cache directory" in low or "mplconfigdir" in low):
                continue
            if "mplconfigdir" in low:
                continue
            if "is not a writable directory" in low and ("pipewise_worker" in low or "pipewise_storage" in low):
                continue
            out.append(ln)
        return "\n".join(out).strip()

    def _diagnose(artifacts: Dict[str, Any], stderr_clean: str) -> (Optional[str], List[str]):
        reason: Optional[str] = None
        tips: List[str] = []

        # Precise user code error
        if artifacts.get("user_code_error"):
            line = artifacts.get("user_error_line")
            err = artifacts.get("user_error") or "User code error"
            reason = f"{err}" + (f" (line {line})" if isinstance(line, int) else "")
            tips = [
                "Fix the syntax at the indicated line.",
                "Python booleans are True/False (capitalized).",
                "Ensure net = pp.create_empty_network(...) exists before creating components.",
            ]
            return reason, tips

        # Pipeflow errors / convergence
        pipe_err = artifacts.get("pipeflow_error")
        design = (artifacts or {}).get("design", {}) or {}
        ext_grids = design.get("ext_grid") or []
        sources = design.get("source") or []
        pipes = design.get("pipe") or []

        if pipe_err:
            if "PipeflowNotConverged" in pipe_err:
                if (not ext_grids and not sources):
                    reason = "No supply/boundary condition defined (no ext_grid or source)."
                    tips = [
                        "Add pp.create_ext_grid(...) or pp.create_source(...).",
                        "Ensure supply is connected via pipes to sinks.",
                        "Open valves and use realistic diameters/lengths/roughness.",
                    ]
                else:
                    reason = "Pipeflow did not converge."
                    tips = [
                        "Check connectivity between supply and sinks.",
                        "Verify at least one ext_grid/source is connected and in service.",
                        "Open valves and check component parameters.",
                    ]
                return reason, tips
            # Other error types
            return pipe_err, tips

        # Fallbacks
        if stderr_clean:
            last = [ln for ln in stderr_clean.splitlines() if ln.strip()]
            if last:
                reason = last[-1].strip()
        if not reason:
            if isinstance(pipes, list) and len(pipes) == 0:
                reason = "No pipes connecting components."
                tips = ["Add pp.create_pipe_from_parameters(...) between junctions."]
            else:
                reason = "Unknown error during run."
                tips = ["Check boundary conditions and connectivity.", "Review component parameters."]

        return reason, tips

    snippet = HARNESS.replace("__USER_CODE_LITERAL__", _json.dumps(code))
    rr = run_snippet_with_result(snippet, limits=limits or DEFAULT_TOOL_LIMITS, timeout=timeout)

    artifacts = rr.result or {}
    stderr_clean = _clean_stderr(rr.stderr or "")
    ok = bool(rr.ok) and not bool(artifacts.get("pipeflow_error")) and not bool(artifacts.get("error")) and not bool(artifacts.get("user_code_error"))

    reason, tips = (None, [])
    if not ok:
        reason, tips = _diagnose(artifacts or {}, stderr_clean)

    return {
        "ok": ok,
        "artifacts": artifacts if ok else (artifacts or {}),
        "logs": (rr.logs or "").strip(),
        "stderr": stderr_clean,
        "returncode": rr.returncode,
        "timed_out": rr.timed_out,
        "wall_time": rr.wall_time,
        "reason": reason,
        "tips": tips,
    }