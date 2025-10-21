// components/ScenarioPanel.jsx
import { useEffect, useState } from "react";
import { scenarioSweep, getSweep, parseGraph } from "../lib/api";

const PARAM_OPTIONS = {
  pipe: [{ key: "pipe.diameter_m", label: "Diameter (m)" }],
  valve: [{ key: "valve.diameter_m", label: "Diameter (m)" }],
  junction: [{ key: "junction.pn_bar", label: "pn_bar (bar)" }],
  ext_grid: [{ key: "ext_grid.p_bar", label: "p_bar (bar)" }],
  sink: [{ key: "sink.mdot_kg_per_s", label: "mdot (kg/s)" }],
  source: [{ key: "source.mdot_kg_per_s", label: "mdot (kg/s)" }],
};

function ValuesInput({ value, onChange, placeholder }) {
  return (
    <input
      className="w-full bg-[var(--panel-2)] border border-slate-700 rounded px-2 py-1 text-xs"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder || "comma-separated numbers"}
    />
  );
}

function SelectorRow({ title, enabled, onToggle, compType, onCompType, compId, setCompId, paramKey, onParamKey, options, ids }) {
  return (
    <div className="grid grid-cols-12 gap-2 items-end">
      <div className="col-span-12 md:col-span-2">
        <label className="text-xs text-slate-400 block">{title}</label>
        <input type="checkbox" checked={enabled} onChange={(e) => onToggle(e.target.checked)} /> <span className="text-xs text-slate-300">Enable</span>
      </div>
      <div className="col-span-12 md:col-span-3">
        <label className="text-xs text-slate-400 block">Component Type</label>
        <select value={compType} onChange={(e) => onCompType(e.target.value)} className="w-full bg-[var(--panel-2)] border border-slate-700 rounded px-2 py-1 text-xs">
          {Object.keys(PARAM_OPTIONS).map(t => <option key={t} value={t}>{t}</option>)}
        </select>
      </div>
      <div className="col-span-12 md:col-span-2">
        <label className="text-xs text-slate-400 block">Component ID</label>
        <select value={compId ?? ""} onChange={(e) => setCompId(e.target.value === "" ? null : parseInt(e.target.value, 10))} className="w-full bg-[var(--panel-2)] border border-slate-700 rounded px-2 py-1 text-xs">
          <option value="">(all or first)</option>
          {ids.map((id) => <option key={id} value={id}>{id}</option>)}
        </select>
      </div>
      <div className="col-span-12 md:col-span-5">
        <label className="text-xs text-slate-400 block">Parameter</label>
        <select value={paramKey} onChange={(e) => onParamKey(e.target.value)} className="w-full bg-[var(--panel-2)] border border-slate-700 rounded px-2 py-1 text-xs">
          {(options[compType] || []).map(opt => <option key={opt.key} value={opt.key}>{opt.label}</option>)}
        </select>
      </div>
    </div>
  );
}

