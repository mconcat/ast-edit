# Week 1–2 Chronological Implementation Plan

This is the Week 1–2 plan rewritten as a strictly ordered sequence of work. It keeps the original scope and success criteria but sequences tasks so you can execute from top to bottom.

## 0. Scope & Success Criteria
- Goal: Establish foundations to collect verified trajectories for an ast-grep refactoring agent: data ingestion, sandbox, state manager, actors, and a teacher-SRL loop (~200–500 verified steps).
- Success criteria:
  - Ingestion scripts populate `data/raw/` with metadata + hashes; processed splits in `data/processed/{train,dev,test}/` with validation + stats.
  - Sandbox runs ast-grep YAML/CLI deterministically in a jailed FS, with logging and unit/integration tests.
  - State manager persists capped interleaved-thinking state (≈400–800 tokens) and enforces caps/summarization.
  - vLLM actors serve quantized Qwen3‑14B with health checks and integrate with state + sandbox.
  - SRL teacher PoC yields verified `<think>/<action>/<state_update>` trajectories with reward annotations.

## 1) Bootstrap & Data Scaffolding (Completed)
- Repository skeleton with `data/`, `dataset/`, `scripts/`, `src/`, `tests/`, `configs/` directories.
- Dataset catalog in `configs/datasets.yaml`.
- Pydantic models and helpers: `src/data/schemas.py`, `src/data/download_utils.py`.
- Ingestion stubs: `scripts/ingest_*.py`, dataset `download.py` scripts and READMEs under `dataset/*`.
- Tests: `tests/test_schemas.py`, `tests/test_download_utils.py`.

## 2) Secure Download & Metadata (Completed)
- Enforce URL scheme allowlist; block RFC1918/localhost ranges.
- Archive extraction hardened against path traversal, symlinks/hardlinks, and archive bombs.
- 5‑minute HTTP timeouts; SHA256 verification; deterministic directory hash; unit tests cover these paths.

## 3) Create Sandbox Configuration (Next)
- Add `configs/sandbox.yaml` with:
  - jailer: `nsjail` or `firejail` (toggle), or `none` during local CI.
  - resource limits: CPU time, memory, file count/size, process count.
  - allowed binaries: `ast-grep`, `python`, `pytest` (explicit allowlist).
  - logging: `logs/sandbox/<task_id>.jsonl` path and rotation settings.

## 4) Implement Sandbox Runner Prototype (Next)
- File: `src/sandbox/runner.py` exposing:
  - `prepare_workspace(task_id, files) -> Path`.
  - `apply_action(workspace, action_dict) -> SandboxResult` (runs ast-grep YAML/CLI, captures stdout/stderr, exit codes, diffs).
  - `run_tests(workspace, test_spec) -> TestResult` (optional pytest or command set).
  - `cleanup(workspace)`.
- Implementation details:
  - Use `subprocess.run` with `timeout` and rlimits (`prlimit`), apply jailer from config when enabled, and disable network.
  - Emit structured JSONL logs to `logs/sandbox/` per step.
- Testing:
  - Unit tests mock `ast-grep` to validate command assembly and timeouts.
  - Integration test applies a sample YAML rule in a temp workspace and checks diff output.

## 5) Structured State Manager
- File: `src/state/manager.py` with model `State` fields: `goals`, `constraints`, `decisions`, `hypotheses`, `history`, `open_issues`, `next_focus`.
- APIs: `load(task_id)`, `save(task_id, state)`, `merge(existing, update)`, `render(state)`.
- Enforce caps (e.g., `len(history) ≤ 3`, text ≤ 256 chars); token budgeting + summarization helper.
- Backend: local SQLite with a JSON column for atomic updates; CLI utility `python -m src.state.manager dump <task_id>`.

## 6) Actor Configs and vLLM Client
- Add `configs/vllm_actors.yaml` enumerating 3 actors (ports, GPU IDs, quantization, TP size).
- Implement `src/actors/vllm_client.py` with `generate(prompt, stop, temperature, seed)` and a `/health` check.

## 7) Actor Loop Integrated with Sandbox
- File: `src/actors/actor_loop.py`:
  - Pull tasks from a local queue (Redis or file-backed stub).
  - Load state, render prompt with `<state>` block, call vLLM client.
  - Parse XML-like tags; validate JSON via schema; send action to sandbox; collect results and diffs.
  - Merge/apply state updates; persist; emit metrics (`actor_latency`, `sandbox_failures`).

## 8) Trajectory Store (Initial)
- `trajectories/raw/*.jsonl` records with schema:
  - `task_id`, `step`, `prompt`, `state_before`, `model_output` (`think`, `action`, `state_update`), `sandbox_result`, `reward`.
- Later convert to Parquet; reuse the same local DVC remote when introduced.

## 9) Teacher Prompts and SRL PoC
- Add `configs/teacher_prompts.yaml` with system + state + user blocks; encourage one action + concise state update.
- Implement `src/teachers/srl_teacher.py`:
  - Sample tasks, render prompt, call MiniMax M2 (GLM‑4.6 fallback), parse/validate outputs.
  - Run sandbox to verify actions; label rewards; store trajectories with model/seed metadata.

## 10) Reporting & Evaluation
- `scripts/report_dataset_stats.py` for processed splits; write `reports/teacher/metrics.md`.
- Targets: ≥200 verified steps by end of week 2; track precision (verified/total) per teacher.

## 11) Security & Compliance Closers
- Sandbox allowlist enforced; all downloads hashed; license in dataset metadata.
- Secrets via git-ignored `.env.local` on each host.
- Decide jailer (`nsjail` vs. `firejail`) and finalize policy in `configs/sandbox.yaml`.

## 12) Week-by-Week Timeline
- Week 1: Steps 3–5 (sandbox config + runner; state manager). Keep data scaffolding green.
- Week 2: Steps 6–9 (actors, trajectory store, teacher PoC) plus Step 10 reporting.

## 13) Open Questions
- Confirm final jailer choice and any host-specific constraints.
- Confirm DVC vs. git-annex for artifact tracking before wiring ingestion to it.

