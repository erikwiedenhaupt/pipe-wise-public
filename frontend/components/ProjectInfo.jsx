// frontend/components/ProjectInfo.jsx
export default function ProjectInfo({ projectId, versionId, runId }) {
    return (
      <div className="flex flex-wrap gap-2 text-xs">
        {projectId && (
          <span className="px-2 py-1 rounded bg-slate-800 text-slate-200 border border-slate-700">
            project: <span className="font-mono">{projectId}</span>
          </span>
        )}
        {versionId && (
          <span className="px-2 py-1 rounded bg-slate-800 text-slate-200 border border-slate-700">
            version: <span className="font-mono">{versionId}</span>
          </span>
        )}
        {runId && (
          <span className="px-2 py-1 rounded bg-slate-800 text-slate-200 border border-slate-700">
            run: <span className="font-mono">{runId}</span>
          </span>
        )}
      </div>
    );
  }