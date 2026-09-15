# Rule: Gemini 15 RPM Rate Limiting & Resilience

## 1. Golden Constraint: 15 Requests Per Minute (RPM)
Google AI Studio free tier limits API accounts to 15 RPM. To ensure zero HTTP 429 disruptions:
- **Client Threshold**: Limit outbound invocations to a maximum of **14 calls per 60-second sliding window**.
- **Central Gateway**: All Gemini calls (LangGraph nodes, Supervisor, Worker agents) must route through `RateLimiter.acquire()`.

## 2. Exponential Backoff & Jitter
- When a 429 `ResourceExhausted` error is encountered upstream:
  - Retry automatically using `tenacity`.
  - Backoff policy: exponential backoff starting at 5s, doubling up to 60s, with a random 0-2s jitter.
  - Set agent status in SQLite to `cooling_down` so the dashboard displays real-time rate limit wait states.
