// components/Chat.jsx
import { useEffect, useMemo, useRef, useState } from "react";
import { chat as chatApi } from "../lib/api";
import ChatMessage from "./ChatMessage";
import ToolCallList from "./ToolCallList";

export default function Chat({ projectId, versionId, runId, audience = "expert", onAdoptRunId, onApplyCode }) {
  const [messages, setMessages] = useState(() => {
    if (typeof window === "undefined") return [];
    const raw = localStorage.getItem(`pipewise_chat_${projectId || "adhoc"}`);
    return raw ? JSON.parse(raw) : [];
  });
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const listRef = useRef(null);

  useEffect(() => {
    if (typeof window === "undefined") return;
    localStorage.setItem(`pipewise_chat_${projectId || "adhoc"}`, JSON.stringify(messages));
  }, [messages, projectId]);

  useEffect(() => {
    const el = listRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages]);

  const send = async () => {
    const text = input.trim();
    if (!text || busy) return;
    setBusy(true);
    setMessages((m) => [...m, { role: "user", content: text }]);
    setInput("");

    try {
      const res = await chatApi({
        project_id: projectId,
        version_id: versionId,
        run_id: runId,
        message: text,
        context: { history: messages.slice(-8), audience },
      });

      // Try to apply code changes if returned by tools (modify_code or fix_issues)
      if (Array.isArray(res.tool_calls)) {
        for (const t of res.tool_calls) {
          const r = t?.result || {};
          if (r.modified_code && typeof onApplyCode === "function") {
            onApplyCode(r.modified_code, r.diff || "");
          }
        }
      }

      // Adopt run_id if new
      const newRunId = res?.references?.run_id;
      if (newRunId && newRunId !== runId && typeof onAdoptRunId === "function") {
        onAdoptRunId(newRunId);
      }

      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          content: res.assistant || "",
          meta: { tool_calls: res.tool_calls || [], references: res.references || {} },
        },
      ]);
    } catch (e) {
      setMessages((m) => [...m, { role: "assistant", content: `[error] ${String(e)}` }]);
    } finally {
      setBusy(false);
    }
  };

  const canSend = input.trim().length > 0 && !busy;

  return (
    <div className="rounded-lg bg-[var(--panel)] border border-slate-700 p-3">
      <div className="flex items-center justify-between mb-2">
        <div className="text-sm text-slate-300">Chat</div>
        <div className="text-xs text-slate-400">{projectId ? `project:${projectId.slice(0, 6)}…` : "no project"} | {audience}</div>
      </div>

      <div ref={listRef} className="h-72 overflow-auto rounded border border-slate-700 bg-[var(--panel-2)] p-2">
        {messages.length === 0 ? (
          <div className="text-sm text-slate-400">
            Try “/simulate”. Ask “summarize the network” or “fix the problems”.
          </div>
        ) : (
          messages.map((m, i) => (
            <div key={i}>
              <ChatMessage role={m.role} content={m.content} />
              {m.role === "assistant" && m.meta ? (
                <div className="ml-1">
                  <ToolCallList toolCalls={m.meta.tool_calls} references={m.meta.references} />
                  {m.meta?.references?.run_id && onAdoptRunId ? (
                    <div className="mt-2">
                      <button
                        className="px-2 py-0.5 text-xs rounded bg-[var(--accent)] hover:opacity-90"
                        onClick={() => onAdoptRunId(m.meta.references.run_id)}
                      >
                        Adopt run_id: {m.meta.references.run_id}
                      </button>
                    </div>
                  ) : null}
                </div>
              ) : null}
            </div>
          ))
        )}
      </div>

      <div className="mt-2 flex gap-2">
        <input
          className="flex-1 bg-[var(--panel-2)] border border-slate-700 rounded px-2 py-1 text-sm"
          placeholder="Type a message… e.g., summarize or fix"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              if (canSend) send();
            }
          }}
        />
        <button onClick={send} disabled={!canSend} className="px-3 py-1 rounded bg-[var(--accent)] hover:opacity-90 disabled:opacity-50">
          {busy ? "Sending…" : "Send"}
        </button>
      </div>
    </div>
  );
}