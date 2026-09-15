# Rule: Testing Protocol

## 1. Test Framework
- Use `pytest` and `pytest-asyncio` for all automated testing.
- Tests reside in `/tests` with naming convention `test_<module_name>.py`.

## 2. Mocking & Isolation
- **LLM Gateway Mocking**: Never invoke live Google AI Studio endpoints in automated tests to prevent burning the 15 RPM quota. Mock `GeminiClientWrapper` outputs using test fixtures.
- **In-Memory SQLite**: Repositories must be tested using SQLite in-memory databases (`:memory:`) with table schemas initialized fresh per test fixture.

## 3. Coverage Requirements
- Verify rate-limiter sliding window behavior under high concurrent load (e.g. 20 concurrent coroutines).
- Verify LangGraph supervisor routing logic: `FINISH`, `worker_<slug>`, and `create_agent`.
- Verify background task execution and run status updates.
