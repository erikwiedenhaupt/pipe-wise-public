# tools/pandapipes_runner.py
"""
Run pandapipes network code in the sandbox and return structured artifacts.

- Executes user code in an isolated process (core.sandbox).
- Ensures pp.pipeflow(net) is called.
- Extracts design tables (net.*) and result tables (net.res_*).
- Returns JSON-serializable artifacts (lists of dicts + summary).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from .base import run_snippet_with_result, SENTINEL, DEFAULT_TOOL_LIMITS  # type: ignore
from core.security import ResourceLimits  # type: ignore

# Use placeholders that won't collide with braces in Python code
HARNESS_TEMPLATE = r'''
# ===== Pipewise Pandapipes Harness =====
import json
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

# Ensure results exist
try:
    pp.pipeflow(net)
except Exception as e:
    # If it fails, we still try to extract whatever exists
    pass

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
        'compressor': to_records(getattr(net, 'compressor', None)),
    }
    artifacts['results'] = {
        'junction': to_records(getattr(net, 'res_junction', None)),
        'pipe': to_records(getattr(net, 'res_pipe', None)),
        'sink': to_records(getattr(net, 'res_sink', None)) if hasattr(net, 'res_sink') else [],
        'source': to_records(getattr(net, 'res_source', None)) if hasattr(net, 'res_source') else [],
        'ext_grid': to_records(getattr(net, 'res_ext_grid', None)) if hasattr(net, 'res_ext_grid') else [],
        'valve': to_records(getattr(net, 'res_valve', None)) if hasattr(net, 'res_valve') else [],
        'compressor': to_records(getattr(net, 'res_compressor', None)) if hasattr(net, 'res_compressor') else [],
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

print("__SENTINEL__" + json.dumps(artifacts))
'''

def run_pandapipes_code(
    code: str,
    *,
    limits: Optional[ResourceLimits] = None,
    timeout: Optional[int] = 60,
) -> Dict[str, Any]:
    snippet = HARNESS_TEMPLATE.replace("__USER_CODE__", code).replace("__SENTINEL__", SENTINEL)
    rr = run_snippet_with_result(snippet, limits=limits or DEFAULT_TOOL_LIMITS, timeout=timeout)
    return {
        "ok": rr.ok,
        "artifacts": rr.result or {},
        "logs": rr.logs,
        "stderr": rr.stderr,
        "returncode": rr.returncode,
        "timed_out": rr.timed_out,
        "wall_time": rr.wall_time,
    }