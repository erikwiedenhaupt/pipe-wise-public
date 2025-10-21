// components/SettingsPanel.jsx
import { useEffect, useState } from "react";

export default function SettingsPanel({ projectId, versionId, runId, onApply }) {
  const [open, setOpen] = useState(false);

  // core IDs
  const [pid, setPid] = useState(projectId || "");
  const [vid, setVid] = useState(versionId || "");
  const [rid, setRid] = useState(runId || "");

  // general
  const [audience, setAudience] = useState("expert");
  const [debug, setDebug] = useState(false);
  const [autoAdoptRun, setAutoAdoptRun] = useState(true);
  const [autoApplyCode, setAutoApplyCode] = useState(true);

  // LLM
  const [model, setModel] = useState("gpt-5-mini-2025-08-07");
  const [length, setLength] = useState("standard"); // strict | standard | loose | custom
  const [lengthHint, setLengthHint] = useState("");
  const [tokenLimit, setTokenLimit] = useState(2500); // manual cap (completion tokens); temperature is always 1

  // KPI thresholds (always visible; editable only if profile is custom)
  const [kpiProfile, setKpiProfile] = useState("standard"); // strict | standard | loose | custom
  const [vOkMax, setVOkMax] = useState(15.0);         // velocity_ok_max
  const [vWarnMax, setVWarnMax] = useState(25.0);     // velocity_warn_max
  const [minPFraction, setMinPFraction] = useState(0.95); // min_p_fraction
  const [reMin, setReMin] = useState(2300.0);         // re_min_turbulent

  // Chat UI
  const [showToolDetails, setShowToolDetails] = useState(false);

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

      if (saved.model) setModel(saved.model);
      if (saved.length) setLength(saved.length);
      if (saved.lengthHint) setLengthHint(saved.lengthHint);
      if (typeof saved.tokenLimit === "number") setTokenLimit(saved.tokenLimit);

      if (saved.kpiProfile) setKpiProfile(saved.kpiProfile);
      if (saved.thresholds) {
        if (typeof saved.thresholds.velocity_ok_max === "number") setVOkMax(saved.thresholds.velocity_ok_max);
        if (typeof saved.thresholds.velocity_warn_max === "number") setVWarnMax(saved.thresholds.velocity_warn_max);
        if (typeof saved.thresholds.min_p_fraction === "number") setMinPFraction(saved.thresholds.min_p_fraction);
        if (typeof saved.thresholds.re_min_turbulent === "number") setReMin(saved.thresholds.re_min_turbulent);
      }

      if (typeof saved.showToolDetails === "boolean") setShowToolDetails(saved.showToolDetails);

      const savedOpen = JSON.parse(localStorage.getItem("pipewise_settings_open") || "false");
      setOpen(!!savedOpen);
    } catch {}
  }, []);

  useEffect(() => {
    const payload = {
      pid, vid, rid,
      audience, debug, autoAdoptRun, autoApplyCode,
      model, length, lengthHint, tokenLimit,
      kpiProfile,
      thresholds: { velocity_ok_max: vOkMax, velocity_warn_max: vWarnMax, min_p_fraction: minPFraction, re_min_turbulent: reMin },
      showToolDetails,
    };
    localStorage.setItem("pipewise_settings", JSON.stringify(payload));
    localStorage.setItem("pipewise_settings_open", JSON.stringify(open));
    onApply?.({
      projectId: pid, versionId: vid, runId: rid,
      audience, debug, autoAdoptRun, autoApplyCode,
      model, length, lengthHint, tokenLimit,
      kpiProfile,
      thresholds: payload.thresholds,
      chatShowToolDetails: showToolDetails,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pid, vid, rid, audience, debug, autoAdoptRun, autoApplyCode, model, length, lengthHint, tokenLimit, kpiProfile, vOkMax, vWarnMax, minPFraction, reMin, showToolDetails, open]);

  const applyPreset = (p) => {
    if (p === "strict") { setVOkMax(10); setVWarnMax(15); setMinPFraction(0.98); setReMin(4000); }
    else if (p === "loose") { setVOkMax(20); setVWarnMax(30); setMinPFraction(0.90); setReMin(2000); }
    else if (p === "standard") { setVOkMax(15); setVWarnMax(25); setMinPFraction(0.95); setReMin(2300); }
  };

  const onKpiProfileChange = (val) => {
    setKpiProfile(val);
    applyPreset(val);
  };

  const disabled = kpiProfile !== "custom";

  return (
    <div className="rounded-lg bg-[var(--panel)] border border-slate-700">
      <div className="flex items-center justify-between px-3 py-2 border-b border-slate-700">
        <button className="text-sm text-slate-200" onClick={() => setOpen(v => !v)}>
          Settings {open ? "▲" : "▼"}
        </button>
        <div className="text-xs text-slate-400">
          {pid ? `proj:${pid.slice(0,6)}…` : "no project"}
        </div>
      </div>

      {open && (
        <div className="p-3 space-y-3">
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

          <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
            <div>
              <label className="text-xs text-slate-400">Audience</label>
              <select value={audience} onChange={(e) => setAudience(e.target.value)} className="w-full bg-[var(--panel-2)] border border-slate-700 rounded px-2 py-1 text-xs">
                <option value="expert">Expert</option>
                <option value="novice">Novice</option>
              </select>
            </div>
            <div>
              <label className="text-xs text-slate-400">Model</label>
              <select value={model} onChange={(e) => setModel(e.target.value)} className="w-full bg-[var(--panel-2)] border border-slate-700 rounded px-2 py-1 text-xs">
                <option value="gpt-5-mini-2025-08-07">gpt-5-mini-2025-08-07</option>
                <option value="gpt-5-nano-2025-08-07">gpt-5-nano-2025-08-07</option>
                <option value="gpt-5-2025-08-07">gpt-5-2025-08-07</option>
              </select>
            </div>
            <div>
              <label className="text-xs text-slate-400">Token limit (completion)</label>
              <input type="number" min={200} max={4000} value={tokenLimit} onChange={(e) => setTokenLimit(parseInt(e.target.value || "2500", 10))} className="w-full bg-[var(--panel-2)] border border-slate-700 rounded px-2 py-1 text-xs" />
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
            <div>
              <label className="text-xs text-slate-400">Length preset</label>
              <select value={length} onChange={(e) => setLength(e.target.value)} className="w-full bg-[var(--panel-2)] border border-slate-700 rounded px-2 py-1 text-xs">
                <option value="strict">Strict (short)</option>
                <option value="standard">Standard</option>
                <option value="loose">Loose (longer)</option>
                <option value="custom">Custom</option>
              </select>
            </div>
            {length === "custom" && (
              <div className="md:col-span-2">
                <label className="text-xs text-slate-400">Custom length hint</label>
                <input value={lengthHint} onChange={(e) => setLengthHint(e.target.value)} placeholder="e.g., 3 bullets; ≤ 100 words" className="w-full bg-[var(--panel-2)] border border-slate-700 rounded px-2 py-1 text-xs" />
              </div>
            )}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-5 gap-2">
            <div className="md:col-span-1">
              <label className="text-xs text-slate-400">KPI profile</label>
              <select value={kpiProfile} onChange={(e) => onKpiProfileChange(e.target.value)} className="w-full bg-[var(--panel-2)] border border-slate-700 rounded px-2 py-1 text-xs">
                <option value="strict">Strict</option>
                <option value="standard">Standard</option>
                <option value="loose">Loose</option>
                <option value="custom">Custom</option>
              </select>
              <div className="text-[11px] text-slate-400 mt-1">
                Preset updates fields; editing is only enabled for Custom.
              </div>
            </div>

            <div>
              <label className="text-xs text-slate-400">Velocity OK max (m/s)</label>
              <input type="number" step="0.1" value={vOkMax} onChange={(e) => setVOkMax(parseFloat(e.target.value || "15"))} disabled={disabled} className={`w-full bg-[var(--panel-2)] border border-slate-700 rounded px-2 py-1 text-xs ${disabled ? "opacity-60" : ""}`} />
            </div>
            <div>
              <label className="text-xs text-slate-400">Velocity WARN max (m/s)</label>
              <input type="number" step="0.1" value={vWarnMax} onChange={(e) => setVWarnMax(parseFloat(e.target.value || "25"))} disabled={disabled} className={`w-full bg-[var(--panel-2)] border border-slate-700 rounded px-2 py-1 text-xs ${disabled ? "opacity-60" : ""}`} />
            </div>
            <div>
              <label className="text-xs text-slate-400">Min p fraction of pn</label>
              <input type="number" step="0.01" value={minPFraction} onChange={(e) => setMinPFraction(parseFloat(e.target.value || "0.95"))} disabled={disabled} className={`w-full bg-[var(--panel-2)] border border-slate-700 rounded px-2 py-1 text-xs ${disabled ? "opacity-60" : ""}`} />
            </div>
            <div>
              <label className="text-xs text-slate-400">Re min turbulent</label>
              <input type="number" step="1" value={reMin} onChange={(e) => setReMin(parseFloat(e.target.value || "2300"))} disabled={disabled} className={`w-full bg-[var(--panel-2)] border border-slate-700 rounded px-2 py-1 text-xs ${disabled ? "opacity-60" : ""}`} />
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
            <div className="flex items-center gap-2">
              <label className="text-xs text-slate-400">Debug panel</label>
              <input type="checkbox" checked={debug} onChange={(e) => setDebug(e.target.checked)} />
            </div>
            <div className="flex items-center gap-2">
              <label className="text-xs text-slate-400">Auto adopt run</label>
              <input type="checkbox" checked={autoAdoptRun} onChange={(e) => setAutoAdoptRun(e.target.checked)} />
            </div>
            <div className="flex items-center gap-2">
              <label className="text-xs text-slate-400">Auto apply code</label>
              <input type="checkbox" checked={autoApplyCode} onChange={(e) => setAutoApplyCode(e.target.checked)} />
            </div>
            <div className="flex items-center gap-2">
              <label className="text-xs text-slate-400">Show tool details in chat</label>
              <input type="checkbox" checked={showToolDetails} onChange={(e) => setShowToolDetails(e.target.checked)} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}