"""Thin wrapper around the Anthropic Claude API, plus helpers for reading its JSON replies.

The advisor only needs one method, ``complete(system, user) -> str``, so tests can pass in a fake model
and the app keeps working (in offline mode) when there is no API key or the call fails.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any, Optional, Protocol

log = logging.getLogger("pawpal.llm")

DEFAULT_MODEL = "claude-haiku-5-5"


class LLMError(RuntimeError):
    """Raised when the model can't be reached or gives an unusable reply."""


class LLM(Protocol):
    name: str

    def complete(self, system: str, user: str) -> str: ...


class ClaudeClient:
    """Calls Claude through the official ``anthropic`` SDK."""

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, max_tokens: int = 800, retries: int = 1):
        try:
            import anthropic  # imported here so the rest of the app works without the package
        except ImportError as exc:
            raise LLMError("The 'anthropic' package is not installed (pip install anthropic)") from exc
        self._anthropic = anthropic
        self._client = anthropic.Anthropic(api_key=api_key, timeout=30.0)
        self.model = model
        self.name = f"claude ({model})"
        self.max_tokens = max_tokens
        self.retries = retries

    def complete(self, system: str, user: str) -> str:
        last_error: Optional[Exception] = None
        for attempt in range(self.retries + 1):
            started = time.perf_counter()
            try:
                response = self._client.messages.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    temperature=0,
                    system=system,
                    messages=[{"role": "user", "content": user}],
                )
            except self._anthropic.APIError as exc:
                last_error = exc
                log.warning("Claude call failed (attempt %d): %s", attempt + 1, exc)
                continue
            text = "".join(getattr(block, "text", "") for block in response.content)
            log.info(
                "Claude call ok model=%s in=%s out=%s %.2fs",
                self.model, response.usage.input_tokens, response.usage.output_tokens,
                time.perf_counter() - started,
            )
            return text
        raise LLMError(f"Claude API error: {last_error}")


def make_llm() -> Optional[LLM]:
    """Return a Claude client if ANTHROPIC_API_KEY is set and the SDK is installed, else None (offline)."""
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        log.info("ANTHROPIC_API_KEY not set; advisor runs in offline mode")
        return None
    try:
        return ClaudeClient(key, model=os.environ.get("PAWPAL_MODEL", DEFAULT_MODEL))
    except LLMError as exc:
        log.warning("Claude unavailable, using offline mode: %s", exc)
        return None


def parse_json_object(text: str) -> dict[str, Any]:
    """Pull the first JSON object out of a model reply (handles ```json fences and extra prose)."""
    if not text:
        raise LLMError("empty reply")
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    candidate = fenced.group(1) if fenced else text[text.find("{"): text.rfind("}") + 1]
    if not candidate:
        raise LLMError("no JSON object in reply")
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise LLMError(f"reply is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise LLMError("reply JSON is not an object")
    return data
