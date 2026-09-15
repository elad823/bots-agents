# Workflow: Systematic Issue Diagnosis & Fix

Use this workflow to diagnose and resolve bugs across the MAS stack.

## Execution Steps

1. **Locate Logs & Stack Traces**:
   - Check SQLite `task_runs` for background job error messages.
   - Inspect FastAPI server logs or Streamlit session state logs.
2. **Reproduce in Isolation**:
   - Write a minimal failing test case in `tests/` isolating the repository, rate limiter, or graph node.
3. **Apply Minimal Targeted Fix**:
   - Update the code adhering strictly to `docs/CODING_STANDARDS.md`.
4. **Regression Verification**:
   - Run `pytest tests/` to ensure no regressions were introduced.
