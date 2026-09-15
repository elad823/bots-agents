# Autonomous Multi-Agent System (MAS) & Visual Control Plane

An autonomous Multi-Agent System inspired by **Grok**, built with **Python 3.11+**, **LangGraph** (Supervisor-Worker architecture), **FastAPI**, **Streamlit**, and **SQLite (WAL mode)**, guarded by a centralized **15 RPM Rate Limiter** for the Google AI Studio (Gemini 1.5 Pro/Flash) free tier.

---

## 🚀 Key Features
- **Dynamic Agent Spawning**: The Supervisor analyzes user intent and dynamically creates, configures, and registers specialized domain agents on the fly in SQLite.
- **Visual Control Plane (Streamlit)**:
  - Sidebar with real-time status indicators: 🟢 **Idle**, 🟠 **Running / Thinking**, 🔴 **Error / Backoff**.
  - Multi-Agent Chat Console with visual delegation breadcrumbs.
  - Autonomous Background Task Manager (Cron & Interval schedules).
  - Agent Forge for inspecting and crafting custom agents.
- **Autonomous Scheduling**: APScheduler / AsyncIO background runner executes cron and interval agent tasks without an active browser session, logging outputs to `task_runs`.
- **15 RPM Rate Limiting & Resilience**: Sliding-window rate limiter (max 14 requests/min) and `tenacity` exponential backoff protect against HTTP 429 errors.
- **Zero-Cost Production Ready**: Designed for deployment on **Google Cloud Run** (free tier backend) and **Streamlit Community Cloud** (free frontend).
- **Persistent State**: Docker volume (`mas_sqlite_data`) and Cloud Storage FUSE ensure SQLite state is never lost on container restarts.

---

## 📁 Project Architecture & Antigravity Structure

```
bots-agents/
├── GEMINI.md                        # Project context loaded at session start
├── mcp_config.json                  # Root MCP tool integration configuration
├── .github/
│   └── workflows/                   # GitHub Actions CI/CD automation pipelines
│       ├── ci.yml                   # Automated tests, linting, and secret scanner
│       ├── deploy-staging.yml       # Staging deployment workflow
│       └── deploy-prod.yml          # Production deployment workflow
├── .agents/                         # Antigravity project customization suite
│   ├── settings.json                # Model selection & guardrails
│   ├── rules/                       # Modular rules (code-style, testing, rate-limiting)
│   ├── workflows/                   # Repeatable workflows (review.md, fix-issue.md)
│   ├── skills/                      # On-demand skills (deploy/SKILL.md)
│   ├── subagents/                   # Sub-agent personas (code-reviewer, security-auditor)
│   ├── hooks.json                   # Tool lifecycle hooks
│   └── hooks/validate-bash.sh       # Shell safety validator
├── docs/
│   ├── PRD.md                       # Product Requirements Document
│   ├── ARCHITECTURE.md              # System architecture & SQLite DDL
│   ├── CODING_STANDARDS.md          # Engineering standards
│   └── DEPLOYMENT.md                # Docker & Zero-Cost Cloud Deployment Guide
├── backend/                         # FastAPI backend & LangGraph engine
│   ├── Dockerfile
│   ├── main.py                      # FastAPI app entrypoint & lifespan
│   ├── core/                        # Config, WAL SQLite database, 15 RPM rate limiter, LLM gateway
│   ├── models/                      # Pydantic schemas (Agent, Message, Task)
│   ├── repositories/                # SQLite data access layer
│   ├── services/                    # Agent service, chat coordinator, scheduler, LangGraph engine
│   └── api/                         # REST routers (agents, chat, tasks, system)
├── frontend/                        # Streamlit visual control dashboard
│   ├── Dockerfile
│   ├── app.py                       # Main Streamlit dashboard
│   ├── components/                  # Sidebar, Chat console, Scheduler view, Agent forge
│   └── utils/api_client.py          # Backend HTTP client
├── scripts/                         # Automation & DevOps tooling
│   ├── validate_secrets.py          # Pre-flight secret leak detection scanner
│   ├── deploy_staging.sh            # Staging Cloud Run deployment script
│   └── deploy_prod.sh               # Production Cloud Run deployment script
├── tests/                           # Complete test suite (17 unit, integration, and e2e tests)
├── data/                            # Persistent SQLite database store
├── docker-compose.yml               # Local multi-container orchestration
├── .env.example                     # Local development environment template
├── .env.staging.example             # Staging environment template
├── .env.production.example          # Production environment template
├── requirements.txt
└── run_tests.py                     # Self-contained test suite runner
```

