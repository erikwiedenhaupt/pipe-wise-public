// components/ScenarioPanel.jsx
import { useState } from "react";

export default function ScenarioPanel({ onRun }) {
  const [name, setName] = useState("diameter");
  const [values, setValues] = useState("0.15 m, 0.2 m, 0.25 m");

  const run = () => {
    const list = values.split(",").map((x) => x.trim()).filter(Boolean);
    onRun?.({ name, values: list });
  };

  return (
    <div className="rounded-lg bg-[var(--panel)] border border-slate-700 p-3">
      <div className="text-sm text-slate-300 mb-2">Scenario Sweep</div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
        <div className="col-span-1">
          <label className="text-xs text-slate-400">Parameter</label>
          <input value={name} onChange={(e) => setName(e.target.value)} className="w-full bg-[var(--panel-2)] border border-slate-700 rounded px-2 py-1" />
        </div>
        <div className="md:col-span-2">
          <label className="text-xs text-slate-400">Values (comma-separated)</label>
          <input value={values} onChange={(e) => setValues(e.target.value)} className="w-full bg-[var(--panel-2)] border border-slate-700 rounded px-2 py-1" />
        </div>
      </div>
      <div className="mt-3">
        <button onClick={run} className="px-3 py-1 rounded bg-[var(--accent)] hover:opacity-90">Run sweep</button>
      </div>
    </div>
  );
}