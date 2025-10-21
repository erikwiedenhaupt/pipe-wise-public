// pages/index.js
import { useEffect, useMemo, useState } from "react";
import CodeEditor from "../components/CodeEditor";
import RunHeader from "../components/RunHeader";
import KPIGrid from "../components/KPIGrid";
import IssueList from "../components/IssueList";
import ScenarioPanel from "../components/ScenarioPanel";
import Chat from "../components/Chat";
import DebugPanel from "../components/DebugPanel";
import SettingsPanel from "../components/SettingsPanel";
import ProjectInfo from "../components/ProjectInfo";
import KPIDetailPanel from "../components/KPIDetailPanel";
import InteractionGraph from "../components/InteractionGraph";
import VisualBuilder from "../components/VisualBuilder";

import { getSweep, parseGraph } from "../lib/api";
import { API_BASE, createProject, addVersion, validateCode, simulate, getRun, getRunKpis, getRunIssues, scenarioSweep } from "../lib/api";

const SAMPLE_CODE = `import pandapipes as pp
net = pp.create_empty_network(fluid="lgas")
j1 = pp.create_junction(net, pn_bar=1.05, tfluid_k=293.15, name="Junction 1")
j2 = pp.create_junction(net, pn_bar=1.05, tfluid_k=293.15, name="Junction 2")
j3 = pp.create_junction(net, pn_bar=1.05, tfluid_k=293.15, name="Junction 3")
pp.create_ext_grid(net, junction=j1, p_bar=1.1, t_k=293.15, name="Grid Connection")
pp.create_sink(net, junction=j3, mdot_kg_per_s=0.045, name="Sink")
pp.create_pipe_from_parameters(net, from_junction=j1, to_junction=j2, length_km=0.1, diameter_m=0.05, name="Pipe 1")
pp.create_valve(net, from_junction=j2, to_junction=j3, diameter_m=0.05, opened=True, name="Valve 1")
pp.pipeflow(net)`;

