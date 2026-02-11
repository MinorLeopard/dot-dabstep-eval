"""Tests for scoring logic."""

import pytest

from src.scoring import normalize_answer, score_answer


class TestNormalizeAnswer:
    def test_strips_whitespace(self):
        assert normalize_answer("  hello  ") == "hello"

    def test_lowercases(self):
        assert normalize_answer("HELLO") == "hello"

    def test_removes_quotes(self):
        assert normalize_answer('"hello"') == "hello"
        assert normalize_answer("'hello'") == "hello"

    def test_removes_trailing_period(self):
        assert normalize_answer("hello.") == "hello"

    def test_collapses_whitespace(self):
        assert normalize_answer("hello   world") == "hello world"


class TestScoreAnswer:
    def test_none_answer_returns_format_missing(self):
        score, err = score_answer(None, "42")
        assert score == 0
        assert err == "format_missing"

    def test_exact_string_match(self):
        score, err = score_answer("Paris", "paris")
        assert score == 1
        assert err is None

    def test_wrong_string(self):
        score, err = score_answer("London", "Paris")
        assert score == 0
        assert err == "wrong_answer"

    def test_numeric_exact(self):
        score, err = score_answer("42", "42")
        assert score == 1
        assert err is None

    def test_numeric_close(self):
        score, err = score_answer("42.001", "42.0")
        assert score == 1
        assert err is None

    def test_numeric_wrong(self):
        score, err = score_answer("100", "42")
        assert score == 0
        assert err == "wrong_answer"

    def test_numeric_with_formatting(self):
        score, err = score_answer("$1,234.56", "1234.56")
        assert score == 1
        assert err is None

    def test_percentage_stripped(self):
        score, err = score_answer("95%", "95")
        assert score == 1
        assert err is None

    def test_quoted_answer_match(self):
        score, err = score_answer('"yes"', "yes")
        assert score == 1
        assert err is None
