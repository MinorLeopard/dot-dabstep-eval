"""Generate submission CSV for all 450 DABStep tasks.

Loads the full task list from HuggingFace (default split, 450 tasks),
fills answers from the latest run artifacts for target tasks,
and emits a submission CSV with empty answers for non-target tasks.

Output format:
    task_id,agent_answer
    0,""
    1,""
    ...
    24,"some answer"
    ...
"""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

ARTIFACTS_DIR = Path("artifacts")
RESULTS_DIR = Path("results")


def _find_latest_run_dir() -> Path | None:
    """Find the newest run directory under artifacts/runs/."""
    runs_dir = ARTIFACTS_DIR / "runs"
    if not runs_dir.is_dir():
        return None
    run_dirs = [d for d in runs_dir.iterdir() if d.is_dir() and (d / "results.jsonl").exists()]
    if not run_dirs:
        return None
    return max(run_dirs, key=lambda d: d.stat().st_mtime)


def _find_latest_results_jsonl() -> Path | None:
    """Find newest results JSONL from artifacts/runs/ or results/."""
    # Prefer artifacts/runs/ first
    run_dir = _find_latest_run_dir()
    if run_dir:
        return run_dir / "results.jsonl"

    # Fall back to results/ directory
    if RESULTS_DIR.is_dir():
        jsonl_files = list(RESULTS_DIR.glob("*.jsonl"))
        if jsonl_files:
            return max(jsonl_files, key=lambda p: p.stat().st_mtime)

    return None


def _load_answers_from_results(results_path: Path) -> dict[str, str]:
    """Load question_id -> parsed_answer from a results JSONL file."""
    answers = {}
    with open(results_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            qid = str(record.get("question_id", ""))
            answer = record.get("parsed_answer")
            if qid and answer is not None:
                answers[qid] = str(answer)
    logger.info("Loaded %d answers from %s", len(answers), results_path)
    return answers


def _load_all_task_ids(split: str = "default") -> list[str]:
    """Load all task IDs from HuggingFace dataset."""
    try:
        from src.dabstep_loader import load_from_hf
        tasks = load_from_hf(split=split)
        return [t.question_id for t in tasks]
    except Exception as exc:
        logger.warning("Failed to load from HF: %s. Trying local JSONL.", exc)

    # Fall back to local all.jsonl
    local_path = Path("data/context/all.jsonl")
    if local_path.exists():
        task_ids = []
        with open(local_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                qid = obj.get("task_id", obj.get("question_id", obj.get("id")))
                if qid is not None:
                    task_ids.append(str(qid))
        logger.info("Loaded %d task IDs from %s", len(task_ids), local_path)
        return task_ids

    raise FileNotFoundError(
        "Cannot load task IDs. Install 'datasets' package or provide data/context/all.jsonl"
    )


def make_submission_csv(
    output_path: Path | None = None,
    results_path: Path | None = None,
    split: str = "default",
) -> Path:
    """Generate submission CSV for all tasks.

    Args:
        output_path: Output CSV path (default: submission.csv).
        results_path: Results JSONL to load answers from (auto-detected if None).
        split: HF dataset split (default: 'default').

    Returns:
        Path to generated CSV file.
    """
    if output_path is None:
        output_path = Path("submission.csv")

    # Load all task IDs
    all_task_ids = _load_all_task_ids(split=split)
    logger.info("Total task IDs: %d", len(all_task_ids))

    # Load answers from results
    answers: dict[str, str] = {}
    if results_path is None:
        results_path = _find_latest_results_jsonl()
    if results_path and results_path.exists():
        answers = _load_answers_from_results(results_path)
        logger.info("Using answers from: %s", results_path)
    else:
        logger.warning("No results file found. All answers will be empty.")

    # Generate CSV
    rows = []
    filled = 0
    for task_id in all_task_ids:
        answer = answers.get(task_id, "")
        rows.append({"task_id": task_id, "agent_answer": answer})
        if answer:
            filled += 1

    # Write CSV
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["task_id", "agent_answer"])
        writer.writeheader()
        writer.writerows(rows)

    # Validate
    errors = _validate_submission(output_path, expected_count=len(all_task_ids))
    if errors:
        for err in errors:
            logger.error("Validation error: %s", err)
        print(f"\nWARNING: {len(errors)} validation errors found!")
    else:
        print("\nSubmission CSV validated successfully.")

    print(f"\nSubmission CSV: {output_path}")
    print(f"  Total rows: {len(rows)}")
    print(f"  Filled answers: {filled}")
    print(f"  Empty answers: {len(rows) - filled}")

    return output_path


def _validate_submission(csv_path: Path, expected_count: int = 450) -> list[str]:
    """Validate submission CSV format.

    Returns list of error messages (empty if valid).
    """
    errors = []

    with open(csv_path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)

        # Check columns
        if reader.fieldnames != ["task_id", "agent_answer"]:
            errors.append(f"Wrong columns: {reader.fieldnames}. Expected: ['task_id', 'agent_answer']")

        rows = list(reader)

    # Check count
    if len(rows) != expected_count:
        errors.append(f"Row count: {len(rows)}. Expected: {expected_count}")

    # Check uniqueness
    task_ids = [r["task_id"] for r in rows]
    if len(task_ids) != len(set(task_ids)):
        dupes = [tid for tid in set(task_ids) if task_ids.count(tid) > 1]
        errors.append(f"Duplicate task_ids: {dupes[:10]}")

    # Check all answers are strings
    for r in rows:
        if not isinstance(r["agent_answer"], str):
            errors.append(f"task_id {r['task_id']}: agent_answer is not a string")

    return errors


def main() -> None:
    """CLI entry point."""
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    parser = argparse.ArgumentParser(description="Generate DABStep submission CSV")
    parser.add_argument("--output", type=Path, default=Path("submission.csv"), help="Output CSV path")
    parser.add_argument("--results", type=Path, default=None, help="Results JSONL to use")
    parser.add_argument("--split", default="default", help="HF dataset split")
    args = parser.parse_args()

    make_submission_csv(
        output_path=args.output,
        results_path=args.results,
        split=args.split,
    )


if __name__ == "__main__":
    main()
