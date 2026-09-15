# Rule: API Conventions & Error Formats

## 1. RESTful Standards
- Resource naming uses plural nouns (e.g., `/api/agents`, `/api/tasks`).
- Standard status codes:
  - `200 OK`: Successful retrieval or update.
  - `201 Created`: Successful creation of agent or task.
  - `400 Bad Request`: Payload validation or parameter failure.
  - `404 Not Found`: Target entity not found in SQLite.
  - `429 Too Many Requests`: Upstream rate limit backoff triggered.
  - `500 Internal Server Error`: Unhandled server exception.

## 2. Standardized Error Response Envelope
All error responses adhere to the standard JSON structure:
```json
{
  "error": "ErrorType",
  "message": "Human readable summary",
  "details": {}
}
```

## 3. Pydantic Schemas
- Separate `Create`, `Update`, and `Response` schemas for domain entities (e.g. `AgentCreate`, `AgentUpdate`, `AgentResponse`).
- Validate inputs strictly using Pydantic V2 `Field(...)` validators.
