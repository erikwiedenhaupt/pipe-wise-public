// components/InteractionGraph.jsx
import { useEffect, useMemo, useRef, useState } from "react";

function joinPath(a, b) { return (a.replace(/\/+$/, "") + "/" + b.replace(/^\/+/, "")); }
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

// Role colors: user (blue), agents (green), tools (grey)
const ROLE_COLOR = { user: "#2563eb", agent: "#10b981", tool: "#64748b" };
const LABEL_COLORS = {
  REQUEST: "#2563eb", CALL: "#10b981",
  OK: "#22c55e", FAIL: "#ef4444",
  KPIS: "#ef4444", ISSUES: "#f97316",
  ANSWER: "#22d3ee", RUN: "#06b6d4", DATA: "#60a5fa",
};

export default function InteractionGraph({ channel }) {
  const canvasRef = useRef(null);
  const [status, setStatus] = useState("disconnected");
  const wsRef = useRef(null);

  const nodesRef = useRef({});
  const edgesRef = useRef({});
  const payloadsRef = useRef([]);   // active moving dots
  const timelineRef = useRef([]);   // frames queue: each frame is array of steps
  const baseSpeedRef = useRef(0.0072);   // doubled baseline speed
  const speedMultRef = useRef(1.00);     // slider sets multiplier, default 100%
  const [speedPct, setSpeedPct] = useState(100);

  const layoutRef = useRef({ width: 1100, height: 520 });
  const animRef = useRef(null);
  const pausedRef = useRef(false);

  // Spinners
  const llmSpinRef = useRef({ active: false, angle: 0 });
  const simSpinRef = useRef({ active: false, angle: 0 });

  const wsUrl = useMemo(
    () => toWsUrlPath(`/chat/ws/debug/${encodeURIComponent(channel || "adhoc")}`),
    [channel]
  );

  const setNode = (id, label, x, y, r, role) => { nodesRef.current[id] = { id, label, x, y, r, role }; };
  const ensureEdge = (from, to) => { const k = `${from}->${to}`; if (!edgesRef.current[k]) edgesRef.current[k] = { from, to, color: "#64748b", w: 2 }; };
  const ensureNode = (id, label, role = "tool") => { if (!nodesRef.current[id]) { const { width, height } = layoutRef.current; setNode(id, label || id, width / 2, height / 2, 22, role); } };

  const initNodes = () => {
    const { width, height } = layoutRef.current;
    const cx = width / 2, cy = height / 2;

    setNode("USER", "User", 110, cy, 26, "user");
    setNode("LLM", "LLM", cx - 220, cy - 10, 30, "agent");
    setNode("SIMULATOR", "Simulator", cx + 160, cy, 30, "agent");

    setNode("VALIDATOR", "Validator", cx + 160, cy - 160, 22, "tool");
    setNode("SANDBOX", "Sandbox", cx + 320, cy - 10, 22, "agent");
    setNode("STORAGE", "Storage", width - 120, cy - 160, 22, "tool");

    setNode("KPIs", "get_kpis", cx + 40, cy + 180, 22, "tool");
    setNode("ISSUES", "get_issues", cx + 260, cy + 180, 22, "tool");
    setNode("PHYSICS", "Physics Engine", cx + 150, cy + 120, 24, "agent");
    setNode("MODIFIER", "Modifier", cx - 120, cy + 180, 22, "agent");
    setNode("COST_ENGINE", "Cost Engine", cx + 420, cy + 120, 22, "agent");
    setNode("TOOL_GENERATOR", "Tool Generator", cx - 360, cy + 120, 22, "agent");

    // Pre-wired edges (diagram)
    ensureEdge("USER", "LLM"); ensureEdge("USER", "SIMULATOR"); ensureEdge("USER", "STORAGE");
    ensureEdge("LLM", "STORAGE"); ensureEdge("STORAGE", "LLM"); ensureEdge("LLM", "SIMULATOR"); ensureEdge("LLM", "USER");
    ensureEdge("LLM", "MODIFIER");
    ensureEdge("SIMULATOR", "VALIDATOR"); ensureEdge("SIMULATOR", "SANDBOX");
    ensureEdge("SIMULATOR", "KPIs"); ensureEdge("SIMULATOR", "ISSUES"); ensureEdge("SIMULATOR", "MODIFIER");
    // Physics: KPIs/ISSUES → PHYSICS → SIMULATOR
    ensureEdge("KPIs", "PHYSICS"); ensureEdge("ISSUES", "PHYSICS"); ensureEdge("PHYSICS", "SIMULATOR");

    // Tool Generator + Cost engine visibly connected
    ensureEdge("TOOL_GENERATOR", "SIMULATOR"); ensureEdge("TOOL_GENERATOR", "STORAGE");
    ensureEdge("SIMULATOR", "TOOL_GENERATOR"); ensureEdge("STORAGE", "TOOL_GENERATOR");
    ensureEdge("COST_ENGINE", "SIMULATOR"); ensureEdge("COST_ENGINE", "STORAGE");
  };

  const queueFrame = (steps) => { timelineRef.current.push(steps); };
  const addPayload = ({ from, to, label, color, bubble }) => {
    payloadsRef.current.push({ from, to, t: 0, label, color, bubble: bubble || null, trail: [] });
    if (payloadsRef.current.length > 300) payloadsRef.current.shift();
  };
  const maybeStartNextFrame = () => {
    const active = payloadsRef.current.some((p) => p.t < 1);
    if (!active && timelineRef.current.length > 0) {
      const next = timelineRef.current.shift();
      next.forEach(addPayload);
    }
  };
  const abortGraph = () => {
    timelineRef.current = [];
    payloadsRef.current = [];
    llmSpinRef.current.active = false;
    simSpinRef.current.active = false;
  };

  const drawTag = (ctx, x, y, text, fill = "#334155", fg = "#e2e8f0") => {
    if (!text) return;
    ctx.font = "11px sans-serif";
    const w = ctx.measureText(text).width + 12;
    ctx.fillStyle = fill;
    if (ctx.roundRect) { ctx.beginPath(); ctx.roundRect(x - w / 2, y - 8, w, 16, 6); ctx.fill(); }
    else { ctx.fillRect(x - w / 2, y - 8, w, 16); }
    ctx.fillStyle = fg; ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillText(text, x, y);
  };

  const drawSpinner = (ctx, node, angle, color) => {
    if (!node) return;
    ctx.save();
    ctx.strokeStyle = color; ctx.lineWidth = 3;
    const r = node.r + 8;
    ctx.beginPath();
    ctx.arc(node.x, node.y, r, angle, angle + Math.PI * 0.75); // rotating arc
    ctx.stroke();
    ctx.restore();
  };

  const draw = () => {
    const canvas = canvasRef.current; if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const { width, height } = layoutRef.current;
    ctx.clearRect(0, 0, width, height);

    // Edges
    Object.values(edgesRef.current).forEach((e) => {
      const a = nodesRef.current[e.from], b = nodesRef.current[e.to]; if (!a || !b) return;
      ctx.strokeStyle = e.color; ctx.lineWidth = e.w || 2;
      ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
    });

    // Payloads
    payloadsRef.current.forEach((p) => {
      const a = nodesRef.current[p.from], b = nodesRef.current[p.to]; if (!a || !b) return;
      const t = Math.max(0, Math.min(1, p.t));
      const x = a.x + (b.x - a.x) * t, y = a.y + (b.y - a.y) * t;

      p.trail.push({ x, y, alpha: 0.6 }); if (p.trail.length > 12) p.trail.shift();
      p.trail.forEach((c, i) => {
        ctx.fillStyle = `rgba(148,163,184,${Math.max(0, c.alpha - i * 0.05)})`;
        ctx.beginPath(); ctx.arc(c.x, c.y, 2.2, 0, 2 * Math.PI); ctx.fill();
      });

      ctx.save(); ctx.shadowColor = p.color; ctx.shadowBlur = 12; ctx.fillStyle = p.color;
      ctx.beginPath(); ctx.arc(x, y, 8, 0, 2 * Math.PI); ctx.fill(); ctx.restore();

      const tagFill = LABEL_COLORS[p.label] || "#475569";
      const fg = p.label === "FAIL" ? "#fff1f2" : "#e2e8f0";
      drawTag(ctx, x, y - 18, p.label, tagFill, fg);
      if (p.bubble && p.bubble.text) drawTag(ctx, x + 16, y + 18, p.bubble.text, p.bubble.color || "#7f1d1d", "#fecaca");
    });

    // Nodes
    Object.values(nodesRef.current).forEach((n) => {
      const fill = ROLE_COLOR[n.role] || "#64748b";
      ctx.fillStyle = fill; ctx.beginPath(); ctx.arc(n.x, n.y, n.r, 0, 2 * Math.PI); ctx.fill();
      ctx.strokeStyle = "#334155"; ctx.lineWidth = 2; ctx.stroke();
      ctx.fillStyle = "#e2e8f0"; ctx.font = "12px sans-serif"; ctx.textAlign = "center";
      ctx.fillText(n.label, n.x, n.y - n.r - 6);
    });

    // Spinners (thinking)
    if (llmSpinRef.current.active) {
      llmSpinRef.current.angle += 0.12;
      drawSpinner(ctx, nodesRef.current["LLM"], llmSpinRef.current.angle, "#22d3ee");
    }
    if (simSpinRef.current.active) {
      simSpinRef.current.angle += 0.12;
      drawSpinner(ctx, nodesRef.current["SIMULATOR"], simSpinRef.current.angle, "#10b981");
    }
  };

  const tick = () => {
    if (!pausedRef.current) {
      const step = baseSpeedRef.current * speedMultRef.current;
      payloadsRef.current.forEach((p) => { p.t += step; });
      payloadsRef.current = payloadsRef.current.filter((p) => p.t < 1.05);
      maybeStartNextFrame();
    }
    draw();
    animRef.current = requestAnimationFrame(tick);
  };

  // Dragging
  useEffect(() => {
    const canvas = canvasRef.current; if (!canvas) return;
    let dragging = null;
    const pos = (ev) => {
      const rect = canvas.getBoundingClientRect();
      const x = (ev.touches ? ev.touches[0].clientX : ev.clientX) - rect.left;
      const y = (ev.touches ? ev.touches[0].clientY : ev.clientY) - rect.top;
      return { x, y };
    };
    const onDown = (ev) => {
      const { x, y } = pos(ev);
      const nodes = Object.values(nodesRef.current);
      for (let i = nodes.length - 1; i >= 0; i--) {
        const n = nodes[i];
        const dx = x - n.x, dy = y - n.y;
        if (Math.hypot(dx, dy) <= n.r + 4) { dragging = { id: n.id, dx, dy }; ev.preventDefault(); break; }
      }
    };
    const onMove = (ev) => {
      if (!dragging) return;
      const { x, y } = pos(ev);
      const n = nodesRef.current[dragging.id];
      if (n) { n.x = x - dragging.dx; n.y = y - dragging.dy; }
    };
    const onUp = () => { dragging = null; };
    canvas.addEventListener("mousedown", onDown);
    canvas.addEventListener("mousemove", onMove);
    canvas.addEventListener("mouseup", onUp);
    canvas.addEventListener("mouseleave", onUp);
    canvas.addEventListener("touchstart", onDown, { passive: false });
    canvas.addEventListener("touchmove", onMove, { passive: false });
    canvas.addEventListener("touchend", onUp);
    return () => {
      canvas.removeEventListener("mousedown", onDown);
      canvas.removeEventListener("mousemove", onMove);
      canvas.removeEventListener("mouseup", onUp);
      canvas.removeEventListener("mouseleave", onUp);
      canvas.removeEventListener("touchstart", onDown);
      canvas.removeEventListener("touchmove", onMove);
      canvas.removeEventListener("touchend", onUp);
    };
  }, []);

  // Boot
  useEffect(() => {
    initNodes(); draw();
    animRef.current = requestAnimationFrame(tick);
    return () => animRef.current && cancelAnimationFrame(animRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // WS → frames (live from debug; no heuristics)
  useEffect(() => {
    if (!channel) return;
    let stop = false, retryMs = 1000;

    const connect = () => {
      if (stop) return;
      setStatus("connecting");
      const ws = new WebSocket(wsUrl); wsRef.current = ws;

      ws.onopen = () => { setStatus("connected"); retryMs = 1000; };

      // components/InteractionGraph.jsx – inside ws.onmessage

ws.onmessage = (evt) => {
  try {
    const msg = JSON.parse(evt.data);
    const ev = msg?.event || {};
    const typ = ev?.type || "";

    if (typ === "chat.start") {
      abortGraph();
      queueFrame([{ from: "USER", to: "LLM", label: "REQUEST", color: LABEL_COLORS.REQUEST }]);
      // Always show LLM ↔ Modifier edge (static connection)
      queueFrame([{ from: "LLM", to: "STORAGE", label: "LINK", color: LABEL_COLORS.CALL }]);

    } else if (typ === "llm.call") {
      llmSpinRef.current.active = true;

    } else if (typ === "tool.call") {
      const name = (ev?.name || "").toLowerCase();

      // Unified simulate flow
      if (name.startsWith("simulate")) {
        llmSpinRef.current.active = false;
        simSpinRef.current.active = true;
        queueFrame([
          { from: "LLM", to: "SIMULATOR", label: "CALL", color: LABEL_COLORS.CALL },
          { from: "SIMULATOR", to: "VALIDATOR", label: "CALL", color: LABEL_COLORS.CALL },
          { from: "VALIDATOR", to: "SANDBOX", label: "CALL", color: LABEL_COLORS.CALL },
          { from: "SANDBOX", to: "SIMULATOR", label: "DATA", color: LABEL_COLORS.DATA },
          { from: "SIMULATOR", to: "PHYSICS", label: "CALL", color: LABEL_COLORS.CALL },
          { from: "PHYSICS", to: "SIMULATOR", label: "DATA", color: LABEL_COLORS.DATA },
          { from: "SIMULATOR", to: "KPIs", label: "CALL", color: LABEL_COLORS.CALL, bubble: { text: "kpis", color: LABEL_COLORS.KPIS } },
          { from: "SIMULATOR", to: "ISSUES", label: "CALL", color: LABEL_COLORS.CALL, bubble: { text: "issues", color: LABEL_COLORS.ISSUES } },
        ]);

      } else if (name === "get_kpis") {
        simSpinRef.current.active = true;
        queueFrame([{ from: "LLM", to: "SIMULATOR", label: "CALL", color: LABEL_COLORS.CALL }]);
        queueFrame([{ from: "SIMULATOR", to: "KPIs", label: "CALL", color: LABEL_COLORS.CALL, bubble: { text: "kpis", color: LABEL_COLORS.KPIS } }]);

      } else if (name === "get_issues") {
        simSpinRef.current.active = true;
        queueFrame([{ from: "LLM", to: "SIMULATOR", label: "CALL", color: LABEL_COLORS.CALL }]);
        queueFrame([{ from: "SIMULATOR", to: "ISSUES", label: "CALL", color: LABEL_COLORS.CALL, bubble: { text: "issues", color: LABEL_COLORS.ISSUES } }]);

      } else if (name === "validate_code") {
        queueFrame([{ from: "LLM", to: "VALIDATOR", label: "CALL", color: LABEL_COLORS.CALL }]);

      } else if (name === "modify_code" || name === "fix_issues") {
        simSpinRef.current.active = true;
        // Pre-check flow before Modifier
        queueFrame([{ from: "LLM", to: "SIMULATOR", label: "CALL", color: LABEL_COLORS.CALL }]);
        queueFrame([{ from: "SIMULATOR", to: "KPIs", label: "CALL", color: LABEL_COLORS.CALL, bubble: { text: "kpis", color: LABEL_COLORS.KPIS } }]);
        queueFrame([{ from: "KPIs", to: "PHYSICS", label: "DATA", color: LABEL_COLORS.DATA }]);
        queueFrame([{ from: "PHYSICS", to: "SIMULATOR", label: "DATA", color: LABEL_COLORS.DATA }]);
        

        queueFrame([{ from: "SIMULATOR", to: "ISSUES", label: "CALL", color: LABEL_COLORS.CALL, bubble: { text: "issues", color: LABEL_COLORS.ISSUES } }]);
        queueFrame([{ from: "ISSUES", to: "PHYSICS", label: "DATA", color: LABEL_COLORS.DATA }]);
        queueFrame([{ from: "PHYSICS", to: "SIMULATOR", label: "DATA", color: LABEL_COLORS.DATA }]);
        queueFrame([{ from: "SIMULATOR", to: "MODIFIER", label: "DATA", color: LABEL_COLORS.DATA }]);
        queueFrame([{ from: "MODIFIER", to: "SIMULATOR", label: "CALL", color: LABEL_COLORS.CALL }]);
        queueFrame([{ from: "SIMULATOR", to: "SANDBOX", label: "CALL", color: LABEL_COLORS.CALL }]);
        queueFrame([{ from: "SANDBOX", to: "SIMULATOR", label: "RESULTS", color: LABEL_COLORS.DATA }]);
        queueFrame([{ from: "SIMULATOR", to: "KPIs", label: "CALL", color: LABEL_COLORS.CALL, bubble: { text: "kpis", color: LABEL_COLORS.KPIS } }]);
        queueFrame([{ from: "KPIs", to: "PHYSICS", label: "DATA", color: LABEL_COLORS.DATA }]);
        queueFrame([{ from: "PHYSICS", to: "SIMULATOR", label: "DATA", color: LABEL_COLORS.DATA }]);
        

        queueFrame([{ from: "SIMULATOR", to: "ISSUES", label: "CALL", color: LABEL_COLORS.CALL, bubble: { text: "issues", color: LABEL_COLORS.ISSUES } }]);
        queueFrame([{ from: "ISSUES", to: "PHYSICS", label: "DATA", color: LABEL_COLORS.DATA }]);
        queueFrame([{ from: "PHYSICS", to: "SIMULATOR", label: "DATA", color: LABEL_COLORS.DATA }]);
        queueFrame([{ from: "SIMULATOR", to: "MODIFIER", label: "OK", color: LABEL_COLORS.OK }]);
        queueFrame([{ from: "MODIFIER", to: "LLM", label: "OK", color: LABEL_COLORS.OK }]);

        
        

      } else if (name === "estimate_cost") {
        queueFrame([{ from: "LLM", to: "SIMULATOR", label: "CALL", color: LABEL_COLORS.CALL }]);
        queueFrame([{ from: "LLM", to: "COST_ENGINE", label: "CALL", color: LABEL_COLORS.CALL }]);
        queueFrame([{ from: "COST_ENGINE", to: "STORAGE", label: "CALL", color: LABEL_COLORS.CALL }]);
        queueFrame([{ from: "STORAGE", to: "COST_ENGINE", label: "DATA", color: LABEL_COLORS.DATA }]);
        queueFrame([{ from: "COST_ENGINE", to: "SIMULATOR", label: "DATA", color: LABEL_COLORS.DATA }]);
        queueFrame([{ from: "SIMULATOR", to: "LLM", label: "DATA", color: LABEL_COLORS.DATA }]);
        

      } else if (name === "list_tools") {
        queueFrame([{ from: "LLM", to: "TOOL_GENERATOR", label: "CALL", color: LABEL_COLORS.CALL }]);
        queueFrame([{ from: "LLM", to: "STORAGE", label: "CALL", color: LABEL_COLORS.CALL }]);
        queueFrame([{ from: "STORAGE", to: "LLM", label: "DATA", color: LABEL_COLORS.DATA }]);
      }

    } else if (typ === "tool.result") {
      const name = (ev?.name || "").toLowerCase();

      if (name === "validate_code") {
        const ok = ev.valid !== false;
        queueFrame([{ from: "VALIDATOR", to: "LLM", label: ok ? "OK" : "FAIL", color: ok ? LABEL_COLORS.OK : LABEL_COLORS.FAIL }]);

      } else if (name.startsWith("simulate")) {
        simSpinRef.current.active = false;
        const ok = ev.ok !== false;
        queueFrame([{ from: "SIMULATOR", to: "LLM", label: ok ? "OK" : "FAIL", color: ok ? LABEL_COLORS.OK : LABEL_COLORS.FAIL }]);

      } else if (name === "get_kpis") {
        queueFrame([{ from: "KPIs", to: "PHYSICS", label: "DATA", color: LABEL_COLORS.DATA }]);
        queueFrame([{ from: "PHYSICS", to: "SIMULATOR", label: "DATA", color: LABEL_COLORS.DATA }]);
        queueFrame([{ from: "SIMULATOR", to: "LLM", label: "OK", color: LABEL_COLORS.OK }]);
        simSpinRef.current.active = false;

      } else if (name === "get_issues") {
        queueFrame([{ from: "ISSUES", to: "PHYSICS", label: "DATA", color: LABEL_COLORS.DATA }]);
        queueFrame([{ from: "PHYSICS", to: "SIMULATOR", label: "DATA", color: LABEL_COLORS.DATA }]);
        queueFrame([{ from: "SIMULATOR", to: "LLM", label: "OK", color: LABEL_COLORS.OK }]);
        simSpinRef.current.active = false;

      } else if (name === "modify_code" || name === "fix_issues") {
        queueFrame([{ from: "MODIFIER", to: "SIMULATOR", label: "CALL", color: LABEL_COLORS.CALL }]);
        queueFrame([{ from: "SIMULATOR", to: "KPIs", label: "CALL", color: LABEL_COLORS.CALL, bubble: { text: "kpis", color: LABEL_COLORS.KPIS } }]);
        queueFrame([{ from: "KPIs", to: "PHYSICS", label: "DATA", color: LABEL_COLORS.DATA }]);
        queueFrame([{ from: "PHYSICS", to: "SIMULATOR", label: "DATA", color: LABEL_COLORS.DATA }]);
        queueFrame([{ from: "SIMULATOR", to: "ISSUES", label: "CALL", color: LABEL_COLORS.CALL, bubble: { text: "issues", color: LABEL_COLORS.ISSUES } }]);
        queueFrame([{ from: "ISSUES", to: "PHYSICS", label: "DATA", color: LABEL_COLORS.DATA }]);
        queueFrame([{ from: "PHYSICS", to: "SIMULATOR", label: "DATA", color: LABEL_COLORS.DATA }]);
        queueFrame([{ from: "SIMULATOR", to: "LLM", label: "OK", color: LABEL_COLORS.OK }]);
        simSpinRef.current.active = false;
        queueFrame([{ from: "LLM", to: "STORAGE", label: "CALL", color: LABEL_COLORS.CALL }]);
        queueFrame([{ from: "STORAGE", to: "LLM", label: "OK", color: LABEL_COLORS.OK }]);

      } else if (name === "estimate_cost") {
        queueFrame([{ from: "COST_ENGINE", to: "LLM", label: "OK", color: LABEL_COLORS.OK }]);

      } else if (name === "list_tools") {
        queueFrame([{ from: "TOOL_GENERATOR", to: "LLM", label: "OK", color: LABEL_COLORS.OK }]);
      }

    } else if (typ === "llm.call" && ev.stage === "forced_final") {
      llmSpinRef.current.active = true;

    } else if (typ === "llm.response" && ev.stage === "forced_final") {
      llmSpinRef.current.active = false;
      queueFrame([{ from: "LLM", to: "USER", label: "ANSWER", color: LABEL_COLORS.ANSWER }]);

    } else if (typ === "ui.switch_run") {
      queueFrame([{ from: "LLM", to: "STORAGE", label: "CALL", color: LABEL_COLORS.CALL }]);
      queueFrame([{ from: "STORAGE", to: "LLM", label: "OK", color: LABEL_COLORS.OK, bubble: { text: "run_id", color: LABEL_COLORS.RUN } }]);

    } else if (typ === "sim.start") {
      abortGraph();
      simSpinRef.current.active = true;
      queueFrame([{ from: "USER", to: "SIMULATOR", label: "REQUEST", color: LABEL_COLORS.REQUEST }]);
      
      queueFrame([{ from: "SIMULATOR", to: "VALIDATOR", label: "CALL", color: LABEL_COLORS.CALL }]);
      queueFrame([{ from: "VALIDATOR", to: "SIMULATOR", label: "OK", color: LABEL_COLORS.OK }]);
      queueFrame([{ from: "SIMULATOR", to: "SANDBOX", label: "CALL", color: LABEL_COLORS.CALL }]);
      queueFrame([{ from: "SANDBOX", to: "SIMULATOR", label: "DATA", color: LABEL_COLORS.DATA }]);
      queueFrame([{ from: "SIMULATOR", to: "PHYSICS", label: "CALL", color: LABEL_COLORS.CALL }]);
      queueFrame([{ from: "PHYSICS", to: "SIMULATOR", label: "DATA", color: LABEL_COLORS.DATA }]);

          


    } else if (typ === "sim.end") {
      simSpinRef.current.active = false;
      const ok = !!ev.ok;
      queueFrame([
        { from: "SIMULATOR", to: "KPIs", label: "CALL", color: LABEL_COLORS.CALL, bubble: { text: "kpis", color: LABEL_COLORS.KPIS } },
        { from: "SIMULATOR", to: "ISSUES", label: "CALL", color: LABEL_COLORS.CALL, bubble: { text: "issues", color: LABEL_COLORS.ISSUES } },
      ]);
      queueFrame([
        { from: "KPIs", to: "PHYSICS", label: "DATA", color: LABEL_COLORS.DATA },
        { from: "ISSUES", to: "PHYSICS", label: "DATA", color: LABEL_COLORS.DATA },
      ]);
      queueFrame([
        { from: "PHYSICS", to: "SIMULATOR", label: "DATA", color: LABEL_COLORS.DATA },
        { from: "PHYSICS", to: "SIMULATOR", label: "DATA", color: LABEL_COLORS.DATA },
      ]);
      queueFrame([{ from: "SIMULATOR", to: "USER", label: ok ? "OK" : "FAIL", color: ok ? LABEL_COLORS.OK : LABEL_COLORS.FAIL }]);

    } else if (typ === "chat.end") {
      llmSpinRef.current.active = false;
    }
  } catch {}
};


      ws.onclose = () => {
        setStatus("disconnected"); wsRef.current = null;
        if (!stop) { setTimeout(connect, retryMs); retryMs = Math.min(retryMs * 2, 10000); }
      };
      ws.onerror = () => {};
    };

    connect();
    return () => { stop = true; try { wsRef.current?.close(); } catch {} wsRef.current = null; };
  }, [wsUrl, channel]);

  // Frontend pulses: abort on new send and validate UI (these don't choreograph; they only abort/start)
  useEffect(() => {
    const onPulse = (e) => {
      const d = e.detail || {};
      if (d.channel && d.channel !== (channel || "adhoc")) return;

      if (d.type === "graph.abort") {
        abortGraph();
      } else if (d.type === "validate.start") {
        abortGraph();
        queueFrame([{ from: "USER", to: "SIMULATOR", label: "REQUEST", color: LABEL_COLORS.REQUEST }]);
        queueFrame([{ from: "SIMULATOR", to: "VALIDATOR", label: "CALL", color: LABEL_COLORS.CALL }]);
      } else if (d.type === "validate.end") {
        const ok = !!d.ok;
        queueFrame([{ from: "VALIDATOR", to: "SIMULATOR", label: ok ? "OK" : "FAIL", color: ok ? LABEL_COLORS.OK : LABEL_COLORS.FAIL }]);
        queueFrame([{ from: "SIMULATOR", to: "USER", label: ok ? "OK" : "FAIL", color: ok ? LABEL_COLORS.OK : LABEL_COLORS.FAIL }]);
      }
    };
    window.addEventListener("pipewise:graph-pulse", onPulse);
    return () => window.removeEventListener("pipewise:graph-pulse", onPulse);
  }, [channel]);

  return (
    <div className="rounded-lg bg-slate-900 border border-slate-700">
      <div className="flex items-center justify-between px-3 py-2 border-b border-slate-700">
        <div className="flex items-center gap-3">
          <div className="text-sm text-slate-200">Agent & Tool Interaction Graph</div>
          <div className="flex items-center gap-2 text-[11px] text-slate-300">
            <span className="inline-flex items-center gap-1"><span style={{background: ROLE_COLOR.user, width: 10, height: 10, borderRadius: 999}}></span> User</span>
            <span className="inline-flex items-center gap-1"><span style={{background: ROLE_COLOR.agent, width: 10, height: 10, borderRadius: 999}}></span> Agents</span>
            <span className="inline-flex items-center gap-1"><span style={{background: ROLE_COLOR.tool, width: 10, height: 10, borderRadius: 999}}></span> Tools</span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className={`text-[10px] px-2 py-0.5 rounded ${
            status === "connected" ? "bg-emerald-500/20 text-emerald-300" :
            status === "connecting" ? "bg-yellow-500/20 text-yellow-300" :
            "bg-slate-600/20 text-slate-300"
          }`}>{status}</span>
          <button className="text-xs px-2 py-1 rounded bg-slate-800 border border-slate-700 text-slate-200"
            onClick={() => { pausedRef.current = !pausedRef.current; }}>
            {pausedRef.current ? "Resume" : "Pause"}
          </button>
          <div className="flex items-center gap-2 text-[11px] text-slate-300">
            <span>Speed</span>
            <input
              type="range" min="50" max="300" step="5"
              value={speedPct}
              onChange={(e) => {
                const pct = parseInt(e.target.value || "100", 10);
                setSpeedPct(pct);
                speedMultRef.current = pct / 100.0;
              }}
            />
            <span>{speedPct}%</span>
          </div>
        </div>
      </div>
      <div className="p-2">
        <canvas
          ref={canvasRef}
          width={layoutRef.current.width}
          height={layoutRef.current.height}
          className="block rounded border border-slate-700 bg-slate-800 cursor-move"
        />
        <div className="mt-2 text-[11px] text-slate-400">
          Live from debug WS: LLM “thinking” spinners; KPIs/ISSUES flow via Physics → Simulator; aborts on new request.
        </div>
      </div>
    </div>
  );
}