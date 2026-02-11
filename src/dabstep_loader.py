"""Load DABStep benchmark tasks from HuggingFace or local JSONL."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

logger = logging.getLogger(__name__)

DABSTEP_HF_REPO = "adyen/DABstep"
DABSTEP_SPLIT = "dev"

TARGET_TASK_IDS: list[int] = [
    24, 43, 44, 625, 973, 1287, 1295, 1296, 1308, 1312,
    1436, 1443, 1485, 1515, 1516, 1519, 1729, 1763, 1817, 1823,
    1853, 2463, 2522, 2527, 2553, 2664, 2725, 2767, 2769, 2771,
]


@dataclass(frozen=True)
class Task:
    """A single DABStep evaluation task."""

    question_id: str
    question: str
    ground_truth: str
    difficulty: str = "unknown"
    metadata: dict = field(default_factory=dict)


def load_from_jsonl(path: Path) -> list[Task]:
    """Load tasks from a local JSONL file.

    Each line must have at minimum: question_id, question, ground_truth.
    """
    tasks: list[Task] = []
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                logger.warning("Skipping malformed JSON at line %d: %s", lineno, exc)
                continue
            try:
                tasks.append(
                    Task(
                        question_id=str(obj["question_id"]),
                        question=obj["question"],
                        ground_truth=str(obj["answer"]),
                        difficulty=str(obj.get("level", "")),
                        metadata={"guidelines": obj.get("guidelines", "")},

                    )
                )
            except KeyError as exc:
                logger.warning("Skipping line %d — missing required field: %s", lineno, exc)
    logger.info("Loaded %d tasks from %s", len(tasks), path)
    return tasks


def load_from_hf(
    repo: str = DABSTEP_HF_REPO,
    split: str = DABSTEP_SPLIT,
    limit: int | None = None,
) -> list[Task]:
    """Load tasks from HuggingFace datasets.

    Requires `datasets` to be installed.
    """
    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise ImportError("Install `datasets` to load from HuggingFace: pip install datasets") from exc

    logger.info("Loading DABStep from HuggingFace: %s [%s]", repo, split)
    ds = load_dataset(repo, split=split)

    tasks: list[Task] = []
    for i, row in enumerate(ds):
        if limit is not None and i >= limit:
            break
        tasks.append(
            Task(
                question_id=str(row["task_id"]),
                question=str(row["question"]),
                ground_truth=str(row["answer"]),
                difficulty=str(row.get("level", "unknown")),
                metadata={"guidelines": row.get("guidelines", "")},
            )
        )
    logger.info("Loaded %d tasks from HuggingFace", len(tasks))
    return tasks


def filter_target_tasks(
    tasks: list[Task],
    target_ids: list[int] | None = None,
) -> list[Task]:
    """Filter tasks to only those whose question_id is in target_ids.

    Raises ValueError if any target IDs are missing from the loaded tasks.
    """
    if target_ids is None:
        target_ids = TARGET_TASK_IDS
    target_strs = {str(tid) for tid in target_ids}
    filtered = [t for t in tasks if t.question_id in target_strs]
    found_ids = {t.question_id for t in filtered}
    missing = target_strs - found_ids
    if missing:
        raise ValueError(
            f"Missing {len(missing)} target task IDs from loaded data: "
            + ", ".join(sorted(missing, key=lambda x: int(x)))
        )
    logger.info("Filtered to %d target tasks", len(filtered))
    return filtered


def load_tasks(
    source: str = "hf",
    path: Path | None = None,
    limit: int | None = None,
) -> list[Task]:
    """Unified loader. source='hf' or 'jsonl'."""
    if source == "jsonl":
        if path is None:
            raise ValueError("path is required when source='jsonl'")
        tasks = load_from_jsonl(path)
    elif source == "hf":
        tasks = load_from_hf(limit=limit)
    else:
        raise ValueError(f"Unknown source: {source!r}. Use 'hf' or 'jsonl'.")

    if limit is not None:
        tasks = tasks[:limit]
    return tasks
