"""Prompt construction and answer parsing for DABStep evaluation."""

from __future__ import annotations

import logging
import re

from src.dabstep_loader import Task

logger = logging.getLogger(__name__)

SYSTEM_INSTRUCTION = (
    "You are answering questions about data analysis and business metrics. "
    "Think step by step, then provide your final answer in EXACTLY this format:\n\n"
    "FINAL_ANSWER: <your answer>\n\n"
    "Your FINAL_ANSWER must be a single value — a number, string, or short phrase. "
    "Do not include units unless the question explicitly asks for them. "
    "If the answer is a number, round to 2 decimal places unless otherwise specified."
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


def parse_final_answer(response_text: str) -> str | None:
    """Extract the FINAL_ANSWER from Dot's response.

    Returns None if no FINAL_ANSWER is found.
    """
    match = FINAL_ANSWER_PATTERN.search(response_text)
    if match is None:
        logger.warning("No FINAL_ANSWER found in response")
        return None
    answer = match.group(1).strip()
    return answer
