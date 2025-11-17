# Week 1–2 Architecture & Implementation Plan

## 0. Scope & Objectives
- **Goal:** Establish the foundations required to start collecting high-quality, structured trajectories for the ast-grep refactoring agent. This covers data ingestion, schema/state utilities, sandbox runners, actor infrastructure, and a teacher-SRL loop capable of validating ~200–500 trajectories.
- **Success Criteria:**
  - All ingestion scripts land the enumerated public datasets in `data/raw/` with reproducible metadata + hashes.
  - Processed splits in `data/processed/{train,dev,test}/` for Python, JS/TS, Java, each with schema validation + stats reports.
  - Sandbox runner executes ast-grep YAML + CLI rewrites deterministically inside a jailed FS, with log capture + unit tests.
  - State manager reads/writes the structured interleaved-thinking state (<400–800 tokens) and enforces caps.
  - vLLM actors can serve quantized Qwen3-14B via HTTP/gRPC with health checks, integrated with the state manager and sandbox.
  - SRL teacher PoC (MiniMax M2 primary, GLM-4.6 fallback) produces verified `<think>/<action>/<state_update>` trajectories with reward annotations.

## 1. Environment & Hardware
- **Learner Box:** `2 × RTX 5090` (FP16 + ZeRO-3). Used for offline SFT prep (if needed) and SRL fine-tuning once data exists.
- **Actor Boxes:** `3 × RTX 3090`, each running a vLLM instance hosting quantized Qwen3-14B (4- or 8-bit) plus ast-grep sandbox processes.
- **Teacher Cloud GPU:** Dedicated cloud instance with **8× A100 (80 GB) or 8× H100 (80 GB)** plus ≥512 GB RAM. Either SKU is acceptable so long as the node can host the teacher stack (MiniMax M2 now preferred) with headroom for concurrent trajectory verification jobs.
- **Storage:** Local NVMe on on-prem boxes; assumption is ≥4 TB usable dedicated to datasets + checkpoints, mirrored to a local HDD array for cold storage. All dataset artifacts and logs stay on the learner/actor hosts to satisfy the “local only” constraint while still allowing HDD-based archival.
- **Networking:** Low-latency LAN between learner and actor boxes. Public ingress blocked except for admin SSH/VPN. _If VPN/firewall requirements differ, please confirm._

## 2. Repository Layout (Week 1–2 additions)
```
.
├── data/
│   ├── raw/          # Placeholder for future normalized data
│   └── processed/    # Placeholder for language-specific splits
│       ├── python/
│       ├── javascript/
│       └── java/
├── dataset/          # Per-dataset download scripts and raw content
│   ├── agentpack/
│   │   ├── download.py
│   │   ├── README.md
│   │   └── content/  # Downloaded archives (git-ignored)
│   ├── canitedit/
│   ├── commitpackft/
│   ├── editpackft/
│   ├── marv/
│   ├── oce_dataft/
│   └── smellycode/
├── scripts/
│   ├── ingest_commitpack.py  # Normalization scripts (stubs)
│   ├── ingest_oce.py
│   ├── ingest_editpack.py
│   ├── ingest_agentpack.py
│   ├── ingest_marv.py
│   ├── ingest_smellycode.py
│   ├── synth_astgrep_rules.py
│   └── report_dataset_stats.py
├── src/
│   ├── data/
│   │   ├── schemas.py        # Pydantic models (DatasetMetadata, NormalizedRecord, DatasetConfig)
│   │   └── download_utils.py # Download helpers with security hardening
│   ├── state/
│   │   └── manager.py        # (not yet implemented)
│   ├── sandbox/
│   │   └── runner.py         # (not yet implemented)
│   ├── actors/
│   │   ├── vllm_client.py    # (not yet implemented)
│   │   └── actor_loop.py     # (not yet implemented)
│   └── teachers/
│       └── srl_teacher.py    # (not yet implemented)
├── tests/
│   ├── conftest.py
│   ├── test_schemas.py
│   └── test_download_utils.py
└── configs/
    ├── datasets.yaml         # Dataset catalog with 7 entries
    ├── sandbox.yaml          # (not yet created)
    ├── vllm_actors.yaml      # (not yet created)
    └── teacher_prompts.yaml  # (not yet created)
```

## 3. Data Ingestion & Processing
### 3.1 Dataset Metadata Contract
Each ingestion script writes a `_meta.json` containing:
```json
{
  "source": "<dataset name>",
  "version": "<semver or commit hash>",
  "license": "<SPDX identifier>",
  "downloaded_at": "ISO8601 timestamp",
  "sha256": "<archive hash>",
  "num_records": 12345
}
```
- Schema validation with `pydantic` models defined in `src/data/schemas.py`.
- Unit tests ensure detection of missing or malformed fields.
- **Test Infrastructure (Implemented):**
  - `tests/test_schemas.py`: validates schema field defaults, language normalization, and metadata serialization
  - `tests/test_download_utils.py`: security-focused tests for URL validation, checksum verification, path traversal prevention, symlink blocking, and directory hashing

