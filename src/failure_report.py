"""Failure analysis report generator.

Produces a structured Markdown report from evaluation results,
including per-question diffs, error taxonomy, and suggested fixes.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from pathlib import Path

logger = logging.getLogger(__name__)

# Error taxonomy categories
ERROR_CATEGORIES = {
    "wrong_aggregation": [
        "sum", "count", "average", "avg", "total", "aggregate", "group by",
    ],
    "wrong_filter": [
        "filter", "where", "condition", "subset", "criteria",
    ],
    "wrong_join": [
        "join", "merge", "relationship", "foreign key",
    ],
    "wrong_definition": [
        "definition", "formula", "calculation", "compute",
    ],
    "formatting_error": [
        "format", "decimal", "round", "precision", "percentage",
    ],
    "missing_tier_filter": [
        "tier", "volume_tier", "fraud_tier", "monthly",
    ],
}


def _extract_question_text(prompt: str) -> str:
    """Extract just the question portion from a full prompt (strip system instruction)."""
    # The prompt format is: SYSTEM_INSTRUCTION + Guidelines: ... + Question: ... + REMINDER
    marker = "Question:"
    idx = prompt.find(marker)
    if idx >= 0:
        rest = prompt[idx + len(marker):]
        # Take up to the REMINDER section
        reminder_idx = rest.find("REMINDER:")
        if reminder_idx >= 0:
            return rest[:reminder_idx].strip()
        return rest.strip()
    return prompt


def _classify_error(
    prompt_or_question: str, guidelines: str, gold: str, predicted: str | None,
    error_type: str | None = None,
) -> str:
    """Classify a wrong answer into an error category based on question context and answer diff."""
    if predicted is None:
        return "format_missing"

    # Extract actual question text (not the full prompt with system instruction)
    question = _extract_question_text(prompt_or_question).lower()
    guidelines_lower = guidelines.lower()
    context = question + " " + guidelines_lower

    # Check for superset/subset errors (strong signal for tier filter issues)
    if error_type in ("superset_answer", "subset_answer"):
        return "missing_tier_filter"

    # Check if answer is a list and gold is a list but completely different
    if "," in (predicted or "") and "," in gold:
        gold_set = set(x.strip() for x in gold.split(","))
        pred_set = set(x.strip() for x in predicted.split(","))
        overlap = gold_set & pred_set
        if len(pred_set) > len(gold_set) * 1.5:
            return "missing_tier_filter"  # likely too many results
        if overlap and len(overlap) < len(gold_set) * 0.5:
            return "wrong_filter"

    # Check for close numeric (formatting/precision)
    if predicted and gold:
        try:
            p = float(predicted.replace(",", "").replace("%", "").replace("$", ""))
            g = float(gold.replace(",", "").replace("%", "").replace("$", ""))
            rel_diff = abs(p - g) / max(abs(g), 1e-9)
            if rel_diff < 0.01:
                return "formatting_error"
            if rel_diff < 0.05:
                return "precision_error"
        except (ValueError, TypeError):
            pass

    # Check for fee/tier questions based on question text (not system instruction)
    fee_keywords = ["fee id", "fee rule", "applicable fee", "matching fee"]
    if any(kw in context for kw in fee_keywords):
        return "wrong_fee_match"

    # Check for aggregation keywords in question
    if any(kw in context for kw in ERROR_CATEGORIES["wrong_aggregation"]):
        return "wrong_aggregation"

    # Check for formatting issues indicated by guidelines
    if any(kw in guidelines_lower for kw in ["decimal", "round", "precision"]):
        return "formatting_error"

    return "wrong_answer"


def generate_failure_report(
    results_path: Path,
    output_path: Path | None = None,
) -> dict:
    """Generate a failure analysis report from results JSONL.

    Args:
        results_path: Path to results JSONL file.
        output_path: Path for the Markdown report. Auto-derived if None.

    Returns:
        Dict with summary stats: total, correct, accuracy, error_breakdown, failures.
    """
    records = []
    with open(results_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    if not records:
        raise ValueError(f"No records in {results_path}")

    total = len(records)
    correct = sum(1 for r in records if r["score"] == 1)
    accuracy = correct / total if total > 0 else 0.0

    # Per-question analysis
    failures = []
    successes = []
    error_types = Counter()
    classified_errors = Counter()

    for r in records:
        if r["score"] == 0:
            category = _classify_error(
                r.get("prompt", ""),
                r.get("guidelines", ""),
                r.get("ground_truth", ""),
                r.get("parsed_answer"),
                error_type=r.get("error_type"),
            )
            failures.append({
                "question_id": r["question_id"],
                "difficulty": r.get("difficulty", "unknown"),
                "ground_truth": r.get("ground_truth", ""),
                "parsed_answer": r.get("parsed_answer"),
                "error_type": r.get("error_type", "unknown"),
                "classified_error": category,
                "guidelines": r.get("guidelines", "")[:200],
                "has_sql": r.get("has_sql", False),
                "has_sql_error": r.get("has_sql_error", False),
                "latency_s": r.get("latency_s"),
                "response_preview": (r.get("dot_response_raw", "") or "")[:500],
            })
            if r.get("error_type"):
                error_types[r["error_type"]] += 1
            classified_errors[category] += 1
        else:
            successes.append({
                "question_id": r["question_id"],
                "difficulty": r.get("difficulty", "unknown"),
                "ground_truth": r.get("ground_truth", ""),
                "parsed_answer": r.get("parsed_answer"),
                "latency_s": r.get("latency_s"),
            })

    # Build report
    if output_path is None:
        output_path = results_path.parent / "failure_report.md"

    lines = []
    lines.append("# Failure Analysis Report\n")
    lines.append(f"- **Results file:** `{results_path}`")
    lines.append(f"- **Total questions:** {total}")
    lines.append(f"- **Correct:** {correct}")
    lines.append(f"- **Accuracy:** {accuracy:.1%}")
    lines.append("")

    # Error breakdown
    lines.append("## Error Type Breakdown\n")
    lines.append("| Error Type | Count |")
    lines.append("|------------|-------|")
    for err, count in error_types.most_common():
        lines.append(f"| {err} | {count} |")
    lines.append("")

    # Classified error breakdown
    lines.append("## Error Category Classification\n")
    lines.append("| Category | Count |")
    lines.append("|----------|-------|")
    for cat, count in classified_errors.most_common():
        lines.append(f"| {cat} | {count} |")
    lines.append("")

    # Per-question details
    lines.append("## Per-Question Analysis\n")

    # Successes first (brief)
    if successes:
        lines.append("### Correct Answers\n")
        lines.append("| QID | Difficulty | Answer | Latency |")
        lines.append("|-----|-----------|--------|---------|")
        for s in successes:
            ans = repr(s["ground_truth"])[:40]
            lat = f"{s['latency_s']:.1f}s" if s["latency_s"] else "N/A"
            lines.append(f"| {s['question_id']} | {s['difficulty']} | {ans} | {lat} |")
        lines.append("")

    # Failures in detail
    if failures:
        lines.append("### Failed Answers\n")
        for f_item in failures:
            lines.append(f"#### Question {f_item['question_id']} ({f_item['difficulty']})")
            lines.append(f"- **Error type:** {f_item['error_type']}")
            lines.append(f"- **Category:** {f_item['classified_error']}")
            lines.append(f"- **Expected:** `{f_item['ground_truth']}`")
            lines.append(f"- **Got:** `{f_item['parsed_answer']}`")
            lines.append(f"- **Guidelines:** {f_item['guidelines']}")
            lines.append(f"- **Has SQL:** {f_item['has_sql']}")
            lines.append(f"- **SQL Error:** {f_item['has_sql_error']}")
            if f_item["response_preview"]:
                preview = f_item["response_preview"].replace("\n", " ")[:300]
                lines.append(f"- **Response preview:** {preview}")
            lines.append("")

    # Suggested instruction updates
    lines.append("## Suggested Instruction Updates\n")
    suggestions = _generate_suggestions(failures, classified_errors)
    for i, s in enumerate(suggestions, 1):
        lines.append(f"{i}. **{s['category']}**: {s['suggestion']}")
    lines.append("")

    report_text = "\n".join(lines)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report_text, encoding="utf-8")
    logger.info("Failure report written to %s", output_path)

    return {
        "total": total,
        "correct": correct,
        "accuracy": accuracy,
        "error_breakdown": dict(error_types),
        "classified_errors": dict(classified_errors),
        "failures": failures,
        "successes": successes,
        "report_path": str(output_path),
    }


def _generate_suggestions(
    failures: list[dict],
    classified_errors: Counter,
) -> list[dict]:
    """Generate suggested instruction updates based on failure patterns."""
    suggestions = []

    if classified_errors.get("missing_tier_filter", 0) > 0:
        suggestions.append({
            "category": "Monthly Tier Filter",
            "suggestion": (
                "Strengthen the instruction about MANDATORY monthly tier lookups. "
                "For fee ID questions by date, ALWAYS join monthly_merchant_stats "
                "to get volume_tier and fraud_tier BEFORE filtering fees. "
                "day_of_year must be converted to month correctly."
            ),
        })

    if classified_errors.get("wrong_fee_match", 0) > 0:
        suggestions.append({
            "category": "Fee ID Matching",
            "suggestion": (
                "Fee matching requires checking ALL criteria simultaneously. "
                "Each fee field that is non-null must match the transaction. "
                "intracountry is computed per-transaction, not per-merchant."
            ),
        })

    if classified_errors.get("precision_error", 0) > 0:
        suggestions.append({
            "category": "Numeric Precision",
            "suggestion": (
                "Fee calculations must use precise arithmetic. "
                "fee = fixed_amount + (rate * eur_amount / 10000.0). "
                "Ensure all intermediate values preserve full precision. "
                "Use the exact fee rate from the matching rule."
            ),
        })

    if classified_errors.get("wrong_aggregation", 0) > 0:
        suggestions.append({
            "category": "Aggregation",
            "suggestion": (
                "Clarify aggregation instructions: 'total' = SUM, "
                "'average' = AVG, 'count' = COUNT. "
                "Check whether to aggregate over all rows or distinct values."
            ),
        })

    if classified_errors.get("wrong_filter", 0) > 0:
        suggestions.append({
            "category": "Filtering",
            "suggestion": (
                "Add explicit day_of_year to month conversion: "
                "Jan=1-31, Feb=32-59, Mar=60-90, Apr=91-120. "
                "NULL in fees means 'matches all', not 'matches NULL'."
            ),
        })

    if classified_errors.get("formatting_error", 0) > 0:
        suggestions.append({
            "category": "Answer Formatting",
            "suggestion": (
                "FINAL_ANSWER must exactly match the format in Guidelines. "
                "For multiple choice: answer with the EXACT letter+option from the choices. "
                "For decimals: match exact decimal places requested."
            ),
        })

    # Check for SQL errors in failures
    sql_error_count = sum(1 for f in failures if f.get("has_sql_error"))
    if sql_error_count > 0:
        suggestions.append({
            "category": "SQL Errors",
            "suggestion": (
                f"{sql_error_count} failures had SQL errors. "
                "Use 'uploads.main.' prefix for all tables. "
                "Column names are case-sensitive."
            ),
        })

    # Check for format_missing errors
    format_missing = sum(1 for f in failures if f.get("error_type") == "format_missing")
    if format_missing > 0:
        suggestions.append({
            "category": "Missing FINAL_ANSWER",
            "suggestion": (
                f"{format_missing} responses lacked FINAL_ANSWER. "
                "Always end with FINAL_ANSWER: <answer>."
            ),
        })

    if not suggestions:
        suggestions.append({
            "category": "General",
            "suggestion": "No specific patterns detected. Review individual failures manually.",
        })

    return suggestions


def main() -> None:
    """CLI entry point."""
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    parser = argparse.ArgumentParser(description="Generate failure analysis report")
    parser.add_argument("results_file", type=Path, help="Path to results JSONL")
    parser.add_argument("--output", type=Path, default=None, help="Output report path")
    args = parser.parse_args()

    stats = generate_failure_report(args.results_file, args.output)
    print(f"\nReport: {stats['report_path']}")
    print(f"Score: {stats['correct']}/{stats['total']} = {stats['accuracy']:.1%}")


if __name__ == "__main__":
    main()