function ResultsTable({ data }) {
  if (!data || !Array.isArray(data.results) || data.results.length === 0) return null;
  const cols = Object.keys(data.results[0].params || {});
  const getG = (g, key) => {
    const it = g.find(x => x.key === key);
    return it ? (it.value == null ? "—" : it.value) : "—";
  };
  return (
    <div className="mt-3 rounded bg-[var(--panel)] border border-slate-700 p-3">
      <div className="text-sm text-slate-300 mb-2">Sweep Results (n={data.design_space_size})</div>
      <div className="overflow-auto">
        <table className="min-w-full text-xs">
          <thead>
            <tr className="text-slate-300">
              {cols.map(c => <th key={c} className="px-2 py-1 text-left border-b border-slate-700">{c}</th>)}
              <th className="px-2 py-1 text-left border-b border-slate-700">max_velocity (m/s)</th>
              <th className="px-2 py-1 text-left border-b border-slate-700">min_node_pressure (bar)</th>
              <th className="px-2 py-1 text-left border-b border-slate-700">max_pipe_dp_bar</th>
            </tr>
          </thead>
          <tbody>
            {data.results.map((r, i) => {
              const g = (r.kpis || {}).global || [];
              return (
                <tr key={i} className="text-slate-100 even:bg-[var(--panel-2)]">
                  {cols.map(c => <td key={c} className="px-2 py-1 border-b border-slate-800">{String(r.params[c])}</td>)}
                  <td className="px-2 py-1 border-b border-slate-800">{getG(g, "max_velocity")}</td>
                  <td className="px-2 py-1 border-b border-slate-800">{getG(g, "min_node_pressure")}</td>
                  <td className="px-2 py-1 border-b border-slate-800">{getG(g, "max_pipe_dp_bar")}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function ScenarioPanel({ onRun, run, projectId, versionId, code, sweepData }) {
  const [enabled2, setEnabled2] = useState(false);

  // Param 1
  const [t1, setT1] = useState("pipe");
  const [id1, setId1] = useState(null);
  const [k1, setK1] = useState("pipe.diameter_m");
  const [v1, setV1] = useState("0.05, 0.06, 0.07");

  // Param 2
  const [t2, setT2] = useState("ext_grid");
  const [id2, setId2] = useState(null);
  const [k2, setK2] = useState("ext_grid.p_bar");
  const [v2, setV2] = useState("1.0, 1.1");

  const [ids, setIds] = useState({ junction: [], pipe: [], valve: [], ext_grid: [], sink: [], source: [] });

  useEffect(() => {
    // auto-get component ids from code via parse-graph
    async function loadIds() {
      try {
        if (!code) { setIds({ junction: [], pipe: [], valve: [], ext_grid: [], sink: [], source: [] }); return; }
        const g = await parseGraph(code);
        // design tables are not directly returned; infer from graph and components count
        const pipeIds = (g.graph?.edges || []).filter(e => e.type === "pipe").map(e => parseInt(e.id, 10)).filter(n => !Number.isNaN(n));
        const valveIds = (g.graph?.edges || []).filter(e => e.type === "valve").map(e => parseInt(e.id, 10)).filter(n => !Number.isNaN(n));
        const junctionIds = (g.graph?.nodes || []).filter(n => n.type === "junction").map(n => parseInt(n.id, 10)).filter(n => !Number.isNaN(n));
        // ext_grids often not in graph edges; expose 0 as a conventional id if present
        const extGridIds = g.components?.ext_grids > 0 ? [0] : [];
        setIds({ junction: junctionIds, pipe: pipeIds, valve: valveIds, ext_grid: extGridIds, sink: [], source: [] });
      } catch {
        setIds({ junction: [], pipe: [], valve: [], ext_grid: [], sink: [], source: [] });
      }
    }
    loadIds();
  }, [code]);

  const runSweep = async () => {
    const parseVals = (s) => s.split(",").map(x => x.trim()).filter(Boolean).map(x => parseFloat(x));
    const params = [
      { name: k1, selector: { type: t1, id: id1 }, values: parseVals(v1) },
    ];
    if (enabled2) params.push({ name: k2, selector: { type: t2, id: id2 }, values: parseVals(v2) });

    if (onRun) {
      await onRun(params);
    } else {
      const payload = { code_or_version: { project_id: projectId, version_id: versionId, code }, parameters: params };
      const res = await scenarioSweep(payload);
      // show results inline
      const data = await getSweep(res.run_id);
      // expose table below (if you keep local state)
      // setSweepDataLocal(data);
    }
  };

  return (
    <div className="rounded-lg bg-[var(--panel)] border border-slate-700 p-3">
      <div className="text-sm text-slate-300 mb-2">Scenario Sweep</div>

      <SelectorRow
        title="Parameter 1"
        enabled={true}
        onToggle={() => {}}
        compType={t1} onCompType={(v) => { setT1(v); setK1((PARAM_OPTIONS[v] || [])[0]?.key || ""); }}
        compId={id1} setCompId={setId1}
        paramKey={k1} onParamKey={setK1}
        options={PARAM_OPTIONS}
        ids={ids[t1] || []}
      />

      <div className="grid grid-cols-12 gap-2 items-end mt-2">
        <div className="col-span-12 md:col-span-12">
          <label className="text-xs text-slate-400 block">Values</label>
          <ValuesInput value={v1} onChange={setV1} placeholder="e.g., 0.05, 0.06, 0.07" />
        </div>
      </div>

      <div className="mt-3">
        <SelectorRow
          title="Parameter 2 (optional)"
          enabled={enabled2}
          onToggle={setEnabled2}
          compType={t2} onCompType={(v) => { setT2(v); setK2((PARAM_OPTIONS[v] || [])[0]?.key || ""); }}
          compId={id2} setCompId={setId2}
          paramKey={k2} onParamKey={setK2}
          options={PARAM_OPTIONS}
          ids={ids[t2] || []}
        />
        {enabled2 && (
          <div className="grid grid-cols-12 gap-2 items-end mt-2">
            <div className="col-span-12 md:col-span-12">
              <label className="text-xs text-slate-400 block">Values</label>
              <ValuesInput value={v2} onChange={setV2} placeholder="e.g., 1.0, 1.1" />
            </div>
          </div>
        )}
      </div>

      <div className="mt-3">
        <button onClick={runSweep} className="px-3 py-1 rounded bg-[var(--accent)] hover:opacity-90">Run sweep</button>
      </div>

      <ResultsTable data={sweepData} />
    </div>
  );
}