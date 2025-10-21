# backend/core/costs.py
from __future__ import annotations
import os
from typing import Any, Dict, List, Optional, Tuple

def _norm_diam_mm(d: Optional[float]) -> Optional[float]:
    if d is None:
        return None
    try:
        val = float(d)
    except Exception:
        return None
    # If value looks like meters (< 10), convert to mm
    return val * 1000.0 if val < 10.0 else val

def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default

def extract_segments_from_artifacts(artifacts: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], float, int]:
    """
    Try to extract pipe segments: [{length_m, diameter_mm, material}], total_length_m, n_segments.
    Fallbacks:
    - artifacts['pipes'] as a list of dicts
    - artifacts['net']['pipe'] table-like dicts
    - artifacts['summary']['total_length_m']
    """
    segments: List[Dict[str, Any]] = []
    total_length_m = 0.0

    # Case 1: explicit pipes list
    pipes = artifacts.get("pipes")
    if isinstance(pipes, list) and pipes:
        for p in pipes:
            length_m = _safe_float(p.get("length") or p.get("length_m"), 0.0)
            diam_mm = _norm_diam_mm(p.get("diameter") or p.get("diameter_m") or p.get("diameter_mm"))
            mat = (p.get("material") or "").lower()
            segments.append({"length_m": length_m, "diameter_mm": diam_mm, "material": mat or None})
            total_length_m += length_m

    # Case 2: pandapipes-style net structure
    if not segments and isinstance(artifacts.get("net"), dict):
        pipe_tbl = artifacts["net"].get("pipe") or artifacts["net"].get("pipes")
        if isinstance(pipe_tbl, dict):
            length_col = pipe_tbl.get("length_m") or pipe_tbl.get("length") or []
            diam_col = pipe_tbl.get("diameter_m") or pipe_tbl.get("diameter") or pipe_tbl.get("diameter_mm") or []
            mat_col = pipe_tbl.get("material") or []
            n = max(len(length_col), len(diam_col), len(mat_col))
            for i in range(n):
                length_m = _safe_float(length_col[i] if i < len(length_col) else 0.0, 0.0)
                diam_mm = _norm_diam_mm(diam_col[i] if i < len(diam_col) else None)
                mat = (mat_col[i] if i < len(mat_col) else None)
                mat = (mat or "").lower() or None
                segments.append({"length_m": length_m, "diameter_mm": diam_mm, "material": mat})
                total_length_m += length_m

    # Case 3: summary fallback
    if total_length_m <= 0.0 and isinstance(artifacts.get("summary"), dict):
        total_length_m = _safe_float(artifacts["summary"].get("total_length_m") or artifacts["summary"].get("total_pipe_length_m"), 0.0)
        if total_length_m > 0.0:
            # Create 1 synthetic segment with avg diameter if available
            avg_diam_m = _safe_float(artifacts["summary"].get("avg_diameter_m"), 0.15)
            segments.append({"length_m": total_length_m, "diameter_mm": _norm_diam_mm(avg_diam_m), "material": None})

    return segments, total_length_m, len(segments)

