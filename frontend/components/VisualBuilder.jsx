// components/VisualBuilder.jsx
import { useEffect, useState, useRef, useCallback } from "react";

const CANVAS_HEIGHT = 700;
const JUNCTION_RADIUS = 15;
const GRID_SIZE = 20;

const COLORS = {
  junction: { default: '#e2e8f0', selected: '#fbbf24', hovered: '#94a3b8' },
  pipe: '#60a5fa',
  valve: '#f59e0b',
  extGrid: '#10b981',
  sink: '#ef4444',
  source: '#8b5cf6',
  pump: '#06b6d4',
  compressor: '#f97316',
  heatExchanger: '#ec4899'
};

export default function VisualBuilder({ code, onApply }) {
  const [open, setOpen] = useState(true);

  // responsive sizing
  const containerRef = useRef(null);
  const canvasRef = useRef(null);
  const [canvasSize, setCanvasSize] = useState({ w: 900, h: CANVAS_HEIGHT });

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => {
      const w = Math.max(480, Math.floor(entry.contentRect.width)); // min guard
      setCanvasSize((s) => ({ ...s, w }));
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const [scale, setScale] = useState(1);
  const [offset, setOffset] = useState({ x: 50, y: 50 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const [dragOffset, setDragOffset] = useState({ x: 0, y: 0 });

  const [autoSync, setAutoSync] = useState(true);
  const lastEditorChangeAtRef = useRef(0);
  const lastBuilderChangeAtRef = useRef(0);
  const lastSeenCodeRef = useRef(code || "");
  const lastPushedCodeRef = useRef("");
  const initialImportedRef = useRef(false);

  useEffect(() => {
    if (code !== lastSeenCodeRef.current) {
      lastSeenCodeRef.current = code || "";
      lastEditorChangeAtRef.current = Date.now();
      if (lastPushedCodeRef.current && code === lastPushedCodeRef.current) {
        lastPushedCodeRef.current = "";
      }
    }
  }, [code]);

  const [junctions, setJunctions] = useState([
    { id: 0, name: "J1", pn_bar: 1.05, tfluid_k: 293.15, x: 100, y: 100 },
    { id: 1, name: "J2", pn_bar: 1.05, tfluid_k: 293.15, x: 300, y: 100 }
  ]);
  const [pipes, setPipes] = useState([]);
  const [valves, setValves] = useState([]);
  const [extGrids, setExtGrids] = useState([]);
  const [sinks, setSinks] = useState([]);
  const [sources, setSources] = useState([]);
  const [pumps, setPumps] = useState([]);
  const [compressors, setCompressors] = useState([]);
  const [heatExchangers, setHeatExchangers] = useState([]);
  const [fluid, setFluid] = useState("lgas");

  const [selectedElement, setSelectedElement] = useState(null);
  const [tool, setTool] = useState("select");
  const [connecting, setConnecting] = useState(null);
  const [hoveredElement, setHoveredElement] = useState(null);
  const [showProperties, setShowProperties] = useState(false);

  const markBuilderChanged = () => { lastBuilderChangeAtRef.current = Date.now(); };

  const screenToCanvas = useCallback((screenX, screenY) => {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return { x: 0, y: 0 };
    return { x: (screenX - rect.left - offset.x) / scale, y: (screenY - rect.top - offset.y) / scale };
  }, [offset, scale]);

  const distanceToLineSegment = (px, py, x1, y1, x2, y2) => {
    const dx = x2 - x1, dy = y2 - y1, length = Math.sqrt(dx * dx + dy * dy);
    if (length === 0) return Math.sqrt((px - x1) ** 2 + (py - y1) ** 2);
    const t = Math.max(0, Math.min(1, ((px - x1) * dx + (px - y1) * dy) / (length * length)));
    const projection_x = x1 + t * dx, projection_y = y1 + t * dy;
    return Math.sqrt((px - projection_x) ** 2 + (py - projection_y) ** 2);
  };

  const findElementAt = useCallback((x, y) => {
    for (const junction of junctions) {
      const dx = x - junction.x, dy = y - junction.y;
      if (Math.sqrt(dx * dx + dy * dy) <= JUNCTION_RADIUS) return { type: "junction", element: junction };
    }
    for (const pipe of pipes) {
      const fromJunction = junctions.find(j => j.id === pipe.from_junction);
      const toJunction = junctions.find(j => j.id === pipe.to_junction);
      if (fromJunction && toJunction) {
        const dist = distanceToLineSegment(x, y, fromJunction.x, fromJunction.y, toJunction.x, toJunction.y);
        if (dist <= 5) return { type: "pipe", element: pipe };
      }
    }
    for (const valve of valves) {
      const fromJunction = junctions.find(j => j.id === valve.from_junction);
      const toJunction = junctions.find(j => j.id === valve.to_junction);
      if (fromJunction && toJunction) {
        const dist = distanceToLineSegment(x, y, fromJunction.x, fromJunction.y, toJunction.x, toJunction.y);
        if (dist <= 5) return { type: "valve", element: valve };
      }
    }
    const components = [
      ...sinks.map(s => ({ ...s, type: "sink", yOffset: -30 })),
      ...extGrids.map(g => ({ ...g, type: "extgrid", yOffset: 30 })),
      ...sources.map(s => ({ ...s, type: "source", yOffset: -50 })),
      ...pumps.map(p => ({ ...p, type: "pump" })),
      ...compressors.map(c => ({ ...c, type: "compressor" })),
      ...heatExchangers.map(h => ({ ...h, type: "heatexchanger" }))
    ];
    for (const component of components) {
      let checkX, checkY, radius = 10;
      if (component.type === "pump" || component.type === "compressor" || component.type === "heatexchanger") {
        const fromJunction = junctions.find(j => j.id === component.from_junction);
        const toJunction = junctions.find(j => j.id === component.to_junction);
        if (fromJunction && toJunction) {
          checkX = (fromJunction.x + toJunction.x) / 2;
          checkY = (fromJunction.y + toJunction.y) / 2;
          radius = 15;
        }
      } else {
        const junction = junctions.find(j => j.id === component.junction);
        if (junction) { checkX = junction.x; checkY = junction.y + (component.yOffset || 0); }
      }
      if (checkX !== undefined && checkY !== undefined) {
        const dx = x - checkX, dy = y - checkY;
        if (Math.sqrt(dx * dx + dy * dy) <= radius) return { type: component.type, element: component };
      }
    }
    return null;
  }, [junctions, pipes, valves, sinks, extGrids, sources, pumps, compressors, heatExchangers]);

  const handleMouseDown = (e) => {
    if (e.button !== 0) return;
    const canvasPos = screenToCanvas(e.clientX, e.clientY);
    const element = findElementAt(canvasPos.x, canvasPos.y);

    if (tool === "select") {
      if (element) {
        setSelectedElement(element);
        setShowProperties(true);
        if (element.type === "junction") {
          setIsDragging(true);
          setDragStart({ x: e.clientX, y: e.clientY });
          setDragOffset({ x: canvasPos.x - element.element.x, y: canvasPos.y - element.element.y });
        }
      } else {
        setSelectedElement(null); setShowProperties(false);
        setIsDragging(true); setDragStart({ x: e.clientX, y: e.clientY });
      }
    } else if (tool === "junction") {
      const newId = Math.max(...junctions.map(j => j.id), -1) + 1;
      setJunctions(prev => [...prev, { id: newId, name: `J${newId + 1}`, pn_bar: 1.05, tfluid_k: 293.15, x: canvasPos.x, y: canvasPos.y }]);
      markBuilderChanged();
    } else if (["pipe", "valve", "pump", "compressor", "heatexchanger"].includes(tool)) {
      if (element && element.type === "junction") {
        if (!connecting) setConnecting({ type: tool, from: element.element.id });
        else if (connecting.from !== element.element.id) {
          const newConnection = { from_junction: connecting.from, to_junction: element.element.id, diameter_m: 0.05, name: `${tool.charAt(0).toUpperCase() + tool.slice(1)} ${getNextId(tool)}` };
          if (tool === "pipe") setPipes(prev => [...prev, { ...newConnection, length_km: 0.1 }]);
          else if (tool === "valve") setValves(prev => [...prev, { ...newConnection, opened: true }]);
          else if (tool === "pump") setPumps(prev => [...prev, { ...newConnection, p_flow_bar: 0.1 }]);
          else if (tool === "compressor") setCompressors(prev => [...prev, { ...newConnection, pressure_ratio: 2.0 }]);
          else if (tool === "heatexchanger") setHeatExchangers(prev => [...prev, { ...newConnection, diameter_m: 0.05, qext_w: 1000 }]);
          setConnecting(null); markBuilderChanged();
        }
      } else setConnecting(null);
    } else if (["extgrid", "sink", "source"].includes(tool) && element && element.type === "junction") {
      const junctionId = element.element.id;
      if (tool === "extgrid") {
        if (!extGrids.find(g => g.junction === junctionId)) { setExtGrids(prev => [...prev, { junction: junctionId, p_bar: 1.1, t_k: 293.15, name: `ExtGrid ${getNextId("extgrid")}` }]); markBuilderChanged(); }
      } else if (tool === "sink") {
        if (!sinks.find(s => s.junction === junctionId)) { setSinks(prev => [...prev, { junction: junctionId, mdot_kg_per_s: 0.02, name: `Sink ${getNextId("sink")}` }]); markBuilderChanged(); }
      } else if (tool === "source") {
        if (!sources.find(s => s.junction === junctionId)) { setSources(prev => [...prev, { junction: junctionId, mdot_kg_per_s: 0.02, name: `Source ${getNextId("source")}` }]); markBuilderChanged(); }
      }
    }
  };

  const getNextId = (type) => {
    const counts = {
      pipe: pipes.length + 1, valve: valves.length + 1, pump: pumps.length + 1,
      compressor: compressors.length + 1, heatexchanger: heatExchangers.length + 1,
      extgrid: extGrids.length + 1, sink: sinks.length + 1, source: sources.length + 1
    };
    return counts[type] || 1;
  };

  const handleMouseMove = (e) => {
    const canvasPos = screenToCanvas(e.clientX, e.clientY);
    if (isDragging) {
      if (selectedElement && selectedElement.type === "junction") {
        setJunctions(prev => prev.map(j => j.id === selectedElement.element.id ? { ...j, x: canvasPos.x - dragOffset.x, y: canvasPos.y - dragOffset.y } : j));
        markBuilderChanged();
      } else {
        const dx = e.clientX - dragStart.x, dy = e.clientY - dragStart.y;
        setOffset(prev => ({ x: prev.x + dx, y: prev.y + dy })); setDragStart({ x: e.clientX, y: e.clientY });
      }
    } else {
      const element = findElementAt(canvasPos.x, canvasPos.y);
      setHoveredElement(element);
    }
  };

  const handleMouseUp = () => { setIsDragging(false); };

  const handleWheel = (e) => {
    e.preventDefault();
    const rect = canvasRef.current.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;
    const scaleFactor = e.deltaY > 0 ? 0.9 : 1.1;
    const newScale = Math.max(0.1, Math.min(3, scale * scaleFactor));
    const scaleChange = newScale / scale;
    setScale(newScale);
    setOffset(prev => ({ x: mouseX - (mouseX - prev.x) * scaleChange, y: mouseY - (mouseY - prev.y) * scaleChange }));
  };

  const draw = useCallback(() => {
    const canvas = canvasRef.current; if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const W = canvas.width, H = canvas.height;
    ctx.clearRect(0, 0, W, H);
    ctx.save(); ctx.translate(offset.x, offset.y); ctx.scale(scale, scale);

    // Grid
    ctx.strokeStyle = '#374151'; ctx.lineWidth = 0.5 / scale;
    for (let x = 0; x <= W; x += GRID_SIZE) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke(); }
    for (let y = 0; y <= H; y += GRID_SIZE) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke(); }

    const drawConnection = (connections, color, drawSymbol) => {
      ctx.strokeStyle = color; ctx.lineWidth = 3 / scale;
      connections.forEach(conn => {
        const fj = junctions.find(j => j.id === conn.from_junction);
        const tj = junctions.find(j => j.id === conn.to_junction);
        if (fj && tj) {
          const isSel = selectedElement?.element === conn;
          const isHov = hoveredElement?.element === conn;
          ctx.strokeStyle = isSel ? '#fbbf24' : isHov ? '#94a3b8' : color;
          ctx.lineWidth = (isSel || isHov ? 4 : 3) / scale;
          ctx.beginPath(); ctx.moveTo(fj.x, fj.y); ctx.lineTo(tj.x, tj.y); ctx.stroke();
          const midX = (fj.x + tj.x) / 2, midY = (fj.y + tj.y) / 2;
          if (drawSymbol) drawSymbol(ctx, conn, midX, midY, isSel || isHov);
        }
      });
    };

    // Pipes
    drawConnection(pipes, COLORS.pipe, (ctx, pipe, x, y, highlighted) => {
      ctx.fillStyle = highlighted ? '#fbbf24' : COLORS.pipe;
      ctx.font = `${10 / scale}px Arial`; ctx.textAlign = 'center';
      ctx.fillText(`${pipe.diameter_m}m`, x, y - 8);
    });
    // Valves
    drawConnection(valves, COLORS.valve, (ctx, valve, x, y, highlighted) => {
      ctx.fillStyle = valve.opened ? '#10b981' : '#ef4444';
      ctx.fillRect(x - 6, y - 6, 12, 12);
      ctx.fillStyle = highlighted ? '#fbbf24' : COLORS.valve;
      ctx.font = `${10 / scale}px Arial`; ctx.textAlign = 'center';
      ctx.fillText(valve.opened ? 'O' : 'C', x, y + 18);
    });
    // Pumps
    drawConnection(pumps, COLORS.pump, (ctx, pump, x, y, highlighted) => {
      ctx.fillStyle = highlighted ? '#fbbf24' : COLORS.pump;
      ctx.beginPath(); ctx.arc(x, y, 12, 0, 2 * Math.PI); ctx.fill();
      ctx.fillStyle = 'white'; ctx.font = `${10 / scale}px Arial`; ctx.textAlign = 'center'; ctx.fillText('P', x, y + 3);
    });
    // Compressors
    drawConnection(compressors, COLORS.compressor, (ctx, comp, x, y, highlighted) => {
      ctx.fillStyle = highlighted ? '#fbbf24' : COLORS.compressor;
      ctx.fillRect(x - 10, y - 8, 20, 16);
      ctx.fillStyle = 'white'; ctx.font = `${10 / scale}px Arial`; ctx.textAlign = 'center'; ctx.fillText('C', x, y + 3);
    });
    // Heat exchangers
    drawConnection(heatExchangers, COLORS.heatExchanger, (ctx, hx, x, y, highlighted) => {
      ctx.fillStyle = highlighted ? '#fbbf24' : COLORS.heatExchanger;
      ctx.beginPath(); ctx.moveTo(x - 10, y - 8); ctx.lineTo(x + 10, y - 8); ctx.lineTo(x + 10, y + 8); ctx.lineTo(x - 10, y + 8); ctx.closePath(); ctx.fill();
      ctx.fillStyle = 'white'; ctx.font = `${8 / scale}px Arial`; ctx.textAlign = 'center'; ctx.fillText('HX', x, y + 2);
    });

    // Junctions
    junctions.forEach(junction => {
      const isSel = selectedElement?.type === "junction" && selectedElement.element.id === junction.id;
      const isHov = hoveredElement?.type === "junction" && hoveredElement.element.id === junction.id;
      ctx.fillStyle = isSel ? COLORS.junction.selected : isHov ? COLORS.junction.hovered : COLORS.junction.default;
      ctx.strokeStyle = '#475569'; ctx.lineWidth = 2 / scale;
      ctx.beginPath(); ctx.arc(junction.x, junction.y, JUNCTION_RADIUS, 0, 2 * Math.PI); ctx.fill(); ctx.stroke();
      ctx.fillStyle = '#1e293b'; ctx.font = `${12 / scale}px Arial`; ctx.textAlign = 'center';
      ctx.fillText(junction.name, junction.x, junction.y + 3);
    });

    const drawAttachment = (components, yOffset, color, symbol, size = 10) => {
      components.forEach(component => {
        const junction = junctions.find(j => j.id === component.junction);
        if (junction) {
          const isSel = selectedElement?.element === component;
          const isHov = hoveredElement?.element === component;
          ctx.fillStyle = isSel ? '#fbbf24' : isHov ? '#94a3b8' : color;
          ctx.beginPath(); ctx.arc(junction.x, junction.y + yOffset, size, 0, 2 * Math.PI); ctx.fill();
          ctx.fillStyle = 'white'; ctx.font = `${8 / scale}px Arial`; ctx.textAlign = 'center'; ctx.fillText(symbol, junction.x, junction.y + yOffset + 2);
        }
      });
    };
    drawAttachment(sinks, -30, COLORS.sink, 'S');
    drawAttachment(extGrids, 30, COLORS.extGrid, 'EG');
    drawAttachment(sources, -50, COLORS.source, 'So');

    ctx.restore();
  }, [junctions, pipes, valves, pumps, compressors, heatExchangers, extGrids, sinks, sources, offset, scale, selectedElement, hoveredElement]);

  useEffect(() => { draw(); }, [draw, canvasSize]);
  useEffect(() => {
    const canvas = canvasRef.current; if (!canvas) return;
    canvas.addEventListener('wheel', handleWheel, { passive: false });
    return () => canvas.removeEventListener('wheel', handleWheel);
  }, [scale, offset]);

  const autoLayoutNetwork = (nodes) => {
    if (!nodes || nodes.length === 0) return [];
    const W = canvasSize.w, H = canvasSize.h;
    if (nodes.length <= 2) return nodes.map((node, idx) => ({ ...node, x: 150 + idx * 200, y: Math.max(120, Math.min(H - 120, 300)) }));
    const layoutNodes = nodes.map((node, idx) => ({ ...node, x: node.x || (150 + (idx % 5) * 160), y: node.y || (150 + Math.floor(idx / 5) * 120) }));
    for (let iter = 0; iter < 10; iter++) {
      layoutNodes.forEach((node, i) => {
        let fx = 0, fy = 0;
        layoutNodes.forEach((other, j) => {
          if (i === j) return;
          const dx = node.x - other.x, dy = node.y - other.y;
          const dist = Math.sqrt(dx * dx + dy * dy) || 1;
          if (dist < 120) { const f = (120 - dist) / 120 * 20; fx += (dx / dist) * f; fy += (dy / dist) * f; }
        });
        node.x += fx * 0.1; node.y += fy * 0.1;
        node.x = Math.max(100, Math.min(W - 100, node.x));
        node.y = Math.max(100, Math.min(H - 100, node.y));
      });
    }
    return layoutNodes;
  };

  function generateCode() {
    const pyBool = (b) => (b ? "True" : "False");
    const lines = [];
    lines.push("import pandapipes as pp");
    lines.push(""); lines.push(`net = pp.create_empty_network(fluid="${fluid}")`); lines.push("");
    lines.push("# Create junctions");
    junctions.forEach((j) => { lines.push(`j${j.id} = pp.create_junction(net, pn_bar=${j.pn_bar}, tfluid_k=${j.tfluid_k}, name="${j.name}")`); });
    lines.push("");
    if (extGrids.length > 0) { lines.push("# Create external grids"); extGrids.forEach((g, i) => { lines.push(`pp.create_ext_grid(net, junction=j${g.junction}, p_bar=${g.p_bar ?? 1.1}, t_k=${g.t_k ?? 293.15}, name="${g.name || `ExtGrid ${i+1}`}")`); }); lines.push(""); }
    if (sources.length > 0) { lines.push("# Create sources"); sources.forEach((s, i) => { lines.push(`pp.create_source(net, junction=j${s.junction}, mdot_kg_per_s=${s.mdot_kg_per_s ?? 0.02}, name="${s.name || `Source ${i+1}`}")`); }); lines.push(""); }
    if (sinks.length > 0) { lines.push("# Create sinks"); sinks.forEach((s, i) => { lines.push(`pp.create_sink(net, junction=j${s.junction}, mdot_kg_per_s=${s.mdot_kg_per_s ?? 0.02}, name="${s.name || `Sink ${i+1}`}")`); }); lines.push(""); }
    if (pipes.length > 0) { lines.push("# Create pipes"); pipes.forEach((p, i) => { lines.push(`pp.create_pipe_from_parameters(net, from_junction=j${p.from_junction}, to_junction=j${p.to_junction}, length_km=${p.length_km}, diameter_m=${p.diameter_m}, name="${p.name || `Pipe ${i+1}`}")`); }); lines.push(""); }
    if (valves.length > 0) { lines.push("# Create valves"); valves.forEach((v, i) => { lines.push(`pp.create_valve(net, from_junction=j${v.from_junction}, to_junction=j${v.to_junction}, diameter_m=${v.diameter_m}, opened=${pyBool(!!v.opened)}, name="${v.name || `Valve ${i+1}`}")`); }); lines.push(""); }
    if (pumps.length > 0) { lines.push("# Create pumps"); pumps.forEach((p, i) => { lines.push(`pp.create_pump(net, from_junction=j${p.from_junction}, to_junction=j${p.to_junction}, std_type="P1", name="${p.name || `Pump ${i+1}`}")`); }); lines.push(""); }
    if (compressors.length > 0) { lines.push("# Create compressors"); compressors.forEach((c, i) => { const pr = (typeof c.pressure_ratio === "number") ? c.pressure_ratio : 2.0; lines.push(`pp.create_compressor(net, from_junction=j${c.from_junction}, to_junction=j${c.to_junction}, pressure_ratio=${pr}, name="${c.name || `Compressor ${i+1}`}")`); }); lines.push(""); }
    if (heatExchangers.length > 0) { lines.push("# Create heat exchangers"); heatExchangers.forEach((h, i) => { const d = (typeof h.diameter_m === "number") ? h.diameter_m : 0.05; const q = (typeof h.qext_w === "number") ? h.qext_w : 1000; lines.push(`pp.create_heat_exchanger(net, from_junction=j${h.from_junction}, to_junction=j${h.to_junction}, diameter_m=${d}, qext_w=${q}, name="${h.name || `HX ${i+1}`}")`); }); lines.push(""); }
    lines.push("# Run simulation"); lines.push("pp.pipeflow(net)"); return lines.join("\n");
  }

  const parseCode = (src) => {
    const text = src || "";
    const parsedJunctions = [], parsedPipes = [], parsedValves = [], parsedExtGrids = [], parsedSources = [], parsedSinks = [], parsedPumps = [], parsedCompressors = [], parsedHX = [];
    let fluidVal = null;

    const mFluid = text.match(/pp\.create_empty_network\([^)]*fluid\s*=\s*['"]([^'"]+)['"]/);
    if (mFluid) fluidVal = mFluid[1];

    const junctionRegex = /j(\d+)\s*=\s*pp\.create_junction\([^)]*name\s*=\s*['"](.*?)['"][^)]*\)/g;
    let match;
    while ((match = junctionRegex.exec(text)) !== null) parsedJunctions.push({ id: parseInt(match[1], 10), name: match[2], pn_bar: 1.05, tfluid_k: 293.15 });

    const pipeRegex = /pp\.create_pipe_from_parameters\([^)]*from_junction\s*=\s*j(\d+)[^)]*to_junction\s*=\s*j(\d+)[^)]*length_km\s*=\s*([\d.eE+\-]+)[^)]*diameter_m\s*=\s*([\d.eE+\-]+)[^)]*(?:name\s*=\s*['"](.*?)['"])?[^)]*\)/g;
    while ((match = pipeRegex.exec(text)) !== null) parsedPipes.push({ from_junction: parseInt(match[1], 10), to_junction: parseInt(match[2], 10), length_km: parseFloat(match[3]), diameter_m: parseFloat(match[4]), name: match[5] || "" });

    const valveRegex = /pp\.create_valve\([^)]*from_junction\s*=\s*j(\d+)[^)]*to_junction\s*=\s*j(\d+)[^)]*(?:diameter_m\s*=\s*([\d.eE+\-]+))?[^)]*opened\s*=\s*(True|False)[^)]*(?:name\s*=\s*['"](.*?)['"])?[^)]*\)/g;
    while ((match = valveRegex.exec(text)) !== null) parsedValves.push({ from_junction: parseInt(match[1], 10), to_junction: parseInt(match[2], 10), diameter_m: match[3] ? parseFloat(match[3]) : 0.05, opened: match[4] === 'True', name: match[5] || "" });

    const extGridRegex = /pp\.create_ext_grid\([^)]*junction\s*=\s*j(\d+)[^)]*(?:p_bar\s*=\s*([\d.eE+\-]+))?[^)]*(?:t_k\s*=\s*([\d.eE+\-]+))?[^)]*(?:name\s*=\s*['"](.*?)['"])?[^)]*\)/g;
    while ((match = extGridRegex.exec(text)) !== null) parsedExtGrids.push({ junction: parseInt(match[1], 10), p_bar: match[2] ? parseFloat(match[2]) : 1.1, t_k: match[3] ? parseFloat(match[3]) : 293.15, name: match[4] || "" });

    const sourceRegex = /pp\.create_source\([^)]*junction\s*=\s*j(\d+)[^)]*(?:mdot_kg_per_s\s*=\s*([\d.eE+\-]+))?[^)]*(?:name\s*=\s*['"](.*?)['"])?[^)]*\)/g;
    while ((match = sourceRegex.exec(text)) !== null) parsedSources.push({ junction: parseInt(match[1], 10), mdot_kg_per_s: match[2] ? parseFloat(match[2]) : 0.02, name: match[3] || "" });

    const sinkRegex = /pp\.create_sink\([^)]*junction\s*=\s*j(\d+)[^)]*(?:mdot_kg_per_s\s*=\s*([\d.eE+\-]+))?[^)]*(?:name\s*=\s*['"](.*?)['"])?[^)]*\)/g;
    while ((match = sinkRegex.exec(text)) !== null) parsedSinks.push({ junction: parseInt(match[1], 10), mdot_kg_per_s: match[2] ? parseFloat(match[2]) : 0.02, name: match[3] || "" });

    const pumpRegex = /pp\.create_pump\([^)]*from_junction\s*=\s*j(\d+)[^)]*to_junction\s*=\s*j(\d+)[^)]*(?:name\s*=\s*['"](.*?)['"])?[^)]*\)/g;
    while ((match = pumpRegex.exec(text)) !== null) parsedPumps.push({ from_junction: parseInt(match[1], 10), to_junction: parseInt(match[2], 10), name: match[3] || "" });

    const compRegex = /pp\.create_compressor\([^)]*from_junction\s*=\s*j(\d+)[^)]*to_junction\s*=\s*j(\d+)[^)]*(?:pressure_ratio\s*=\s*([\d.eE+\-]+))?[^)]*(?:name\s*=\s*['"](.*?)['"])?[^)]*\)/g;
    while ((match = compRegex.exec(text)) !== null) parsedCompressors.push({ from_junction: parseInt(match[1], 10), to_junction: parseInt(match[2], 10), pressure_ratio: match[3] ? parseFloat(match[3]) : 2.0, name: match[4] || "" });

    const hxRegex = /pp\.create_heat_exchanger\([^)]*from_junction\s*=\s*j(\d+)[^)]*to_junction\s*=\s*j(\d+)[^)]*(?:diameter_m\s*=\s*([\d.eE+\-]+))?[^)]*(?:qext_w\s*=\s*([\d.eE+\-]+))?[^)]*(?:name\s*=\s*['"](.*?)['"])?[^)]*\)/g;
    while ((match = hxRegex.exec(text)) !== null) parsedHX.push({ from_junction: parseInt(match[1], 10), to_junction: parseInt(match[2], 10), diameter_m: match[3] ? parseFloat(match[3]) : 0.05, qext_w: match[4] ? parseFloat(match[4]) : 1000, name: match[5] || "" });

    return { fluid: fluidVal, junctions: parsedJunctions, pipes: parsedPipes, valves: parsedValves, extGrids: parsedExtGrids, sources: parsedSources, sinks: parsedSinks, pumps: parsedPumps, compressors: parsedCompressors, heatExchangers: parsedHX };
  };

  const importFromCode = async (srcText) => {
    try {
      const parsed = parseCode(srcText ?? code ?? "");
      if (parsed.junctions.length > 0) {
        const layoutedJunctions = autoLayoutNetwork(parsed.junctions);
        setJunctions(layoutedJunctions);
        setPipes(parsed.pipes); setValves(parsed.valves);
        setExtGrids(parsed.extGrids); setSinks(parsed.sinks); setSources(parsed.sources);
        setPumps(parsed.pumps); setCompressors(parsed.compressors); setHeatExchangers(parsed.heatExchangers);
        if (parsed.fluid) setFluid(parsed.fluid);
      } else {
        const defaults = [
          { id: 0, name: "J1", pn_bar: 1.05, tfluid_k: 293.15 },
          { id: 1, name: "J2", pn_bar: 1.05, tfluid_k: 293.15 },
          { id: 2, name: "J3", pn_bar: 1.05, tfluid_k: 293.15 }
        ];
        setJunctions(autoLayoutNetwork(defaults));
        setPipes([]); setValves([]); setExtGrids([]); setSinks([]); setSources([]); setPumps([]); setCompressors([]); setHeatExchangers([]);
      }
      setOffset({ x: 50, y: 50 }); setScale(1); setSelectedElement(null); setShowProperties(false); setConnecting(null);
    } catch (error) { console.warn("Import failed:", error); }
  };

  useEffect(() => {
    if (!initialImportedRef.current) {
      const src = lastSeenCodeRef.current || code || "";
      if (src.trim()) importFromCode(src);
      initialImportedRef.current = true;
    }
  }, []);

  useEffect(() => {
    if (!autoSync) return;
    const id = setInterval(() => {
      const tE = lastEditorChangeAtRef.current || 0;
      const tB = lastBuilderChangeAtRef.current || 0;
      const editorCode = lastSeenCodeRef.current || "";
      const generated = generateCode();
      if (tE > tB + 150 && editorCode !== generated) { importFromCode(editorCode); lastBuilderChangeAtRef.current = tE; return; }
      if (tB > tE + 150 && editorCode !== generated) {
        if (lastPushedCodeRef.current !== generated) { onApply?.(generated); lastPushedCodeRef.current = generated; }
      }
    }, 1500);
    return () => clearInterval(id);
  }, [autoSync, onApply, fluid, junctions, pipes, valves, extGrids, sinks, sources, pumps, compressors, heatExchangers]);

  const deleteSelected = () => {
    if (!selectedElement) return;
    const { type, element } = selectedElement;
    if (type === "junction") {
      const id = element.id;
      setJunctions(prev => prev.filter(j => j.id !== id));
      setPipes(prev => prev.filter(p => p.from_junction !== id && p.to_junction !== id));
      setValves(prev => prev.filter(v => v.from_junction !== id && v.to_junction !== id));
      setPumps(prev => prev.filter(p => p.from_junction !== id && p.to_junction !== id));
      setCompressors(prev => prev.filter(c => c.from_junction !== id && c.to_junction !== id));
      setHeatExchangers(prev => prev.filter(h => h.from_junction !== id && h.to_junction !== id));
      setExtGrids(prev => prev.filter(g => g.junction !== id));
      setSinks(prev => prev.filter(s => s.junction !== id));
      setSources(prev => prev.filter(s => s.junction !== id));
    } else if (type === "pipe") setPipes(prev => prev.filter(p => p !== element));
    else if (type === "valve") setValves(prev => prev.filter(v => v !== element));
    else if (type === "pump") setPumps(prev => prev.filter(p => p !== element));
    else if (type === "compressor") setCompressors(prev => prev.filter(c => c !== element));
    else if (type === "heatexchanger") setHeatExchangers(prev => prev.filter(h => h !== element));
    else if (type === "sink") setSinks(prev => prev.filter(s => s !== element));
    else if (type === "extgrid") setExtGrids(prev => prev.filter(g => g !== element));
    else if (type === "source") setSources(prev => prev.filter(s => s !== element));
    setSelectedElement(null); setShowProperties(false); markBuilderChanged();
  };

  const deleteAll = () => {
    if (!window.confirm("Delete all components on the canvas?")) return;
    setJunctions([]); setPipes([]); setValves([]); setPumps([]); setCompressors([]); setHeatExchangers([]);
    setExtGrids([]); setSinks([]); setSources([]); setSelectedElement(null); setShowProperties(false); markBuilderChanged();
  };

  const updateSelectedProperty = (property, value) => {
    if (!selectedElement) return;
    const { type, element } = selectedElement;
    const upd = (arr, setFn) => { setFn(arr.map(a => a === element ? { ...a, [property]: value } : a)); };
    if (type === "junction") setJunctions(junctions.map(j => j.id === element.id ? { ...j, [property]: value } : j));
    else if (type === "pipe") upd(pipes, setPipes);
    else if (type === "valve") upd(valves, setValves);
    else if (type === "pump") upd(pumps, setPumps);
    else if (type === "compressor") upd(compressors, setCompressors);
    else if (type === "heatexchanger") upd(heatExchangers, setHeatExchangers);
    else if (type === "sink") upd(sinks, setSinks);
    else if (type === "extgrid") upd(extGrids, setExtGrids);
    else if (type === "source") upd(sources, setSources);
    setSelectedElement(prev => prev ? ({ ...prev, element: { ...prev.element, [property]: value } }) : prev);
    markBuilderChanged();
  };

  const renderProperties = () => {
    if (!showProperties || !selectedElement) return null;
    const { type, element } = selectedElement;
    const label = (s) => <label className="text-xs text-slate-400 block">{s}</label>;
    const input = (val, set, step = "0.01") => (
      <input className="w-full bg-[var(--panel-2)] border border-slate-700 rounded px-2 py-1 text-xs" type="number" step={step}
             value={val ?? ""} onChange={(e) => set(parseFloat(e.target.value))} />
    );
    const text = (val, set) => (
      <input className="w-full bg-[var(--panel-2)] border border-slate-700 rounded px-2 py-1 text-xs"
             value={val ?? ""} onChange={(e) => set(e.target.value)} />
    );
    const bool = (val, set) => (<input type="checkbox" checked={!!val} onChange={(e) => set(e.target.checked)} />);

    return (
      <div className="w-72 bg-slate-800 border border-slate-700 rounded p-3 text-xs">
        <div className="font-medium text-slate-200 mb-2">Properties: {type}</div>
        {type === "junction" && (
          <div className="space-y-2">
            {label("Name")}{text(element.name || "", (v) => updateSelectedProperty("name", v))}
            {label("pn_bar")}{input(element.pn_bar, (v) => updateSelectedProperty("pn_bar", v))}
            {label("tfluid_k")}{input(element.tfluid_k, (v) => updateSelectedProperty("tfluid_k", v))}
          </div>
        )}
        {type === "pipe" && (
          <div className="space-y-2">
            {label("Diameter (m)")} {input(element.diameter_m, (v) => updateSelectedProperty("diameter_m", v))}
            {label("Length (km)")} {input(element.length_km, (v) => updateSelectedProperty("length_km", v))}
            {label("Name")} {text(element.name || "", (v) => updateSelectedProperty("name", v))}
          </div>
        )}
        {type === "valve" && (
          <div className="space-y-2">
            {label("Diameter (m)")} {input(element.diameter_m, (v) => updateSelectedProperty("diameter_m", v))}
            <div className="flex items-center gap-2">{label("Opened")}{bool(element.opened, (v) => updateSelectedProperty("opened", v))}</div>
            {label("Name")} {text(element.name || "", (v) => updateSelectedProperty("name", v))}
          </div>
        )}
        {type === "pump" && (<div className="space-y-2">{label("Name")} {text(element.name || "", (v) => updateSelectedProperty("name", v))}</div>)}
        {type === "compressor" && (
          <div className="space-y-2">
            {label("Pressure ratio")} {input(element.pressure_ratio ?? 2.0, (v) => updateSelectedProperty("pressure_ratio", v), "0.01")}
            {label("Name")} {text(element.name || "", (v) => updateSelectedProperty("name", v))}
          </div>
        )}
        {type === "heatexchanger" && (
          <div className="space-y-2">
            {label("Diameter (m)")} {input(element.diameter_m ?? 0.05, (v) => updateSelectedProperty("diameter_m", v))}
            {label("qext_w")} {input(element.qext_w ?? 1000, (v) => updateSelectedProperty("qext_w", v), "1")}
            {label("Name")} {text(element.name || "", (v) => updateSelectedProperty("name", v))}
          </div>
        )}
        {type === "extgrid" && (
          <div className="space-y-2">
            {label("p_bar")} {input(element.p_bar ?? 1.1, (v) => updateSelectedProperty("p_bar", v))}
            {label("t_k")} {input(element.t_k ?? 293.15, (v) => updateSelectedProperty("t_k", v))}
            {label("Name")} {text(element.name || "", (v) => updateSelectedProperty("name", v))}
          </div>
        )}
        {type === "sink" && (
          <div className="space-y-2">
            {label("mdot_kg_per_s")} {input(element.mdot_kg_per_s ?? 0.02, (v) => updateSelectedProperty("mdot_kg_per_s", v), "0.001")}
            {label("Name")} {text(element.name || "", (v) => updateSelectedProperty("name", v))}
          </div>
        )}
        {type === "source" && (
          <div className="space-y-2">
            {label("mdot_kg_per_s")} {input(element.mdot_kg_per_s ?? 0.02, (v) => updateSelectedProperty("mdot_kg_per_s", v), "0.001")}
            {label("Name")} {text(element.name || "", (v) => updateSelectedProperty("name", v))}
          </div>
        )}
        <div className="mt-3 flex gap-2">
          <button className="px-2 py-1 rounded bg-red-600 hover:bg-red-700 text-white" onClick={deleteSelected}>Delete</button>
          <button className="px-2 py-1 rounded bg-slate-700 hover:bg-slate-600" onClick={() => setShowProperties(false)}>Close</button>
        </div>
      </div>
    );
  };

  return (
    <div className="rounded-lg bg-slate-900 border border-slate-700">
      <div className="flex items-center justify-between px-3 py-2 border-b border-slate-700">
        <button className="text-sm text-slate-200 font-medium" onClick={() => setOpen(v => !v)}>
          Enhanced PandaPipes Visual Builder {open ? "▲" : "▼"}
        </button>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-1 text-xs text-slate-300">
            <input type="checkbox" checked={autoSync} onChange={(e) => setAutoSync(e.target.checked)} />
            Auto-sync
          </label>
          <div className="text-xs text-slate-400">
            J:{junctions.length} P:{pipes.length} V:{valves.length} Pu:{pumps.length} C:{compressors.length} HX:{heatExchangers.length}
          </div>
        </div>
      </div>

      {open && (
        <div className="p-4 space-y-4">
          {/* Toolbar */}
          <div className="flex gap-2 flex-wrap">
            <div className="flex gap-1 bg-slate-800 p-1 rounded">
              <button className={`px-3 py-1 rounded text-xs ${tool === "select" ? "bg-blue-600" : "bg-slate-700 hover:bg-slate-600"}`} onClick={() => { setTool("select"); setConnecting(null); }}>
                Select
              </button>
              <button className={`px-3 py-1 rounded text-xs ${tool === "junction" ? "bg-blue-600" : "bg-slate-700 hover:bg-slate-600"}`} onClick={() => { setTool("junction"); setConnecting(null); }}>
                Junction
              </button>
            </div>
            <div className="flex gap-1 bg-slate-800 p-1 rounded">
              <button className={`px-3 py-1 rounded text-xs ${tool === "pipe" ? "bg-blue-600" : "bg-slate-700 hover:bg-slate-600"}`} onClick={() => setTool("pipe")}>Pipe</button>
              <button className={`px-3 py-1 rounded text-xs ${tool === "valve" ? "bg-blue-600" : "bg-slate-700 hover:bg-slate-600"}`} onClick={() => setTool("valve")}>Valve</button>
              <button className={`px-3 py-1 rounded text-xs ${tool === "pump" ? "bg-blue-600" : "bg-slate-700 hover:bg-slate-600"}`} onClick={() => setTool("pump")}>Pump</button>
              <button className={`px-3 py-1 rounded text-xs ${tool === "compressor" ? "bg-blue-600" : "bg-slate-700 hover:bg-slate-600"}`} onClick={() => setTool("compressor")}>Compressor</button>
              <button className={`px-3 py-1 rounded text-xs ${tool === "heatexchanger" ? "bg-blue-600" : "bg-slate-700 hover:bg-slate-600"}`} onClick={() => setTool("heatexchanger")}>Heat Ex.</button>
            </div>
            <div className="flex gap-1 bg-slate-800 p-1 rounded">
              <button className={`px-3 py-1 rounded text-xs ${tool === "extgrid" ? "bg-blue-600" : "bg-slate-700 hover:bg-slate-600"}`} onClick={() => { setTool("extgrid"); setConnecting(null); }}>Ext Grid</button>
              <button className={`px-3 py-1 rounded text-xs ${tool === "source" ? "bg-blue-600" : "bg-slate-700 hover:bg-slate-600"}`} onClick={() => { setTool("source"); setConnecting(null); }}>Source</button>
              <button className={`px-3 py-1 rounded text-xs ${tool === "sink" ? "bg-blue-600" : "bg-slate-700 hover:bg-slate-600"}`} onClick={() => { setTool("sink"); setConnecting(null); }}>Sink</button>
            </div>
            <div className="border-l border-slate-600 mx-2"></div>
            {selectedElement && (
              <button className="px-3 py-1 rounded text-xs bg-red-600 hover:bg-red-700 text-white" onClick={deleteSelected}>Delete</button>
            )}
            <button className="px-3 py-1 rounded text-xs bg-red-700 hover:bg-red-800 text-white border border-red-900" onClick={deleteAll}>
              Delete All
            </button>
            <button className="px-3 py-1 rounded text-xs bg-slate-700 hover:bg-slate-600 border border-slate-600" onClick={() => { setOffset({ x: 50, y: 50 }); setScale(1); }}>
              Reset View
            </button>
          </div>

          {connecting && (
            <div className="text-xs text-amber-400 bg-amber-900/20 p-2 rounded border border-amber-700">
              Click target junction to connect {connecting.type}...
            </div>
          )}

          <div className="flex gap-4">
            <div ref={containerRef} className="border-2 border-slate-600 bg-slate-800 rounded min-w-0 w-full">
              <canvas
                ref={canvasRef}
                width={canvasSize.w}
                height={canvasSize.h}
                style={{ display: "block", width: "100%", height: canvasSize.h, borderRadius: "4px", cursor: tool === "select" ? "default" : "crosshair" }}
                onMouseDown={handleMouseDown}
                onMouseMove={handleMouseMove}
                onMouseUp={handleMouseUp}
                onMouseLeave={handleMouseUp}
              />
            </div>
            {renderProperties()}
          </div>

          <div className="flex gap-3 items-center text-xs bg-slate-800 p-3 rounded">
            <div className="flex gap-2 items-center">
              <label className="text-slate-400">Fluid:</label>
              <input className="bg-slate-700 border border-slate-600 rounded px-2 py-1 w-20" value={fluid} onChange={(e) => { setFluid(e.target.value); markBuilderChanged(); }} />
            </div>
            <div className="flex-1"></div>
            <button onClick={() => onApply?.(generateCode())} className="px-4 py-1 rounded bg-green-600 hover:bg-green-700 text-white font-medium">
              Generate Code → Editor
            </button>
            <button onClick={() => importFromCode()} className="px-4 py-1 rounded bg-blue-600 hover:bg-blue-700 text-white">
              Import from Editor
            </button>
          </div>

          <div className="text-xs text-slate-500 bg-slate-800/50 p-3 rounded space-y-1">
            <div><strong>Building:</strong> Select tool → Click/drag to create elements</div>
            <div><strong>Connections:</strong> Select Pipe/Valve/etc → Click junction → Click target junction</div>
            <div><strong>Navigation:</strong> Drag junctions to move • Scroll to zoom • Drag canvas to pan</div>
            <div><strong>Editing:</strong> Click elements to select and edit properties in the side panel</div>
          </div>
        </div>
      )}
    </div>
  );
}