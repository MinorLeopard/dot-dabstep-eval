"""Tests for prompt construction and answer parsing."""

import pytest

from src.dabstep_loader import Task
from src.prompting import build_prompt, parse_final_answer


class TestBuildPrompt:
    def test_contains_question(self):
        task = Task(question_id="1", question="What is 2+2?", ground_truth="4")
        prompt = build_prompt(task)
        assert "What is 2+2?" in prompt

    def test_contains_format_instruction(self):
        task = Task(question_id="1", question="test", ground_truth="x")
        prompt = build_prompt(task)
        assert "FINAL_ANSWER" in prompt


class TestParseFinalAnswer:
    def test_parses_standard_format(self):
        text = "Some reasoning...\nFINAL_ANSWER: 42\n"
        assert parse_final_answer(text) == "42"

    def test_parses_case_insensitive(self):
        text = "final_answer: Paris"
        assert parse_final_answer(text) == "Paris"

    def test_returns_none_when_missing(self):
        text = "I think the answer is 42 but I won't format it."
        assert parse_final_answer(text) is None

    def test_parses_multiword_answer(self):
        text = "FINAL_ANSWER: New York City"
        assert parse_final_answer(text) == "New York City"

    def test_parses_from_long_response(self):
        text = (
            "Let me think about this.\n"
            "Step 1: analyze the data\n"
            "Step 2: compute the result\n"
            "FINAL_ANSWER: 3.14\n"
            "That's my answer."
        )
        assert parse_final_answer(text) == "3.14"

    def test_strips_whitespace(self):
        text = "FINAL_ANSWER:   hello world   \n"
        assert parse_final_answer(text) == "hello world"
