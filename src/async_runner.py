"""Async evaluation runner — concurrent question submission with polling and manifests.

Submits all questions concurrently via a thread pool, tracks per-question status,
and writes structured artifacts to artifacts/runs/<run_id>/.
"""

from __future__ import annotations

import json
import logging
import random
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed, Future
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.dabstep_loader import Task, filter_target_tasks, load_tasks
from src.dot_client import (
    DotClient,
    DotEmptyResponseError,
    DotHttpError,
    FakeDotClient,
    LiveDotClient,
)
from src.prompting import build_prompt, parse_final_answer
from src.scoring import score_answer
from src.runner import generate_run_id

logger = logging.getLogger(__name__)

ARTIFACTS_DIR = Path("artifacts")
RESULTS_DIR = Path("results")
SUBMISSIONS_DIR = Path("submissions")

# Exponential backoff schedule for polling (seconds)
POLL_BACKOFF = [30, 60, 120, 300, 600, 900]  # then every 900s
MAX_WALL_CLOCK_S = 45 * 60  # 45 minutes


@dataclass
class QuestionStatus:
    """Tracks the status of a single submitted question."""

    question_id: str
    request_id: str  # chat_id sent to Dot
    run_id: str
    submitted_at: str
    status: str = "pending"  # pending -> running -> completed | error | timeout
    completed_at: str | None = None
    latency_s: float | None = None
    raw_text: str = ""
    parsed_answer: str | None = None
    ground_truth: str = ""
    difficulty: str = "unknown"
    guidelines: str = ""
    score: int = 0
    error_type: str | None = None
    dot_status: int | None = None
    dot_error_body: str | None = None
    has_sql: bool = False
    has_sql_error: bool = False
    response_length: int = 0
    prompt: str = ""


PER_QUESTION_TIMEOUT_S = 45 * 60  # 45 minutes per question hard cap
RATE_LIMIT_RETRIES = 3


def _execute_question(
    task: Task,
    client: DotClient,
    run_id: str,
) -> QuestionStatus:
    """Execute a single question against the Dot client. Runs in a worker thread.

    Includes:
    - Per-question 45-min hard timeout
    - Retry with exponential backoff + jitter for rate-limit (429) and 5xx errors
    """
    chat_id = f"{run_id}_{task.question_id}"
    prompt = build_prompt(task)
    now_str = datetime.now(timezone.utc).isoformat()

    qs = QuestionStatus(
        question_id=task.question_id,
        request_id=chat_id,
        run_id=run_id,
        submitted_at=now_str,
        status="running",
        ground_truth=task.ground_truth,
        difficulty=task.difficulty,
        guidelines=task.metadata.get("guidelines", ""),
        prompt=prompt,
    )

    t0 = time.monotonic()

    for attempt in range(RATE_LIMIT_RETRIES):
        elapsed = time.monotonic() - t0
        if elapsed > PER_QUESTION_TIMEOUT_S:
            qs.error_type = "dot_timeout"
            qs.status = "timeout"
            qs.dot_error_body = f"Per-question timeout after {elapsed:.0f}s"
            logger.warning("TIMEOUT Q%s after %.0fs", task.question_id, elapsed)
            break

        try:
            # Use fresh chat_id on retries to avoid stale state
            retry_chat_id = chat_id if attempt == 0 else f"{chat_id}_r{attempt}"
            response = client.query(prompt, chat_id=retry_chat_id)
            qs.raw_text = response.text
            qs.dot_status = 200
            qs.status = "completed"
            break  # success
        except DotHttpError as exc:
            qs.dot_status = exc.status_code
            qs.dot_error_body = str(exc)[:500]
            # Retry on 429 (rate limit) or 5xx
            if exc.status_code in (429, 500, 502, 503) and attempt < RATE_LIMIT_RETRIES - 1:
                backoff = (2 ** attempt) * 10 + random.uniform(0, 5)
                logger.warning(
                    "HTTP %d on Q%s (attempt %d/%d), retrying in %.0fs",
                    exc.status_code, task.question_id, attempt + 1, RATE_LIMIT_RETRIES, backoff,
                )
                time.sleep(backoff)
                continue
            qs.error_type = "dot_http_error"
            qs.status = "error"
            logger.error("HTTP %d on Q%s: %s", qs.dot_status, task.question_id, str(exc)[:200])
            break
        except DotEmptyResponseError as exc:
            qs.dot_status = 200
            qs.dot_error_body = str(exc)[:500]
            qs.error_type = "dot_empty_response"
            qs.status = "error"
            logger.error("Empty response on Q%s: %s", task.question_id, exc)
            break
        except Exception as exc:
            qs.dot_error_body = f"{type(exc).__name__}: {exc}"[:500]
            # Retry on generic timeout/connection errors
            if attempt < RATE_LIMIT_RETRIES - 1 and "timeout" in str(exc).lower():
                backoff = (2 ** attempt) * 15 + random.uniform(0, 5)
                logger.warning(
                    "Timeout Q%s (attempt %d/%d), retrying in %.0fs",
                    task.question_id, attempt + 1, RATE_LIMIT_RETRIES, backoff,
                )
                time.sleep(backoff)
                continue
            qs.error_type = "client_error"
            qs.status = "error"
            logger.error("Client error on Q%s: %s", task.question_id, str(exc)[:200])
            break

    qs.latency_s = round(time.monotonic() - t0, 2)
    qs.completed_at = datetime.now(timezone.utc).isoformat()

    # Parse and score if we got a response
    if qs.status == "completed":
        qs.parsed_answer = parse_final_answer(qs.raw_text)
        qs.score, qs.error_type = score_answer(qs.parsed_answer, qs.ground_truth)
        qs.has_sql = bool(re.search(r'\bSELECT\b', qs.raw_text, re.IGNORECASE))
        qs.has_sql_error = bool(re.search(
            r'(?:SQL error|syntax error|no such table|OperationalError)',
            qs.raw_text, re.IGNORECASE,
        ))
        qs.response_length = len(qs.raw_text)

    return qs


