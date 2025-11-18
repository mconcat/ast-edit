# Week 3–4 Chronological Implementation Plan

This is the Week 3–4 plan rewritten as a strictly ordered sequence of work. It focuses on turning the Stage‑1 infrastructure into a working training pipeline: Stage 0/1 SFT plus an initial SRL trainer run.

## 0. Scope & Success Criteria
- Goal: Build and exercise the first end‑to‑end training loops on top of the Stage‑1 infra: (a) supervised fine‑tuning on text edits and ast‑grep formats, and (b) a small offline SRL run on verified teacher trajectories.
- Success criteria:
  - Normalized SFT datasets (text edits + ast‑grep formats) exist under `data/processed/{train,dev,test}/` with schema validation and basic stats.
  - Stage 0 SFT: a Qwen3‑14B (or smaller dev model) can be fine‑tuned to map instructions + pre‑code → post‑code, with saved checkpoints and eval metrics.
  - Stage 1 SFT: a model can be fine‑tuned to map instructions + pre‑code → ast‑grep actions (YAML/CLI), validated by applying rules offline.
  - SRL: a trainer runs over teacher trajectories with an action‑similarity reward, producing a new checkpoint and basic reward/accuracy curves.
  - All training scripts are reproducible from config (no hard‑coded paths), and can run on a single box (2×5090) without manual hacks.

## 1) Normalize & Split Datasets for SFT
- Implement ingestion/normalization scripts (or finish stubs) to convert raw sources into `NormalizedRecord` instances:
  - `scripts/ingest_commitpackft.py`, `scripts/ingest_editpackft.py`, `scripts/ingest_smellycode.py`.
  - Use `src/data/schemas.NormalizedRecord` and `DatasetMetadata` for all outputs.
- Write normalized JSONL under:
  - `data/processed/train/*.jsonl`
  - `data/processed/dev/*.jsonl`
  - `data/processed/test/*.jsonl`
- Add a simple validation/stats script (extend `scripts/report_dataset_stats.py`) to check:
  - Required fields present; languages normalized.
  - Record counts per split and per source.
  - Rough size in GB so training configs can set expectations.

## 2) Stage 0 SFT – Text Edit Behavior
- Define a data mix for Stage 0 SFT (text edits only):
  - CommitPackFT (~60%), EditPackFT (~40%) as per PLAN (adjusted to current dataset mix).
- Implement a training script, e.g. `src/training/train_sft_stage0.py`:
  - Loads processed JSONL datasets, builds prompts of the form:
    - `[system]` editing/refactoring behavior
    - `[user]` instruction + pre‑code
    - `[assistant]` post‑code
  - Uses HF Transformers + Accelerate/DeepSpeed YAML configs from `configs/accelerate.yaml`.
  - Supports LoRA/QLoRA and checkpointing into `models/sft_stage0/`.
- Add a small evaluation routine:
  - Hold‑out OCE/CanItEdit tasks.
  - Log exact string match and basic code similarity metrics.
- Document a single command that runs Stage 0 SFT on a single machine (2×5090 or smaller dev setup).

## 3) Stage 1 SFT – ast‑grep Action Format
- Prepare training data that maps tasks to ast‑grep actions:
  - Synthetic codemods (from `scripts/synth_astgrep_rules.py` once filled in).
  - Simple OCE/CommitPackFT tasks manually or heuristically converted to ast‑grep rules.
  - ast‑grep docs/examples normalized into the action schema from PLAN §11.1.
- Implement a second training script, e.g. `src/training/train_sft_stage1_astgrep.py`:
  - Input: instruction + pre‑code (+ optional prior `<state>` snippet).
  - Target: `<think>/<action>/<state_update>` or just `<action>` block containing the normalized ast‑grep action JSON/YAML.
  - Reuse the same model/config stack as Stage 0 (perhaps with a smaller LR and shorter contexts).
- Add an offline validator:
  - For a small eval set, run the model, parse the emitted action, and apply it via the sandbox (`src/sandbox/runner.py`).
  - Log success rate (# of tasks where applying the action produces the expected post‑code or passes tests).
- Save Stage 1 SFT checkpoints under `models/sft_stage1_astgrep/` with a simple README summarizing data and hyperparameters.

## 4) Scale Up Teacher Trajectory Collection
- Move from the Stage‑1 SRL PoC to a more systematic teacher trajectory collection:
  - Add a CLI or small orchestrator around `src/teachers/srl_teacher.py` (e.g. `scripts/run_teacher_batch.py`) that:
    - Reads a list of tasks from a JSONL manifest.
    - Runs the teacher model via `VLLMClient` or a remote API.
    - Writes raw trajectories under `trajectories/raw/teacher/`.
- Add a filtering/cleanup script, e.g. `src/srl/make_trajs.py`:
  - Reads raw teacher trajectories.
  - Verifies actions via the sandbox (already wired).
  - Keeps only verified steps; drops invalid JSON, failed actions, or low‑reward steps.
  - Writes cleaned SRL datasets under `data/processed/srl/{train,dev}.jsonl`.
- Target: 10–20k verified teacher steps by the end of Week 4, with per‑dataset stats written to `reports/teacher/metrics.md` (extending the existing teacher metrics script).

## 5) Implement SRL Reward & Trainer
- Implement an action‑similarity reward module, e.g. `src/srl/reward_srl.py`:
  - Parse teacher and student actions into the normalized schema.
  - Compute `S_field` (field‑level match score) and `S_str` (string similarity on `rule_yaml`/`cli`).
  - Combine into `R_srl = 0.7 * S_field + 0.3 * S_str`, clipped to [−0.2, 1.0], with −0.2 for invalid actions (as in PLAN §12.1).
- Implement an offline SRL trainer, e.g. `src/srl/train_srl.py`:
  - Loads teacher trajectories and the Stage 1 SFT model as a starting point.
  - Uses TRL or a lightweight RL loop to train on action‑only reward:
    - Student generates actions for each teacher state.
    - `reward_srl` computes per‑step reward.
    - Optimizer updates the policy toward teacher‑like actions.
  - Writes checkpoints to `models/srl_stage2/` and logs reward/accuracy curves (e.g. into `reports/srl/` or W&B/MLflow).
- Provide a one‑command SRL training entrypoint (documented in a short README under `src/srl/`).

## 6) Evaluation & Reporting for Stage 2
- Add or extend evaluation scripts to quantify the benefits of SFT + SRL:
  - `eval_canitedit.py`:
    - Runs both SFT‑only and SFT+SRL models on the CanItEdit benchmark.
    - Reports success rate, ExcessCode, and average number of rules per task.
  - Simple regression eval on a held‑out subset of OCE/CommitPackFT.
- Add a Stage‑2 report under `reports/training/stage2.md`:
  - Data used (sources, record counts, splits).
  - SFT Stage 0/1 config summaries and key metrics.
  - SRL run details (steps, reward curves, best checkpoint).
  - Short “lessons learned” / open issues to feed into the GRPO (Stage 3) plan.

## 7) Readiness for Stage 3 (GRPO) – Checklist
- Confirm:
  - Stage 1 SFT + Stage 2 SRL checkpoints are saved and loadable by TRL/Transformers.
  - Clean SRL trajectories with the schema in PLAN §6 are available and versioned (even if just via git for now).
  - Sandbox/state manager/actors are stable under light load and ready to be called from GRPO rollouts.
  - Hardware configuration and DeepSpeed/Accelerate YAMLs have been smoke‑tested with a tiny GRPO run (even if Stage 3 proper is deferred).
