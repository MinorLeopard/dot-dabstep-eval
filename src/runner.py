"""Evaluation runner — orchestrates load, prompt, call, score, and write."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from tqdm import tqdm

from src.dabstep_loader import load_tasks
from src.dot_client import (
    DotClient,
    DotEmptyResponseError,
    DotHttpError,
    DotTimeoutError,
    FakeDotClient,
    LiveDotClient,
)
from src.prompting import build_prompt, parse_final_answer
from src.scoring import score_answer

logger = logging.getLogger(__name__)

RESULTS_DIR = Path("results")


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

    Returns:
        Path to the results JSONL file.
    """
    if client is None:
        logger.warning("No client provided — using FakeDotClient")
        client = FakeDotClient()

    if run_id is None:
        run_id = generate_run_id()

    tasks = load_tasks(source=source, path=jsonl_path, limit=limit)
    if not tasks:
        raise ValueError("No tasks loaded. Check source and path.")

    results_dir.mkdir(parents=True, exist_ok=True)
    output_path = results_dir / f"{run_id}.jsonl"

    total_score = 0
    total = 0
    error_counts: dict[str, int] = {}

    logger.info("Starting eval run %s — %d tasks", run_id, len(tasks))

    with open(output_path, "w", encoding="utf-8") as out:
        for task in tqdm(tasks, desc=f"Eval {run_id}"):
            prompt = build_prompt(task)

            parsed_answer: str | None = None
            latency_ms: int | None = None
            retries: int | None = None
            dot_error_type: str | None = None

            try:
                response = client.query(prompt)
                raw_text = response.text
                if response.usage:
                    latency_ms = response.usage.get("latency_ms")
                    retries = response.usage.get("retries")
            except DotHttpError as exc:
                logger.error("HTTP error on %s: %s", task.question_id, exc)
                raw_text = ""
                dot_error_type = "dot_http_error"
            except DotTimeoutError as exc:
                logger.error("Timeout on %s: %s", task.question_id, exc)
                raw_text = ""
                dot_error_type = "dot_timeout"
            except DotEmptyResponseError as exc:
                logger.error("Empty response on %s: %s", task.question_id, exc)
                raw_text = ""
                dot_error_type = "dot_empty_response"
            except Exception as exc:
                logger.error("Client error on %s: %s", task.question_id, exc)
                raw_text = ""
                dot_error_type = "client_error"

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
                "prompt": prompt,
                "dot_response_raw": raw_text,
                "parsed_answer": parsed_answer,
                "ground_truth": task.ground_truth,
                "score": sc,
                "error_type": error_type,
                "dot_mode": dot_mode,
                "latency_ms": latency_ms,
                "retries": retries,
            }
            out.write(json.dumps(record) + "\n")

    accuracy = total_score / total if total > 0 else 0.0
    logger.info(
        "Run %s complete — %d/%d correct (%.1f%%), errors: %s",
        run_id,
        total_score,
        total,
        accuracy * 100,
        error_counts,
    )

    return output_path


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
        choices=["live", "fake"],
        help="Client to use: 'live' for real Dot API, 'fake' for deterministic testing",
    )
    parser.add_argument(
        "--dot-mode",
        default="agentic",
        choices=["ask", "agentic"],
        help="Dot API mode: 'ask' for /api/ask, 'agentic' for /api/agentic",
    )
    args = parser.parse_args()

    if args.client == "live":
        client: DotClient = LiveDotClient(mode=args.dot_mode)
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
    )
    print(f"Results written to {output}")


if __name__ == "__main__":
    main()
