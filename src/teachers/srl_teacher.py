from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    yaml = None  # type: ignore

from src.actors.vllm_client import VLLMClient
from src.data.schemas import repo_root
from src.sandbox import runner as sandbox_runner
from src.state import manager as state_manager


def _config_path() -> Path:
    return repo_root() / "configs" / "teacher_prompts.yaml"


def _load_prompts_config() -> Dict[str, Any]:
    cfg_path = _config_path()
    if not cfg_path.exists() or yaml is None:
        return {
            "system": "You are an expert ast-grep refactoring teacher.",
            "instructions": "Respond with <think>, <action>, and <state_update> blocks.",
            "stop": ["</state_update>"],
            "temperature": 0.2,
            "max_tokens": 512,
        }
    data = yaml.safe_load(cfg_path.read_text()) or {}
    return {
        "system": str(data.get("system", "")),
        "instructions": str(data.get("instructions", "")),
        "stop": data.get("stop") or ["</state_update>"],
        "temperature": float(data.get("temperature", 0.2)),
        "max_tokens": int(data.get("max_tokens", 512)),
    }


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


def _next_step_index(task_id: str) -> int:
    path = _trajectory_path(task_id)
    if not path.exists():
        return 1
    count = 0
    with path.open("r", encoding="utf-8") as fh:
        for _ in fh:
            count += 1
    return count + 1


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


def _build_prompt(base_prompt: str, state_text: str, cfg: Mapping[str, Any]) -> str:
    """Construct the teacher prompt from system text, base prompt, and state."""
    parts = []
    system = str(cfg.get("system") or "").strip()
    if system:
        parts.append(system)
    parts.append(base_prompt)
    if state_text:
        parts.append("<state>\n" + state_text + "\n</state>")
    instructions = str(cfg.get("instructions") or "").strip()
    if instructions:
        parts.append(instructions)
    return "\n\n".join(parts)


def _compute_reward(parsed: Mapping[str, Any], sandbox_result: Optional[Any]) -> float:
    """Simple reward: 1.0 for valid parse + successful sandbox run, else 0.0."""
    if parsed.get("parse_error"):
        return 0.0
    if not parsed.get("action") or not parsed.get("state_update"):
        return 0.0
    if sandbox_result is None:
        return 0.0
    if getattr(sandbox_result, "exit_code", 1) != 0:
        return 0.0
    return 1.0


def run_teacher_step(task: Mapping[str, Any], *, client: Optional[VLLMClient] = None) -> None:
    """Run a single teacher-labeled step for a task and append a trajectory record.

    The task mapping should contain:
      - task_id: unique identifier
      - prompt: base user prompt string
      - workspace_files: optional mapping of relative path -> file content
    """
    cfg = _load_prompts_config()
    task_id = str(task["task_id"])
    base_prompt = str(task["prompt"])

    state_before = state_manager.load(task_id)
    state_text = state_manager.render(state_before)
    prompt = _build_prompt(base_prompt, state_text, cfg)

    if client is None:
        client = VLLMClient()

    teacher_start = time.time()
    model_text = client.generate(
        prompt,
        stop=cfg.get("stop"),
        temperature=float(cfg.get("temperature", 0.2)),
        max_tokens=int(cfg.get("max_tokens", 512)),
    )
    teacher_latency = time.time() - teacher_start

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

    reward = _compute_reward(parsed, sandbox_result)

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
        "reward": reward,
        "teacher": {
            "model": getattr(client, "model", None),
        },
        "metrics": {
            "teacher_latency_sec": teacher_latency,
            "sandbox_failed": sandbox_result_dict is None or (sandbox_result and sandbox_result.exit_code != 0),
        },
    }
    _append_trajectory_step(task_id, record)


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m src.teachers.srl_teacher")
    parser.add_argument(
        "tasks_path",
        help="Path to a JSONL file containing queued tasks.",
    )
    args = parser.parse_args(argv)

    client = VLLMClient()
    path = Path(args.tasks_path)
    if not path.exists():
        raise SystemExit(f"Tasks file not found: {path}")

    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            task = json.loads(line)
            run_teacher_step(task, client=client)


if __name__ == "__main__":
    main()

