"""Tests for async evaluation runner."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from src.async_runner import (
    QuestionStatus,
    _execute_question,
    run_async_eval,
    submit_questions_async,
    poll_results,
)
from src.dabstep_loader import Task
from src.dot_client import FakeDotClient


def _make_task(qid: str = "1", question: str = "What is 2+2?", gt: str = "4") -> Task:
    return Task(
        question_id=qid,
        question=question,
        ground_truth=gt,
        difficulty="easy",
        metadata={"guidelines": "Answer with a number."},
    )


class TestExecuteQuestion:
    def test_returns_question_status(self):
        task = _make_task()
        client = FakeDotClient()
        qs = _execute_question(task, client, "test_run")

        assert isinstance(qs, QuestionStatus)
        assert qs.question_id == "1"
        assert qs.status == "completed"
        assert qs.run_id == "test_run"
        assert qs.latency_s is not None
        assert qs.latency_s >= 0
        assert qs.raw_text  # non-empty
        assert qs.parsed_answer is not None  # FakeDotClient always includes FINAL_ANSWER

    def test_correct_answer_override(self):
        task = _make_task(gt="fake_answer")
        client = FakeDotClient(answer_override="fake_answer")
        qs = _execute_question(task, client, "test_run")

        assert qs.score == 1
        assert qs.error_type is None
        assert qs.parsed_answer == "fake_answer"


class TestSubmitAndPoll:
    def test_submit_returns_futures(self):
        tasks = [_make_task(str(i)) for i in range(3)]
        client = FakeDotClient()
        futures = submit_questions_async(tasks, client, "test_run", max_workers=2)

        assert len(futures) == 3
        assert all(qid in futures for qid in ["0", "1", "2"])

    def test_poll_completes_all(self):
        tasks = [_make_task(str(i)) for i in range(3)]
        client = FakeDotClient()
        futures = submit_questions_async(tasks, client, "test_run", max_workers=2)
        results = poll_results(futures, max_wall_clock_s=60)

        assert len(results) == 3
        assert all(isinstance(r, QuestionStatus) for r in results.values())
        assert all(r.status == "completed" for r in results.values())


class TestRunAsyncEval:
    def test_full_pipeline_fake_client(self, tmp_path):
        """End-to-end test with FakeDotClient and local JSONL."""
        # Create a small test JSONL
        tasks_data = [
            {"task_id": "1", "question": "What is 2+2?", "answer": "4", "level": "easy", "guidelines": "number"},
            {"task_id": "2", "question": "What color?", "answer": "blue", "level": "easy", "guidelines": "color"},
        ]
        jsonl_path = tmp_path / "tasks.jsonl"
        with open(jsonl_path, "w") as f:
            for t in tasks_data:
                f.write(json.dumps(t) + "\n")

        result = run_async_eval(
            client=FakeDotClient(),
            source="jsonl",
            jsonl_path=jsonl_path,
            run_id="test_async_001",
        )

        assert result["run_id"] == "test_async_001"
        assert result["total"] == 2
        assert isinstance(result["accuracy"], float)

        # Check artifacts were created
        run_dir = result["run_dir"]
        assert (run_dir / "manifest.json").exists()
        assert (run_dir / "results.jsonl").exists()
        assert (run_dir / "submission.jsonl").exists()

        # Verify manifest structure
        with open(run_dir / "manifest.json") as f:
            manifest = json.load(f)
        assert manifest["run_id"] == "test_async_001"
        assert manifest["total_questions"] == 2
        assert "1" in manifest["questions"]
        assert "2" in manifest["questions"]
