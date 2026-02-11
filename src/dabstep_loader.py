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
