// components/SettingsPanel.jsx
import { useEffect, useState } from "react";

export default function SettingsPanel({ projectId, versionId, runId, onApply }) {
  const [pid, setPid] = useState(projectId || "");
  const [vid, setVid] = useState(versionId || "");
  const [rid, setRid] = useState(runId || "");
  const [audience, setAudience] = useState("expert");
  const [debug, setDebug] = useState(false);
  const [autoAdoptRun, setAutoAdoptRun] = useState(true);
  const [autoApplyCode, setAutoApplyCode] = useState(true);

  useEffect(() => {
    try {
      const saved = JSON.parse(localStorage.getItem("pipewise_settings") || "{}");
      if (saved.pid) setPid(saved.pid);
      if (saved.vid) setVid(saved.vid);
      if (saved.rid) setRid(saved.rid);
      if (saved.audience) setAudience(saved.audience);
      if (typeof saved.debug === "boolean") setDebug(saved.debug);
      if (typeof saved.autoAdoptRun === "boolean") setAutoAdoptRun(saved.autoAdoptRun);
      if (typeof saved.autoApplyCode === "boolean") setAutoApplyCode(saved.autoApplyCode);
    } catch {}
  }, []);

  useEffect(() => {
    localStorage.setItem(
      "pipewise_settings",
      JSON.stringify({ pid, vid, rid, audience, debug, autoAdoptRun, autoApplyCode })
    );
    onApply?.({ projectId: pid, versionId: vid, runId: rid, audience, debug, autoAdoptRun, autoApplyCode });
  }, [pid, vid, rid, audience, debug, autoAdoptRun, autoApplyCode]);

  return (
    <div className="rounded-lg bg-[var(--panel)] border border-slate-700 p-3">
      <div className="text-sm text-slate-300 mb-2">Settings</div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
        <div>
          <label className="text-xs text-slate-400">Project ID</label>
          <input value={pid} onChange={(e) => setPid(e.target.value)} className="w-full bg-[var(--panel-2)] border border-slate-700 rounded px-2 py-1 text-xs" />
        </div>
        <div>
          <label className="text-xs text-slate-400">Version ID</label>
          <input value={vid} onChange={(e) => setVid(e.target.value)} className="w-full bg-[var(--panel-2)] border border-slate-700 rounded px-2 py-1 text-xs" />
        </div>
        <div>
          <label className="text-xs text-slate-400">Run ID</label>
          <input value={rid} onChange={(e) => setRid(e.target.value)} className="w-full bg-[var(--panel-2)] border border-slate-700 rounded px-2 py-1 text-xs" />
        </div>
      </div>

      <div className="mt-3 grid grid-cols-1 md:grid-cols-3 gap-2">
        <div>
          <label className="text-xs text-slate-400">Audience</label>
          <select value={audience} onChange={(e) => setAudience(e.target.value)} className="w-full bg-[var(--panel-2)] border border-slate-700 rounded px-2 py-1 text-xs">
            <option value="expert">Expert</option>
            <option value="novice">Novice</option>
          </select>
        </div>
        <div className="flex items-end gap-2">
          <label className="text-xs text-slate-400">Debug</label>
          <input type="checkbox" checked={debug} onChange={(e) => setDebug(e.target.checked)} />
        </div>
        <div className="flex items-end gap-4">
          <label className="text-xs text-slate-400">Auto adopt run</label>
          <input type="checkbox" checked={autoAdoptRun} onChange={(e) => setAutoAdoptRun(e.target.checked)} />
          <label className="text-xs text-slate-400">Auto apply code</label>
          <input type="checkbox" checked={autoApplyCode} onChange={(e) => setAutoApplyCode(e.target.checked)} />
        </div>
      </div>
    </div>
  );
}