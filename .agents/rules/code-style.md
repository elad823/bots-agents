# Rule: Code Style & Architectural Standards

## 1. Python 3.11+ Standards
- Use modern Python type hints on every function: `param: str -> dict[str, Any]`, `val: int | None = None`.
- Never use untyped signatures or raw `Any` without explanation.
- Target line length: 100 characters. Follow PEP 8 naming: `snake_case` for functions/variables, `PascalCase` for classes.

## 2. Layered Architecture (Zero Leaks)
- **Routes (`backend/api/`)**: Handle HTTP requests, parameters, and status codes. Never place SQL queries or LangGraph logic in routes.
- **Services (`backend/services/`)**: Orchestrate agents, workflows, background schedules, and business logic.
- **Repositories (`backend/repositories/`)**: Manage SQLite queries, parameterized SQL statements, and transactions.
- **LLM Gateway (`backend/core/`)**: Mediate all interactions with Google AI Studio via rate limiters and tenacity retries.

## 3. Asynchronous Non-Blocking Execution
- All database I/O, LLM network requests, and background jobs must use `async`/`await`.
- Never block the event loop with synchronous time delays (use `asyncio.sleep()`) or blocking HTTP libraries (use `httpx.AsyncClient`).

## 4. Git Branching & Deployment Rules
- **Task-Specific Branch Naming**: Branches must be named specifically after the task being performed:
  - `feature/<task-name>` (e.g. `feature/staging-cd-prod-manual-gate`)
  - `fix/<bug-name>` (e.g. `fix/rate-limiter-timeout`)
  - `chore/<task-name>` (e.g. `chore/dependency-updates`)
  - `docs/<task-name>` (e.g. `docs/deployment-guide`)
  - *Never use generic names like `test`, `dev`, `my-branch`.*
- **Promotion Flow (Option 1)**:
  - Always work on a task branch and open a PR against `main`.
  - Merging to `main` automatically triggers deployment to **Staging** (`mas-backend-staging`).
  - **Production Guardrail**: Production deployment is **NEVER automatic**, even if all tests pass. Production rollouts require explicit manual dispatch (`workflow_dispatch`) with `DEPLOY_PRODUCTION` confirmation.

