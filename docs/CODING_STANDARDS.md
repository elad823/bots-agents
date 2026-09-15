# Engineering & Coding Standards
## Project: Autonomous Multi-Agent System (MAS) & Visual Control Plane

### 1. Architectural Principles & SOLID Guidelines

To ensure the Multi-Agent System remains robust, testable, and maintainable, all codebase contributions must adhere strictly to **SOLID** object-oriented and functional architecture principles:

1. **Single Responsibility Principle (SRP):**
   - Each module, class, or function must have one, and only one, reason to change.
   - Example: An agent repository handles database queries for agents. It must **never** invoke LLMs or validate HTTP payloads.
2. **Open/Closed Principle (OCP):**
   - Classes and graph components must be open for extension but closed for modification.
   - Adding a new agent or tool should not require rewriting the core graph execution engine; it must dynamically register into existing abstractions.
3. **Liskov Substitution Principle (LSP):**
   - Any worker agent abstraction must satisfy the unified agent protocol (`BaseWorkerAgent`), ensuring interchangeable invocation across the LangGraph network.
4. **Interface Segregation Principle (ISP):**
   - Clients (e.g., Streamlit, Background Worker) must not depend on interfaces or endpoints they do not use. Interfaces and Pydantic schemas must be lean and role-specific.
5. **Dependency Inversion Principle (DIP):**
   - High-level policy (e.g., `ChatService`, `SupervisorEngine`) must depend on abstractions (interfaces, base classes), not low-level SQLite drivers or external SDK implementations directly.

---

### 2. Strict Separation of Concerns (Layered Architecture)

The codebase strictly enforces four distinct tiers of responsibility. Data flows downwards; dependencies point inwards:

```
[ Frontend: Streamlit App ]
            │ HTTP (httpx)
            ▼
[ API Layer: FastAPI Routers ]
   - Path operations, request parsing, response model validation, HTTP exceptions.
   - NO business logic or SQL statements permitted here.
            │
            ▼
[ Service Layer: Orchestration & Domain Logic ]
   - LangGraph coordinator, agent lifecycle, task scheduling, supervisor reasoning.
   - Coordinates between Repositories and the LLM Gateway.
            │
            ▼
[ Data Access Layer: Repositories (SQLite) ]
   - Parameterized SQL queries, transactions, row-to-model mapping.
   - NO business logic or LLM calls permitted here.
            │
            ▼
[ Infrastructure: Resilient LLM Gateway ]
   - Gemini API wrappers, sliding-window rate limiters, Tenacity retries.
```

---

### 3. Strict Python 3.11+ Type Hinting (`typing`)

1. **No Untyped Signatures:**
   - Every function and method must declare type annotations for all parameters and explicit return types (`-> ReturnType` or `-> None`).
   - The use of raw `Any` is strictly forbidden unless dealing with untyped 3rd-party outputs, and even then, must be accompanied by an explanatory comment or cast.
2. **Modern Typing Constructs:**
   - Use Python 3.11+ built-in generic syntax: `list[str]` instead of `typing.List[str]`, `dict[str, Any]` instead of `typing.Dict`.
   - Use union operator syntax `T | None` instead of `Optional[T]`.
   - Utilize `TypedDict` for LangGraph agent states.
   - Utilize `Literal` for constrained string enumerations (e.g., status: `Literal["idle", "running", "error"]`).
   - Use `Protocol` from `typing` for structural subtyping and interface decoupling.
3. **Pydantic V2 Models:**
   - All external API request and response data must be modeled using Pydantic `BaseModel` with explicit field validations (`Field(...)`).

Example:
```python
from typing import Literal, Protocol
from pydantic import BaseModel, Field

class AgentStatus(BaseModel):
    agent_id: str = Field(..., description="Unique UUID for the agent")
    slug: str = Field(..., pattern="^[a-z0-9_]+$")
    status: Literal["idle", "running", "error"]
    requests_remaining: int = Field(ge=0, le=14)

class LLMProviderProtocol(Protocol):
    async def generate_response(self, prompt: str, system_prompt: str | None = None) -> str:
        ...
```

