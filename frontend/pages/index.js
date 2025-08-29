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
import {
  API_BASE,
  createProject, addVersion, validateCode,
  simulate, getRun, getRunKpis, getRunIssues,
  scenarioSweep
} from "../lib/api";

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
  const [errors, setErrors] = useState([]);
  const [settings, setSettings] = useState({
    audience: "expert",
    debug: false,
    autoAdoptRun: true,
    autoApplyCode: true,
    projectId: "",
    versionId: "",
    runId: ""
  });

  // Create a project on first load
  useEffect(() => {
    createProject("dev-project")
      .then(({ project_id }) => setProject({ id: project_id }))
      .catch((e) => setErrors((p) => [...p, String(e)]));
  }, []);

  // Apply settings changes: sync IDs
  const applySettings = (s) => {
    setSettings((prev) => ({ ...prev, ...s }));
    if (s.projectId) setProject({ id: s.projectId });
    if (s.versionId) setVersion({ id: s.versionId });
    if (s.runId) adoptRunId(s.runId);
  };

  const doValidate = async () => {
    setBusy(true);
    setValidation(null);
    try {
      const res = await validateCode(code);
      setValidation(res);
    } catch (e) {
      setErrors((p) => [...p, String(e)]);
    } finally {
      setBusy(false);
    }
  };

  const doSaveVersion = async () => {
    const pid = project?.id || settings.projectId;
    if (!pid) return;
    setBusy(true);
    try {
      const res = await addVersion(pid, code, { label: "v1" });
      setVersion({ id: res.version_id });
    } catch (e) {
      setErrors((p) => [...p, String(e)]);
    } finally {
      setBusy(false);
    }
  };

  const refreshRun = async (rid = runId) => {
    if (!rid) return;
    try {
      const r = await getRun(rid);
      setRun({ id: rid, ...r });
      const k = await getRunKpis(rid);
      setKpis(k);
      const i = await getRunIssues(rid);
      setIssues(i);
    } catch (e) {
      setErrors((p) => [...p, String(e)]);
    }
  };

  const doSimulate = async () => {
    const pid = project?.id || settings.projectId;
    const vid = version?.id || settings.versionId;
    setBusy(true);
    try {
      const res = await simulate({ project_id: pid, version_id: vid, code });
      // Auto-fill settings with IDs so chat always has context
      applySettings({ projectId: pid || "", versionId: vid || "", runId: res.run_id || "" });
      if (settings.autoAdoptRun !== false) setRunId(res.run_id);
      await refreshRun(res.run_id);
    } catch (e) {
      setErrors((p) => [...p, String(e)]);
    } finally {
      setBusy(false);
    }
  };

  const doSweep = async ({ name, values }) => {
    const pid = project?.id || settings.projectId;
    const vid = version?.id || settings.versionId;
    if (!pid) return;
    setBusy(true);
    try {
      const payload = { code_or_version: { project_id: pid, version_id: vid, code }, parameters: [{ name, values }] };
      const res = await scenarioSweep(payload);
      if (settings.autoAdoptRun) setRunId(res.run_id);
      await refreshRun(res.run_id);
    } catch (e) {
      setErrors((p) => [...p, String(e)]);
    } finally {
      setBusy(false);
    }
  };

  const adoptRunId = async (rid) => {
    if (settings.autoAdoptRun) setRunId(rid);
    await refreshRun(rid);
  };

  const onApplyCodeFromChat = (newCode, diff) => {
    if (settings.autoApplyCode) {
      setCode(newCode);
    }
  };

  const debugData = useMemo(
    () => ({
      API_BASE, project, version, runId, run,
      validation, kpis, issues, settings
    }),
    [project, version, runId, run, validation, kpis, issues, settings]
  );

  return (
    <main className="max-w-7xl mx-auto p-4 space-y-4">
      <header className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Pipewise Dev UI</h1>
        <div className="text-xs text-slate-400">API: {API_BASE}</div>
      </header>
      <ProjectInfo
        projectId={project?.id || settings.projectId}
        versionId={version?.id || settings.versionId}
        runId={runId || settings.runId}
      />
      <SettingsPanel
        projectId={project?.id}
        versionId={version?.id}
        runId={runId}
        onApply={applySettings}
      />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <section className="space-y-3">
          <CodeEditor value={code} onChange={setCode} />
          <div className="flex gap-2">
            <button onClick={doValidate} disabled={busy} className="px-3 py-1 rounded bg-[var(--panel)] border border-slate-700 hover:bg-slate-800">Validate</button>
            <button onClick={doSaveVersion} disabled={busy || !(project?.id || settings.projectId)} className="px-3 py-1 rounded bg-[var(--panel)] border border-slate-700 hover:bg-slate-800">Save Version</button>
            <button onClick={doSimulate} disabled={busy} className="px-3 py-1 rounded bg-[var(--accent)] hover:opacity-90">Simulate</button>
          </div>
          {validation ? (
            <div className="rounded bg-[var(--panel)] border border-slate-700 p-3 text-sm">
              <div className="text-slate-300 mb-1">Validation</div>
              <pre className="text-xs text-slate-300 overflow-auto max-h-48">{JSON.stringify(validation, null, 2)}</pre>
            </div>
          ) : null}
          <ScenarioPanel onRun={doSweep} />
        </section>

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
          <KPIGrid kpis={kpis} />
          <IssueList issues={issues.issues} suggestions={issues.suggestions} />
        </section>
      </div>

      <Chat
        projectId={project?.id || settings.projectId}
        versionId={version?.id || settings.versionId}
        runId={runId || settings.runId}
        audience={settings.audience}
        onAdoptRunId={adoptRunId}
        onApplyCode={onApplyCodeFromChat}
      />

      {settings.debug ? <DebugPanel channel={project?.id || settings.projectId || "adhoc"} /> : null}

      {errors.length ? (
        <div className="text-xs text-rose-400">{errors.map((e, i) => <div key={i}>Error: {e}</div>)}</div>
      ) : null}
    </main>
  );
}