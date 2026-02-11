"""Load DABStep benchmark tasks from HuggingFace or local JSONL.

Key behaviors:
- HF dataset is multi-config; we ALWAYS load config="tasks" for real runs.
- `limit` is a warmup convenience: loads split[:limit] from HF.
- If you want curated IDs (e.g. TARGET_TASK_IDS), use `target_ids` (loads full split then filters).
- Do NOT combine `limit` with `target_ids` (would silently drop higher IDs).
- Unit tests use a mocked `load_dataset()` that may not accept `name=` and may treat the 2nd positional arg as split.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

DABSTEP_HF_REPO = "adyen/DABstep"
DABSTEP_CONFIG = "tasks"
DABSTEP_SPLIT = "default"

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

    Accepts either:
      - question_id or task_id or id
      - question
      - answer (ground truth) or ground_truth
      - guidelines (optional)
      - level/difficulty (optional)
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

            qid = obj.get("question_id", obj.get("task_id", obj.get("id")))
            q = obj.get("question", "")
            ans = obj.get("answer", obj.get("ground_truth", ""))

            if qid is None or not q or ans == "":
                logger.warning(
                    "Skipping line %d — missing required fields (qid=%r question_len=%d answer_len=%d)",
                    lineno,
                    qid,
                    len(str(q or "")),
                    len(str(ans or "")),
                )
                continue

            tasks.append(
                Task(
                    question_id=str(qid),
                    question=str(q),
                    ground_truth=str(ans),
                    difficulty=str(obj.get("level", obj.get("difficulty", "unknown"))),
                    metadata={"guidelines": obj.get("guidelines", "")},
                )
            )

    logger.info("Loaded %d tasks from %s", len(tasks), path)
    return tasks


def _hf_load_dataset_tasks(repo: str, split: str):
    """Internal: load HF dataset config='tasks' robustly.

    This must work for:
    - real `datasets.load_dataset`
    - unit-test mocks that may not accept keyword args
      and may treat 2nd positional arg as `split`.
    """
    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise ImportError("Install `datasets` to load from HuggingFace: pip install datasets") from exc

    # Try signatures from most-specific (real HF) -> most-compatible (mocks).
    candidates = [
        # Real HF: force config via keyword name
        lambda: load_dataset(repo, name=DABSTEP_CONFIG, split=split),
        # Real HF: config as 2nd positional, split as 3rd positional (NO split= kw)
        # This avoids the mock bug where 2nd positional is interpreted as split.
        lambda: load_dataset(repo, DABSTEP_CONFIG, split),
        # Last resort: just pass split (keeps very simple mocks happy)
        lambda: load_dataset(repo, split=split),
        lambda: load_dataset(repo, split),
    ]

    last_err: Exception | None = None
    for fn in candidates:
        try:
            return fn()
        except TypeError as e:
            last_err = e
            continue

    raise TypeError(f"Could not call load_dataset with any supported signature. Last error: {last_err}")


def _row_get(row, key: str, default=""):
    """Safer access for datasets Row objects and plain dicts."""
    try:
        if key in row:
            val = row[key]
            return default if val is None else val
    except Exception:
        pass
    try:
        return row.get(key, default)  # type: ignore[attr-defined]
    except Exception:
        return default


def load_from_hf(
    repo: str = DABSTEP_HF_REPO,
    split: str = DABSTEP_SPLIT,
    limit: int | None = None,
    *,
    target_ids: list[int] | None = None,
) -> list[Task]:
    """Load tasks from HuggingFace datasets.

    - If `limit` is provided: warmup mode -> loads split[:limit].
    - If `target_ids` is provided: loads FULL split then filters to those IDs.
    - Do NOT combine `limit` with `target_ids`.
    """
    if target_ids is not None and limit is not None:
        raise ValueError("Use either limit OR target_ids, not both (they conflict).")

    hf_split = split
    if limit is not None:
        hf_split = f"{split}[:{limit}]"

    logger.info("Loading DABStep from HuggingFace: repo=%s config=%s split=%s", repo, DABSTEP_CONFIG, hf_split)
    ds = _hf_load_dataset_tasks(repo=repo, split=hf_split)

    # Helpful debug
    try:
        logger.info("HF dataset columns: %s", list(ds.features.keys()))
    except Exception:
        pass

    tasks: list[Task] = []
    for row in ds:
        qid = _row_get(row, "task_id", _row_get(row, "question_id", _row_get(row, "id", "")))
        q = _row_get(row, "question", "")
        ans = _row_get(row, "answer", _row_get(row, "ground_truth", ""))

        tasks.append(
            Task(
                question_id=str(qid),
                question=str(q),
                ground_truth=str(ans),
                difficulty=str(_row_get(row, "level", _row_get(row, "difficulty", "unknown"))),
                metadata={"guidelines": _row_get(row, "guidelines", "")},
            )
        )

    if target_ids is not None:
        return filter_target_tasks(tasks, target_ids=target_ids)

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
    *,
    target_ids: list[int] | None = None,
    split: str | None = None,
) -> list[Task]:
    """Unified loader. source='hf' or 'jsonl'."""
    if source == "jsonl":
        if path is None:
            raise ValueError("path is required when source='jsonl'")
        if limit is not None or target_ids is not None:
            raise ValueError("limit/target_ids are only supported for source='hf'")
        return load_from_jsonl(path)

    if source == "hf":
        kw: dict = {"limit": limit, "target_ids": target_ids}
        if split is not None:
            kw["split"] = split
        return load_from_hf(**kw)

    raise ValueError(f"Unknown source: {source!r}. Use 'hf' or 'jsonl'.")