### 3.2 Ingestion Steps (per dataset)
1. **Download/Sync** using authenticated URLs when required (AgentPack may need credentials; store in `.env` + use `dotenv`) directly onto the learner/actor machine's HDD array (no cloud buckets) so every dataset stays co-located with the GPUs.
   - Implementation uses `src/data/download_utils.py` with security hardening:
     - URL scheme validation (HTTP/HTTPS only)
     - SSRF prevention (blocks private/loopback/link-local IPs)
     - Path traversal protection for archive extraction
     - Symlink attack prevention
     - Archive bomb protection (50GB size limit)
2. **Verify Integrity** via SHA256 + size comparison against official manifest.
3. **Normalize** into common JSONL structure: `{ "instruction": str, "pre": str, "post": str, "language": str, "tags": [str], "metadata": {...} }`.
   - The `metadata` field (dict) captures dataset-specific structured data such as test assets, commit provenance, smell types, etc.
4. **Store** raw archives untouched under `dataset/<name>/content/` and normalized JSONL under `data/raw/<dataset>/normalized/` (once normalization scripts are implemented).
5. **Process** into splits by language using heuristics:
   - Use file extensions + tree-sitter detection to confirm language.
   - Deduplicate identical `(instruction, pre)` pairs across datasets.
   - Filter max input length to 2k tokens for week-1 emphasis.
6. **Report** summary stats via `scripts/report_dataset_stats.py` (counts, avg tokens, language ratios). Save as Markdown under `reports/datasets/<dataset>.md`.

### 3.3 Synthetic ast-grep Rule Generation
- `scripts/synth_astgrep_rules.py` enumerates template rewrites (rename, wrap call, add guard) and applies them to permissively-licensed snippets.
- Output schema extends base JSONL with `"gold_action": {"pattern": ..., "rewrite": ...}` for use in reward shaping.
- Include at least 200 synthetic examples/week 1 to unblock sandbox validation.

### 3.4 Data Versioning & Governance
- Track `data/raw` and `data/processed` via **DVC** pointing at the learner/actor machine’s local HDD array (e.g., `/mnt/data/dvc`). This keeps every version on-prem while still providing reproducible hashes and the ability to roll back.
- Each ingestion script ends by `dvc add`-ing the normalized/processed outputs and `dvc push`-ing to the local remote so additions from the cloud teacher runs can be merged incrementally via `dvc pull`.
- Maintain a manifest `reports/datasets/ingestions.md` logging ingestion events (timestamp, operator, DVC commit SHA) so we can audit when new data arrived.
- Dataset stats & sample hashes are written to local Markdown reports; we intentionally avoid third-party artifact services per the “local storage” requirement.

## 4. Sandbox Runner
### 4.1 Requirements
- Execute ast-grep actions deterministically on provided code snapshot.
- Support both inline CLI patterns and YAML rule files.
- Run inside a jailed directory (e.g., `./.sandbox/<uuid>`), copying only required files.
- Enforce resource limits: CPU cores=2, RAM=4 GB, wall time=30s, disallow network.
- Capture stdout/stderr, exit codes, diffs, and optional test results.

### 4.2 Architecture
- `sandbox/runner.py` exposes:
  - `prepare_workspace(task_id, files) -> Path`
  - `apply_action(workspace, action_dict) -> SandboxResult`
  - `run_tests(workspace, test_spec) -> TestResult`
  - `cleanup(workspace)`
- Uses `subprocess.run` with `timeout`, `resource` limits (Linux `prlimit`), and `seccomp` via `nsjail` or `firejail` (configurable in `configs/sandbox.yaml`).
- Logs emitted to `logs/sandbox/<task_id>.jsonl`.

### 4.3 Testing
- Unit tests mock ast-grep binary to ensure correct command assembly.
- Integration tests spin up temp workspace with sample code & YAML rule to ensure diff output matches expectation.
- Add regression fixtures for Windows-incompatible paths even if we deploy on Linux (ensures portability).

## 5. Structured State Manager
### 5.1 Schema
- `state.manager.State` (pydantic model) with fields `goals`, `constraints`, `decisions`, `hypotheses`, `history`, `open_issues`, `next_focus`.
- Enforce max lengths (e.g., `len(history) ≤ 3`, `len(text) ≤ 256 chars`).
- Provide `token_budget` method to approximate tokens via `tiktoken` or heuristic; if > budget, summarize using `summarize_history()` helper.

### 5.2 APIs
- `load(task_id) -> State`
- `save(task_id, state)`
- `merge(existing_state, state_update) -> State` with deduping + trimming.
- `render(state) -> str` to insert into prompts.
- Storage backend: local SQLite + JSON column for atomic updates.

