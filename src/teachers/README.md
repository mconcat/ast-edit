# Teachers subsystem

This package contains teacher components that generate supervised trajectories for training and evaluation, using the same sandbox and state manager as the actors.

## Files

- `srl_teacher.py` – simple teacher loop for step‑wise supervision:
  - `_load_prompts_config()` reads `configs/teacher_prompts.yaml` (or falls back to a small default) to obtain the system text, instructions, stop tokens, and generation parameters.
  - `run_teacher_step(task, client=None)`:
    - Loads the current task state from `src.state.manager`.
    - Builds a teacher prompt that includes the base task prompt, a `<state>...</state>` block, and structured instructions.
    - Calls a `VLLMClient` (teacher model) to get output, expected to contain `<think>`, `<action>`, and `<state_update>` blocks.
    - Parses and JSON‑decodes the `action` and `state_update` blocks, runs the action via the sandbox, and merges the state update into the persistent state.
    - Computes a simple reward (1.0 for valid parse + successful sandbox run, else 0.0) and appends a JSONL trajectory record under `trajectories/raw/<task_id>.jsonl`.
  - CLI entrypoint: `python -m src.teachers.srl_teacher tasks.jsonl` reads tasks from a JSONL file and runs one teacher‑labeled step per line.

## Prompt configuration

- `configs/teacher_prompts.yaml` defines:
  - `system`: high‑level role description for the teacher model (e.g., expert ast‑grep refactoring teacher).
  - `instructions`: format and guidelines for emitting `<think>`, `<action>`, and `<state_update>` blocks with valid JSON inside the latter two.
  - `stop`, `temperature`, and `max_tokens`: default generation parameters passed to the vLLM client.

## Architecture

- **State and sandbox reuse**:
  - The teacher loop uses the same `State` representation and SQLite backend as the actor loop, ensuring consistency between teacher‑labeled and actor‑generated trajectories.
  - Actions are executed via `src.sandbox.runner` in per‑task workspaces, with rlimits, allowlisted binaries, diffs, and JSONL sandbox logs.

- **Trajectory format**:
  - Teacher trajectories share the same JSONL structure as actor trajectories, with an additional `teacher` block (e.g., `{"model": "qwen2-14b-instruct"}`) and a scalar `reward`.
  - This makes it easy to mix or compare actor and teacher steps when training or evaluating policies.

The teachers subsystem is intentionally minimal: it wraps the existing vLLM client, sandbox, and state manager with a small amount of prompt logic and reward shaping, so you can experiment with teacher policies without changing the core infrastructure.

