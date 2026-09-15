# Antigravity & Gemini Project Context: Autonomous MAS

Welcome to the **Autonomous Multi-Agent System (MAS)** project workspace. This file (`GEMINI.md`) is loaded automatically at the start of every Antigravity / Gemini session to establish project scope, technical constraints, coding standards, and operational guidelines.

---

## 1. Project Overview & Tech Stack
- **System**: Local, autonomous Multi-Agent System with a visual control plane inspired by "Grok".
- **LLM Engine**: Google AI Studio (Gemini 1.5 Pro / Flash) with strict client-side **15 RPM free tier rate limiting**.
- **Backend**: Python 3.11+, FastAPI (REST API & background lifespan).
- **Multi-Agent Orchestration**: LangGraph (Supervisor architecture, dynamic agent spawning, and routing).
- **Frontend / Dashboard**: Streamlit (Visual control plane, live status indicators 🟢 Idle / 🟠 Running / 🔴 Error, task manager).
- **Database / State**: SQLite with Write-Ahead Logging (`WAL` mode) in `data/mas_database.db`.
- **Background Tasks**: APScheduler (`AsyncIOScheduler`) for autonomous recurring cron and interval jobs.
- **Infrastructure**: Docker, `docker-compose.yml` with named persistent volume `mas_sqlite_data`, zero-cost deployment to Google Cloud Run & Streamlit Community Cloud.

---

## 2. Mandatory Rules & Architectural Invariants
1. **Gemini 15 RPM Compliance**: Every outbound LLM call MUST pass through the centralized `RateLimiter` sliding window (max 14 requests/min) and retry with `tenacity` exponential backoff on HTTP 429.
2. **Strict Layered Separation**:
   - `Routes` (FastAPI endpoints only, input parsing, HTTP status codes)
   - `Services` (Business logic, LangGraph supervisor, agent spawning, scheduler)
   - `Repositories` (SQLite data access via `aiosqlite`, parameterized queries, transactions)
   - `LLM Gateway` (Gemini API clients, rate limit guards, retries)
3. **Strict Python Typing**: Full type annotations (`typing`, `list[...]`, `T | None`, `TypedDict`, Pydantic V2 models). Zero untyped function signatures.
4. **Non-Blocking Asynchronous Code**: Use `async`/`await` for all I/O, database access, and HTTP requests (`httpx.AsyncClient`).
5. **Persistent State**: Never write SQLite data to ephemeral container directories; always store in `/app/data` backed by persistent volume.

---

## 3. Project Configuration & Tooling
- **Project Rules**: Located in `.agents/rules/` (`code-style.md`, `testing.md`, `api-conventions.md`, `rate-limiting.md`).
- **Skills**: Located in `.agents/skills/` (e.g., `deploy/SKILL.md`).
- **Hooks**: Lifecycle hooks configured in `.agents/hooks.json` and `.agents/hooks/`.
- **MCP Servers**: Configured in `.agents/mcp_config.json`.
- **Documentation**: Comprehensive specs in `docs/` (`PRD.md`, `ARCHITECTURE.md`, `CODING_STANDARDS.md`, `DEPLOYMENT.md`).
