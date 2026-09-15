import asyncio
import sys
import os

# Enforce hermetic test mode with mock API key to protect rate limit quota and ensure isolation
os.environ["GEMINI_API_KEY"] = "mock_dev_key"
os.environ["ENVIRONMENT"] = "testing"

# Ensure current directory is on PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from tests.test_rate_limiter import (
    test_rate_limiter_immediate_acquire,
    test_rate_limiter_throttles_when_saturated,
    test_rate_limiter_concurrent_burst,
)
from tests.test_database import (
    test_database_initialization_and_seeding,
)
from tests.test_repositories import (
    test_agent_repository_crud,
    test_message_repository_history,
    test_task_repository_lifecycle,
)
from tests.test_supervisor import (
    test_supervisor_direct_chat,
    test_supervisor_delegation_to_researcher,
    test_dynamic_agent_spawning,
)
from tests.test_scheduler import (
    test_scheduler_manual_trigger,
    test_scheduler_lifecycle,
)
from tests.test_api import (
    test_api_system_and_agents,
    test_api_chat_and_tasks,
)
from tests.test_frontend_client import (
    test_api_client_initialization,
)
from tests.test_e2e_persistence import (
    test_e2e_container_restart_persistence,
)


async def test_e2e_api_pipeline_integration() -> None:
    import subprocess
    import sys
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "pytest", "tests/test_e2e_pipeline.py", "-q",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"E2E Pipeline test suite failed:\n{stdout.decode()}\n{stderr.decode()}")


async def run_all() -> None:
    print("========================================")
    print(" Running MAS Core Infrastructure Tests ")
    print("========================================")

    from backend.core.database import init_database
    await init_database()

    tests = [
        ("Rate Limiter - Immediate Acquire", test_rate_limiter_immediate_acquire),
        ("Rate Limiter - Throttling when Saturated", test_rate_limiter_throttles_when_saturated),
        ("Rate Limiter - Concurrent Burst", test_rate_limiter_concurrent_burst),
        ("Database - Init & Seeding", test_database_initialization_and_seeding),
        ("Repository - Agent CRUD & Constraints", test_agent_repository_crud),
        ("Repository - Message History & Sessions", test_message_repository_history),
        ("Repository - Task Lifecycle & Run Logs", test_task_repository_lifecycle),
        ("Supervisor - Direct Conversational Chat", test_supervisor_direct_chat),
        ("Supervisor - Worker Delegation & Synthesis", test_supervisor_delegation_to_researcher),
        ("Supervisor - Dynamic Agent Spawning & Routing", test_dynamic_agent_spawning),
        ("Scheduler - Manual Autonomous Trigger", test_scheduler_manual_trigger),
        ("Scheduler - Lifecycle Startup & Stop", test_scheduler_lifecycle),
        ("API Routes - System Status & Agents CRUD", test_api_system_and_agents),
        ("API Routes - Chat Dispatch & Tasks Run", test_api_chat_and_tasks),
        ("Frontend - API Client Fallback & Quota", test_api_client_initialization),
        ("E2E Docker Volume - Container Persistence", test_e2e_container_restart_persistence),
        ("E2E Pipeline - Full API & Lifecycle Integration", test_e2e_api_pipeline_integration),
    ]







    passed = 0
    failed = 0

    for name, test_fn in tests:
        print(f"[*] Running: {name} ...", end=" ", flush=True)
        try:
            await test_fn()
            print("PASSED ✅")
            passed += 1
        except Exception as e:
            print(f"FAILED ❌: {e}")
            failed += 1

    print("\n----------------------------------------")
    print(f"Results: {passed} passed, {failed} failed")
    print("----------------------------------------")

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run_all())
