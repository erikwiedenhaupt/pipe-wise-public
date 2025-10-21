// components/IssueList.jsx
function Sev({ s }) {
    const c = s === "error" ? "text-rose-400" : s === "warn" ? "text-amber-300" : "text-slate-300";
    return <span className={`text-xs ${c}`}>{s}</span>;
  }
  
  export default function IssueList({ issues = [], suggestions = [] }) {
    return (
      <div className="rounded-lg bg-[var(--panel)] border border-slate-700 p-3">
        <div className="mb-2 text-sm text-slate-300">Issues</div>
        {issues.length === 0 ? (
          <div className="text-slate-400 text-sm">No issues reported.</div>
        ) : (
          <ul className="space-y-2">
            {issues.map((it) => (
              <li key={it.id} className="bg-[var(--panel-2)] border border-slate-700 rounded p-2">
                <div className="flex justify-between">
                  <div className="font-medium">{it.description}</div>
                  <Sev s={it.severity} />
                </div>
                {it.component_ref ? <div className="text-xs text-slate-400 mt-1">Component: {it.component_ref}</div> : null}
              </li>
            ))}
          </ul>
        )}
  
        <div className="mt-4 mb-2 text-sm text-slate-300">Suggestions</div>
        {suggestions.length === 0 ? (
          <div className="text-slate-400 text-sm">No suggestions yet.</div>
        ) : (
          <ul className="space-y-2">
            {suggestions.map((s) => (
              <li key={s.id} className="bg-[var(--panel-2)] border border-slate-700 rounded p-2">
                <div className="font-medium">{s.title}</div>
                <div className="text-xs text-slate-400 mt-1">{s.detail}</div>
                {s.actions?.length ? (
                  <div className="mt-2 text-xs text-slate-300">
                    Actions: {s.actions.map((a, i) => <code key={i} className="bg-slate-800 px-1 py-0.5 rounded mx-1">{a.type}</code>)}
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </div>
    );
  }