"""Prompt construction and answer parsing for DABStep evaluation."""

from __future__ import annotations

import logging
import re

from src.dabstep_loader import Task

logger = logging.getLogger(__name__)

SYSTEM_INSTRUCTION = (
    "You are answering questions about data analysis and business metrics. "
    "Use the data and tools available to you to compute the answer.\n\n"
    "TIME BUDGET: You have at most 90 seconds. Use the fastest correct method "
    "(direct aggregation, minimal scan). Do NOT perform lengthy exploratory analysis.\n\n"
    "Reply with ONLY your final answer in EXACTLY this format:\n\n"
    "FINAL_ANSWER: <your answer>\n\n"
    "IMPORTANT RULES:\n"
    "- Your FINAL_ANSWER must contain ONLY the answer value — no explanations, no units unless asked.\n"
    "- Follow the Guidelines section EXACTLY for formatting (commas, decimals, rounding, list format, etc.).\n"
    "- If the Guidelines say 'respond with Not Applicable', use exactly: FINAL_ANSWER: Not Applicable\n"
    "- If you cannot compute the answer, respond: FINAL_ANSWER: Not Applicable\n"
    "- Do NOT say 'I don't know'. Do NOT ask clarifying questions.\n"
    "- You MUST always end your response with the FINAL_ANSWER line."
)

FINAL_ANSWER_PATTERN = re.compile(r"FINAL_ANSWER:\s*(.+?)(?:\n|$)", re.IGNORECASE)


def build_prompt(task: Task) -> str:
    """Build the full prompt for a DABStep task."""
    guidelines = task.metadata.get("guidelines", "")
    parts = [SYSTEM_INSTRUCTION]
    if guidelines:
        parts.append(f"Guidelines:\n{guidelines}")
    parts.append(f"Question: {task.question}")
    return "\n\n".join(parts)


def _clean_answer(raw: str) -> str:
    """Apply safe normalization to a parsed answer string."""
    answer = raw.strip()
    # Remove surrounding backticks (``answer`` or `answer`)
    if answer.startswith("```") and answer.endswith("```"):
        answer = answer[3:-3].strip()
    if answer.startswith("`") and answer.endswith("`"):
        answer = answer[1:-1].strip()
    # Remove surrounding quotes
    if len(answer) >= 2 and answer[0] == answer[-1] and answer[0] in ('"', "'"):
        answer = answer[1:-1].strip()
    # Collapse multiple spaces
    answer = re.sub(r"[ \t]+", " ", answer)
    return answer


def parse_final_answer(response_text: str) -> str | None:
    """Extract the FINAL_ANSWER from Dot's response.

    Returns None if no FINAL_ANSWER is found.
    Uses the LAST match if multiple FINAL_ANSWER lines exist.
    """
    matches = list(FINAL_ANSWER_PATTERN.finditer(response_text))
    if not matches:
        logger.warning("No FINAL_ANSWER found in response")
        return None
    # Use the last FINAL_ANSWER (model may refine its answer)
    answer = matches[-1].group(1).strip()
    answer = _clean_answer(answer)
    return answer
