# Week 1–2 Progress (Chronological)

This report is reordered to reflect the sequence of work completed so far and the exact order of remaining tasks.

## A. Progress To Date (in order)
1) Repository bootstrap and layout
- ✅ Created repo skeleton with `data/`, `dataset/`, `scripts/`, `src/`, `tests/`, `configs/` and matching `.gitignore`/`.gitkeep`.

2) Dataset models and secure download utilities
- ✅ Implemented `src/data/schemas.py` (`DatasetMetadata`, `NormalizedRecord` with `metadata` dict, `DatasetConfig`).
- ✅ Implemented `src/data/download_utils.py` with URL allowlist, SSRF protections, archive traversal/symlink/bomb defenses, timeouts, and directory hashing.
- ✅ Tests in `tests/test_schemas.py` and `tests/test_download_utils.py` validate schema defaults, ISO serialization, language normalization, checksum enforcement, traversal blocking, and symlink rejection.

3) Dataset scaffolding
- ✅ Added `configs/datasets.yaml` and per-dataset `dataset/<name>/download.py` + README stubs.
- ✅ Stubbed normalization scripts `scripts/ingest_*.py` and reporting `scripts/report_dataset_stats.py`.
- ⏳ Actual downloads and normalization are deferred until we can access upstream endpoints.

4) Synthetic ast-grep generation scaffolding
- ✅ Placeholder `scripts/synth_astgrep_rules.py` exists; rule templates and generation logic will be added after sandbox runner is available.

5) Sandbox, state manager, and actor infrastructure
- ✅ Sandbox prototype: `configs/sandbox.yaml` and `src/sandbox/runner.py` with per-task workspaces, allowlisted commands, rlimits, JSONL logging, and unified diffs; tests in `tests/test_sandbox_runner.py`.
- ✅ Structured state manager: `src/state/manager.py` with `State` dataclass, caps, SQLite backend, CLI dump helper, and tests in `tests/test_state_manager.py`.
- ✅ vLLM actor configs and client: `configs/vllm_actors.yaml` plus `src/actors/vllm_client.py` (`generate`, `/health`), with tests in `tests/test_vllm_client.py`.
- ✅ Actor loop integrated with sandbox and trajectory store: `src/actors/actor_loop.py` wiring vLLM → state → sandbox and writing JSONL records under `trajectories/raw/`; tests in `tests/test_actor_loop.py`.
- ✅ Subsystem documentation: `src/sandbox/README.md`, `src/state/README.md`, and `src/actors/README.md` describe architecture and APIs.

## B. Remaining Sequence of Work
1) Teacher prompts and SRL PoC
- Add `configs/teacher_prompts.yaml` and implement `src/teachers/srl_teacher.py` to generate and verify teacher steps via the sandbox, then label rewards and store trajectories with model/seed metadata.

2) Reporting and evaluation
- Produce `reports/teacher/metrics.md`; target ≥200 verified steps by end of week 2; track precision (verified/total) per teacher.

3) Data versioning & governance
- Wire DVC (or chosen alternative) to local storage; add ingestion manifest and DVC add/push hooks where appropriate.

4) Security & compliance closers
- Decide jailer (`nsjail` vs `firejail`) and finalize policy; automate license manifest; add secrets management notes for local `.env.local`.

## C. Notes & Clarifications
- Addressed: `NormalizedRecord` already includes a `metadata` dict for tests/provenance; downstream code should consume it rather than parsing `tags`.
- Blockers: network access to upstream datasets (for actual downloads), teacher GPU availability window, and jailer selection.
- Environment/hardware assumptions unchanged; hostnames/IPs and secrets bootstrap documentation still pending.
