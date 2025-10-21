export default function RunHeader({ run, onRefresh, onDelete }) {
  if (!run) return null;
  const statusColor = {
    succeeded: "text-[var(--ok)]",
    success: "text-[var(--ok)]",
    running: "text-blue-400",
    queued: "text-blue-300",
    failed: "text-[var(--fail)]",
    error: "text-[var(--fail)]",
  }[String(run.status || "").toLowerCase()] || "text-slate-300";

  const failure = (run.artifacts && run.artifacts.failure) || {};
  const reason = failure.reason;
  const tips = Array.isArray(failure.tips) ? failure.tips : [];
  const codeLine = failure.code_line;
  const codeMsg = failure.code_message;

  return (
    <div className="flex items-center justify-between rounded-lg bg-[var(--panel)] p-3 border border-slate-700">
      <div className="min-w-0">
        <div className="text-sm text-slate-400">Run</div>
        <div className="text-lg font-semibold">id: {run.id || "(N/A)"} <span className={`${statusColor}`}>[{run.status}]</span></div>

        {String(run.status || "").toLowerCase() === "failed" && (reason || tips.length > 0 || codeLine) ? (
          <div className="mt-2">
            {codeLine ? <div className="text-sm text-amber-300">User code error line: {codeLine}{codeMsg ? ` · ${codeMsg}` : ""}</div> : null}
            {reason ? <div className="text-sm text-rose-300">Failure reason: {reason}</div> : null}
            {tips.length > 0 ? (
              <ul className="list-disc pl-5 mt-1 text-xs text-slate-200">
                {tips.map((t, i) => <li key={i} className="mb-0.5">{t}</li>)}
              </ul>
            ) : null}
          </div>
        ) : null}

        {run.logs ? <div className="mt-2 text-xs text-slate-400 line-clamp-3">{run.logs}</div> : null}
      </div>
      <div className="flex-shrink-0 flex gap-2">
        <button onClick={onRefresh} className="px-3 py-1 rounded bg-[var(--accent)] hover:opacity-90">Refresh</button>
        <button onClick={onDelete} className="px-3 py-1 rounded bg-[var(--panel-2)] border border-slate-600 hover:bg-slate-800">Delete</button>
      </div>
    </div>
  );
}