---

### 4. Asynchronous Programming (`asyncio`, `httpx`)

1. **Non-Blocking Execution:**
   - All I/O operations (FastAPI endpoints, LangGraph node calls, LLM requests, SQLite reads/writes) must be non-blocking using `async` / `await`.
   - SQLite queries must be dispatched via `aiosqlite` or executed in a threadpool executor via `asyncio.to_thread` to prevent event loop blocking.
2. **HTTP Client Best Practices:**
   - Use `httpx.AsyncClient` with proper connection pooling and timeouts for all external HTTP communication.
   - Always manage clients via asynchronous context managers or app lifespans to prevent socket leaks.
3. **Background Tasks & Concurrency:**
   - Scheduled tasks run concurrently without blocking the main event loop.
   - Use `asyncio.Lock` or semaphores when modifying shared state (e.g., the rate limiter's sliding window timestamps).

---

### 5. Centralized Error Handling & Logging

1. **Custom Exception Hierarchy:**
   All domain-level errors inherit from a base `MASException`:
   ```python
   class MASException(Exception):
       """Base exception for all MAS errors."""
       def __init__(self, message: str, details: dict | None = None):
           super().__init__(message)
           self.details = details or {}

   class RateLimitExceededException(MASException):
       """Raised when client-side or upstream 15 RPM limit is breached."""
       pass

   class AgentNotFoundException(MASException):
       """Raised when an agent slug or ID cannot be located."""
       pass

   class GraphExecutionException(MASException):
       """Raised when LangGraph supervisor/worker encounters an unrecoverable failure."""
       pass
   ```

2. **Consistent API Error Responses:**
   FastAPI exception handlers map domain exceptions to RFC 7807 compliant JSON envelopes:
   ```json
   {
     "error": "RateLimitExceeded",
     "message": "Gemini 15 RPM threshold reached. Backing off.",
     "details": {
       "retry_after_seconds": 12,
       "current_window_requests": 14
     }
   }
   ```

3. **Structured Logging:**
   - Use standard `logging` with a structured format (Timestamp, Level, Logger, Correlation ID/Session ID, Message).
   - Log all agent transitions (e.g., `Supervisor -> Delegating to: Researcher`), rate-limit waits, and background job triggers.

---

### 6. LLM Rate-Limit Compliance (Gemini 15 RPM Rules)

1. **Sliding-Window Guard:**
   - Never dispatch an LLM call directly to Gemini without passing through `RateLimiter.acquire()`.
   - The sliding-window algorithm monitors timestamps in the last 60 seconds. If `count >= 14`, the coroutine sleeps until the slot frees.
2. **Tenacity Retry Configuration:**
   - Catch `GoogleAPIError`, `ResourceExhausted` (429), and connection resets.
   - Retries must employ exponential backoff with random jitter:
     ```python
     @retry(
         reraise=True,
         stop=stop_after_attempt(5),
         wait=wait_exponential(multiplier=2, min=5, max=60) + wait_random(0, 2),
         retry=retry_if_exception_type(TransientLLMException)
     )
     async def call_gemini(...):
         ...
     ```

---

### 7. Testing & Quality Assurance Standards

1. **Unit & Integration Testing:**
   - Tests live in `/tests` and run using `pytest` and `pytest-asyncio`.
   - Repository tests use in-memory SQLite (`:memory:`) to guarantee isolation and zero filesystem residue.
   - LLM Gateway tests mock Google AI Studio responses to ensure unit tests run instantly and never consume the 15 RPM quota.
2. **Clean Code & Formatting:**
   - Follow PEP 8 guidelines.
   - Target line length: 100 characters.
   - Self-documenting code: docstrings for public classes and methods outlining parameters, return values, and exceptions raised.
