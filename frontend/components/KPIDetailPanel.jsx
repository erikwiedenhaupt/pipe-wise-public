// components/KPIDetailPanel.jsx
import { useMemo, useState } from "react";

export default function KPIDetailPanel({ kpis }) {
  const [typ, setTyp] = useState("pipe");
  const [idv, setIdv] = useState("");

  const options = useMemo(() => {
    const per_node = kpis?.per_node || {};
    const per_pipe = kpis?.per_pipe || {};
    return {
      node: Object.keys(per_node),
      pipe: Object.keys(per_pipe),
    };
  }, [kpis]);

  const items = useMemo(() => {
    if (typ === "node") {
      return (kpis?.per_node || {})[idv] || [];
    }
    if (typ === "pipe") {
      return (kpis?.per_pipe || {})[idv] || [];
    }
    return [];
  }, [typ, idv, kpis]);

  return (
    <div className="rounded-lg bg-[var(--panel)] border border-slate-700 p-3">
      <div className="mb-2 text-sm text-slate-300">Component KPIs</div>
      <div className="flex gap-2 mb-2">
        <select value={typ} onChange={(e) => { setTyp(e.target.value); setIdv(""); }} className="bg-[var(--panel-2)] border border-slate-700 rounded px-2 py-1 text-xs">
          <option value="pipe">pipe</option>
          <option value="node">node (junction)</option>
        </select>
        <select value={idv} onChange={(e) => setIdv(e.target.value)} className="bg-[var(--panel-2)] border border-slate-700 rounded px-2 py-1 text-xs">
          <option value="">(select id)</option>
          {(options[typ] || []).map(id => <option key={id} value={id}>{id}</option>)}
        </select>
      </div>
      {!idv ? (
        <div className="text-xs text-slate-400">Select a component id.</div>
      ) : (
        <div className="overflow-auto">
          <table className="min-w-full text-xs">
            <thead>
              <tr className="text-slate-300">
                <th className="px-2 py-1 text-left border-b border-slate-700">key</th>
                <th className="px-2 py-1 text-left border-b border-slate-700">value</th>
                <th className="px-2 py-1 text-left border-b border-slate-700">unit</th>
                <th className="px-2 py-1 text-left border-b border-slate-700">status</th>
              </tr>
            </thead>
            <tbody>
              {items.map((it, i) => (
                <tr key={i} className="text-slate-100 even:bg-[var(--panel-2)]">
                  <td className="px-2 py-1 border-b border-slate-800">{it.key}</td>
                  <td className="px-2 py-1 border-b border-slate-800">{it.value == null ? "—" : String(it.value)}</td>
                  <td className="px-2 py-1 border-b border-slate-800">{it.unit || ""}</td>
                  <td className="px-2 py-1 border-b border-slate-800">{it.status || ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}