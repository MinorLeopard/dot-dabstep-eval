"""Client for calling the Dot API.

Provides FakeDotClient for deterministic testing and LiveDotClient
for real Dot API calls via POST + polling.
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
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


class DotTimeoutError(DotApiError):
    """Raised when polling for Dot response exceeds the timeout."""

    def __init__(self, chat_id: str, elapsed: float) -> None:
        self.chat_id = chat_id
        self.elapsed = elapsed
        super().__init__(f"Dot API timeout after {elapsed:.1f}s for chat_id={chat_id}")


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
    def query(self, prompt: str) -> DotResponse:
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

    def query(self, prompt: str) -> DotResponse:
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

    Sends prompts to the Dot API and polls for assistant responses.

    Environment variables (or .env file):
        DOT_API_KEY:  API authentication key (required).
        DOT_BASE_URL: API base URL, e.g. https://test.getdot.ai (required).

    Args:
        api_key:       Override for DOT_API_KEY env var.
        base_url:      Override for DOT_BASE_URL env var.
        mode:          ``'agentic'`` (POST /api/agentic) or ``'ask'`` (POST /api/ask).
        poll_timeout:  Max seconds to poll for a response.
        poll_interval: Seconds between poll requests.
    """

    DEFAULT_POLL_TIMEOUT = 60.0
    DEFAULT_POLL_INTERVAL = 1.0

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        mode: str = "agentic",
        poll_timeout: float = DEFAULT_POLL_TIMEOUT,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
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

        self.poll_timeout = poll_timeout
        self.poll_interval = poll_interval

        self._client = httpx.Client(
            base_url=self.base_url,
            headers=self._build_headers(),
            timeout=30.0,
        )
        logger.info(
            "LiveDotClient initialized: base_url=%s, mode=%s, poll_timeout=%.0fs",
            self.base_url,
            self.mode,
            self.poll_timeout,
        )

    def _build_headers(self) -> dict[str, str]:
        """Build auth headers. Sends both X-API-KEY and API-KEY for compatibility."""
        return {
            "X-API-KEY": self.api_key,
            "API-KEY": self.api_key,
            "Content-Type": "application/json",
        }

    def _post_prompt(self, prompt: str) -> str:
        """POST the prompt to the appropriate endpoint, return chat_id."""
        endpoint = f"/api/{self.mode}"
        payload = {"prompt": prompt}

        logger.debug("POST %s (prompt length=%d)", endpoint, len(prompt))

        resp = self._client.post(endpoint, json=payload)
        if resp.status_code != 200:
            raise DotHttpError(resp.status_code, resp.text[:500])

        data = resp.json()
        chat_id = data.get("chat_id")
        if not chat_id:
            raise DotHttpError(
                resp.status_code,
                f"Response missing 'chat_id': {resp.text[:200]}",
            )

        logger.debug("Got chat_id=%s", chat_id)
        return chat_id

    def _poll_response(self, chat_id: str) -> tuple[str, int]:
        """Poll GET /api/c2/{chat_id} until assistant text is non-empty.

        Returns:
            Tuple of (assistant_text, retries).
        """
        endpoint = f"/api/c2/{chat_id}"
        start = time.monotonic()
        retries = 0

        while True:
            elapsed = time.monotonic() - start
            if elapsed > self.poll_timeout:
                raise DotTimeoutError(chat_id, elapsed)

            resp = self._client.get(endpoint)
            if resp.status_code != 200:
                raise DotHttpError(resp.status_code, resp.text[:500])

            data = resp.json()
            assistant_text = self._extract_assistant_text(data)

            if assistant_text:
                logger.debug(
                    "Got response after %.1fs (%d retries): %d chars",
                    elapsed,
                    retries,
                    len(assistant_text),
                )
                return assistant_text, retries

            retries += 1
            time.sleep(self.poll_interval)

    @staticmethod
    def _extract_assistant_text(data: dict[str, Any]) -> str:
        """Extract the assistant's message text from the poll response.

        Handles multiple possible response shapes:
        - ``{"messages": [{"role": "assistant", "content": "..."}]}``
        - ``{"response": "..."}``
        - ``{"text": "..."}``
        - ``{"answer": "..."}``
        """
        # Shape 1: messages array (most common)
        messages = data.get("messages", [])
        if isinstance(messages, list):
            for msg in reversed(messages):
                if isinstance(msg, dict) and msg.get("role") == "assistant":
                    text = msg.get("content", "").strip()
                    if text:
                        return text

        # Shape 2: direct response field
        for key in ("response", "text", "answer"):
            val = data.get(key, "")
            if isinstance(val, str) and val.strip():
                return val.strip()

        return ""

    def query(self, prompt: str) -> DotResponse:
        """Send a prompt to Dot and return the response.

        Raises:
            DotHttpError: Non-200 HTTP status from Dot API.
            DotTimeoutError: Polling exceeded poll_timeout.
            DotEmptyResponseError: Polling completed but no assistant text.
        """
        start_ms = time.monotonic()

        chat_id = self._post_prompt(prompt)
        assistant_text, retries = self._poll_response(chat_id)

        if not assistant_text:
            raise DotEmptyResponseError(chat_id)

        elapsed_ms = (time.monotonic() - start_ms) * 1000

        return DotResponse(
            text=assistant_text,
            usage={
                "latency_ms": round(elapsed_ms),
                "chat_id": chat_id,
                "retries": retries,
            },
        )
