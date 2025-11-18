from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from src.actors.vllm_client import VLLMClient
from src.data.schemas import repo_root
from src.sandbox import runner as sandbox_runner
from src.state import manager as state_manager


def _trajectories_root() -> Path:
    root = repo_root()
    base = root / "trajectories" / "raw"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _trajectory_path(task_id: str) -> Path:
    return _trajectories_root() / f"{task_id}.jsonl"


def _append_trajectory_step(task_id: str, record: Mapping[str, Any]) -> None:
    path = _trajectory_path(task_id)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def _extract_block(text: str, tag: str) -> Optional[str]:
    start_tag = f"<{tag}>"
    end_tag = f"</{tag}>"
    start = text.find(start_tag)
    if start == -1:
        return None
    start += len(start_tag)
    end = text.find(end_tag, start)
    if end == -1:
        return None
    return text[start:end].strip()


def _parse_model_output(raw: str) -> Dict[str, Any]:
    think = _extract_block(raw, "think")
    action_raw = _extract_block(raw, "action")
    state_update_raw = _extract_block(raw, "state_update")

    action_obj: Optional[Dict[str, Any]] = None
    state_update_obj: Optional[Dict[str, Any]] = None
    parse_error: Optional[str] = None

    if action_raw:
        try:
            candidate = json.loads(action_raw)
            if isinstance(candidate, dict):
                action_obj = candidate
        except json.JSONDecodeError:
            parse_error = parse_error or "invalid_action_json"
    if state_update_raw:
        try:
            candidate = json.loads(state_update_raw)
            if isinstance(candidate, dict):
                state_update_obj = candidate
        except json.JSONDecodeError:
            parse_error = parse_error or "invalid_state_update_json"

    return {
        "raw": raw,
        "think": think,
        "action": action_obj,
        "state_update": state_update_obj,
        "parse_error": parse_error,
    }


def _to_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)]


def _state_from_update(obj: Mapping[str, Any]) -> state_manager.State:
    return state_manager.State(
        goals=_to_str_list(obj.get("goals")),
        constraints=_to_str_list(obj.get("constraints")),
        decisions=_to_str_list(obj.get("decisions")),
        hypotheses=_to_str_list(obj.get("hypotheses")),
        history=_to_str_list(obj.get("history")),
        open_issues=_to_str_list(obj.get("open_issues")),
        next_focus=str(obj.get("next_focus", "")),
    )


def _next_step_index(task_id: str) -> int:
    path = _trajectory_path(task_id)
    if not path.exists():
        return 1
    count = 0
    with path.open("r", encoding="utf-8") as fh:
        for _ in fh:
            count += 1
    return count + 1


def run_single_step(task: Mapping[str, Any], *, client: Optional[VLLMClient] = None) -> None:
    """Run a single actor step for a task and append a trajectory record.

    The task mapping should contain:
      - task_id: unique identifier
      - prompt: base user prompt string
      - workspace_files: optional mapping of relative path -> file content
    """
    task_id = str(task["task_id"])
    base_prompt = str(task["prompt"])

    state_before = state_manager.load(task_id)
    state_text = state_manager.render(state_before)
    if state_text:
        prompt = f"{base_prompt}\n\n<state>\n{state_text}\n</state>"
    else:
        prompt = base_prompt

    if client is None:
        client = VLLMClient()

    actor_start = time.time()
    model_text = client.generate(
        prompt,
        stop=task.get("stop"),
        temperature=float(task.get("temperature", 0.1)),
        seed=task.get("seed"),
        max_tokens=task.get("max_tokens"),
    )
    actor_latency = time.time() - actor_start

    parsed = _parse_model_output(model_text)

    workspace_files = task.get("workspace_files") or {}
    sandbox_result = None
    workspace = sandbox_runner.prepare_workspace(task_id, workspace_files)
    try:
        action_obj = parsed.get("action")
        if isinstance(action_obj, dict) and action_obj.get("command"):
            sandbox_result = sandbox_runner.apply_action(workspace, action_obj)
    finally:
        sandbox_runner.cleanup(workspace)

    state_after = state_before
    state_update_obj = parsed.get("state_update")
    if isinstance(state_update_obj, dict):
        update_state = _state_from_update(state_update_obj)
        state_after = state_manager.merge(state_before, update_state)
        state_manager.save(task_id, state_after)

    sandbox_result_dict: Optional[Dict[str, Any]] = None
    if sandbox_result is not None:
        sandbox_result_dict = {
            "cmd": sandbox_result.cmd,
            "exit_code": sandbox_result.exit_code,
            "stdout": sandbox_result.stdout,
            "stderr": sandbox_result.stderr,
            "duration_sec": sandbox_result.duration_sec,
            "error": sandbox_result.error,
            "diff": sandbox_result.diff,
            "changed_files": sandbox_result.changed_files,
        }

    record: Dict[str, Any] = {
        "task_id": task_id,
        "step": _next_step_index(task_id),
        "prompt": prompt,
        "state_before": asdict(state_before),
        "state_after": asdict(state_after),
        "model_output": parsed,
        "sandbox_result": sandbox_result_dict,
        "reward": None,
        "metrics": {
            "actor_latency_sec": actor_latency,
            "sandbox_failed": sandbox_result_dict is None or (sandbox_result and sandbox_result.exit_code != 0),
        },
    }
    _append_trajectory_step(task_id, record)


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m src.actors.actor_loop")
    parser.add_argument(
        "tasks_path",
        help="Path to a JSONL file containing queued tasks.",
    )
    parser.add_argument(
        "--actor-name",
        dest="actor_name",
        default=None,
        help="Name of the actor from configs/vllm_actors.yaml to use.",
    )
    args = parser.parse_args(argv)

    client = VLLMClient(actor_name=args.actor_name) if args.actor_name else VLLMClient()
    path = Path(args.tasks_path)
    if not path.exists():
        raise SystemExit(f"Tasks file not found: {path}")

    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            task = json.loads(line)
            run_single_step(task, client=client)


if __name__ == "__main__":
    main()

