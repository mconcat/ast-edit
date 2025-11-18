import os

import pytest

from src.state import manager


def test_merge_applies_caps_and_extends_lists():
    long_text = "x" * 300
    existing = manager.State(
        goals=["goal1"],
        history=["h1", "h2", "h3"],
        next_focus="old focus",
    )
    update = manager.State(
        goals=["goal2"],
        history=["h4", "h5"],
        next_focus=long_text,
    )

    merged = manager.merge(existing, update)

    # Goals are concatenated.
    assert merged.goals == ["goal1", "goal2"]
    # History is capped to the most recent entries.
    assert len(merged.history) <= 3
    assert merged.history[-1] == "h5"
    # next_focus is truncated to max length.
    assert len(merged.next_focus) <= manager._MAX_TEXT_LEN


def test_save_and_load_roundtrip(tmp_path, monkeypatch):
    def fake_db_path():
        return tmp_path / "state.sqlite3"

    monkeypatch.setattr(manager, "_db_path", fake_db_path)

    state = manager.State(
        goals=["g1"],
        constraints=["c1"],
        decisions=["d1"],
        hypotheses=["h1"],
        history=["step1"],
        open_issues=["issue1"],
        next_focus="focus",
    )

    manager.save("task1", state)
    loaded = manager.load("task1")

    assert loaded == manager.State(
        goals=["g1"],
        constraints=["c1"],
        decisions=["d1"],
        hypotheses=["h1"],
        history=["step1"],
        open_issues=["issue1"],
        next_focus="focus",
    )


def test_load_missing_returns_default(tmp_path, monkeypatch):
    def fake_db_path():
        return tmp_path / "state.sqlite3"

    monkeypatch.setattr(manager, "_db_path", fake_db_path)

    loaded = manager.load("missing_task")
    assert isinstance(loaded, manager.State)
    assert loaded.goals == []
    assert loaded.history == []

