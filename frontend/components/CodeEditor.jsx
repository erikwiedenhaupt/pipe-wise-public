import dynamic from "next/dynamic";
import { useEffect, useMemo, useRef } from "react";

const Monaco = dynamic(() => import("@monaco-editor/react"), { ssr: false });

export default function CodeEditor({ value, onChange, runtimeErrorLine = null, validationErrorLines = [] }) {
  const editorRef = useRef(null);
  const monacoRef = useRef(null);
  const decosRef = useRef([]);

  const options = useMemo(() => ({
    fontSize: 13,
    minimap: { enabled: false },
    wordWrap: "on",
    scrollBeyondLastLine: false,
    automaticLayout: true,
    glyphMargin: true,
  }), []);

  // Inject CSS once for line highlights
  useEffect(() => {
    if (typeof document === "undefined") return;
    if (document.getElementById("pipewise-editor-styles")) return;
    const style = document.createElement("style");
    style.id = "pipewise-editor-styles";
    style.innerHTML = `
      .monaco-editor .pipewise-error-line {
        background-color: rgba(220, 38, 38, 0.22) !important; /* dark red */
      }
      .monaco-editor .pipewise-runtime-line {
        background-color: rgba(234, 179, 8, 0.25) !important; /* yellow */
      }
    `;
    document.head.appendChild(style);
  }, []);

  const onMount = (editor, monaco) => {
    editorRef.current = editor;
    monacoRef.current = monaco;
  };

  // Update decorations when lines change
  useEffect(() => {
    const ed = editorRef.current;
    const monaco = monacoRef.current;
    if (!ed || !monaco) return;

    const decos = [];

    const addWholeLineDeco = (line, className) => {
      if (typeof line === "number" && line >= 1) {
        const model = ed.getModel();
        const lineCount = model ? model.getLineCount() : 0;
        const ln = Math.min(Math.max(1, line), Math.max(1, lineCount));
        decos.push({
          range: new monaco.Range(ln, 1, ln, 1),
          options: {
            isWholeLine: true,
            className,
          },
        });
      }
    };

    // Validation failures: dark red (all at once)
    const uniqValLines = [...new Set((validationErrorLines || []).filter((n) => typeof n === "number"))];
    uniqValLines.forEach((ln) => addWholeLineDeco(ln, "pipewise-error-line"));

    // Runtime error line: yellow
    if (typeof runtimeErrorLine === "number") {
      addWholeLineDeco(runtimeErrorLine, "pipewise-runtime-line");
    }

    const newIds = ed.deltaDecorations(decosRef.current, decos);
    decosRef.current = newIds;
  }, [runtimeErrorLine, validationErrorLines, value]);

  return (
    <div className="rounded-lg overflow-hidden border border-slate-700">
      <div className="block text-sm px-3 py-2 bg-[var(--panel)] border-b border-slate-700 text-slate-300">
        Network code (pandapipes)
      </div>
      <div className="h-[360px]">
        <Monaco
          height="100%"
          defaultLanguage="python"
          theme="vs-dark"
          value={value}
          onChange={(v) => onChange(v ?? "")}
          options={options}
          onMount={onMount}
        />
      </div>
    </div>
  );
}