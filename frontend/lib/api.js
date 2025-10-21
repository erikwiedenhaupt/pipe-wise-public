// lib/api.js
const inferBase = () => {
    if (typeof window !== "undefined" && window.location) {
      // If you proxy /api in dev, this works out of the box.
      return "/api";
    }
    return "http://localhost:8000/api";
  };
  
  export const API_BASE = process.env.NEXT_PUBLIC_API_BASE || inferBase();
  
  async function api(path, { method = "GET", body, headers = {} } = {}) {
    const res = await fetch(`${API_BASE}${path}`, {
      method,
      headers: {
        "Content-Type": "application/json",
        ...headers,
      },
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!res.ok) {
      const txt = await res.text().catch(() => "");
      throw new Error(`${res.status} ${res.statusText}: ${txt}`);
    }
    if (res.status === 204) return null;
    return res.json();
  }
  
  export const health = () => api("/healthz");
  export const createProject = (name) => api("/projects", { method: "POST", body: { name } });
  export const addVersion = (projectId, code, meta = {}) =>
    api(`/projects/${projectId}/versions`, { method: "POST", body: { code, meta } });
  export const getVersion = (projectId, versionId) =>
    api(`/projects/${projectId}/versions/${versionId}`);
  
  export const validateCode = (code) => api("/validate", { method: "POST", body: { code } });
  
  export const simulate = ({ project_id, version_id, code, options = {} }) =>
    api("/simulate", { method: "POST", body: { project_id, version_id, code, options } });
  
  export const getRun = (runId) => api(`/runs/${runId}`);
  export const getRunKpis = (runId) => api(`/runs/${runId}/kpis`);
  export const getRunIssues = (runId) => api(`/runs/${runId}/issues`);
  export const listProjectRuns = (projectId) => api(`/projects/${projectId}/runs`);
  export const deleteRun = (runId) => api(`/runs/${runId}`, { method: "DELETE" });
  export const getSweep = (runId) => api(`/sweeps/${runId}`);
  export const listTools = () => api("/tools");
  // lib/api.js – add this export
  export const parseGraph = (code) => api("/parse-graph", { method: "POST", body: { code } });
  
  export const scenarioSweep = (payload) =>
    api("/scenario-sweep", { method: "POST", body: payload });
  
  export const chat = (payload) => api("/chat", { method: "POST", body: payload });

  // frontend/lib/api.js (example wrapper)
export async function postChat(apiBase, payload) {
  const res = await fetch(`${apiBase}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`chat failed: ${res.status}`);
  const data = await res.json();

  // If backend produced a new run, switch UI selection
  // lib/api.js inside postChat(...)
  const newRunId = data?.references?.new_run_id;
  if (newRunId && data?.references?.should_switch_run) {
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('pipewise:switch-run', { detail: { runId: newRunId } }));
    }
  } else {
    const rid = data?.references?.run_id;
    if (rid && data?.references?.should_switch_run) {
      if (typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent('pipewise:switch-run', { detail: { runId: rid } }));
      }
    }
  }
  return data;
}