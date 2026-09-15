from __future__ import annotations

import os

try:
    import pytest
except ImportError:
    class _MockMark:
        @staticmethod
        def asyncio(fn):
            return fn
    class _MockPytest:
        mark = _MockMark()
    pytest = _MockPytest()

from frontend.utils.api_client import APIClient


@pytest.mark.asyncio
async def test_api_client_initialization() -> None:
    """Test API client defaults and resilient status reporting."""
    client = APIClient(base_url="http://127.0.0.1:9999")  # Unreachable port
    status = client.get_system_status()
    # With in-process fallback, status is gracefully reported as 'ok', otherwise 'offline'
    assert status["status"] in ("ok", "offline")
    assert "rate_limiter" in status
    assert status["rate_limiter"]["max_rpm"] == 14


