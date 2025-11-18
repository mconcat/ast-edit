# Actors subsystem

This package holds the vLLM client and actor loop that drive model‑based editing steps, integrate with the sandbox, and write trajectories.

## Files

- `vllm_client.py` – HTTP client for vLLM:
  - `ActorConfig` / `VLLMConfig`: dataclasses describing available actors (name, `base_url`, `model`, tensor parallelism, GPU id) and shared client settings (`timeout_sec`, `max_tokens`).
  - `_load_config()`: reads `configs/vllm_actors.yaml` (or falls back to a single localhost actor) and returns a `VLLMConfig`.
  - `VLLMClient(actor_name=None)`:
    - `health() -> bool`: sends `GET /health` to the selected actor and returns `True` on a healthy response.
    - `generate(prompt, stop, temperature, seed, max_tokens) -> str`: calls `POST /generate` and returns generated text, handling several common response formats (`{"text": ...}`, `{"choices":[{"text": ...}]}`, chat‑style `{"choices":[{"message":{"content": ...}}]}`).

- `actor_loop.py` – single‑step actor loop and trajectory writer:
  - `run_single_step(task, client=None)`: runs one generation/sandbox step for a `task` mapping that contains:
    - `task_id`: unique identifier.
    - `prompt`: base user/system prompt.
    - `workspace_files`: optional mapping of `relative_path -> content` for seeding the sandbox workspace.
    - Optional fields like `stop`, `temperature`, `seed`, `max_tokens` forwarded to the vLLM client.
  - CLI entrypoint: `python -m src.actors.actor_loop tasks.jsonl [--actor-name NAME]`:
    - Reads a JSONL file where each line is a task mapping and runs `run_single_step` sequentially using the chosen actor.

## Architecture

- **State integration**:
  - For each step, the loop loads `state_before` from `src.state.manager.load(task_id)` and renders it via `render(state_before)`.
  - The rendered state is injected into the model prompt as:
    ```text
    <state>
    ...rendered state...
    </state>
    ```
  - Model outputs can propose a `state_update` block, which is parsed and merged into the existing state via `merge`, then persisted with `save`.

- **Model I/O and tagging**:
  - The actor expects the model to emit simple XML‑like tags:
    - `<think>...</think>` – free‑form reasoning.
    - `<action>...JSON...</action>` – JSON object describing the sandbox action, typically including a `command` list.
    - `<state_update>...JSON...</state_update>` – JSON object describing state deltas.
  - `_parse_model_output` extracts these blocks and attempts to parse JSON for the `action` and `state_update` sections, recording a `parse_error` flag when decoding fails.

- **Sandbox integration**:
  - A per‑task workspace is created with `sandbox_runner.prepare_workspace(task_id, workspace_files)`.
  - If a valid `action` with `command` is present, `sandbox_runner.apply_action` is called inside the workspace to run `ast-grep`, tests, or other allowed commands; stdout/stderr, exit code, and diffs are captured.
  - `sandbox_runner.cleanup` is always invoked in a `finally` block to ensure workspaces are removed.

- **Trajectory store**:
  - Trajectories are written as JSONL under `trajectories/raw/<task_id>.jsonl`.
  - Each call to `run_single_step` appends a record with:
    - `task_id`, `step` (1‑based, inferred from existing lines), `prompt`.
    - `state_before` and `state_after` (both serialized from the `State` dataclass).
    - `model_output` (raw text plus parsed `think`, `action`, `state_update`, and `parse_error`).
    - `sandbox_result` (subset of `SandboxResult` fields).
    - `reward` (currently `None`) and simple metrics such as `actor_latency_sec` and `sandbox_failed`.

The actors subsystem is intentionally minimal: it defines a small contract for model outputs, relies on the sandbox and state manager for side effects, and records enough structured information in trajectories to later train or evaluate agents and teacher policies.

