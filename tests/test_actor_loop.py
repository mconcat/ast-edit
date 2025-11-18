import json
from pathlib import Path
from typing import Any, Dict

from dataclasses import dataclass

import pytest

from src.actors import actor_loop
from src.sandbox import runner as sandbox_runner
from src.state import manager as state_manager


@dataclass
class DummySandboxResult:
    cmd: list[str]
    exit_code: int
    stdout: str
    stderr: str
    duration_sec: float
    error: str | None = None
    diff: str | None = None
    changed_files: list[str] | None = None


class DummyClient:
    def __init__(self, text: str):
        self._text = text

    def generate(self, *args: Any, **kwargs: Any) -> str:  # noqa: D401 - simple stub
        return self._text


def test_run_single_step_writes_trajectory_and_updates_state(tmp_path, monkeypatch):
    def fake_repo_root():
        return tmp_path

    monkeypatch.setattr("src.actors.actor_loop.repo_root", fake_repo_root)
    monkeypatch.setattr("src.state.manager._db_path", lambda: tmp_path / "state.sqlite3")

    def fake_prepare_workspace(task_id: str, files: Dict[str, str]):  # type: ignore[override]
        ws = tmp_path / ".sandbox" / task_id
        ws.mkdir(parents=True, exist_ok=True)
        for rel, content in files.items():
            p = ws / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
        return ws

    def fake_apply_action(workspace: Path, action: Dict[str, Any], timeout_sec=None):  # type: ignore[override]
        return DummySandboxResult(
            cmd=action["command"],
            exit_code=0,
            stdout="ok",
            stderr="",
            duration_sec=0.1,
            diff="",
            changed_files=[],
        )

    def fake_cleanup(workspace: Path) -> None:  # type: ignore[override]
        assert workspace.exists()

    monkeypatch.setattr(actor_loop, "sandbox_runner", sandbox_runner)
    monkeypatch.setattr(actor_loop.sandbox_runner, "prepare_workspace", fake_prepare_workspace)
    monkeypatch.setattr(actor_loop.sandbox_runner, "apply_action", fake_apply_action)
    monkeypatch.setattr(actor_loop.sandbox_runner, "cleanup", fake_cleanup)

    model_output = """
<think>
Reflect on the task.
</think>
<action>
{"command": ["python", "main.py"]}
</action>
<state_update>
{"history": ["did something"], "next_focus": "next step"}
</state_update>
"""
    client = DummyClient(model_output)

    task = {
        "task_id": "task-1",
        "prompt": "Do the thing",
        "workspace_files": {"main.py": "print('hi')"},
    }

    actor_loop.run_single_step(task, client=client)

    traj_path = tmp_path / "trajectories" / "raw" / "task-1.jsonl"
    assert traj_path.exists()
    lines = traj_path.read_text().strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])

    assert record["task_id"] == "task-1"
    assert record["step"] == 1
    assert "Do the thing" in record["prompt"]
    assert record["model_output"]["think"].startswith("Reflect")
    assert record["model_output"]["action"]["command"] == ["python", "main.py"]
    assert record["state_after"]["history"][-1] == "did something"
    assert record["state_after"]["next_focus"] == "next step"
    assert record["sandbox_result"]["exit_code"] == 0

