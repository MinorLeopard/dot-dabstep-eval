"""Tests for failure report generator."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.failure_report import (
    _classify_error,
    generate_failure_report,
)


def _make_results_jsonl(tmp_path: Path, records: list[dict]) -> Path:
    path = tmp_path / "results.jsonl"
    with open(path, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    return path


class TestClassifyError:
    def test_format_missing(self):
        assert _classify_error("What?", "", "42", None) == "format_missing"

    def test_tier_related_superset(self):
        """Superset errors are classified as missing_tier_filter."""
        result = _classify_error(
            "What are the applicable fee IDs?",
            "",
            "1, 2, 3",
            "1, 2, 3, 4, 5",
            error_type="superset_answer",
        )
        assert result == "missing_tier_filter"

    def test_aggregation(self):
        result = _classify_error(
            "What is the total sum of payments?",
            "",
            "1000",
            "500",
        )
        assert result == "wrong_aggregation"


class TestGenerateFailureReport:
    def test_generates_report(self, tmp_path):
        records = [
            {
                "question_id": "1",
                "difficulty": "easy",
                "guidelines": "Answer with number",
                "prompt": "What is 2+2?",
                "dot_response_raw": "FINAL_ANSWER: 4",
                "parsed_answer": "4",
                "ground_truth": "4",
                "score": 1,
                "error_type": None,
                "has_sql": False,
                "has_sql_error": False,
                "latency_s": 1.5,
            },
            {
                "question_id": "2",
                "difficulty": "medium",
                "guidelines": "Answer with color",
                "prompt": "What color is the sky?",
                "dot_response_raw": "FINAL_ANSWER: green",
                "parsed_answer": "green",
                "ground_truth": "blue",
                "score": 0,
                "error_type": "wrong_answer",
                "has_sql": False,
                "has_sql_error": False,
                "latency_s": 2.0,
            },
        ]
        results_path = _make_results_jsonl(tmp_path, records)
        output_path = tmp_path / "report.md"

        stats = generate_failure_report(results_path, output_path)

        assert stats["total"] == 2
        assert stats["correct"] == 1
        assert stats["accuracy"] == 0.5
        assert len(stats["failures"]) == 1
        assert len(stats["successes"]) == 1
        assert output_path.exists()

        report_text = output_path.read_text()
        assert "Failure Analysis Report" in report_text
        assert "Question 2" in report_text

    def test_all_correct(self, tmp_path):
        records = [
            {
                "question_id": "1",
                "difficulty": "easy",
                "guidelines": "",
                "prompt": "Q",
                "dot_response_raw": "FINAL_ANSWER: yes",
                "parsed_answer": "yes",
                "ground_truth": "yes",
                "score": 1,
                "error_type": None,
                "has_sql": False,
                "has_sql_error": False,
                "latency_s": 1.0,
            },
        ]
        results_path = _make_results_jsonl(tmp_path, records)
        stats = generate_failure_report(results_path, tmp_path / "report.md")

        assert stats["accuracy"] == 1.0
        assert len(stats["failures"]) == 0
