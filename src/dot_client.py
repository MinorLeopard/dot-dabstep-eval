"""Client for calling the Dot API.

Provides FakeDotClient for deterministic testing and LiveDotClient
for real Dot API calls.
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DotResponse:
    """Raw response from Dot."""

    text: str
    usage: dict | None = None


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class DotApiError(Exception):
    """Base exception for Dot API errors."""


class DotHttpError(DotApiError):
    """Raised when Dot API returns a non-200 HTTP status."""

    def __init__(self, status_code: int, detail: str = "") -> None:
        self.status_code = status_code
        super().__init__(f"Dot API HTTP {status_code}: {detail}")


class DotEmptyResponseError(DotApiError):
    """Raised when Dot returns an empty or missing assistant message."""

    def __init__(self, chat_id: str) -> None:
        self.chat_id = chat_id
        super().__init__(f"Dot API returned empty response for chat_id={chat_id}")


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class DotClient(ABC):
    """Abstract base class for Dot API clients."""

    @abstractmethod
    def query(self, prompt: str, chat_id: str | None = None) -> DotResponse:
        """Send a prompt to Dot and return the raw response."""
        ...


# ---------------------------------------------------------------------------
# Fake client (testing)
# ---------------------------------------------------------------------------


class FakeDotClient(DotClient):
    """Deterministic fake client for testing.

    Returns a canned response that includes FINAL_ANSWER derived
    from a hash of the prompt, making it reproducible but wrong
    (so scoring logic is properly exercised).
    """

    def __init__(self, answer_override: str | None = None) -> None:
        self.answer_override = answer_override

    def query(self, prompt: str, chat_id: str | None = None) -> DotResponse:
        if self.answer_override is not None:
            answer = self.answer_override
        else:
            digest = hashlib.md5(prompt.encode()).hexdigest()[:8]
            answer = f"fake_{digest}"

        text = (
            f"Let me analyze this step by step.\n"
            f"After careful consideration...\n"
            f"FINAL_ANSWER: {answer}"
        )
        logger.debug("FakeDotClient returning answer=%s", answer)
        return DotResponse(text=text, usage={"prompt_tokens": len(prompt), "completion_tokens": len(text)})


# ---------------------------------------------------------------------------
# Live client
# ---------------------------------------------------------------------------


class LiveDotClient(DotClient):
    """Real Dot API client.

    Sends a chat message to the Dot API and returns the assistant response.
    The request body matches Dot's schema::

        {
            "chat_id": "<caller-supplied id>",
            "messages": [{"role": "user", "content": "<prompt>"}]
        }

    The response is expected immediately (no polling).

    Environment variables (or .env file):
        DOT_API_KEY:  API authentication key (required).
        DOT_BASE_URL: API base URL, e.g. https://test.getdot.ai (required).

    Args:
        api_key:      Override for DOT_API_KEY env var.
        base_url:     Override for DOT_BASE_URL env var.
        mode:         ``'agentic'`` (POST /api/agentic) or ``'ask'`` (POST /api/ask).
        timeout:      HTTP request timeout in seconds.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        mode: str = "agentic",
        timeout: float = 120.0,
    ) -> None:
        # Best-effort .env loading
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass

        self.api_key = api_key or os.environ.get("DOT_API_KEY", "")
        if not self.api_key:
            raise ValueError(
                "DOT_API_KEY must be set via env var, .env file, or api_key parameter"
            )

        self.base_url = (base_url or os.environ.get("DOT_BASE_URL", "")).rstrip("/")
        if not self.base_url:
            raise ValueError(
                "DOT_BASE_URL must be set via env var, .env file, or base_url parameter"
            )

        if mode not in ("ask", "agentic"):
            raise ValueError(f"mode must be 'ask' or 'agentic', got {mode!r}")
        self.mode = mode

        self._client = httpx.Client(
            base_url=self.base_url,
            headers=self._build_headers(),
            timeout=timeout,
        )
        logger.info(
            "LiveDotClient initialized: base_url=%s, mode=%s",
            self.base_url,
            self.mode,
        )

    def _build_headers(self) -> dict[str, str]:
        """Build auth headers. Sends both X-API-KEY and API-KEY for compatibility."""
        return {
            "X-API-KEY": self.api_key,
            "API-KEY": self.api_key,
            "Content-Type": "application/json",
        }

    @staticmethod
    def _extract_assistant_text(data: dict[str, Any]) -> str:
        """Extract the assistant's message text from the API response.

        Handles multiple response shapes:
        - ``[{"role": "assistant", "content": "..."}]``  (agentic — list, normalized to messages)
        - ``{"messages": [{"role": "assistant", "content": "..."}]}``
        - ``{"explanation": "..."}``  (/api/ask response)
        - ``{"response": "..."}``
        - ``{"text": "..."}``
        """
        # Shape 1: messages array
        messages = data.get("messages", [])
        if isinstance(messages, list):
            for msg in reversed(messages):
                if isinstance(msg, dict) and msg.get("role") == "assistant":
                    text = msg.get("content", "").strip()
                    if text:
                        return text

        # Shape 2: direct response field (e.g. /api/ask returns {"explanation": "..."})
        for key in ("explanation", "response", "text", "answer"):
            val = data.get(key, "")
            if isinstance(val, str) and val.strip():
                return val.strip()

        return ""

    def query(self, prompt: str, chat_id: str | None = None) -> DotResponse:
        """Send a prompt to Dot and return the response.

        Args:
            prompt:  The user message text.
            chat_id: Deterministic chat identifier. Auto-generated UUID if None.

        Raises:
            DotHttpError: Non-200 HTTP status from Dot API.
            DotEmptyResponseError: Response contained no assistant text.
        """
        if chat_id is None:
            chat_id = uuid.uuid4().hex

        endpoint = f"/api/{self.mode}"
        payload = {
            "chat_id": chat_id,
            "messages": [{"role": "user", "content": prompt}],
        }

        logger.debug("POST %s chat_id=%s (prompt length=%d)", endpoint, chat_id, len(prompt))
        start = time.monotonic()

        resp = self._client.post(endpoint, json=payload)
        if resp.status_code != 200:
            raise DotHttpError(resp.status_code, resp.text[:500])

        raw = resp.json()
        # Normalize: /api/agentic returns a list, /api/ask returns a dict
        data = {"messages": raw} if isinstance(raw, list) else raw
        assistant_text = self._extract_assistant_text(data)

        elapsed_ms = (time.monotonic() - start) * 1000

        if not assistant_text:
            raise DotEmptyResponseError(chat_id)

        logger.debug("Got response in %.0fms: %d chars", elapsed_ms, len(assistant_text))

        return DotResponse(
            text=assistant_text,
            usage={
                "latency_ms": round(elapsed_ms),
                "chat_id": chat_id,
            },
        )
