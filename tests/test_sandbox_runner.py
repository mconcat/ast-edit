from pathlib import Path
from typing import Mapping

import os
import sys

import pytest

from src.sandbox import runner


def test_prepare_workspace_writes_files(tmp_path, monkeypatch):
    # Force work root under tmp to avoid touching repo
    monkeypatch.setenv("PYTHONPATH", os.getcwd())

    # Monkeypatch config loader to use tmp dirs
    def fake_load_config():
        cfg = runner.SandboxConfig.defaults()
        cfg.work_root = tmp_path / ".sandbox"
        cfg.logs_dir = tmp_path / "logs"
        return cfg

    monkeypatch.setattr(runner, "_load_config", fake_load_config)

    ws = runner.prepare_workspace("task1", {"a/b.txt": "hello", "main.py": "print('hi')"})
    assert (ws / "a" / "b.txt").read_text() == "hello"
    assert (ws / "main.py").read_text().strip().startswith("print")


def test_apply_action_rejects_disallowed_binary(tmp_path, monkeypatch):
    def fake_load_config():
        cfg = runner.SandboxConfig.defaults()
        cfg.work_root = tmp_path / ".sandbox"
        cfg.logs_dir = tmp_path / "logs"
        cfg.allowed_binaries = ["python"]
        return cfg

    monkeypatch.setattr(runner, "_load_config", fake_load_config)
    ws = runner.prepare_workspace("task2", {"noop.txt": "x"})
    res = runner.apply_action(ws, {"command": ["rm", "-rf", "."]})
    assert res.exit_code == 126
    assert "not allowed" in res.stderr


def test_apply_action_timeout(tmp_path, monkeypatch):
    def fake_load_config():
        cfg = runner.SandboxConfig.defaults()
        cfg.work_root = tmp_path / ".sandbox"
        cfg.logs_dir = tmp_path / "logs"
        cfg.allowed_binaries = ["python"]
        cfg.default_timeout_sec = 1
        cfg.cpu_time_sec = 1
        return cfg

    monkeypatch.setattr(runner, "_load_config", fake_load_config)
    ws = runner.prepare_workspace("task3", {"sleep.py": "import time; time.sleep(5)"})
    res = runner.apply_action(ws, {"command": ["python", "sleep.py"]})
    # Timeout error exit code
    assert res.exit_code in (124, 137)


def test_cleanup_removes_workspace(tmp_path, monkeypatch):
    def fake_load_config():
        cfg = runner.SandboxConfig.defaults()
        cfg.work_root = tmp_path / ".sandbox"
        cfg.logs_dir = tmp_path / "logs"
        return cfg

    monkeypatch.setattr(runner, "_load_config", fake_load_config)
    ws = runner.prepare_workspace("task4", {"file.txt": "data"})
    assert ws.exists()
    runner.cleanup(ws)
    assert not ws.exists()


def test_apply_action_captures_diff_and_changed_files(tmp_path, monkeypatch):
    def fake_load_config():
        cfg = runner.SandboxConfig.defaults()
        cfg.work_root = tmp_path / ".sandbox"
        cfg.logs_dir = tmp_path / "logs"
        cfg.allowed_binaries = ["python"]
        cfg.default_timeout_sec = 5
        cfg.cpu_time_sec = 5
        return cfg

    monkeypatch.setattr(runner, "_load_config", fake_load_config)

    files = {
        "file.txt": "line1\n",
        "update.py": (
            "from pathlib import Path\n"
            "p = Path('file.txt')\n"
            "p.write_text('line1\\nline2\\n')\n"
        ),
    }
    ws = runner.prepare_workspace("task_diff", files)
    res = runner.apply_action(ws, {"command": ["python", "update.py"]})
    assert res.exit_code == 0
    assert res.diff is not None
    assert "a/file.txt" in res.diff
    assert "b/file.txt" in res.diff
    assert "line2" in res.diff
    assert res.changed_files is not None
    assert "file.txt" in res.changed_files
