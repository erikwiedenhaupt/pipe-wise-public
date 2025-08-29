Here’s a polished, good-looking version of your README that uses clear hierarchy, spacing, and some visual polish to make it easier to skim.

```markdown
# 🌐 Pipewise – LLM-Assisted Pandapipes Analysis

Pipewise is a **full-stack application** that helps non-technical users understand and improve gas/heat networks modeled in **pandapipes**.  

It combines:

- 🎨 **Frontend**: Next.js + Tailwind UI with chat & visualization  
- ⚡ **Backend**: FastAPI with sandboxed pandapipes execution, KPIs, diagnostics, and Azure OpenAI agents  
- 💾 **Storage**: SQLite + JSON artifacts for reproducible runs and audits  

---

## ✨ Key Capabilities

- 🔒 Run pandapipes code safely in a sandbox and persist artifacts  
- 📊 Compute KPIs and detect issues (e.g., high velocities, low pressures)  
- 🤖 LLM assistant that calls tools (`simulate`, `get_kpis`, `diagnose`, `auto-fix`) and produces **plain-language summaries**  
- 🛠️ Code mutation tools (increase diameter, bump ext_grid pressure, set fluid, etc.)  
- 🔄 Iterative auto-fix workflows (e.g., target velocity)  
- 📈 Scenario sweeps to explore parameter spaces  
- 🧩 Developer-friendly tool registry and agent supervisor  

---

## 📂 Repository Structure

```

backend/
agents/        # Agent modules (simulate, KPI, diagnostics, optimize, toolsmith)
api/           # FastAPI routers
core/          # Storage, tool registry, sandbox, orchestrator, WS debugging
tools/         # Pandapipes runner, KPI calc, issue detection, mutations, scenarios
frontend/
components/    # React components
lib/           # API helpers
pages/         # Next.js pages (UI flows, chat)
styles/        # Tailwind styles
.git-hidden/     # Ignored data

````

---

## 🏗️ Architecture

**High-level flow:**
1. User creates a project and saves network code (version).  
2. Simulation runs in a sandboxed subprocess.  
3. Backend stores artifacts (design/results tables + summary).  
4. KPIs & issues derived from artifacts.  
5. LLM chat orchestrates tool calls + compaction → generates clear answer.  

**Security:**  
- Subprocess with CPU/memory/time limits  
- Artifacts & scratch space stored under `/tmp/pipewise_storage`  

**Azure OpenAI:**  
- Uses Chat Completions API with tool calling  
- Fallback to compact summaries if content filters trigger  
- Token budgets optimized to avoid context overflow  

---

## 🚀 Quick Start

### Prerequisites
- Docker & Docker Compose  
- Node 18+ (if running frontend locally)  
- Python 3.11+ (if running backend locally)  
- Azure OpenAI deployment (model name + API version)  

### Environment Variables

| Name                      | Required | Default               | Description |
|---------------------------|----------|-----------------------|-------------|
| `AZURE_OPENAI_ENDPOINT`   | ✅ yes   | —                     | API endpoint (e.g. `https://your-resource.openai.azure.com`) |
| `AZURE_OPENAI_API_KEY`    | ✅ yes   | —                     | Azure API key |
| `AZURE_OPENAI_API_VERSION`| ✅ yes   | `2025-04-01-preview`  | API version |
| `AZURE_OPENAI_DEPLOYMENT` | ✅ yes   | —                     | Model name (e.g., `gpt-5`) |
| `PIPEWISE_STORAGE_PATH`   | ❌ no    | `/tmp/pipewise_storage` | DB + artifact storage |
| `PIPEWISE_API_VERSION`    | ❌ no    | `v1`                  | Reported API version |
| `PIPEWISE_VERSION`        | ❌ no    | `0.1.0`               | Service version |

**Frontend config (`frontend/.env.local`):**
```bash
NEXT_PUBLIC_API_BASE=http://localhost:8000/api
````

### Run with Docker Compose

```bash
docker compose up --build
```

* Backend → [http://localhost:8000](http://localhost:8000) (docs at `/docs`)
* Frontend → [http://localhost:3000](http://localhost:3000)

### Local Dev (separate terminals)

**Backend**

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**Frontend**

```bash
cd frontend
npm install
npm run dev
```

---

## 🔄 Core Workflows

### 1) Create Project & Version

```bash
curl -X POST http://localhost:8000/api/projects \
  -H "Content-Type: application/json" \
  -d '{}'