---

## ⚡ Quickstart

### 1. Environment Setup
Copy the environment template and configure your Google AI Studio API key:
```bash
cp .env.example .env
# Edit .env and set GEMINI_API_KEY=your_actual_key
```
*(Note: If left as `mock_dev_key`, the system automatically runs in high-fidelity mock mode, perfect for offline development and testing).*

### 2. Run Automated Test Suite & Pre-Flight Secret Scanner
Validate that your codebase has zero secret leaks and all 17 unit, integration, and E2E pipeline tests pass:
```bash
# Run security & secret leak audit
python3 scripts/validate_secrets.py

# Run complete 17-test suite (using virtual environment)
.venv/bin/python run_tests.py
# Or with system python if dependencies are installed:
python3 run_tests.py
```

### 3. Run Locally (Direct)
**Start Backend (Terminal 1):**
```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```
API Documentation will be available at: `http://localhost:8000/docs`.

**Start Frontend (Terminal 2):**
```bash
streamlit run frontend/app.py --server.port 8501
```
Visual Dashboard will open at: `http://localhost:8501`.

---

## 🐳 Docker & Docker Compose Orchestration

Run both backend and frontend in isolated containers with persistent named volume:
```bash
docker compose up --build -d
```
- **Streamlit Control Plane**: `http://localhost:8501`
- **FastAPI API & Docs**: `http://localhost:8000/docs`
- **Volume Persistence**: Data resides in `mas_sqlite_data` and persists across container stops and restarts.

Stop containers:
```bash
docker compose down
```

---

## 🔄 CI/CD Pipeline & Remote DevOps Automation

The project includes an enterprise-grade, automated CI/CD lifecycle powered by **GitHub Actions** and strict security protocols:

### Workflows Overview
- **`.github/workflows/ci.yml`**: Triggers on every push or pull request to `main` and `feature/*`.
  - Enforces automated security scanning via `scripts/validate_secrets.py`.
  - Executes flake8 syntax/style validation.
  - Runs all 17 unit, integration, and E2E pipeline tests.
  - Uploads code coverage reports.
- **`.github/workflows/deploy-staging.yml`**: Continuous Deployment to the Cloud Run Staging environment on pushes to `feature/*` or manual dispatch.
- **`.github/workflows/deploy-prod.yml`**: Zero-downtime Continuous Deployment to Cloud Run Production upon release tags or merges to `main`.

### Remote Work Security & Secret Protection
- **Zero-Commit Policy**: Secrets (`.env`, `*.key`, `*credentials*.json`) are excluded via `.gitignore`.
- **Pre-Flight Scanner**: `scripts/validate_secrets.py` blocks any commit or CI build containing exposed Google AI Studio keys, GCP service account credentials, or private keys.
- **GitHub Secrets Configuration**: Deployment environments utilize isolated GitHub Environment secrets (`GEMINI_API_KEY`, `GCP_PROJECT_ID`, `GCP_SA_KEY`).

---

## ☁️ Zero-Cost Cloud Deployment Guide

See **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)** for complete step-by-step instructions:
1. **FastAPI Backend on Google Cloud Run**:
   - Zero-cost within Cloud Run's free tier (2M requests/month, 360k vCPU-seconds).
   - Mount a free Google Cloud Storage bucket (5GB free) via Cloud Run Volume Mount (GCS FUSE) to persist `/app/data/mas_database.db`.
2. **Frontend on Streamlit Community Cloud**:
   - Connect your GitHub repository at [share.streamlit.io](https://share.streamlit.io/).
   - Add Secret `BACKEND_API_URL = "https://your-cloud-run-service.a.run.app"`.

