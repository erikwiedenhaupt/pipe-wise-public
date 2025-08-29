// frontend/components/ToolCallList.jsx
export default function ToolCallList({ toolCalls = [] }) {
  if (!toolCalls.length) return null;
  return (
    <div className="space-y-3">
      {toolCalls.map((t, i) => (
        <div
          key={i}
          className="rounded-md border border-slate-700 bg-slate-900 text-slate-100"
        >
          <div className="px-3 py-2 border-b border-slate-700 flex items-center justify-between">
            <div className="font-medium">{t.name}</div>
            {t.args && Object.keys(t.args).length > 0 && (
              <div className="text-xs text-slate-400">
                args: {Object.keys(t.args).join(", ")}
              </div>
            )}
          </div>
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
          {t.result?.keys && Array.isArray(t.result.keys) && (
            <div className="px-3 pb-3 text-xs text-slate-400">
              Keys: {t.result.keys.join(", ")}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}