def submit_questions_async(
    tasks: list[Task],
    client: DotClient,
    run_id: str,
    max_workers: int = 5,
) -> dict[str, Future]:
    """Submit all questions concurrently via thread pool.

    Returns a dict mapping question_id -> Future[QuestionStatus].
    The caller should use poll_results() to wait for completion.
    """
    executor = ThreadPoolExecutor(max_workers=max_workers)
    futures: dict[str, Future] = {}

    for task in tasks:
        future = executor.submit(_execute_question, task, client, run_id)
        futures[task.question_id] = future
        logger.info("Submitted question %s", task.question_id)

    return futures


def poll_results(
    futures: dict[str, Future],
    max_wall_clock_s: int = MAX_WALL_CLOCK_S,
) -> dict[str, QuestionStatus]:
    """Poll for completion of all submitted questions.

    Uses exponential backoff: 30s -> 60s -> 2m -> 5m -> 10m -> 15m -> every 15m.
    Returns dict mapping question_id -> QuestionStatus.
    """
    results: dict[str, QuestionStatus] = {}
    start = time.monotonic()
    poll_idx = 0

    while True:
        elapsed = time.monotonic() - start
        pending = []
        newly_done = []

        for qid, future in futures.items():
            if qid in results:
                continue
            if future.done():
                try:
                    qs = future.result(timeout=0)
                    results[qid] = qs
                    newly_done.append(qid)
                except Exception as exc:
                    # Future raised an unhandled exception
                    qs = QuestionStatus(
                        question_id=qid,
                        request_id="",
                        run_id="",
                        submitted_at="",
                        status="error",
                        error_type="client_error",
                        dot_error_body=f"Future exception: {exc}"[:500],
                    )
                    results[qid] = qs
                    newly_done.append(qid)
            else:
                pending.append(qid)

        if newly_done:
            for qid in newly_done:
                qs = results[qid]
                status_icon = "+" if qs.score == 1 else ("X" if qs.status == "error" else "-")
                logger.info(
                    "[%s] Q%s completed: score=%d answer=%s (%.1fs)",
                    status_icon, qid, qs.score,
                    repr(qs.parsed_answer)[:60] if qs.parsed_answer else "None",
                    qs.latency_s or 0,
                )

        # Running score tally
        done_count = len(results)
        correct_count = sum(1 for r in results.values() if r.score == 1)

        if not pending:
            logger.info(
                "All %d questions completed (%.1fs elapsed) — score %d/%d",
                done_count, elapsed, correct_count, done_count,
            )
            break

        if elapsed > max_wall_clock_s:
            logger.warning(
                "TIMEOUT: Wall clock limit (%.0fs). %d pending [%s] — marking TIMEOUT.",
                elapsed, len(pending), ", ".join(sorted(pending)),
            )
            for qid in pending:
                futures[qid].cancel()
                results[qid] = QuestionStatus(
                    question_id=qid,
                    request_id=f"timeout_{qid}",
                    run_id="",
                    submitted_at="",
                    status="timeout",
                    error_type="dot_timeout",
                )
            break

        # Exponential backoff with jitter (±20%)
        base_wait = POLL_BACKOFF[min(poll_idx, len(POLL_BACKOFF) - 1)]
        jitter = base_wait * random.uniform(-0.2, 0.2)
        wait = max(5, base_wait + jitter)
        pending_str = ", ".join(sorted(pending))
        elapsed_min = elapsed / 60
        print(
            f"  POLL iter={poll_idx} | {done_count}/{len(futures)} done "
            f"(score {correct_count}/{done_count}) | pending=[{pending_str}] "
            f"| elapsed={elapsed_min:.1f}m | next_check={wait:.0f}s",
            flush=True,
        )
        time.sleep(wait)
        poll_idx += 1

    return results


