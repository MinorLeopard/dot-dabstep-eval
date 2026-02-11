"""Tests for dabstep_loader — HuggingFace loading and field mapping."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.dabstep_loader import Task, load_from_hf, load_tasks


# A fake row mimicking what HuggingFace datasets returns for adyen/DABstep
FAKE_HF_ROW = {
    "task_id": "task_42",
    "question": "What is the total revenue?",
    "answer": "123456.78",
    "level": "easy",
    "guidelines": "Use the payments table.",
}


class _FakeDataset:
    """Minimal iterable that behaves like a HuggingFace Dataset."""

    def __init__(self, rows: list[dict]):
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)

    def __len__(self):
        return len(self._rows)


def _mock_load_dataset(repo, split=None):
    return _FakeDataset([FAKE_HF_ROW])


@patch("src.dabstep_loader.load_dataset", create=True)
def test_load_from_hf_field_mapping(mock_ld):
    """load_from_hf maps task_id→question_id, answer→ground_truth, level→difficulty."""
    mock_ld.side_effect = _mock_load_dataset

    # Patch the import inside load_from_hf
    with patch.dict("sys.modules", {"datasets": type("M", (), {"load_dataset": _mock_load_dataset})}):
        tasks = load_from_hf(limit=1)

    assert len(tasks) == 1
    t = tasks[0]

    # question_id must equal the dataset's task_id (non-numeric)
    assert t.question_id == "task_42"
    assert not t.question_id.isdigit(), "question_id should be the task_id string, not a numeric index"

    # ground_truth must be non-empty
    assert t.ground_truth, "ground_truth must be non-empty"
    assert t.ground_truth == "123456.78"

    # Other fields
    assert t.question == "What is the total revenue?"
    assert t.difficulty == "easy"
    assert t.metadata["guidelines"] == "Use the payments table."


@patch("src.dabstep_loader.load_dataset", create=True)
def test_load_tasks_hf_returns_task(mock_ld):
    """load_tasks(source='hf', limit=1) returns a Task with correct fields."""
    mock_ld.side_effect = _mock_load_dataset

    with patch.dict("sys.modules", {"datasets": type("M", (), {"load_dataset": _mock_load_dataset})}):
        tasks = load_tasks(source="hf", limit=1)

    assert len(tasks) == 1
    assert isinstance(tasks[0], Task)
    assert tasks[0].ground_truth != ""
    assert tasks[0].question_id == "task_42"


try:
    from datasets import load_dataset as _ld  # noqa: F401
    _has_datasets = True
except ImportError:
    _has_datasets = False


@pytest.mark.skipif(not _has_datasets, reason="datasets library not installed")
def test_load_from_hf_real_dataset():
    """Integration: load one real row from adyen/DABstep dev split and verify mapping."""
    tasks = load_tasks(source="hf", limit=1)
    assert len(tasks) == 1

    t = tasks[0]

    # DABStep tasks config does not include answers (ground_truth is empty)
    assert t.ground_truth is not None

    # Verify against direct dataset access for the first row
    from datasets import load_dataset
    ds = load_dataset("adyen/DABstep", name="tasks", split="default[:1]")
    first_row = next(iter(ds))
    assert t.question_id == str(first_row["task_id"])
    assert t.ground_truth == str(first_row["answer"])
    assert t.difficulty == str(first_row["level"])
    assert t.metadata.get("guidelines") == first_row.get("guidelines", "")
