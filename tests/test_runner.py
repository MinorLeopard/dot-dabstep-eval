"""Tests for the evaluation runner using FakeDotClient."""

import json
import tempfile
from pathlib import Path

from src.dot_client import FakeDotClient
from src.runner import run_eval


def _make_tasks_jsonl(tmp: Path, tasks: list[dict]) -> Path:
    path = tmp / "tasks.jsonl"
    with open(path, "w") as f:
        for t in tasks:
            f.write(json.dumps(t) + "\n")
    return path


def test_run_eval_writes_results():
    """Full integration: load JSONL -> fake client -> score -> write results."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        tasks_path = _make_tasks_jsonl(
            tmp,
            [
                {"question_id": "q1", "question": "What is 1+1?", "answer": "2", "level": "easy"},
                {"question_id": "q2", "question": "Capital of France?", "answer": "Paris", "level": "easy"},
            ],
        )
        results_dir = tmp / "results"

        output = run_eval(
            client=FakeDotClient(),
            source="jsonl",
            jsonl_path=tasks_path,
            run_id="test_run",
            results_dir=results_dir,
        )

        assert output.exists()
        lines = output.read_text().strip().split("\n")
        assert len(lines) == 2

        for line in lines:
            record = json.loads(line)
            assert "question_id" in record
            assert "score" in record
            assert "parsed_answer" in record
            assert "ground_truth" in record
            assert "error_type" in record


def test_run_eval_with_override_correct():
    """FakeDotClient with answer_override can produce correct scores."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        tasks_path = _make_tasks_jsonl(
            tmp,
            [{"question_id": "q1", "question": "test", "answer": "42", "level": "easy"}],
        )

        output = run_eval(
            client=FakeDotClient(answer_override="42"),
            source="jsonl",
            jsonl_path=tasks_path,
            run_id="test_correct",
            results_dir=tmp / "results",
        )

        record = json.loads(output.read_text().strip())
        assert record["score"] == 1
        assert record["error_type"] is None