### 5.3 Testing & Validation
- Tests cover merge semantics, token budgeting, schema validation on malformed updates.
- Provide CLI `python -m src.state.manager dump <task_id>` for debugging actor runs.

## 6. Actor Infrastructure (vLLM + sandbox)
### 6.1 vLLM Deployment
- `configs/vllm_actors.yaml` enumerates 3 instances:
  - GPU IDs per actor, port (8001/8002/8003), tensor parallel size=1, quantization `bitsandbytes-4bit`.
- Systemd or supervisord units ensure auto-restart.
- Health endpoint `/health` polled every 15s.

### 6.2 Actor Loop (`src/actors/actor_loop.py`)
1. Pull batch of prompts + metadata from Redis queue (`redis://actor-queue:6379/0`).
2. Fetch state via `state_manager.load(task_id)`.
3. Render prompt template with `<state>` block.
4. Call `vllm_client.generate(prompt, stop=["</action>", "</state_update>"])`.
5. Parse XML-like tags, validate JSON using `jsonschema` (defined in `src/data/schemas.py`).
6. Send action to sandbox runner; collect result, tests, diffs.
7. Merge state updates; persist; push full step to `trajectories/` store (see §7).
8. Emit metrics via Prometheus client (`actor_latency`, `sandbox_failures`).

### 6.3 Observability
- Logs written to structured JSON files under `logs/actors/` and `logs/sandbox/`, rotated daily via `logrotate`. No centralized aggregation is required, but the JSON schema mirrors what we would normally ship to Loki so future tooling can ingest it if desired.

## 7. Trajectory Store (Week-1 implementation)
- Simple JSONL files under `trajectories/raw/` with schema:
```json
{
  "task_id": "uuid",
  "step": 1,
  "prompt": {...},
  "state_before": {...},
  "model_output": {"think": str, "action": {...}, "state_update": {...}},
  "sandbox_result": {...},
  "reward": null
}
```
- Later converted to Parquet with additional reward columns once SRL labels exist.
- Sync trajectories to the same local DVC remote on the learner box so verified data from cloud teacher runs can be pulled back without relying on third-party object storage.

## 8. SRL Teacher PoC
### 8.1 Prompt Template (`configs/teacher_prompts.yaml`)
```
[system] You are a senior ast-grep engineer...
[state] <structured JSON>
[user] <instruction + code + feedback>
```
- Encourage teacher to produce exactly one action + concise state update.

### 8.2 Loop (`teachers/srl_teacher.py`)
1. Sample tasks from processed datasets.
2. Render prompt with empty or prior state.
3. Call the MiniMax M2 teacher model (fallback: GLM-4.6 only if M2 availability lags).
4. Parse/validate outputs.
5. Run sandbox to verify action.
6. Assign reward labels (`verified=true/false`, diffs, test outcomes).
7. Store trajectories + metadata (model name, temperature, seed).

### 8.3 Evaluation & Targets
- Collect at least 200 verified steps across languages by end of week 2.
- Track teacher precision (verified / total) in `reports/teacher/metrics.md`.
- Track separate metrics per teacher (MiniMax M2 primary, GLM-4.6 fallback) so we can compare yield if we ever have to switch.

## 9. Security & Compliance Checklist
- Sandbox uses allowlist of binaries (`ast-grep`, `python`, `pytest`).
- All downloads hashed; license stored in metadata.
- **Download Security (Implemented):**
  - URL scheme validation (HTTP/HTTPS only, rejects file://, ftp://, etc.)
  - SSRF prevention: blocks requests to private (RFC1918), loopback (127.0.0.0/8), link-local (169.254.0.0/16), and reserved IP ranges
  - Path traversal protection: validates all archive members stay within destination directory
  - Symlink attack prevention: rejects symlinks and hardlinks in tar archives
  - Archive bomb protection: enforces 50GB uncompressed size limit
  - Timeout enforcement: 5-minute timeout for HTTP downloads
  - Test coverage: comprehensive security tests in `tests/test_download_utils.py`
- Secrets (dataset creds, API keys) stored via git-ignored `.env.local` files on each learner/actor node. Because traffic flows directly between the local machines and the teacher cloud box (no third-party services), we do not need Vault or any external secret manager for this sprint.

## 10. Week-1/Week-2 Timeline
| Week | Tasks |
| ---- | ----- |
| 1 | finalize repo skeleton, dataset ingestion scripts, metadata schemas, sandbox prototype, state manager stub, vLLM config drafts |
| 2 | complete integration tests, deploy vLLM actors, finish actor loop + trajectory store, stand up SRL teacher PoC, collect ≥200 verified trajectories |

## 11. Open Questions / Clarifications Needed
All previously open questions for week 1–2 are now resolved (teacher hardware, data versioning strategy, logging, secrets, and teacher model priority). Flag any new constraints if they arise, but the plan is otherwise execution-ready.
