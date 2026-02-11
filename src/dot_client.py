"""Client for calling the Dot API.

Currently a stub — replace FakeDotClient with a real implementation
once the Dot API is available.
"""

from __future__ import annotations

import hashlib
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DotResponse:
    """Raw response from Dot."""

    text: str
    usage: dict | None = None


class DotClient(ABC):
    """Abstract base class for Dot API clients."""

    @abstractmethod
    def query(self, prompt: str) -> DotResponse:
        """Send a prompt to Dot and return the raw response."""
        ...


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


class LiveDotClient(DotClient):
    """Real Dot API client — NOT YET IMPLEMENTED.

    TODO: Implement once Dot API access is available.
    Expects DOT_API_KEY and DOT_API_URL environment variables.
    """

    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        raise NotImplementedError(
            "LiveDotClient is not yet implemented. "
            "Use FakeDotClient for testing or implement this class."
        )

    def query(self, prompt: str) -> DotResponse:
        raise NotImplementedError
