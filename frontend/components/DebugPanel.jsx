// components/DebugPanel.jsx
import { useEffect, useMemo, useRef, useState } from "react";

function joinPath(a, b) {
  return (a.replace(/\/+$/, "") + "/" + b.replace(/^\/+/, ""));
}

// replace toWsUrlPath in both files
function toWsUrlPath(path) {
  const base = process.env.NEXT_PUBLIC_API_BASE || "/api";
  const origin = typeof window !== "undefined" ? window.location.origin : "http://localhost:3000";
  const u = new URL(base, origin);
  u.protocol = u.protocol === "https:" ? "wss:" : "ws:";
  u.pathname = (u.pathname.replace(/\/+$/, "") || "") + (path.startsWith("/") ? path : `/${path}`);
  u.search = ""; u.hash = "";
  return u.toString();
}

function EventRow({ ev }) {
  const type = ev?.event?.type || "unknown";
  const at = ev?.at ? new Date(ev.at).toLocaleTimeString() : "";
  const badge =
    type.startsWith("tool") ? "bg-amber-500/20 text-amber-300"
      : type.startsWith("llm") ? "bg-sky-500/20 text-sky-300"
      : type.startsWith("chat") ? "bg-emerald-500/20 text-emerald-300"
      : "bg-slate-500/20 text-slate-300";
  const detail = ev?.event || {};
  return (
    <div className="px-3 py-2 border-b border-slate-800">
      <div className="flex items-center gap-2">
        <span className={`text-[10px] px-2 py-0.5 rounded ${badge}`}>{type}</span>
        <span className="text-xs text-slate-400">{at}</span>
      </div>
      {detail.content_preview && (
        <div className="mt-1 text-xs text-slate-200 whitespace-pre-wrap">
          {detail.content_preview}
        </div>
      )}
      <details className="mt-1">
        <summary className="text-xs text-slate-400 cursor-pointer">details</summary>
        <pre className="text-[11px] mt-1 p-2 rounded bg-slate-800 text-slate-100 overflow-x-auto">
          {JSON.stringify(detail, null, 2)}
        </pre>
      </details>
    </div>
  );
}

export default function DebugPanel({ channel, initial = null }) {
  const [open, setOpen] = useState(false);
  const [paused, setPaused] = useState(false);
  const [events, setEvents] = useState(initial ? [{ at: null, event: initial }] : []);
  const [status, setStatus] = useState("disconnected");
  const wsRef = useRef(null);
  const bottomRef = useRef(null);

  const wsUrl = useMemo(
    () => toWsUrlPath(`/chat/ws/debug/${encodeURIComponent(channel || "adhoc")}`),
    [channel]
  );

  useEffect(() => {
    if (!channel) return;
    let stop = false;
    let retryMs = 1000;

    const connect = () => {
      if (stop) return;
      setStatus("connecting");
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        setStatus("connected");
        retryMs = 1000;
      };

      // components/DebugPanel.jsx (patch inside ws.onmessage)
    ws.onmessage = (evt) => {
      try {
        const msg = JSON.parse(evt.data);
        // forward run switch events to the app
        if (msg?.event?.type === 'ui.switch_run' && msg?.event?.run_id) {
          window.dispatchEvent(
            new CustomEvent('pipewise:switch-run', { detail: { runId: msg.event.run_id } })
          );
        }
        if (!paused) {
          setEvents((prev) => [...prev, msg].slice(-500));
        }
      } catch {
        // ignore
      }
    };

      ws.onclose = () => {
        setStatus("disconnected");
        wsRef.current = null;
        if (!stop) {
          setTimeout(connect, retryMs);
          retryMs = Math.min(retryMs * 2, 10000);
        }
      };

      ws.onerror = () => {
        // allow close handler to handle reconnection
      };
    };

    connect();
    return () => {
      stop = true;
      try { wsRef.current?.close(); } catch {}
      wsRef.current = null;
    };
  }, [wsUrl, channel, paused]);

  useEffect(() => {
    if (!paused && bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [events, paused]);

  const clear = () => setEvents([]);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(JSON.stringify(events, null, 2));
    } catch {}
  };

  return (
    <div className="rounded-lg bg-slate-900 border border-slate-700">
      <div className="flex items-center justify-between px-3 py-2 border-b border-slate-700">
        <button
          className="text-sm font-medium text-slate-200"
          onClick={() => setOpen((v) => !v)}
        >
          Debug {open ? "▲" : "▼"}
        </button>
        <div className="flex items-center gap-2">
          <span className={`text-[10px] px-2 py-0.5 rounded ${
            status === "connected" ? "bg-emerald-500/20 text-emerald-300" :
            status === "connecting" ? "bg-yellow-500/20 text-yellow-300" :
            "bg-slate-600/20 text-slate-300"
          }`}>
            {status}
          </span>
          <button className="text-xs px-2 py-1 rounded bg-slate-800 border border-slate-700 text-slate-200"
            onClick={() => setPaused((p) => !p)}>
            {paused ? "Resume" : "Pause"}
          </button>
          <button className="text-xs px-2 py-1 rounded bg-slate-800 border border-slate-700 text-slate-200"
            onClick={clear}>
            Clear
          </button>
          <button className="text-xs px-2 py-1 rounded bg-slate-800 border border-slate-700 text-slate-200"
            onClick={copy}>
            Copy
          </button>
        </div>
      </div>
      {open && (
        <div className="max-h-72 overflow-auto">
          {events.length === 0 ? (
            <div className="px-3 py-4 text-sm text-slate-400">No events yet.</div>
          ) : (
            events.map((ev, idx) => <EventRow key={idx} ev={ev} />)
          )}
          <div ref={bottomRef} />
        </div>
      )}
    </div>
  );
}