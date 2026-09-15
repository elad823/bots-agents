# Workflow: Code Review & Quality Audit

Use this workflow to review pending code changes against project standards.

## Execution Steps

1. **Verify Strict Typing & Layering**:
   - Check that all functions have complete type annotations.
   - Ensure no SQL queries exist in `backend/api/` and no HTTP logic exists in `backend/repositories/`.
2. **Verify Rate-Limiting Guardrails**:
   - Ensure all LLM calls invoke `RateLimiter.acquire()` before sending requests to Gemini.
   - Check that `tenacity` retry decorators handle `ResourceExhausted` (429).
3. **Run Test Suite**:
   - Execute `pytest tests/` to verify rate-limiter, repository, and supervisor tests pass.
4. **Inspect SQLite Concurrency**:
   - Confirm WAL mode is enabled on connection (`PRAGMA journal_mode=WAL;`).