def _write_manifest(
    run_dir: Path,
    run_id: str,
    results: dict[str, QuestionStatus],
) -> Path:
    """Write run manifest JSON."""
    manifest = {
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "total_questions": len(results),
        "completed": sum(1 for r in results.values() if r.status == "completed"),
        "errors": sum(1 for r in results.values() if r.status == "error"),
        "timeouts": sum(1 for r in results.values() if r.status == "timeout"),
        "questions": {},
    }
    for qid, qs in results.items():
        manifest["questions"][qid] = {
            "request_id": qs.request_id,
            "status": qs.status,
            "submitted_at": qs.submitted_at,
            "completed_at": qs.completed_at,
            "latency_s": qs.latency_s,
            "score": qs.score,
            "error_type": qs.error_type,
            "parsed_answer": qs.parsed_answer,
            "ground_truth": qs.ground_truth,
        }

    manifest_path = run_dir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    return manifest_path


def _write_results_jsonl(
    run_dir: Path,
    run_id: str,
    results: dict[str, QuestionStatus],
    dot_mode: str,
) -> Path:
    """Write results JSONL (compatible with existing format)."""
    results_path = run_dir / "results.jsonl"
    with open(results_path, "w", encoding="utf-8") as f:
        for qs in results.values():
            record = {
                "question_id": qs.question_id,
                "difficulty": qs.difficulty,
                "guidelines": qs.guidelines,
                "chat_id": qs.request_id,
                "prompt": qs.prompt,
                "dot_response_raw": qs.raw_text,
                "parsed_answer": qs.parsed_answer,
                "ground_truth": qs.ground_truth,
                "score": qs.score,
                "error_type": qs.error_type,
                "dot_mode": dot_mode,
                "dot_status": qs.dot_status,
                "dot_error_body": qs.dot_error_body,
                "latency_s": qs.latency_s,
                "response_length": qs.response_length,
                "has_sql": qs.has_sql,
                "has_sql_error": qs.has_sql_error,
            }
            f.write(json.dumps(record) + "\n")

    # Also write to results/ directory for compatibility
    compat_path = RESULTS_DIR / f"{run_id}.jsonl"
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(compat_path, "w", encoding="utf-8") as f:
        for qs in results.values():
            record = {
                "question_id": qs.question_id,
                "difficulty": qs.difficulty,
                "guidelines": qs.guidelines,
                "chat_id": qs.request_id,
                "prompt": qs.prompt,
                "dot_response_raw": qs.raw_text,
                "parsed_answer": qs.parsed_answer,
                "ground_truth": qs.ground_truth,
                "score": qs.score,
                "error_type": qs.error_type,
                "dot_mode": dot_mode,
                "dot_status": qs.dot_status,
                "dot_error_body": qs.dot_error_body,
                "latency_s": qs.latency_s,
                "response_length": qs.response_length,
                "has_sql": qs.has_sql,
                "has_sql_error": qs.has_sql_error,
            }
            f.write(json.dumps(record) + "\n")

    return results_path


def _write_submission(
    run_dir: Path,
    run_id: str,
    results: dict[str, QuestionStatus],
) -> Path:
    """Write HF-compatible submission JSONL."""
    sub_path = run_dir / "submission.jsonl"
    with open(sub_path, "w", encoding="utf-8") as f:
        for qs in results.values():
            row = {
                "task_id": qs.question_id,
                "agent_answer": qs.parsed_answer if qs.parsed_answer is not None else "",
                "reasoning_trace": qs.raw_text,
            }
            f.write(json.dumps(row) + "\n")

    # Also write to submissions/ for compatibility
    SUBMISSIONS_DIR.mkdir(parents=True, exist_ok=True)
    compat_path = SUBMISSIONS_DIR / f"{run_id}.jsonl"
    with open(compat_path, "w", encoding="utf-8") as f:
        for qs in results.values():
            row = {
                "task_id": qs.question_id,
                "agent_answer": qs.parsed_answer if qs.parsed_answer is not None else "",
                "reasoning_trace": qs.raw_text,
            }
            f.write(json.dumps(row) + "\n")

    return sub_path


