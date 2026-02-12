"""Tests for submission CSV generator."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.make_submission_csv import (
    _load_answers_from_results,
    _validate_submission,
    make_submission_csv,
)


def _make_results_jsonl(tmp_path: Path, answers: dict[str, str]) -> Path:
    path = tmp_path / "results.jsonl"
    with open(path, "w") as f:
        for qid, ans in answers.items():
            record = {
                "question_id": qid,
                "parsed_answer": ans,
                "ground_truth": ans,
                "score": 1,
            }
            f.write(json.dumps(record) + "\n")
    return path


class TestLoadAnswers:
    def test_loads_answers(self, tmp_path):
        results_path = _make_results_jsonl(tmp_path, {"1": "yes", "2": "no"})
        answers = _load_answers_from_results(results_path)
        assert answers == {"1": "yes", "2": "no"}

    def test_skips_none_answers(self, tmp_path):
        path = tmp_path / "results.jsonl"
        with open(path, "w") as f:
            f.write(json.dumps({"question_id": "1", "parsed_answer": None}) + "\n")
            f.write(json.dumps({"question_id": "2", "parsed_answer": "ok"}) + "\n")
        answers = _load_answers_from_results(path)
        assert "1" not in answers
        assert answers["2"] == "ok"


class TestValidateSubmission:
    def test_valid_csv(self, tmp_path):
        csv_path = tmp_path / "sub.csv"
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["task_id", "agent_answer"])
            writer.writeheader()
            for i in range(5):
                writer.writerow({"task_id": str(i), "agent_answer": ""})

        errors = _validate_submission(csv_path, expected_count=5)
        assert errors == []

    def test_wrong_count(self, tmp_path):
        csv_path = tmp_path / "sub.csv"
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["task_id", "agent_answer"])
            writer.writeheader()
            writer.writerow({"task_id": "1", "agent_answer": ""})

        errors = _validate_submission(csv_path, expected_count=5)
        assert any("Row count" in e for e in errors)

    def test_duplicate_ids(self, tmp_path):
        csv_path = tmp_path / "sub.csv"
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["task_id", "agent_answer"])
            writer.writeheader()
            writer.writerow({"task_id": "1", "agent_answer": ""})
            writer.writerow({"task_id": "1", "agent_answer": ""})

        errors = _validate_submission(csv_path, expected_count=2)
        assert any("Duplicate" in e for e in errors)


class TestMakeSubmissionCsv:
    def test_generates_csv_with_mock_tasks(self, tmp_path):
        """Test CSV generation with mocked task IDs."""
        results_path = _make_results_jsonl(tmp_path, {"0": "answer_0", "2": "answer_2"})
        output_path = tmp_path / "submission.csv"

        mock_task_ids = [str(i) for i in range(5)]

        with patch("src.make_submission_csv._load_all_task_ids", return_value=mock_task_ids):
            result = make_submission_csv(
                output_path=output_path,
                results_path=results_path,
            )

        assert result.exists()

        with open(result, newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 5
        assert rows[0]["agent_answer"] == "answer_0"
        assert rows[1]["agent_answer"] == ""
        assert rows[2]["agent_answer"] == "answer_2"
        assert rows[3]["agent_answer"] == ""
        assert rows[4]["agent_answer"] == ""
