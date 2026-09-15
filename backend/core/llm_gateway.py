from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Any, Callable, TypeVar, cast

try:
    from tenacity import (
        retry,
        stop_after_attempt,
        wait_exponential,
        wait_random,
        retry_if_exception_type,
    )
except ImportError:
    # Graceful fallback decorator when tenacity is not yet installed in host environment
    def retry(*args: Any, **kwargs: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            return fn
        return decorator

    def stop_after_attempt(*args: Any, **kwargs: Any) -> Any:
        return None

    def wait_exponential(*args: Any, **kwargs: Any) -> Any:
        return 0

    def wait_random(*args: Any, **kwargs: Any) -> Any:
        return 0

    def retry_if_exception_type(*args: Any, **kwargs: Any) -> Any:
        return None

from backend.core.config import settings
from backend.core.rate_limiter import rate_limiter

logger = logging.getLogger("mas.llm_gateway")


T = TypeVar("T")

# Try importing Google Generative AI
try:
    import google.generativeai as genai
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False


class TransientLLMException(Exception):
    """Exception class indicating a retryable upstream error (e.g. HTTP 429 ResourceExhausted)."""
    pass


class LLMGateway:
    """Resilient gateway for Google AI Studio (Gemini 1.5 Pro / Flash).

    Enforces 15 RPM sliding-window rate limiting and tenacity exponential backoff
    on all outbound LLM calls, with seamless dev-mode mock capabilities.
    """

    def __init__(self) -> None:
        self.default_model = settings.gemini_model_default
        if not self.is_mock_mode and HAS_GENAI:
            genai.configure(api_key=self.api_key)
            logger.info("LLMGateway initialized with live Google AI Studio API key.")
        else:
            logger.info("LLMGateway initialized in Mock/Dev mode or using direct REST fallback.")

    @property
    def api_key(self) -> str:
        return settings.gemini_api_key

    @property
    def is_mock_mode(self) -> bool:
        key = self.api_key
        return not key or key == "mock_dev_key" or key.startswith("mock_")

    async def _call_rest_api(
        self,
        prompt: str,
        system_prompt: str | None,
        model_name: str,
        caller_id: str,
    ) -> str:
        """Direct REST invocation for Google Generative Language API without SDK dependency."""
        import urllib.request
        import urllib.error

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={self.api_key}"
        payload: dict[str, Any] = {
            "contents": [{"parts": [{"text": prompt}]}]
        }
        if system_prompt:
            payload["systemInstruction"] = {
                "parts": [{"text": system_prompt}]
            }

        def _sync_request() -> str:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=45) as resp:
                    res = json.loads(resp.read().decode("utf-8"))
                    candidates = res.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            return parts[0].get("text", "")
                    return ""
            except urllib.error.HTTPError as err:
                status = err.code
                body = err.read().decode("utf-8", errors="ignore")
                if status == 429 or "resourceexhausted" in body.lower() or "quota" in body.lower():
                    logger.warning("Upstream 429 hit for '%s'. Retrying with backoff...", caller_id)
                    raise TransientLLMException(f"Upstream rate limit hit (HTTP 429): {body}")
                logger.error("Direct Gemini REST call failed (%s): %s", status, body)
                raise RuntimeError(f"Gemini API error (HTTP {status}): {body}") from err

        return await asyncio.to_thread(_sync_request)

    @retry(
        reraise=True,
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=2, min=4, max=30) + wait_random(0, 2),
        retry=retry_if_exception_type(TransientLLMException),
    )
    async def generate_response(
        self,
        prompt: str,
        system_prompt: str | None = None,
        model_name: str | None = None,
        caller_id: str = "supervisor",
    ) -> str:
        """Invokes Gemini with rate-limit guardrails and exponential backoff."""
        # 1. Acquire slot in sliding-window rate limiter
        wait_time = await rate_limiter.acquire(caller_id=caller_id)
        if wait_time > 0:
            logger.info("Caller '%s' paused for %.2fs due to 15 RPM rate limiting.", caller_id, wait_time)

        target_model = model_name or self.default_model
        if "1.5" in target_model:
            target_model = "gemini-2.5-flash"

        # 2. Mock mode handling
        if self.is_mock_mode:
            return self._mock_generate_response(prompt, system_prompt, caller_id)

        # 3. Live Google AI Studio invocation (try SDK first, fallback to REST)
        if HAS_GENAI:
            try:
                genai.configure(api_key=self.api_key)
                model = genai.GenerativeModel(
                    model_name=target_model,
                    system_instruction=system_prompt if system_prompt else None,
                )
                response = await asyncio.to_thread(model.generate_content, prompt)
                return response.text
            except Exception as exc:
                err_msg = str(exc).lower()
                if "429" in err_msg or "resourceexhausted" in err_msg or "quota" in err_msg:
                    logger.warning("Upstream 429 ResourceExhausted hit for caller '%s'. Retrying with backoff...", caller_id)
                    raise TransientLLMException(f"Upstream rate limit hit: {exc}") from exc
                logger.warning("genai SDK failed, attempting direct REST fallback: %s", exc)

        return await self._call_rest_api(prompt, system_prompt, target_model, caller_id)

    def _mock_generate_response(
        self,
        prompt: str,
        system_prompt: str | None = None,
        caller_id: str = "supervisor",
    ) -> str:
        """Deterministic high-utility mock responses for offline dev and test suites."""
        p_lower = prompt.lower()
        
        # Check if caller is supervisor asked to create an agent
        if caller_id == "supervisor" and any(word in p_lower for word in ["create", "spawn", "expert in", "specialist in"]):
            match = re.search(r"(?:expert|specialist|agent)\s+in\s+([a-zA-Z0-9_\s]+)", prompt, re.IGNORECASE)
            domain = match.group(1).strip() if match else "Specialized Domain"
            slug = domain.lower().replace(" ", "_")[:20]
            
            return json.dumps({
                "action": "SPAWN_AGENT",
                "name": f"{domain.capitalize()} Expert",
                "slug": slug,
                "role": f"Expert consultant specialized in {domain}",
                "system_prompt": f"You are an elite expert in {domain}. Provide detailed, practical domain solutions.",
                "delegated_task": prompt
            })

        # Supervisor general delegation or response
        if caller_id == "supervisor":
            if "research" in p_lower or "analyze" in p_lower:
                return json.dumps({
                    "action": "DELEGATE",
                    "target_agent": "researcher",
                    "delegated_task": prompt
                })
            return f"[Supervisor]: I have received your request regarding: '{prompt}'. As the MAS coordinator, I am monitoring all registered agents and workflows."

        # Specialized worker agent responses
        return f"[{caller_id.capitalize()} Specialist]: Successfully analyzed '{prompt}'. Based on my domain expertise, the recommended approach is fully verified and aligned with best practices."


# Global Singleton LLM Gateway
llm_gateway = LLMGateway()
