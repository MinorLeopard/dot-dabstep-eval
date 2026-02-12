#!/usr/bin/env python3
"""
Convert partial submission.jsonl (e.g., target30)
into full 450-row submission.jsonl.

Each row format:
{"task_id": "2725", "agent_answer": "", "reasoning_trace": ""}
"""

import json
import argparse
from pathlib import Path


def read_partial_submission(path: Path) -> dict[str, dict]:
    """
    Returns:
        {
            "973": {
                "agent_answer": "...",
                "reasoning_trace": "..."
            }
        }
    """
    data = {}

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue

            obj = json.loads(line)
            tid = str(obj.get("task_id"))

            data[tid] = {
                "agent_answer": obj.get("agent_answer", "") or "",
                "reasoning_trace": obj.get("reasoning_trace", "") or "",
            }

    return data


def load_all_task_ids():
    from datasets import load_dataset

    ds = load_dataset("adyen/DABstep", "tasks", split="default")

    task_ids = [str(row["task_id"]) for row in ds]

    # Ensure uniqueness + preserve order
    seen = set()
    ordered = []
    for tid in task_ids:
        if tid not in seen:
            ordered.append(tid)
            seen.add(tid)

    if len(ordered) != 450:
        raise RuntimeError(f"Expected 450 unique task_ids, got {len(ordered)}")

    return ordered


def write_full_submission(all_task_ids, partial_data, output_path: Path):
    with output_path.open("w", encoding="utf-8") as f:
        for tid in all_task_ids:
            if tid in partial_data:
                row = {
                    "task_id": tid,
                    "agent_answer": partial_data[tid]["agent_answer"],
                    "reasoning_trace": partial_data[tid]["reasoning_trace"],
                }
            else:
                row = {
                    "task_id": tid,
                    "agent_answer": "",
                    "reasoning_trace": "",
                }

            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"✔ Full submission written to: {output_path}")
    filled = sum(1 for tid in all_task_ids if tid in partial_data)
    print(f"Filled answers: {filled}")
    print(f"Empty answers: {len(all_task_ids) - filled}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--partial",
        required=True,
        type=Path,
        help="Path to partial submission.jsonl (e.g., target30 output)",
    )
    parser.add_argument(
        "--out",
        default="submission_full.jsonl",
        type=Path,
        help="Output full submission JSONL",
    )

    args = parser.parse_args()

    partial_data = read_partial_submission(args.partial)
    all_task_ids = load_all_task_ids()
    write_full_submission(all_task_ids, partial_data, args.out)


if __name__ == "__main__":
    main()
