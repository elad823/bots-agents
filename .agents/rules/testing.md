# Rule: Testing Protocol

## 1. Test Framework
- Use `pytest` and `pytest-asyncio` for all automated testing.
- Tests reside in `/tests` with naming convention `test_<module_name>.py`.

## 2. Mocking & Isolation
- **LLM Gateway Mocking**: Never invoke live Google AI Studio endpoints in automated tests to prevent burning the 15 RPM quota. Mock `GeminiClientWrapper` outputs using test fixtures.
- **In-Memory SQLite**: Repositories must be tested using SQLite in-memory databases (`:memory:`) with table schemas initialized fresh per test fixture.

## 3. Coverage & Verification Requirements
- **Pre-Flight Security Audit**: Run `python3 scripts/validate_secrets.py` to ensure zero exposed credentials, API keys, or uncommitted `.env` files.
- **Rate-Limiter**: Verify sliding window behavior under high concurrent load (e.g. 20 concurrent coroutines).
- **Multi-Agent Supervisor**: Verify LangGraph supervisor routing logic: `FINISH`, `worker_<slug>`, and `create_agent`.
- **Scheduler**: Verify background task execution and run status updates.
- **E2E & Container Persistence**: Verify SQLite data retention across container/database re-inits (`test_e2e_persistence.py`).
- **E2E Pipeline Integration**: Verify full lifecycle promotion and multi-agent execution pipeline (`test_e2e_pipeline.py`).
- **Runner**: Execute via `.venv/bin/python run_tests.py` or `pytest tests/` (all 17 tests must pass).