def estimate_network_build_cost(
    artifacts: Dict[str, Any],
    *,
    region: Optional[str] = None,
    context: Optional[str] = None,
    profile: Optional[str] = None,
    valve_spacing_m: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Rough EU CAPEX estimate (EUR) for laying the network:
    - Supply cost per meter depends on material and diameter.
    - Installation/excavation/reinstatement per meter depends on urban/rural context.
    - Valves, fittings, pumps, and overhead (engineering + contingency).

    Tunables via env:
    COST_REGION (EU|DE|EU_EAST) default EU
    COST_CONTEXT (urban|rural) default urban
    COST_PROFILE (distribution|transmission) default distribution
    COST_ENGINEERING_PCT default 0.10
    COST_CONTINGENCY_PCT default 0.15
    COST_VALVE_SPACING_M default 200
    COST_VALVE_PE_EUR default 400
    COST_VALVE_STEEL_EUR default 800
    COST_PUMP_EUR default 5000
    """
    region = (region or os.getenv("COST_REGION", "EU")).upper()
    context = (context or os.getenv("COST_CONTEXT", "urban")).lower()
    profile = (profile or os.getenv("COST_PROFILE", "distribution")).lower()
    valve_spacing_m = valve_spacing_m or _safe_float(os.getenv("COST_VALVE_SPACING_M", 200.0), 200.0)

    eng_pct = _safe_float(os.getenv("COST_ENGINEERING_PCT", 0.10), 0.10)
    cont_pct = _safe_float(os.getenv("COST_CONTINGENCY_PCT", 0.15), 0.15)

    valve_cost_pe = _safe_float(os.getenv("COST_VALVE_PE_EUR", 400.0), 400.0)
    valve_cost_steel = _safe_float(os.getenv("COST_VALVE_STEEL_EUR", 800.0), 800.0)
    pump_cost_eur = _safe_float(os.getenv("COST_PUMP_EUR", 5000.0), 5000.0)

    # Region factor
    region_factor = 1.0
    if region in ("DE", "DACH", "EU_WEST"):
        region_factor = 1.1
    elif region in ("EU_EAST", "CEE"):
        region_factor = 0.9

    # Context rates per meter (EUR/m)
    if context == "urban":
        install_excav_eur_m = 80.0  # excavation + bedding
        reinstatement_eur_m = 40.0  # paving/asphalt
    else:
        install_excav_eur_m = 50.0
        reinstatement_eur_m = 20.0

    # Supply base rates (EUR/m) for PE vs steel; scaled by diameter
    def supply_rate_eur_per_m(material: str, diam_mm: Optional[float]) -> float:
        dmm = diam_mm or 150.0
        m = (material or "").lower()
        if profile == "transmission" or m == "steel":
            base = 80.0  # ~DN100 steel
            alpha = 1.1
        else:
            base = 25.0  # ~DN50 PE
            alpha = 1.2
        return base * max(0.6, (dmm / (100.0 if m == "steel" else 50.0)) ** alpha)

    segments, total_length_m, n_segments = extract_segments_from_artifacts(artifacts)

    # Count valves and pumps if present
    valves_count = 0
    pumps_count = 0
    if isinstance(artifacts.get("valves"), list):
        valves_count = len(artifacts["valves"])
    elif isinstance(artifacts.get("net"), dict) and isinstance(artifacts["net"].get("valve"), dict):
        valves_count = len(artifacts["net"]["valve"].get("name") or [])  # rough
    if isinstance(artifacts.get("pumps"), list):
        pumps_count = len(artifacts["pumps"])
    elif isinstance(artifacts.get("net"), dict) and isinstance(artifacts["net"].get("pump"), dict):
        pumps_count = len(artifacts["net"]["pump"].get("name") or [])

    # Fallback valve estimation by spacing
    if valves_count == 0 and total_length_m > 0:
        valves_count = max(1, int(total_length_m / valve_spacing_m))

    # Per-segment costs
    supply_sum = 0.0
    install_sum = 0.0
    reinst_sum = 0.0
    fittings_sum = 0.0
    pe_len = 0.0
    steel_len = 0.0

    for seg in segments:
        length_m = _safe_float(seg.get("length_m"), 0.0)
        diam_mm = _norm_diam_mm(seg.get("diameter_mm"))
        mat = seg.get("material") or ("steel" if (diam_mm or 0) >= 200 else "pe")
        pe_len += length_m if mat == "pe" else 0.0
        steel_len += length_m if mat == "steel" else 0.0

        supply = supply_rate_eur_per_m(mat, diam_mm) * length_m
        install = install_excav_eur_m * length_m
        reinst = reinstatement_eur_m * length_m
        fittings = 0.10 * supply  # 10% of supply cost for fittings/couplers

        supply_sum += supply
        install_sum += install
        reinst_sum += reinst
        fittings_sum += fittings

    # If no segments (unknown artifacts), assume a small test network of 100m PE DN100
    confidence = "high" if n_segments > 0 else "low"
    if n_segments == 0:
        length_m = total_length_m if total_length_m > 0 else 100.0
        supply = supply_rate_eur_per_m("pe", 100.0) * length_m
        install = install_excav_eur_m * length_m
        reinst = reinstatement_eur_m * length_m
        fittings = 0.10 * supply
        supply_sum += supply
        install_sum += install
        reinst_sum += reinst
        fittings_sum += fittings
        pe_len += length_m

    # Valves and pumps
    valves_cost = valves_count * ((valve_cost_steel if steel_len > pe_len else valve_cost_pe))
    pumps_cost = pumps_count * pump_cost_eur

    base_sum = supply_sum + install_sum + reinst_sum + fittings_sum + valves_cost + pumps_cost
    base_sum *= region_factor

    engineering = eng_pct * base_sum
    contingency = cont_pct * (base_sum + engineering)

    total_mid = base_sum + engineering + contingency
    # Low/high bounds ±15%
    total_low = 0.85 * total_mid
    total_high = 1.15 * total_mid

    breakdown = {
        "supply_eur": round(supply_sum * region_factor, 2),
        "installation_excavation_eur": round(install_sum * region_factor, 2),
        "reinstatement_eur": round(reinst_sum * region_factor, 2),
        "fittings_eur": round(fittings_sum * region_factor, 2),
        "valves_eur": round(valves_cost * region_factor, 2),
        "pumps_eur": round(pumps_cost * region_factor, 2),
        "engineering_eur": round(engineering, 2),
        "contingency_eur": round(contingency, 2),
    }

    return {
        "total_low_eur": round(total_low, 2),
        "total_mid_eur": round(total_mid, 2),
        "total_high_eur": round(total_high, 2),
        "breakdown": breakdown,
        "assumptions": {
            "region": region,
            "context": context,
            "profile": profile,
            "region_factor": region_factor,
            "engineering_pct": eng_pct,
            "contingency_pct": cont_pct,
            "valve_spacing_m": valve_spacing_m,
            "confidence": confidence,
        },
    }