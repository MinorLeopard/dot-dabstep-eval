"""Scoring logic for DABStep evaluation.

DABStep uses exact-match scoring with normalization:
- Strip whitespace and lowercase
- Numeric answers: compare as floats with tolerance
- String answers: exact match after normalization
"""

from __future__ import annotations

import logging
import math
import re

logger = logging.getLogger(__name__)

NUMERIC_TOLERANCE = 1e-6


def normalize_answer(answer: str) -> str:
    """Normalize an answer string for comparison."""
    answer = answer.strip().lower()
    # Remove surrounding quotes
    if len(answer) >= 2 and answer[0] == answer[-1] and answer[0] in ("'", '"'):
        answer = answer[1:-1].strip()
    # Remove trailing periods
    answer = answer.rstrip(".")
    # Collapse whitespace
    answer = re.sub(r"\s+", " ", answer)
    return answer


def _try_parse_float(s: str) -> float | None:
    """Attempt to parse a string as a float."""
    s = s.strip().replace(",", "").replace("%", "").replace("$", "")
    try:
        return float(s)
    except (ValueError, OverflowError):
        return None


def _try_parse_list(s: str) -> list[str] | None:
    """Attempt to parse a comma-separated list."""
    if "," not in s:
        return None
    items = [item.strip() for item in s.split(",") if item.strip()]
    if len(items) < 2:
        return None
    return items


def score_answer(parsed_answer: str | None, ground_truth: str) -> tuple[int, str | None]:
    """Score a parsed answer against ground truth.

    Returns:
        (score, error_type) — score is 0 or 1.
        error_type is None on correct, or a string describing the failure.
    """
    if parsed_answer is None:
        return 0, "format_missing"

    norm_parsed = normalize_answer(parsed_answer)
    norm_truth = normalize_answer(ground_truth)

    # Try numeric comparison first
    parsed_num = _try_parse_float(norm_parsed)
    truth_num = _try_parse_float(norm_truth)

    if parsed_num is not None and truth_num is not None:
        if math.isclose(parsed_num, truth_num, rel_tol=1e-4, abs_tol=NUMERIC_TOLERANCE):
            return 1, None
        return 0, "wrong_answer"

    # String exact match
    if norm_parsed == norm_truth:
        return 1, None

    # Try set-based comparison for comma-separated lists
    parsed_list = _try_parse_list(norm_parsed)
    truth_list = _try_parse_list(norm_truth)
    if parsed_list is not None and truth_list is not None:
        if set(parsed_list) == set(truth_list):
            return 1, None
        parsed_set = set(parsed_list)
        truth_set = set(truth_list)
        if parsed_set > truth_set:
            return 0, "superset_answer"
        if parsed_set < truth_set:
            return 0, "subset_answer"
        return 0, "wrong_list"

    return 0, "wrong_answer"
