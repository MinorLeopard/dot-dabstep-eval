"""Evaluation runner — orchestrates load, prompt, call, score, and write."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from tqdm import tqdm

from src.dabstep_loader import filter_target_tasks, load_tasks
from src.dot_client import (
    DotClient,
    DotEmptyResponseError,
    DotHttpError,
    FakeDotClient,
    LiveDotClient,
)
from src.prompting import build_prompt, parse_final_answer
from src.scoring import score_answer

logger = logging.getLogger(__name__)

RESULTS_DIR = Path("results")
SUBMISSIONS_DIR = Path("submissions")


def generate_run_id() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    short_uuid = uuid.uuid4().hex[:6]
    return f"{ts}_{short_uuid}"


def run_eval(
    client: DotClient | None = None,
    source: str = "hf",
    jsonl_path: Path | None = None,
    limit: int | None = None,
    run_id: str | None = None,
    results_dir: Path = RESULTS_DIR,
    dot_mode: str = "agentic",
    target30: bool = False,
    target_n: int | None = None,
    split: str | None = None,
) -> Path:
    """Run the full evaluation pipeline.

    Args:
        client: DotClient instance. Defaults to FakeDotClient.
        source: 'hf' or 'jsonl'.
        jsonl_path: Path to JSONL file (if source='jsonl').
        limit: Max number of tasks to evaluate.
        run_id: Custom run ID. Auto-generated if None.
        results_dir: Directory to write results.
        dot_mode: Dot API mode used (recorded in each result).
        target30: If True, filter to the 30 target task IDs.
        target_n: If set, slice to first N tasks AFTER target30 filtering.
        split: HF dataset split to use (e.g. 'dev', 'default').

    Returns:
        Path to the results JSONL file.
    """
    if client is None:
        logger.warning("No client provided — using FakeDotClient")
        client = FakeDotClient()

    if run_id is None:
        run_id = generate_run_id()

    tasks = load_tasks(source=source, path=jsonl_path, limit=limit, split=split)
    if target30:
        tasks = filter_target_tasks(tasks)
    if target_n is not None:
        tasks = tasks[:target_n]
        logger.info("Sliced to first %d tasks (--target-n)", target_n)
    if not tasks:
        raise ValueError("No tasks loaded. Check source and path.")

    # Sanity-check ground truth
    empty_gt = sum(1 for t in tasks if not t.ground_truth)
    if empty_gt:
        logger.warning(
            "WARNING: %d/%d tasks have EMPTY ground_truth — local scoring will be unreliable!",
            empty_gt, len(tasks),
        )

    results_dir.mkdir(parents=True, exist_ok=True)
    output_path = results_dir / f"{run_id}.jsonl"

    total_score = 0
    total = 0
    error_counts: dict[str, int] = {}
    submission_rows: list[dict] = []

    logger.info("Starting eval run %s — %d tasks", run_id, len(tasks))

    consecutive_errors = 0
    MAX_CONSECUTIVE_ERRORS = 2

    with open(output_path, "w", encoding="utf-8") as out:
        for task in tqdm(tasks, desc=f"Eval {run_id}"):
            prompt = build_prompt(task)
            chat_id = f"{run_id}_{task.question_id}"

            parsed_answer: str | None = None
            latency_s: float | None = None
            dot_status: int | None = None
            dot_error_body: str | None = None
            dot_error_type: str | None = None
            raw_text = ""

            import time as _time
            t0 = _time.monotonic()
            try:
                response = client.query(prompt, chat_id=chat_id)
                raw_text = response.text
                dot_status = 200
                if response.usage:
                    pass  # latency computed below from wall clock
                consecutive_errors = 0
            except DotHttpError as exc:
                dot_status = exc.status_code
                dot_error_body = str(exc)[:500]
                dot_error_type = "dot_http_error"
                logger.error("HTTP %d on %s: %s", dot_status, task.question_id, dot_error_body[:200])
                consecutive_errors += 1
            except DotEmptyResponseError as exc:
                dot_status = 200
                dot_error_body = str(exc)[:500]
                dot_error_type = "dot_empty_response"
                logger.error("Empty response on %s: %s", task.question_id, exc)
                consecutive_errors += 1
            except Exception as exc:
                dot_error_body = f"{type(exc).__name__}: {exc}"[:500]
                dot_error_type = "client_error"
                logger.error("Client error on %s: %s", task.question_id, dot_error_body[:200])
                consecutive_errors += 1
            latency_s = round(_time.monotonic() - t0, 2)

            if dot_error_type:
                sc, error_type = 0, dot_error_type
            else:
                parsed_answer = parse_final_answer(raw_text)
                sc, error_type = score_answer(parsed_answer, task.ground_truth)

            total_score += sc
            total += 1
            if error_type:
                error_counts[error_type] = error_counts.get(error_type, 0) + 1

            record = {
                "question_id": task.question_id,
                "difficulty": task.difficulty,
                "guidelines": task.metadata.get("guidelines", ""),
                "chat_id": chat_id,
                "prompt": prompt,
                "dot_response_raw": raw_text,
                "parsed_answer": parsed_answer,
                "ground_truth": task.ground_truth,
                "score": sc,
                "error_type": error_type,
                "dot_mode": dot_mode,
                "dot_status": dot_status,
                "dot_error_body": dot_error_body,
                "latency_s": latency_s,
            }
            out.write(json.dumps(record) + "\n")

            submission_rows.append({
                "task_id": task.question_id,
                "agent_answer": parsed_answer if parsed_answer is not None else "",
                "reasoning_trace": raw_text,
            })

            # Fail-fast: abort after MAX_CONSECUTIVE_ERRORS consecutive Dot failures
            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                logger.error(
                    "FAIL-FAST: %d consecutive Dot errors — aborting run. Last: %s",
                    consecutive_errors, dot_error_type,
                )
                break


    accuracy = total_score / total if total > 0 else 0.0
    logger.info(
        "Run %s complete — %d/%d correct (%.1f%%), errors: %s",
        run_id,
        total_score,
        total,
        accuracy * 100,
        error_counts,
    )

    # Always write HF-compatible submission file
    sub_dir = SUBMISSIONS_DIR
    sub_dir.mkdir(parents=True, exist_ok=True)
    sub_path = sub_dir / f"{run_id}.jsonl"
    with open(sub_path, "w", encoding="utf-8") as sf:
        for row in submission_rows:
            sf.write(json.dumps(row) + "\n")

    score_pct = (total_score / total * 100) if total > 0 else 0.0
    print()
    print("=" * 60)
    print(f"  Score: {total_score}/{total} = {score_pct:.1f}%")
    print(f"  Results:    {output_path}")
    print(f"  Submission: {sub_path}")
    print("=" * 60)

    return output_path


def _print_diagnostic_report(results_path: Path) -> None:
    """Print a compact per-task diagnostic after a run."""
    try:
        records = []
        with open(results_path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    records.append(json.loads(line))
        if not records:
            return

        print("\n" + "=" * 80)
        print("  PER-TASK DIAGNOSTIC REPORT")
        print("=" * 80)
        for r in records:
            qid = r["question_id"]
            gt = r.get("ground_truth", "")
            gt_preview = (gt[:120] + "...") if len(gt) > 120 else gt
            gt_display = repr(gt_preview) if gt else "(EMPTY)"
            raw = r.get("dot_response_raw", "")
            err_body = r.get("dot_error_body", "")
            preview = (raw[:300] if raw else err_body[:300]).replace("\n", " | ")

            print(f"\n  [{qid}] difficulty={r.get('difficulty','?')}")
            print(f"    guidelines : {r.get('guidelines','')[:100]}")
            print(f"    ground_truth: {gt_display} (len={len(gt)})")
            print(f"    dot_status : {r.get('dot_status','?')}  latency_s: {r.get('latency_s','?')}")
            print(f"    response   : {preview[:300]}")
            print(f"    parsed     : {r.get('parsed_answer')}")
            print(f"    score={r['score']}  error_type={r.get('error_type')}")
        print("=" * 80)
    except Exception as exc:
        logger.warning("Could not print diagnostic report: %s", exc)


def main() -> None:
    """CLI entry point."""
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    parser = argparse.ArgumentParser(description="Run DABStep evaluation")
    parser.add_argument("--source", default="hf", choices=["hf", "jsonl"])
    parser.add_argument("--jsonl-path", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--run-id", type=str, default=None)
    parser.add_argument("--results-dir", type=Path, default=RESULTS_DIR)
    parser.add_argument(
        "--client",
        default="fake",
        choices=["live", "dot", "fake"],
        help="Client to use: 'live'/'dot' for real Dot API, 'fake' for deterministic testing",
    )
    parser.add_argument(
        "--dot-mode",
        default="agentic",
        choices=["ask", "agentic"],
        help="Dot API mode: 'ask' for /api/ask, 'agentic' for /api/agentic",
    )
    parser.add_argument(
        "--target30",
        action="store_true",
        help="Run only the 30 target task IDs and produce a submission file",
    )
    parser.add_argument(
        "--target-n",
        type=int,
        default=None,
        help="After --target30 filtering, slice to first N tasks",
    )
    parser.add_argument(
        "--split",
        type=str,
        default=None,
        help="HF dataset split to use (e.g. 'dev', 'default'). Default: 'default'",
    )
    args = parser.parse_args()

    if args.client in ("live", "dot"):
        client: DotClient = LiveDotClient(mode=args.dot_mode)
        # Preflight check
        print("Running Dot API preflight check...")
        pf = client.preflight()
        print(f"  Preflight: ok={pf['ok']}  status={pf['status_code']}  latency={pf['latency_s']}s")
        if not pf["ok"]:
            print(f"  Body: {pf['body_preview'][:300]}")
            print("  WARNING: Dot API preflight FAILED — run may fail.")
    else:
        client = FakeDotClient()

    output = run_eval(
        client=client,
        source=args.source,
        jsonl_path=args.jsonl_path,
        limit=args.limit,
        run_id=args.run_id,
        results_dir=args.results_dir,
        dot_mode=args.dot_mode,
        target30=args.target30,
        target_n=args.target_n,
        split=args.split,
    )
    print(f"Results written to {output}")

    # Compact per-task diagnostic report
    _print_diagnostic_report(output)


if __name__ == "__main__":
    main()
