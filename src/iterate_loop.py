"""Iterate loop: analyze failures -> patch DOT context -> rerun evaluation.

Runs up to N iterations of:
1. Run async dev evaluation
2. Generate failure analysis report
3. Export context snapshot (before)
4. Propose and apply instruction fixes via DotContextManager
5. Export context snapshot (after)
6. Check stopping conditions

Stops when:
- Max iterations reached (default: 5)
- No improvement for 2 consecutive iterations
- Perfect score achieved
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from src.async_runner import run_async_eval
from src.dot_client import DotClient, LiveDotClient, FakeDotClient
from src.failure_report import generate_failure_report

logger = logging.getLogger(__name__)

ARTIFACTS_DIR = Path("artifacts")
SCORE_HISTORY_PATH = ARTIFACTS_DIR / "score_history.json"

# The org-note ID used for fee/domain instructions
INSTRUCTIONS_NOTE_ID = "org_instructions"
INSTRUCTIONS_NOTE_TITLE = "DABStep Fee & Domain Instructions"


def _load_score_history() -> list[dict]:
    """Load score history from artifacts/score_history.json."""
    if SCORE_HISTORY_PATH.exists():
        with open(SCORE_HISTORY_PATH, encoding="utf-8") as f:
            return json.load(f)
    return []


def _save_score_history(history: list[dict]) -> None:
    """Save score history."""
    SCORE_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SCORE_HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)


def _export_context_snapshot(output_path: Path) -> bool:
    """Export DOT context snapshot using the export utility.

    Returns True if successful, False if failed (e.g., no API key).
    """
    try:
        from tools.dot_context_manager import DotContextManager
        from tools.export_dot_context_snapshot import (
            _format_relationships,
            _format_assets,
            _format_table_section,
            _pick_table_ids,
        )

        mgr = DotContextManager()
        tables_lite = mgr.list_tables(lite=True)
        table_ids = _pick_table_ids(tables_lite, None)
        rels = mgr.list_relationships()
        assets = mgr.list_external_assets()

        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        base_url = os.environ.get("DOT_BASE_URL", "").rstrip("/")

        md_parts = []
        md_parts.append(f"# Dot Context Snapshot\n\n- Exported: **{now}**\n- Base URL: **{base_url}**\n")
        md_parts.append(_format_relationships(rels))
        md_parts.append(_format_assets(assets, include_full_notes=True))
        md_parts.append("# Tables\n")

        for tid in table_ids:
            try:
                t = mgr.get_table(tid)
                md_parts.append(_format_table_section(t))
            except Exception as e:
                md_parts.append(f"## Table: `{tid}`\n\n**ERROR:** `{e}`\n")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("\n".join(md_parts).strip() + "\n", encoding="utf-8")
        logger.info("Context snapshot written to %s", output_path)
        return True

    except Exception as exc:
        logger.warning("Failed to export context snapshot: %s", exc)
        return False


def _build_updated_instructions(
    current_instructions: str,
    failure_stats: dict,
) -> str | None:
    """Build updated instruction text based on failure analysis.

    Returns updated instruction text, or None if no changes needed.
    """
    failures = failure_stats.get("failures", [])
    classified = failure_stats.get("classified_errors", {})

    if not failures:
        logger.info("No failures — no instruction updates needed.")
        return None

    # Start with current instructions
    updates = []

    # Add specific fixes based on classified errors
    if classified.get("missing_tier_filter", 0) > 0:
        tier_fix = (
            "\n\n## CRITICAL: day_of_year to Month Conversion for Fee Lookups\n"
            "When a question specifies a date (e.g., 'the 10th of 2023' means day_of_year=10):\n"
            "1. Convert day_of_year to month: Jan=1-31, Feb=32-59, Mar=60-90, "
            "Apr=91-120, May=121-151, Jun=152-181, Jul=182-212, Aug=213-243, "
            "Sep=244-273, Oct=274-304, Nov=305-334, Dec=335-365\n"
            "2. Look up monthly_merchant_stats for that merchant/year/month\n"
            "3. Use volume_tier and fraud_tier to filter fees\n"
            "4. Also filter by the merchant's account_type, mcc, capture_delay_bucket, "
            "and the payment's card_scheme, aci, is_credit, intracountry\n"
            "5. intracountry = CASE WHEN issuing_country = acquirer_country THEN 1 ELSE 0 END\n"
        )
        if "day_of_year to Month Conversion" not in current_instructions:
            updates.append(tier_fix)

    if classified.get("precision_error", 0) > 0:
        prec_fix = (
            "\n\n## Fee Calculation Precision\n"
            "fee = fixed_amount + (rate * eur_amount / 10000.0)\n"
            "- Use DOUBLE precision throughout.\n"
            "- Sum fees across ALL matching transactions.\n"
            "- When comparing scenarios (delta), compute each scenario's total separately "
            "then subtract: delta = new_total - old_total.\n"
            "- Preserve full decimal precision unless the guidelines request rounding.\n"
        )
        if "Fee Calculation Precision" not in current_instructions:
            updates.append(prec_fix)

    if classified.get("wrong_fee_match", 0) > 0:
        fee_fix = (
            "\n\n## Fee Rule Matching Checklist\n"
            "To find applicable fee IDs for a merchant+transaction:\n"
            "1. Get merchant's: account_type, merchant_category_code, capture_delay_bucket, acquirer\n"
            "2. Get transaction's: card_scheme, aci, is_credit\n"
            "3. Compute: intracountry = (issuing_country = acquirer_country)\n"
            "4. Get monthly tiers: volume_tier, fraud_tier from monthly_merchant_stats\n"
            "5. A fee matches if ALL non-null criteria match:\n"
            "   - card_scheme = exact match\n"
            "   - account_type: list contains merchant's type (or empty = all)\n"
            "   - aci: list contains payment's ACI (or empty = all)\n"
            "   - mcc: list contains merchant's MCC (or empty = all)\n"
            "   - is_credit: matches or NULL\n"
            "   - intracountry: matches or NULL\n"
            "   - capture_delay: matches merchant_data.capture_delay_bucket or NULL\n"
            "   - monthly_volume: matches volume_tier or NULL\n"
            "   - monthly_fraud_level: matches fraud_tier or NULL\n"
        )
        if "Fee Rule Matching Checklist" not in current_instructions:
            updates.append(fee_fix)

    if classified.get("formatting_error", 0) > 0:
        fmt_fix = (
            "\n\n## Answer Formatting Rules\n"
            "- Follow the Guidelines section EXACTLY for format.\n"
            "- For multiple choice: answer with the EXACT option text including letter "
            "(e.g., 'B. BE', not just 'NL').\n"
            "- For decimals: match exact decimal places requested.\n"
            "- For lists: comma-separated, no brackets.\n"
        )
        if "Answer Formatting Rules" not in current_instructions:
            updates.append(fmt_fix)

    if classified.get("wrong_filter", 0) > 0:
        filter_fix = (
            "\n\n## Fee Matching Filter Logic\n"
            "- NULL or empty list in a fee field = wildcard (matches everything).\n"
            "- For list fields: the value must be IN the list.\n"
            "- intracountry: CASE WHEN issuing_country = acquirer_country THEN 1 ELSE 0 END.\n"
        )
        if "Fee Matching Filter Logic" not in current_instructions:
            updates.append(filter_fix)

    # Check for SQL errors in failures
    sql_errors = sum(1 for f in failures if f.get("has_sql_error"))
    if sql_errors > 0:
        sql_fix = (
            "\n\n## SQL Table Reference\n"
            "- All tables prefixed with `uploads.main.`\n"
            "- Fee columns: monthly_fraud_level (not fraud_level), monthly_volume (not volume).\n"
        )
        if "SQL Table Reference" not in current_instructions:
            updates.append(sql_fix)

    # Check for format_missing
    format_missing = sum(1 for f in failures if f.get("error_type") == "format_missing")
    if format_missing > 0:
        final_fix = (
            "\n\n## CRITICAL: Always Include FINAL_ANSWER\n"
            "You MUST end EVERY response with:\n"
            "```\n"
            "FINAL_ANSWER: <your answer>\n"
            "```\n"
            "Even if you encounter a SQL error, provide your best estimate.\n"
        )
        if "CRITICAL: Always Include FINAL_ANSWER" not in current_instructions:
            updates.append(final_fix)

    if not updates:
        logger.info("No new instruction updates to apply.")
        return None

    updated = current_instructions.rstrip() + "\n" + "\n".join(updates)
    logger.info("Generated %d instruction updates", len(updates))
    return updated


def _get_current_instructions() -> str:
    """Get current instruction note content from DOT or local file."""
    # Try reading from local instruction file first
    local_path = Path("data/dot_fee_instructions.md")
    if local_path.exists():
        return local_path.read_text(encoding="utf-8")

    # Try fetching from DOT API
    try:
        from tools.dot_context_manager import DotContextManager
        mgr = DotContextManager()
        assets = mgr.list_external_assets()
        for a in assets:
            if a.get("id") == INSTRUCTIONS_NOTE_ID:
                return a.get("dot_description", "")
    except Exception as exc:
        logger.warning("Failed to fetch instructions from DOT: %s", exc)

    return ""


def _apply_instructions(instructions: str) -> bool:
    """Apply updated instructions to DOT context via the context manager.

    Returns True if successful.
    """
    # Write to local file
    local_path = Path("data/dot_fee_instructions.md")
    local_path.write_text(instructions, encoding="utf-8")
    logger.info("Updated local instructions file: %s (%d chars)", local_path, len(instructions))

    # Try pushing to DOT API
    try:
        from tools.dot_context_manager import DotContextManager
        mgr = DotContextManager()
        result = mgr.upsert_note(
            INSTRUCTIONS_NOTE_ID,
            INSTRUCTIONS_NOTE_TITLE,
            instructions,
        )
        logger.info("Pushed instructions to DOT: %s", result)
        return True
    except Exception as exc:
        logger.warning("Failed to push instructions to DOT API: %s", exc)
        logger.info("Instructions saved locally only. Push manually if needed.")
        return False


def _write_iteration_summary(
    run_dir: Path,
    iteration: int,
    run_id: str,
    eval_result: dict,
    failure_stats: dict,
    instructions_updated: bool,
    prev_best: float,
) -> Path:
    """Write a per-iteration summary markdown file."""
    accuracy = eval_result["accuracy"]
    total = eval_result["total"]
    correct = eval_result["total_score"]
    delta = accuracy - prev_best

    lines = [
        f"# Iteration {iteration} Summary\n",
        f"- **Run ID:** `{run_id}`",
        f"- **Score:** {correct}/{total} = {accuracy:.1%}",
        f"- **Previous best:** {prev_best:.1%}",
        f"- **Delta:** {delta:+.1%}",
        f"- **Instructions updated:** {instructions_updated}",
        "",
        "## Per-Question Results\n",
        "| QID | Score | Expected | Got | Error |",
        "|-----|-------|----------|-----|-------|",
    ]

    # Successes
    for s in failure_stats.get("successes", []):
        gt = s["ground_truth"][:30]
        pa = (s["parsed_answer"] or "")[:30]
        lines.append(f"| {s['question_id']} | 1 | `{gt}` | `{pa}` | - |")

    # Failures
    for f_item in failure_stats.get("failures", []):
        gt = f_item["ground_truth"][:30]
        pa = (f_item["parsed_answer"] or "None")[:30]
        err = f_item.get("classified_error", f_item.get("error_type", ""))
        lines.append(f"| {f_item['question_id']} | 0 | `{gt}` | `{pa}` | {err} |")

    lines.append("")

    # Error summary
    if failure_stats.get("classified_errors"):
        lines.append("## Error Categories\n")
        for cat, count in failure_stats["classified_errors"].items():
            lines.append(f"- **{cat}:** {count}")
        lines.append("")

    # Context notes updated
    if instructions_updated:
        lines.append("## Context Changes Applied\n")
        lines.append("- Pushed updated `org_instructions` note to DOT API")
        for cat, count in failure_stats.get("classified_errors", {}).items():
            if count > 0:
                lines.append(f"  - Addressed: {cat} ({count} failures)")
        lines.append("")

    summary_path = run_dir / "iteration_summary.md"
    summary_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Iteration summary written to %s", summary_path)
    return summary_path


def run_iterate_loop(
    client: DotClient | None = None,
    source: str = "hf",
    split: str | None = "dev",
    limit: int | None = 10,
    dot_mode: str = "agentic",
    max_iterations: int = 5,
    max_stale: int = 2,
    max_workers: int = 5,
    target30: bool = False,
    target_n: int | None = None,
) -> dict:
    """Run the iterate loop: eval -> analyze -> patch -> rerun.

    Args:
        client: DotClient instance.
        source: Task source ('hf' or 'jsonl').
        split: HF split (default 'dev' for dev iteration).
        limit: Max tasks per iteration (default 10 for dev).
        dot_mode: 'agentic' or 'ask'.
        max_iterations: Max loop iterations (default 5).
        max_stale: Stop after this many iterations without improvement (default 2).
        max_workers: Concurrent workers for async eval.
        target30: If True, use target 30 tasks.
        target_n: Slice to first N tasks.

    Returns:
        Dict with iteration history and final stats.
    """
    if client is None:
        logger.warning("No client provided — using FakeDotClient")
        client = FakeDotClient()

    history = _load_score_history()
    best_score = max((h["accuracy"] for h in history), default=0.0)
    stale_count = 0

    print("\n" + "=" * 60)
    print("  ITERATE LOOP: Analyze -> Patch Context -> Rerun")
    print(f"  Max iterations: {max_iterations}, Stop after {max_stale} stale")
    print(f"  Best historical score: {best_score:.1%}")
    print("=" * 60)

    for iteration in range(1, max_iterations + 1):
        print(f"\n{'='*60}")
        print(f"  ITERATION {iteration}/{max_iterations}")
        print(f"{'='*60}")

        # Step 1: Run async evaluation
        print("\n  [1/5] Running async evaluation...")
        eval_result = run_async_eval(
            client=client,
            source=source,
            split=split,
            limit=limit,
            dot_mode=dot_mode,
            max_workers=max_workers,
            target30=target30,
            target_n=target_n,
        )

        run_id = eval_result["run_id"]
        run_dir = eval_result["run_dir"]
        accuracy = eval_result["accuracy"]

        # Step 2: Generate failure report
        print("\n  [2/5] Generating failure report...")
        results_path = run_dir / "results.jsonl"
        report_path = run_dir / "failure_report.md"
        failure_stats = generate_failure_report(results_path, report_path)
        print(f"    Report: {report_path}")

        # Step 3: Export context snapshot (before)
        print("\n  [3/5] Exporting context snapshot (before)...")
        context_before_path = run_dir / "context_before.md"
        _export_context_snapshot(context_before_path)

        # Step 4: Propose and apply instruction updates
        print("\n  [4/5] Proposing instruction updates...")
        current_instructions = _get_current_instructions()
        updated_instructions = _build_updated_instructions(current_instructions, failure_stats)

        if updated_instructions:
            _apply_instructions(updated_instructions)
            print("    Instructions updated.")

            # Export context snapshot (after)
            context_after_path = run_dir / "context_after.md"
            _export_context_snapshot(context_after_path)

            # Write diff summary
            diff_path = run_dir / "instruction_diff.md"
            diff_lines = [
                "# Instruction Diff Summary\n",
                f"- **Iteration:** {iteration}",
                f"- **Run ID:** {run_id}",
                f"- **Before length:** {len(current_instructions)} chars",
                f"- **After length:** {len(updated_instructions)} chars",
                f"- **Added:** {len(updated_instructions) - len(current_instructions)} chars",
                "",
                "## Changes Applied",
                "",
                "New sections added based on failure analysis:",
                "",
            ]
            for cat, count in failure_stats.get("classified_errors", {}).items():
                if count > 0:
                    diff_lines.append(f"- {cat}: {count} failures addressed")
            diff_path.write_text("\n".join(diff_lines), encoding="utf-8")
        else:
            print("    No instruction changes needed.")

        # Step 5: Update score history + write per-iteration summary
        entry = {
            "iteration": iteration,
            "run_id": run_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total": eval_result["total"],
            "correct": eval_result["total_score"],
            "accuracy": accuracy,
            "error_counts": eval_result["error_counts"],
            "instructions_updated": updated_instructions is not None,
        }
        history.append(entry)
        _save_score_history(history)

        # Write per-iteration summary
        _write_iteration_summary(
            run_dir, iteration, run_id, eval_result, failure_stats,
            updated_instructions is not None, best_score,
        )

        print(f"\n  [5/5] Score: {eval_result['total_score']}/{eval_result['total']} = {accuracy:.1%}")
        print(f"    Best so far: {max(best_score, accuracy):.1%}")

        # Check stopping conditions
        if accuracy >= 1.0:
            print("\n  PERFECT SCORE! Stopping.")
            break

        if accuracy > best_score:
            best_score = accuracy
            stale_count = 0
            print(f"    Improvement! New best: {best_score:.1%}")
        else:
            stale_count += 1
            print(f"    No improvement ({stale_count}/{max_stale} stale iterations)")

        if stale_count >= max_stale:
            print(f"\n  No improvement for {max_stale} iterations. Stopping.")
            break

    # Final summary
    print("\n" + "=" * 60)
    print("  ITERATE LOOP COMPLETE")
    print(f"  Iterations: {len(history)}")
    print(f"  Best accuracy: {best_score:.1%}")
    print(f"  Score history: {SCORE_HISTORY_PATH}")
    print("=" * 60)

    return {
        "iterations": len(history),
        "best_accuracy": best_score,
        "history": history,
        "score_history_path": str(SCORE_HISTORY_PATH),
    }


def main() -> None:
    """CLI entry point for iterate loop."""
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    parser = argparse.ArgumentParser(description="Run iterate loop: eval -> analyze -> patch -> rerun")
    parser.add_argument(
        "--client", default="fake", choices=["live", "dot", "fake"],
        help="Client: 'live'/'dot' for real Dot API, 'fake' for testing",
    )
    parser.add_argument("--dot-mode", default="agentic", choices=["ask", "agentic"])
    parser.add_argument("--source", default="hf", choices=["hf", "jsonl"])
    parser.add_argument("--split", default="dev")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--max-iterations", type=int, default=5)
    parser.add_argument("--max-stale", type=int, default=2)
    parser.add_argument("--max-workers", type=int, default=5)
    parser.add_argument("--target30", action="store_true")
    parser.add_argument("--target-n", type=int, default=None)
    parser.add_argument("--reset-history", action="store_true", help="Reset score history before starting")
    args = parser.parse_args()

    if args.reset_history and SCORE_HISTORY_PATH.exists():
        SCORE_HISTORY_PATH.unlink()
        print("Score history reset.")

    if args.client in ("live", "dot"):
        client: DotClient = LiveDotClient(mode=args.dot_mode)
        print("Running Dot API preflight check...")
        pf = client.preflight()
        print(f"  Preflight: ok={pf['ok']}  status={pf['status_code']}  latency={pf['latency_s']}s")
        if not pf["ok"]:
            print(f"  WARNING: Preflight FAILED.")
    else:
        client = FakeDotClient()

    result = run_iterate_loop(
        client=client,
        source=args.source,
        split=args.split,
        limit=args.limit,
        dot_mode=args.dot_mode,
        max_iterations=args.max_iterations,
        max_stale=args.max_stale,
        max_workers=args.max_workers,
        target30=args.target30,
        target_n=args.target_n,
    )
    print(f"\nFinal best accuracy: {result['best_accuracy']:.1%}")


if __name__ == "__main__":
    main()