```

Save version with pandapipes code:

```bash
curl -X POST http://localhost:8000/api/projects/<PROJECT_ID>/versions \
  -H "Content-Type: application/json" \
  -d '{"code":"...", "meta":{"label":"v1"}}'
```

---

### 2) Run Simulation

```bash
curl -X POST http://localhost:8000/api/simulate \
  -H "Content-Type: application/json" \
  -d '{"project_id":"<PROJECT_ID>", "version_id":"<VERSION_ID>"}'
```

Artifacts → `/tmp/pipewise_storage/artifacts_<RUN_ID>.json`

---

### 3) Inspect KPIs & Issues

```bash
curl http://localhost:8000/api/runs/<RUN_ID>/kpis
curl http://localhost:8000/api/runs/<RUN_ID>/issues
```

---

### 4) Chat Assistant

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "project_id":"<PROJECT_ID>",
    "version_id":"<VERSION_ID>",
    "run_id":"<RUN_ID>",
    "message":"Summarize for a non-technical audience",
    "context":{"audience":"novice"}
  }'
```

Debug LLM with:

```bash
ws://localhost:8000/api/chat/ws/debug/<PROJECT_ID>
```

---

### 5) Auto-Fix Velocity

Ask: *“Fix max velocity to 12 m/s”*
→ Assistant runs iterative diameter scaling / pressure bump until target is met.

---

### 6) Modify Code Explicitly

```bash
curl -X POST http://localhost:8000/api/modify \
  -H "Content-Type: application/json" \
  -d '{ "code_or_version": {"code":"..."}, "actions": [{"type":"scale_diameter", "factor": 1.12}] }'
```

---

### 7) Scenario Sweep

```bash
curl -X POST http://localhost:8000/api/scenario-sweep \
  -H "Content-Type: application/json" \
  -d '{ "code_or_version":{"code":"..."}, "parameters":[{"name":"diameter","values":[0.08,0.10,0.12]}] }'
```

---

## 🧰 LLM Chat Tools

| Tool            | Purpose                         |
| --------------- | ------------------------------- |
| `simulate`      | Run pandapipes & save artifacts |
| `get_kpis`      | Compute KPIs from artifacts     |
| `get_issues`    | Detect issues & suggest fixes   |
| `modify_code`   | Apply textual mutations to code |
| `fix_issues`    | Auto-resolve issues (iterative) |
| `validate_code` | Static pandapipes code checks   |
| `list_tools`    | List registered tools           |

---

## 📝 Pandapipes Example

```python
import pandapipes as pp

net = pp.create_empty_network(fluid="lgas")

j1 = pp.create_junction(net, pn_bar=5.0, tfluid_k=293.15, name="J1")
j2 = pp.create_junction(net, pn_bar=5.0, tfluid_k=293.15, name="J2")

pp.create_ext_grid(net, junction=j1, p_bar=5.0, t_k=293.15, name="Grid")
pp.create_sink(net, junction=j2, mdot_kg_per_s=2.0, name="Demand")

pp.create_pipe_from_parameters(
    net, from_junction=j1, to_junction=j2,
    length_km=0.2, diameter_m=0.100, k_mm=0.1, name="P0"
)
```

---

## 🛠️ Troubleshooting

* **`no_code` error** → Ensure `source_code` is embedded in artifacts
* **Azure `content_filter` block** → Pipewise retries with sanitized compact summary
* **Empty responses** → Large code, context overflow → tool payloads are compacted
* **CORS/404 from frontend** → Check `NEXT_PUBLIC_API_BASE` points to backend `/api`
* **Sandbox too strict** → Adjust `core/security.py` limits

---

## 🔧 Customization

* **Models** → Use a larger-context Azure OpenAI model for big codebases
* **Prompts** → Edit `SYSTEM_PROMPT_BASE` + styles in `routes_chat.py`
* **Diagnostics** → Update KPI thresholds in `kpi_calculator.py` & `issue_detector.py`
* **Mutations** → Extend `network_mutations.py` with new actions
* **Scenarios** → Add combinatorics in `scenario_engine.py`

---

## 🗺️ Roadmap

* Interactive graph overlays & KPI visualization
* Streaming chat + live tool progress in UI
* Scenario reports & Pareto front analysis
* Multi-run comparisons & regression checks
* Fine-grained mutation selectors (by ID/tag)
* Audit logs & stronger policy handling

---



Would you like me to also generate **badges (Docker, Node, Python, License, etc.)** at the top so it looks like a polished open-source project on GitHub?
```
