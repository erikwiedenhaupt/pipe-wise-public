// components/KPIGrid.jsx
function Pill({ status }) {
  const map = {
    OK: "bg-emerald-500/20 text-emerald-300",
    WARN: "bg-amber-500/20 text-amber-300",
    FAIL: "bg-rose-500/20 text-rose-300",
  };
  return <span className={`px-2 py-0.5 rounded text-xs ${map[status] || "bg-slate-600/30 text-slate-300"}`}>{status || "N/A"}</span>;
}

function thresholdsFromSettings(settings = {}) {
  const prof = (settings.kpiProfile || "standard").toLowerCase();
  if (prof === "strict") return { vOk: 10, vWarn: 15, minFrac: 0.98, reMin: 4000 };
  if (prof === "loose") return { vOk: 20, vWarn: 30, minFrac: 0.90, reMin: 2000 };
  if (prof === "custom") {
    const t = settings.thresholds || {};
    return { vOk: t.velocity_ok_max ?? 15, vWarn: t.velocity_warn_max ?? 25, minFrac: t.min_p_fraction ?? 0.95, reMin: t.re_min_turbulent ?? 2300 };
  }
  return { vOk: 15, vWarn: 25, minFrac: 0.95, reMin: 2300 };
}

function overrideStatus(k, th) {
  // Only adjust known KPIs
  if (k.key === "max_velocity") {
    const v = typeof k.value === "number" ? k.value : null;
    if (v == null) return { ...k };
    const status = v <= th.vOk ? "OK" : (v <= th.vWarn ? "WARN" : "FAIL");
    return { ...k, status };
  }
  if (k.key === "velocity_violations") {
    const n = typeof k.value === "number" ? k.value : 0;
    return { ...k, status: n === 0 ? "OK" : "WARN" };
  }
  if (k.key === "pressure_violations") {
    const n = typeof k.value === "number" ? k.value : 0;
    return { ...k, status: n === 0 ? "OK" : "WARN" };
  }
  return { ...k };
}

export default function KPIGrid({ kpis, settings }) {
  const th = thresholdsFromSettings(settings);
  const items = (kpis?.global || []).map((k, i) => ({ ...overrideStatus(k, th), _id: i }));

  // Highlights: max pipe velocity and lowest node pressure from per_* if present
  let highlight = [];
  try {
    const perPipe = kpis?.per_pipe || {};
    const perNode = kpis?.per_node || {};
    // find max velocity pipe
    let maxV = null, maxPid = null;
    Object.entries(perPipe).forEach(([pid, arr]) => {
      const v = (arr || []).find(x => x.key === "velocity")?.value;
      if (typeof v === "number" && (maxV === null || v > maxV)) { maxV = v; maxPid = pid; }
    });
    if (maxV != null) highlight.push({ label: "Max pipe velocity", value: `${maxV.toFixed(2)} m/s (pipe ${maxPid})` });
    // find lowest node pressure
    let minP = null, minNid = null;
    Object.entries(perNode).forEach(([nid, arr]) => {
      const p = (arr || []).find(x => x.key === "pressure")?.value;
      if (typeof p === "number" && (minP === null || p < minP)) { minP = p; minNid = nid; }
    });
    if (minP != null) highlight.push({ label: "Min node pressure", value: `${minP.toFixed(3)} bar (node ${minNid})` });
  } catch {}

  return (
    <div className="rounded-lg bg-[var(--panel)] border border-slate-700 p-3">
      <div className="mb-2 text-sm text-slate-300">KPIs (global)</div>
      {items.length === 0 ? (
        <div className="text-slate-400 text-sm">No KPIs yet.</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          {items.map((k) => (
            <div key={k._id} className="flex items-center justify-between bg-[var(--panel-2)] border border-slate-700 rounded p-2">
              <div>
                <div className="font-medium">{k.key || k.name}</div>
                <div className="text-xs text-slate-400">
                  {typeof k.value === "object" ? JSON.stringify(k.value) : k.value} {k.unit || ""}
                </div>
              </div>
              <Pill status={k.status} />
            </div>
          ))}
        </div>
      )}

      {highlight.length > 0 && (
        <div className="mt-3">
          <div className="mb-1 text-sm text-slate-300">Highlights</div>
          <ul className="text-xs text-slate-300 list-disc pl-5">
            {highlight.map((h, i) => <li key={i}><span className="text-slate-400">{h.label}:</span> {h.value}</li>)}
          </ul>
        </div>
      )}
    </div>
  );
}