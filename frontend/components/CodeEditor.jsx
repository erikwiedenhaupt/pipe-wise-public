// components/CodeEditor.jsx
import { useId } from "react";

export default function CodeEditor({ value, onChange }) {
  const id = useId();
  return (
    <div className="rounded-lg overflow-hidden border border-slate-700">
      <label htmlFor={id} className="block text-sm px-3 py-2 bg-[var(--panel)] border-b border-slate-700 text-slate-300">
        Network code (pandapipes)
      </label>
      <textarea
        id={id}
        className="w-full h-[360px] resize-y bg-[var(--panel-2)] text-slate-100 p-3 font-mono text-sm outline-none"
        spellCheck="false"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder='import pandapipes as pp\nnet = pp.create_empty_network(fluid="lgas")\n...'
      />
    </div>
  );
}