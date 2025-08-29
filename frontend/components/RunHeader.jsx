// components/RunHeader.jsx
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
  
    return (
      <div className="flex items-center justify-between rounded-lg bg-[var(--panel)] p-3 border border-slate-700">
        <div>
          <div className="text-sm text-slate-400">Run</div>
          <div className="text-lg font-semibold">id: {run.id || "(N/A)"} <span className={`${statusColor}`}>[{run.status}]</span></div>
          {run.logs ? <div className="mt-1 text-xs text-slate-400 line-clamp-2">{run.logs}</div> : null}
        </div>
        <div className="flex gap-2">
          <button onClick={onRefresh} className="px-3 py-1 rounded bg-[var(--accent)] hover:opacity-90">Refresh</button>
          <button onClick={onDelete} className="px-3 py-1 rounded bg-[var(--panel-2)] border border-slate-600 hover:bg-slate-800">Delete</button>
        </div>
      </div>
    );
  }