Perfect — thanks for the context! Since this README is for the **public GitHub version** of your thesis project, I’ll:

* Keep the **academic tone** (since it’s part of your seminar paper).
* Include your **abstract** and **access note** explicitly.
* Add **badges** and visuals for GitHub readability.
* Integrate your **Quick Start (Appendix P)** cleanly under setup instructions.
* Keep everything markdown-compatible for GitHub’s renderer (including code, tables, and links).

Here’s your **polished, badge-ready README.md** for `pipe-wise-public` 👇

---

# 🧠 Pipe-Wise — Digital AI Twin for Urban Infrastructure

**Seminar Thesis — Development of a Digital AI Twin for Urban Infrastructure**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](./LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-green.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker\&logoColor=white)](https://www.docker.com/)
[![FastAPI](https://img.shields.io/badge/FastAPI-Backend-009688?logo=fastapi\&logoColor=white)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Next.js-Frontend-000000?logo=next.js\&logoColor=white)](https://nextjs.org/)

> *“Urban pipe networks react in subtle, nonlinear ways — a small pressure tweak here, a flow shift there. Pipe-Wise turns that complexity into a transparent, conversational digital twin.”*

---

## 🧩 Abstract

Urban pipe networks — natural gas, hydrogen, heat, and water — react in subtle ways to small changes: widen one segment or nudge inlet pressure, and pressures and velocities shift across the map.

This thesis presents a conversational **Digital AI Twin** that lets a user describe goals in natural language and then watches the system carry out careful, traceable steps:
validate code, simulate safely, read KPIs, detect issues, and apply modest edits.

The twin is built on **PandaPipes** and can switch fluids (natural gas, hydrogen, heat, water) without changing orchestration. Multiple cooperating agents — **Supervisor, Compliance, Sandbox, Physics, Toolsmith, Cost, and Critic-Memory** — each plan, execute, score, and learn locally while contributing to a shared optimization plan.

Across runs, the AI twin learns from score deltas and agent feedback, adapting its behavior to reduce iterations and sharpen edits over time.

The largest test conducted is the **Branitz natural-gas network** (4,635 pipes, 4,187 junctions), alongside a **hydrogen microgrid** and a **compact heat loop**.
When using GPT-5 and GPT-5-mini as planners, the system raises simulation success rates significantly:

* Natural gas → **88%** (↑ from 71%)
* Hydrogen → **85%**
* Heat → **92%**

Safety stems from AST/whitelist validation and isolated execution; reproducibility from stored artifacts; observability from a live WebSocket debug channel and an interaction graph.

The work demonstrates that multi-agent orchestration with small, explainable steps leads to practical, physically consistent AI control in urban infrastructure.

---

## 📖 Repository Access

> **Important Access Note**
>
> • **Public repository (current version)** — [pipe-wise-public](https://github.com/erikwiedenhaupt/pipe-wise-public)
>   ↳ This repository hosts the *publicly available* version and may not include the latest internal updates.
>
> • **Latest version (restricted access)** — [pipe-wise](https://github.com/erikwiedenhaupt/pipe-wise)
>   ↳ Contains full networks and supplementary materials. Access available upon request.
>
> • **Contact** — [erik.wiedenhaupt@ieg-extern.fraunhofer.de](mailto:erik.wiedenhaupt@ieg-extern.fraunhofer.de)

---

## 🚀 Overview

**Pipe-Wise** is a **conversational AI twin** for **urban infrastructure simulation**.
It enables natural-language interaction with multi-fluid pipe networks (gas, hydrogen, heat, water) — safely, reproducibly, and observably.

### 🔍 Core Features

| Capability                     | Description                                          |
| ------------------------------ | ---------------------------------------------------- |
| 🧮 **Simulation & Validation** | Safe runs in a sandbox with AST/whitelist validation |
| 🔧 **KPI Tracking**            | Velocity, pressure, Reynolds, Δp, and temperature    |
| 💬 **Conversational Agent**    | LLM-based assistant that diagnoses and fixes issues  |
| 🏗️ **CAPEX Estimation**       | Cost agents estimate regional build expenses         |
| 🧠 **Learning Agents**         | Adaptive improvement from previous runs              |
| 🌐 **Observability**           | Live WebSocket debug + interaction graph             |
| 💾 **Reproducibility**         | Artifacts saved per run for full traceability        |

---

## 🧭 Architecture

```text
Pipe-Wise
│
├─ frontend/          # Next.js UI (Chat, Visual Builder, KPIs, Graph)
│   ├─ components/    # Chat, KPIGrid, IssueList, etc.
│   └─ (Dockerfile.frontend)
│
├─ backend/           # FastAPI API (simulate, validate, chat, memory)
│   ├─ api/           # routes_*.py
│   ├─ core/          # sandbox, storage, security, costs, memory
│   ├─ tools/         # pandapipes_runner, kpi_calculator, etc.
│   ├─ agents/        # Supervisor, Physics, Toolsmith, Cost, Critic
│   └─ (Dockerfile.backend)
│
├─ docker-compose.yml
└─ LICENSE
```

---

## ⚙️ Prerequisites

* 🐳 Docker or Docker Compose (recommended)
* 🟢 Node.js v18 + npm
* 🐍 Python 3.11
* 🔑 Azure OpenAI credentials
* 🔗 Git

---

## 🧪 Quick Start (Docker Recommended)

### 1️⃣ Clone the Repository

```bash
git clone https://github.com/erikwiedenhaupt/pipe-wise-public
cd pipe-wise-public
```

### 2️⃣ Create Backend `.env`

Create `.env` at the repository root (for Docker) or under `backend/.env` (for local runs).
Replace placeholders with your actual Azure OpenAI credentials.
Do **not** commit this file.

```env
AZURE_OPENAI_ENDPOINT=https://YOUR_RESOURCE.openai.azure.com/
AZURE_OPENAI_API_KEY=YOUR_KEY
AZURE_OPENAI_DEPLOYMENT=gpt-4o-mini-2024-07-18
AZURE_OPENAI_API_VERSION=2024-02-15-preview
AZURE_OPENAI_EMBEDDINGS_DEPLOYMENT=text-embedding-3-large
PIPEWISE_CHAT_ENGINE=responses
MEMORY_TOP_K=5
PIPEWISE_AGENT_LEARNING=1
```

### 3️⃣ Create Frontend `.env.local`

```bash
echo "NEXT_PUBLIC_API_BASE=http://localhost:8000/api" > frontend/.env.local
```

### 4️⃣ Build and Run

```bash
docker compose up -d --build
```

**Access:**

* 🌐 Frontend → [http://localhost:3000](http://localhost:3000)
* ⚙️ Backend → [http://localhost:8000](http://localhost:8000)
* 📚 API Docs → [http://localhost:8000/docs](http://localhost:8000/docs)
* 💓 Health → [http://localhost:8000/api/healthz](http://localhost:8000/api/healthz)

---

## 🧩 Local Development (Optional)

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev -- -H 0.0.0.0 -p 3000
```

---

## 📊 API Overview

| Endpoint                | Method   | Purpose                 |
| ----------------------- | -------- | ----------------------- |
| `/api/healthz`          | GET      | Health check            |
| `/api/version`          | GET      | API version             |
| `/api/simulate`         | POST     | Run simulation          |
| `/api/validate`         | POST     | Validate code           |
| `/api/chat`             | POST     | Conversational AI agent |
| `/api/runs/{id}`        | GET      | Retrieve run            |
| `/api/runs/{id}/issues` | GET      | Get issue list          |
| `/api/projects`         | GET/POST | Manage projects         |

---

## 🧠 Academic Context

This repository supports the seminar thesis:

> **Wiedenhaupt, Erik.**
> *“Development of a Digital AI Twin for Urban Infrastructure.”*
> Fraunhofer IEG, 2025.

If you reference this work, please cite both the **thesis title** and the **GitHub repository**.

---

## 🪪 License

Licensed under the **MIT License** — see [`LICENSE`](./LICENSE).

---

## ✨ Roadmap

* [ ] Adaptive target selection via small learning loops
* [ ] Enhanced Δp hotspot diagnostics
* [ ] Multimodal plan/image ingestion
* [ ] Agent-based selector refinement
* [ ] Hybrid reasoning for physical vs. financial constraints

---

💬 **Contact:** [erik.wiedenhaupt@ieg-extern.fraunhofer.de](mailto:erik.wiedenhaupt@ieg-extern.fraunhofer.de)
🔗 **Public Repo:** [https://github.com/erikwiedenhaupt/pipe-wise-public](https://github.com/erikwiedenhaupt/pipe-wise-public)

---

Would you like me to make a **lightweight academic header banner (SVG with title + badges)** to go above the README, so it looks professional on GitHub (like a research project page)?
