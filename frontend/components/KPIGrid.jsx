// components/KPIGrid.jsx
function Pill({ status }) {
    const map = {
      OK: "bg-emerald-500/20 text-emerald-300",
      WARN: "bg-amber-500/20 text-amber-300",
      FAIL: "bg-rose-500/20 text-rose-300",
    };
    return <span className={`px-2 py-0.5 rounded text-xs ${map[status] || "bg-slate-600/30 text-slate-300"}`}>{status || "N/A"}</span>;
  }
  
  export default function KPIGrid({ kpis }) {
    const items = (kpis?.global || []).map((k, i) => ({ ...k, _id: i }));
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
      </div>
    );
  }