export default function Home() {
  const [code, setCode] = useState(SAMPLE_CODE);
  const [project, setProject] = useState(null);
  const [version, setVersion] = useState(null);
  const [runId, setRunId] = useState(null);
  const [run, setRun] = useState(null);
  const [kpis, setKpis] = useState(null);
  const [issues, setIssues] = useState({ issues: [], suggestions: [] });
  const [validation, setValidation] = useState(null);
  const [busy, setBusy] = useState(false);
  const [simProg, setSimProg] = useState(null);
  const [wsSim, setWsSim] = useState(null);
  const [sweepData, setSweepData] = useState(null);
  const [errors, setErrors] = useState([]);
  const [settings, setSettings] = useState({
    audience: "expert", debug: false, autoAdoptRun: true, autoApplyCode: true,
    projectId: "", versionId: "", runId: ""
  });

  function ValidationPanel({ data }) {
    if (!data) return null;
    const ok = data.ok === true;
    const statusCls = ok ? "bg-emerald-500/20 text-emerald-300" : "bg-rose-500/20 text-rose-300";
    const inferred = data.inferred || {};
    const comps = inferred.components || {};
    const msgBadge = (lvl) => lvl === "blocked" || lvl === "error" ? "bg-rose-500/20 text-rose-300" : lvl === "warn" ? "bg-amber-500/20 text-amber-300" : "bg-slate-600/30 text-slate-300";
    return (
      <div className="rounded bg-[var(--panel)] border border-slate-700 p-3 text-sm">
        <div className="flex items-center justify-between mb-2">
          <div className="text-slate-300">Validation</div>
          <span className={`px-2 py-0.5 rounded text-xs ${statusCls}`}>{ok ? "OK" : "Blocked"}</span>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
          <div className="bg-[var(--panel-2)] border border-slate-700 rounded p-2"><div className="text-slate-400">Fluid</div><div className="text-slate-100">{inferred.fluid || "—"}</div></div>
          <div className="bg-[var(--panel-2)] border border-slate-700 rounded p-2"><div className="text-slate-400">Junctions</div><div className="text-slate-100">{comps.junctions ?? 0}</div></div>
          <div className="bg-[var(--panel-2)] border border-slate-700 rounded p-2"><div className="text-slate-400">Pipes</div><div className="text-slate-100">{comps.pipes ?? 0}</div></div>
          <div className="bg-[var(--panel-2)] border border-slate-700 rounded p-2"><div className="text-slate-400">Valves</div><div className="text-slate-100">{comps.valves ?? 0}</div></div>
        </div>
        {(Array.isArray(data.messages) && data.messages.length > 0) && (
          <div className="mt-3">
            <div className="text-slate-300 mb-1">Messages</div>
            <ul className="space-y-1">
              {data.messages.map((m, i) => (
                <li key={i} className="flex items-center gap-2 bg-[var(--panel-2)] border border-slate-700 rounded p-2">
                  <span className={`px-2 py-0.5 rounded text-[10px] ${msgBadge((m.level || "").toLowerCase())}`}>{(m.level || "").toUpperCase()}</span>
                  <span className="text-xs text-slate-200">{m.text || ""}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    );
  }

  const setCodeAndInvalidate = (newCode) => { setCode(newCode); setValidation(null); };

  useEffect(() => { createProject("dev-project").then(({ project_id }) => setProject({ id: project_id })).catch((e) => setErrors((p) => [...p, String(e)])); }, []);

  useEffect(() => {
    const channel = project?.id || settings.projectId || "adhoc";
    if (!channel) return;
    const base = process.env.NEXT_PUBLIC_API_BASE || "/api";
    let u;
    try { u = new URL(base, window.location.origin); } catch { u = new URL(window.location.origin); u.pathname = base; }
    u.protocol = u.protocol === "https:" ? "wss:" : "ws:"; u.pathname = (u.pathname.replace(/\/+$/, "") || "") + "/chat/ws/debug/" + encodeURIComponent(channel);
    u.search = ""; u.hash = "";
    const ws = new WebSocket(u.toString());
    setWsSim(ws);
    ws.onmessage = (evt) => {
      try {
        const m = JSON.parse(evt.data);
        const ev = m?.event || {};
        if (!ev?.type) return;
        if (ev.type === "sim.start") {
          setSimProg({ runId: ev.run_id, percent: 0, elapsed: 0, eta_secs: null, running: true });
        } else if (ev.type === "sim.progress") {
          setSimProg((p) => ({ ...(p || {}), runId: ev.run_id, percent: ev.percent ?? 0, elapsed: ev.elapsed ?? 0, eta_secs: ev.eta_secs ?? null, running: true }));
        } else if (ev.type === "sim.stderr") {
          setSimProg((p) => ({ ...(p || {}), lastStderr: ev.stderr }));
        } else if (ev.type === "sim.end") {
          setSimProg((p) => ({ ...(p || {}), runId: ev.run_id, running: false, finishedOk: !!ev.ok, percent: 100 }));
        }
      } catch {}
    };
    ws.onclose = () => setWsSim(null);
    ws.onerror = () => {};
    return () => { try { ws.close(); } catch {} setWsSim(null); };
  }, [project?.id, settings.projectId]);

  useEffect(() => {
    const onSwitch = (e) => { const rid = e.detail?.runId; if (rid) adoptRunId(rid); };
    window.addEventListener('pipewise:switch-run', onSwitch);
    return () => window.removeEventListener('pipewise:switch-run', onSwitch);
  }, []);

  const applySettings = (s) => {
    setSettings((prev) => ({ ...prev, ...s }));
    if (s.projectId) setProject({ id: s.projectId });
    if (s.versionId) setVersion({ id: s.versionId });
    if (s.runId) adoptRunId(s.runId);
  };

  const doValidate = async () => {
    setBusy(true); setValidation(null);
    try {
      const ch = project?.id || settings.projectId || "adhoc";
      window.dispatchEvent(new CustomEvent("pipewise:graph-pulse", { detail: { channel: ch, type: "graph.abort" } }));
      window.dispatchEvent(new CustomEvent("pipewise:graph-pulse", { detail: { channel: ch, type: "validate.start" } }));
      const res = await validateCode(code);
      setValidation(res);
      window.dispatchEvent(new CustomEvent("pipewise:graph-pulse", { detail: { channel: ch, type: "validate.end", ok: !!res.ok, inferred: res.inferred, messages: res.messages || [] } }));
    } catch (e) { setErrors((p) => [...p, String(e)]); } finally { setBusy(false); }
  };

  const validationErrorLines = useMemo(() => {
    const msgs = (validation && Array.isArray(validation.messages)) ? validation.messages : [];
    const lines = [];
    for (const m of msgs) {
      const lvl = String(m.level || "").toLowerCase();
      if ((lvl === "blocked" || lvl === "error") && m.where && typeof m.where.line === "number") lines.push(m.where.line);
    }
    return [...new Set(lines)];
  }, [validation]);

  const doSaveVersion = async () => {
    const pid = project?.id || settings.projectId; if (!pid) return;
    setBusy(true);
    try { const res = await addVersion(pid, code, { label: "v1" }); setVersion({ id: res.version_id }); }
    catch (e) { setErrors((p) => [...p, String(e)]); } finally { setBusy(false); }
  };

  const runtimeErrorLine = useMemo(() => {
    try { const ln = run?.artifacts?.failure?.code_line; return (typeof ln === "number" && ln >= 1) ? ln : null; } catch { return null; }
  }, [run]);

  const refreshRun = async (rid = runId) => {
    if (!rid) return;
    try {
      const r = await getRun(rid); setRun({ id: rid, ...r });
      const k = await getRunKpis(rid); setKpis(k);
      const i = await getRunIssues(rid); setIssues(i);
    } catch (e) { setErrors((p) => [...p, String(e)]); }
  };

  const doSimulate = async () => {
    if (validation && validation.ok === false) { setErrors((p) => [...p, "Simulate blocked by validation. Open Validate to see details."]); return; }
    const pid = project?.id || settings.projectId;
    const vid = version?.id || settings.versionId;
    setBusy(true);
    try {
      const res = await simulate({ project_id: pid, version_id: vid, code });
      applySettings({ projectId: pid || "", versionId: vid || "", runId: res.run_id || "" });
      if (settings.autoAdoptRun !== false) setRunId(res.run_id);
      await refreshRun(res.run_id);
    } catch (e) { setErrors((p) => [...p, String(e)]); } finally { setBusy(false); }
  };

  const doSweep = async (parameters) => {
    const pid = project?.id || settings.projectId;
    const vid = version?.id || settings.versionId;
    if (!pid) return;
    setBusy(true);
    try {
      const payload = { code_or_version: { project_id: pid, version_id: vid, code }, parameters };
      const res = await scenarioSweep(payload);
      if (settings.autoAdoptRun) setRunId(res.run_id);
      const data = await getSweep(res.run_id);
      setSweepData(data);
      await refreshRun(res.run_id);
    } catch (e) { setErrors((p) => [...p, String(e)]); } finally { setBusy(false); }
  };

  const adoptRunId = async (rid) => { if (settings.autoAdoptRun) setRunId(rid); await refreshRun(rid); };
  const onApplyCodeFromChat = (newCode, diff) => { if (settings.autoApplyCode) setCodeAndInvalidate(newCode); };

  const debugData = useMemo(() => ({ API_BASE, project, version, runId, run, validation, kpis, issues, settings }), [project, version, runId, run, validation, kpis, issues, settings]);

  return (
    <main className="max-w-7xl mx-auto p-4 space-y-4">
      <header className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Pipewise Dev UI</h1>
        <div className="text-xs text-slate-400">API: {API_BASE}</div>
      </header>

      <ProjectInfo projectId={project?.id || settings.projectId} versionId={version?.id || settings.versionId} runId={runId || settings.runId} />

      {/* Settings at the top */}
      <SettingsPanel projectId={project?.id} versionId={version?.id} runId={runId} onApply={applySettings} />

      {/* Row: Visual Builder + Chat (side-by-side) */}
      <div className="grid grid-cols-12 gap-4">
        <div className="col-span-7 min-w-0">
          <div className="space-y-3">
            <VisualBuilder code={code} onApply={(newCode) => setCodeAndInvalidate(newCode)} />
          </div>
        </div>
        <div className="col-span-5 min-w-0">
          <div className="space-y-3">
            <Chat
              projectId={project?.id || settings.projectId}
              versionId={version?.id || settings.versionId}
              runId={runId || settings.runId}
              audience={settings.audience}
              settings={settings}
              onAdoptRunId={adoptRunId}
              onApplyCode={onApplyCodeFromChat}
            />
          </div>
        </div>
      </div>



      {/* Row: Interaction Graph (own full-width row) */}
      <div className="grid grid-cols-1 gap-4">
        <section className="space-y-3">
          <InteractionGraph channel={project?.id || settings.projectId || "adhoc"} />
        </section>
      </div>

      {/* Row: Code Editor (full-width) */}
      <div className="grid grid-cols-1 gap-4">
        <section className="space-y-3">
          <CodeEditor
            value={code}
            onChange={setCodeAndInvalidate}
            runtimeErrorLine={runtimeErrorLine}
            validationErrorLines={validationErrorLines}
          />
          <div className="flex gap-2">
            <button onClick={doValidate} disabled={busy} className="px-3 py-1 rounded bg-[var(--panel)] border border-slate-700 hover:bg-slate-800">Validate</button>
            <button onClick={doSaveVersion} disabled={busy || !(project?.id || settings.projectId)} className="px-3 py-1 rounded bg-[var(--panel)] border border-slate-700 hover:bg-slate-800">Save Version</button>
            <button
              onClick={doSimulate}
              disabled={busy || !(validation && validation.ok === true)}
              title={!validation ? "Please run Validate first." : (validation.ok === false ? "Validation failed. Fix issues before simulating." : "")}
              className="px-3 py-1 rounded bg-[var(--accent)] hover:opacity-90 disabled:opacity-50"
            >
              Simulate
            </button>
            {simProg?.running ? (
              <div className="mt-2">
                <div className="flex items-center justify-between text-xs text-slate-300">
                  <div>Running simulation…</div>
                  <div>{simProg.percent ?? 0}% {typeof simProg.elapsed === "number" ? `· ${simProg.elapsed.toFixed(1)}s` : ""} {typeof simProg.eta_secs === "number" ? `· HALT in ${simProg.eta_secs}s` : ""}</div>
                </div>
                <div className="w-full h-2 bg-slate-800 rounded overflow-hidden mt-1">
                  <div className="h-2 bg-[var(--accent)] transition-all" style={{ width: `${Math.max(0, Math.min(100, simProg.percent || 0))}%` }} />
                </div>
                {simProg.lastStderr ? (<div className="mt-1 text-[11px] text-amber-300 line-clamp-2">stderr: {simProg.lastStderr}</div>) : null}
              </div>
            ) : null}
          </div>
        </section>
      </div>



      {/* KPIs, Run Header, Issues, Scenario below */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <section className="space-y-3">
          <RunHeader
            run={run ? run : (runId ? { id: runId, status: "queued" } : null)}
            onRefresh={() => refreshRun()}
            onDelete={async () => {
              if (!runId) return;
              await fetch(`${API_BASE}/runs/${runId}`, { method: "DELETE" }).catch(() => {});
              setRunId(null); setRun(null); setKpis(null); setIssues({ issues: [], suggestions: [] });
            }}
          />
          <KPIGrid kpis={kpis} settings={settings} />
          <KPIDetailPanel kpis={kpis} />
        </section>
        <section className="space-y-3">
          <IssueList issues={issues.issues} suggestions={issues.suggestions} />
          <ScenarioPanel
            onRun={doSweep}
            run={run ? run : (runId ? { id: runId, artifacts: {} } : null)}
            projectId={project?.id || settings.projectId}
            versionId={version?.id || settings.versionId}
            code={code}
            sweepData={sweepData}
          />
        </section>
      </div>

      {settings.debug ? <DebugPanel channel={project?.id || settings.projectId || "adhoc"} /> : null}

      {errors.length ? (<div className="text-xs text-rose-400">{errors.map((e, i) => <div key={i}>Error: {e}</div>)}</div>) : null}
    </main>
  );
}