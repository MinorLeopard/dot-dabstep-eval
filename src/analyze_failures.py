"""Analyze evaluation results — failure clustering and breakdowns."""

from __future__ import annotations

import json
import logging
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


def load_results(path: Path) -> pd.DataFrame:
    """Load a results JSONL file into a DataFrame."""
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    if not records:
        raise ValueError(f"No records found in {path}")
    return pd.DataFrame(records)


def summary(df: pd.DataFrame) -> dict:
    """Compute summary statistics."""
    total = len(df)
    correct = int(df["score"].sum())
    return {
        "total": total,
        "correct": correct,
        "accuracy": correct / total if total > 0 else 0.0,
        "by_difficulty": (
            df.groupby("difficulty")["score"]
            .agg(["count", "sum", "mean"])
            .rename(columns={"count": "total", "sum": "correct", "mean": "accuracy"})
            .to_dict("index")
        ),
        "error_breakdown": dict(Counter(df.loc[df["score"] == 0, "error_type"])),
    }


def print_report(stats: dict) -> None:
    """Pretty-print an evaluation report."""
    print("=" * 60)
    print(f"  DABStep Evaluation Report")
    print("=" * 60)
    print(f"  Total:    {stats['total']}")
    print(f"  Correct:  {stats['correct']}")
    print(f"  Accuracy: {stats['accuracy']:.1%}")
    print()

    print("  By Difficulty:")
    for diff, vals in sorted(stats["by_difficulty"].items()):
        print(f"    {diff:12s}  {vals['correct']:.0f}/{vals['total']:.0f}  ({vals['accuracy']:.1%})")
    print()

    if stats["error_breakdown"]:
        print("  Error Breakdown:")
        for err, count in sorted(stats["error_breakdown"].items(), key=lambda x: -x[1]):
            print(f"    {err:20s}  {count}")
    print("=" * 60)


def show_failures(df: pd.DataFrame, n: int = 10) -> None:
    """Print sample failures for manual inspection."""
    failures = df[df["score"] == 0]
    if failures.empty:
        print("No failures to show.")
        return

    sample = failures.head(n)
    print(f"\n  Sample Failures ({min(n, len(failures))} of {len(failures)}):\n")
    for _, row in sample.iterrows():
        print(f"  [{row['question_id']}] difficulty={row['difficulty']}")
        print(f"    error:    {row['error_type']}")
        print(f"    expected: {row['ground_truth']}")
        print(f"    got:      {row['parsed_answer']}")
        print()


def find_newest_results() -> Path | None:
    """Find the newest results JSONL file using pathlib (works on Windows and Unix)."""
    results_dir = Path("results")
    if not results_dir.is_dir():
        return None
    jsonl_files = list(results_dir.glob("*.jsonl"))
    if not jsonl_files:
        return None
    return max(jsonl_files, key=lambda p: p.stat().st_mtime)


def main() -> None:
    """CLI entry point."""
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    parser = argparse.ArgumentParser(description="Analyze DABStep eval results")
    parser.add_argument("results_file", nargs="?", type=Path, default=None, help="Path to results JSONL (auto-detects newest if omitted)")
    parser.add_argument("--failures", type=int, default=10, help="Number of sample failures to show")
    args = parser.parse_args()

    results_file: Path | None = args.results_file
    if results_file is None:
        results_file = find_newest_results()
        if results_file is None:
            print("No results JSONL files found in results/. Run 'make run_eval' first, or pass a path explicitly.")
            sys.exit(1)
        print(f"Auto-detected newest results: {results_file}")

    df = load_results(results_file)
    stats = summary(df)
    print_report(stats)
    show_failures(df, n=args.failures)


if __name__ == "__main__":
    main()