def run_async_eval(
    client: DotClient | None = None,
    source: str = "hf",
    jsonl_path: Path | None = None,
    limit: int | None = None,
    run_id: str | None = None,
    dot_mode: str = "agentic",
    target30: bool = False,
    target_n: int | None = None,
    split: str | None = None,
    max_workers: int = 5,
    max_wall_clock_s: int = MAX_WALL_CLOCK_S,
) -> dict:
    """Run the full async evaluation pipeline.

    Returns dict with keys: run_id, run_dir, results_path, manifest_path,
    total_score, total, accuracy, results (dict of QuestionStatus).
    """
    if client is None:
        logger.warning("No client provided — using FakeDotClient")
        client = FakeDotClient()

    if run_id is None:
        run_id = generate_run_id()

    # Load tasks
    tasks = load_tasks(source=source, path=jsonl_path, limit=limit, split=split)
    if target30:
        tasks = filter_target_tasks(tasks)
    if target_n is not None:
        tasks = tasks[:target_n]
        logger.info("Sliced to first %d tasks (--target-n)", target_n)
    if not tasks:
        raise ValueError("No tasks loaded. Check source and path.")

    # Create run directory
    run_dir = ARTIFACTS_DIR / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    logger.info(
        "Starting async eval run %s — %d tasks, %d workers",
        run_id, len(tasks), max_workers,
    )

    # Submit all questions
    futures = submit_questions_async(tasks, client, run_id, max_workers=max_workers)

    # Poll for results
    results = poll_results(futures, max_wall_clock_s=max_wall_clock_s)

    # Compute summary
    total = len(results)
    total_score = sum(r.score for r in results.values())
    accuracy = total_score / total if total > 0 else 0.0
    error_counts: dict[str, int] = {}
    for r in results.values():
        if r.error_type:
            error_counts[r.error_type] = error_counts.get(r.error_type, 0) + 1

    # Write artifacts
    manifest_path = _write_manifest(run_dir, run_id, results)
    results_path = _write_results_jsonl(run_dir, run_id, results, dot_mode)
    sub_path = _write_submission(run_dir, run_id, results)

    logger.info(
        "Run %s complete — %d/%d correct (%.1f%%), errors: %s",
        run_id, total_score, total, accuracy * 100, error_counts,
    )

    # Print summary
    print()
    print("=" * 60)
    print(f"  Async Eval Run: {run_id}")
    print(f"  Score: {total_score}/{total} = {accuracy * 100:.1f}%")
    print(f"  Artifacts: {run_dir}")
    print(f"  Results:   {results_path}")
    print(f"  Manifest:  {manifest_path}")
    print(f"  Submission: {sub_path}")
    if error_counts:
        print(f"  Errors: {error_counts}")
    print("=" * 60)

    return {
        "run_id": run_id,
        "run_dir": run_dir,
        "results_path": results_path,
        "manifest_path": manifest_path,
        "total_score": total_score,
        "total": total,
        "accuracy": accuracy,
        "results": results,
        "error_counts": error_counts,
    }


def main() -> None:
    """CLI entry point for async evaluation."""
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    parser = argparse.ArgumentParser(description="Run DABStep async evaluation")
    parser.add_argument("--source", default="hf", choices=["hf", "jsonl"])
    parser.add_argument("--jsonl-path", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--run-id", type=str, default=None)
    parser.add_argument(
        "--client", default="fake", choices=["live", "dot", "fake"],
        help="Client: 'live'/'dot' for real Dot API, 'fake' for testing",
    )
    parser.add_argument(
        "--dot-mode", default="agentic", choices=["ask", "agentic"],
        help="Dot API mode",
    )
    parser.add_argument("--target30", action="store_true", help="Filter to 30 target task IDs")
    parser.add_argument("--target-n", type=int, default=None)
    parser.add_argument("--split", type=str, default=None)
    parser.add_argument(
        "--max-workers", type=int, default=5,
        help="Max concurrent Dot API calls (default: 5)",
    )
    parser.add_argument(
        "--max-wall-clock", type=int, default=45,
        help="Max wall clock minutes before timeout (default: 45)",
    )
    args = parser.parse_args()

    if args.client in ("live", "dot"):
        client: DotClient = LiveDotClient(mode=args.dot_mode)
        print("Running Dot API preflight check...")
        pf = client.preflight()
        print(f"  Preflight: ok={pf['ok']}  status={pf['status_code']}  latency={pf['latency_s']}s")
        if not pf["ok"]:
            print(f"  Body: {pf['body_preview'][:300]}")
            print("  WARNING: Dot API preflight FAILED — run may fail.")
    else:
        client = FakeDotClient()

    result = run_async_eval(
        client=client,
        source=args.source,
        jsonl_path=args.jsonl_path,
        limit=args.limit,
        run_id=args.run_id,
        dot_mode=args.dot_mode,
        target30=args.target30,
        target_n=args.target_n,
        split=args.split,
        max_workers=args.max_workers,
        max_wall_clock_s=args.max_wall_clock * 60,
    )
    print(f"\nResults written to {result['run_dir']}")


if __name__ == "__main__":
    main()
