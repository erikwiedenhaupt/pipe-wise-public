
# Pipe-Wise

**Pipe-Wise** is a tool for creating, analyzing, and interacting with **Panda-Pipes networks**. It combines a **frontend** (Next.js) for uploads and chat with a **backend** (FastAPI) for analysis and communication with an LLM agent.

---

## 📝 Features

* Create or upload Panda-Pipes networks
* Analysis by an LLM agent (via OpenAI GPT API)
* Interactive chat interface for discussing the network structure
* Detection of potential weaknesses in the network
* Hot-reload for rapid development in both frontend and backend

---

## ⚙️ Architecture

```
Pipe-Wise
│
├─ frontend/          # Next.js App (Upload + Chat)
│   ├─ pages/
│   ├─ components/
│   ├─ package.json
│   └─ Dockerfile
│
├─ backend/           # FastAPI API (Upload, Analysis)
│   ├─ main.py
│   ├─ requirements.txt
│   ├─ .env           # API Keys, Configuration (do not commit!)
│   └─ Dockerfile
│
└─ docker-compose.yml
```

---

## 🚀 Installation & Usage

### 1. Prerequisites

* Docker & Docker Compose
* Node.js / npm (for local frontend development)
* Git

---

### 2. Clone the repository

```bash
git clone https://github.com/<USERNAME>/pipe-wise.git
cd pipe-wise
```

---

### 3. Create a `.env` file

In the `backend/` directory:

```bash
cd backend
nano .env
```

Example `.env`:

```
OPENAI_API_KEY=your_api_key_here
OPENAI_API_ENDPOINT=https://fhgenie-api-ieg-fred-ieg.openai.azure.com/
MODEL=gpt-4o-mini-2024-07-18
```

> ⚠️ Never commit this file to GitHub

---

### 4. Start Docker containers

From the root directory:

```bash
docker-compose up -d --build
```

* `-d` → run in background
* `--build` → rebuild images (needed after code changes)

### 5. Access

* **Frontend:** `http://<VPS-IP>:3000`
* **Backend API & Docs:** `http://<VPS-IP>:8000` and `http://<VPS-IP>:8000/docs`

---

### 6. Hot-Reload

* Frontend: changes in `frontend/` are automatically reloaded
* Backend: changes in `backend/` are automatically reloaded with `uvicorn --reload`

---

### 7. LLM Integration

* Backend communicates with the OpenAI GPT API using `.env` configuration
* LLM agent can analyze networks, provide comments, and detect weaknesses

---

### 8. Development

#### Local testing without Docker

Frontend:

```bash
cd frontend
npm install
npm run dev -- -H 0.0.0.0 -p 3000
```

Backend:

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

---

### 9. Git Workflow

1. Create a branch:

```bash
git checkout -b feature/<feature-name>
```

2. Commit changes:

```bash
git add .
git commit -m "Description of changes"
git push origin feature/<feature-name>
```

3. Open a Pull Request → Review → Merge

---

### 10. Notes

* Ports `3000` (frontend) and `8000` (backend) must be open on the VPS
* `.env` must not be public


