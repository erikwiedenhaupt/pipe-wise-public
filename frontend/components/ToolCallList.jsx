// frontend/components/ToolCallList.jsx
export default function ToolCallList({ toolCalls = [], collapsedDefault = true }) {
  if (!toolCalls.length) return null;
  return (
    <div className="space-y-3">
      {toolCalls.map((t, i) => {
        const summary = `${t.name}${t.result?.keys ? ` · keys: ${t.result.keys.join(", ")}` : ""}`;
        return (
          <details key={i} open={!collapsedDefault} className="rounded-md border border-slate-700 bg-slate-900 text-slate-100">
            <summary className="px-3 py-2 border-b border-slate-700 cursor-pointer flex items-center justify-between">
              <div className="font-medium text-sm">{summary}</div>
              {t.args && Object.keys(t.args).length > 0 && (
                <div className="text-[11px] text-slate-400">args: {Object.keys(t.args).join(", ")}</div>
              )}
            </summary>
            {t.args && (
              <pre className="m-3 rounded bg-slate-800 text-slate-100 p-2 overflow-x-auto text-xs font-mono">
                {JSON.stringify(t.args, null, 2)}
              </pre>
            )}
            {t.result && (
              <pre className="m-3 rounded bg-slate-800 text-slate-100 p-2 overflow-x-auto text-xs font-mono">
                {JSON.stringify(t.result, null, 2)}
              </pre>
            )}
          </details>
        );
      })}
    </div>
  );
}