# Stage 2 Plan — Supervised Reinforcement Learning (Trace Distillation for AST-grab)

Stage 2 implements **Supervised Reinforcement Learning (SRL)** as described in the 2024 SRL paper (trace imitation via GRPO-style policy optimization on teacher rollouts). We **remove SFT** entirely: the student policy is trained to follow the **teacher’s intermediate reasoning and state transitions** captured from AST-grab tasks. The plan below is implementation-ready and scoped to SRL only.

## 0) Scope & Success Criteria
- Deliverables
  - Cloud-hosted teacher that streams `<think>/<action>/<state_update>` traces for AST-grab tasks into `trajectories/raw/teacher/`.
  - Filtering pipeline that validates actions in the sandbox and emits SRL-ready JSONL traces under `data/processed/srl/{train,dev}.jsonl`.
  - SRL trainer (GRPO-style objective from the paper) that optimizes the student on offline traces; checkpoints in `models/srl_stage2/`, logs in `reports/srl/`.
  - Eval scripts comparing student vs teacher on held-out tasks (execution success + trace similarity).
- Success criteria
  - ≥10k verified teacher steps with valid tags and passing sandbox validation.
  - Student execution success on held-out tasks ≥90% of teacher success, with `<think>` and `<state_update>` tokens ≤800 per block.
  - Reproducible runs from config; one command per stage (teacher batch, filtering, SRL train, eval) runs end-to-end on 2×5090.

## 1) Prerequisites & Inputs
- Stage 1 artifacts: sandbox runner (`src/sandbox/runner.py`), state manager (PLAN.md §5 schema), task manifests under `data/processed/{train,dev,test}/`.
- Hardware: cloud GPU box (teacher: ≈100B with ≥8k context), on-prem 2×5090 for SRL training.
- Access to teacher API or vLLM serving; configs stored in `configs/teacher.yaml`.

## 2) Teacher Setup & Prompting (Cloud)
1. **Serve the teacher**
   - Launch vLLM/provider with long context (≥8k), `temperature≈0.3`, `top_p=0.9`, logprobs off. Pin version in `configs/teacher.yaml`.
2. **Prompt contract (paper-aligned trace tags)**
   - System: ast-grep refactoring agent that must emit tagged reasoning + action + state update.
   - Inputs: prior `<state>` (compact JSON), user instruction + pre-code, and any feedback from sandbox/tests.
   - Required output format:
     ```
     <think>stepwise rationale that justifies the chosen AST pattern and safety checks</think>
     <action>{normalized ast_grep action JSON}</action>
     <state_update>{"decisions":[], "constraints":[], "open_issues":[], "next_focus":[]}</state_update>
     ```
   - Enforce concise `<think>`; reject missing/misordered tags.
3. **Task sampling**
   - Balance Python/JS/Java tasks from Stage 1 plus any synthetic AST-grab tasks under `dataset/astgrep_synth/*.jsonl`.
   - Run `scripts/run_teacher_batch.py` to stream tasks and write shards to `trajectories/raw/teacher/{date}/shard_*.jsonl`.
4. **Execution check**
   - After each teacher action, call `src/sandbox/runner.py` to apply ast-grep and capture diffs/tests. Persist `env_report` with the model output.

## 3) Trajectory Schema & Storage
- JSONL per step under `trajectories/raw/teacher/` with fields: `task_id`, `source`, `split`, `input`, `state_in`, `model_output`, `think`, `action`, `state_update`, `env_report`, `timestamp`, `teacher_config`.
- Add `src/srl/schema.py` validator: enforce required tags, `<think>` ≤512 tokens, allowed `state_update` keys, and action schema (PLAN.md §11.1).

## 4) Filtering & QA Pipeline
Implement `src/srl/make_trajs.py`:
1. **Parse & normalize** teacher text into structured objects via the state manager and ast-grep action schema.
2. **Validity gates**
   - JSON-parseable `<action>` with allowed fields; no empty patterns.
   - `<state_update>` only {`decisions`, `constraints`, `open_issues`, `next_focus`}; dedupe + truncate.
   - `<think>` non-empty and within token budget.
3. **Execution gates**
   - `env_report.ok == true` AND (tests passed OR diff matches expected post-code when provided).
   - Drop steps with stderr timeouts or schema violations.
4. **Quality scoring** (store `trace_quality`)
   - `S_action`: sandbox success (1/0) plus field-level validity.
   - `S_state`: coverage of constraints/decisions mentioned in `<think>` vs `state_update` (keyword overlap heuristic).
   - `S_think`: presence of rationale for pattern choice and safety checks; brevity score vs length budget.
   - Keep `trace_quality >= 0.6`; log rejections to `reports/teacher/rejections.md`.
5. **Output** cleaned SRL datasets to `data/processed/srl/train.jsonl` and `dev.jsonl` with per-source stats in `reports/teacher/metrics.md`.

## 5) SRL Training Pipeline (Paper-faithful GRPO SRL)
Implement `src/srl/train_trace_srl.py` following the SRL paper’s objective: optimize a policy on **teacher rollouts** using a GRPO-like loss that maximizes reward for matching teacher actions + intermediate reasoning while regularizing toward the base model.
1. **Model init**
   - Base: Qwen3-14B (or smaller dev checkpoint) with LoRA/QLoRA adapters. Special tokens for `<think>`, `<action>`, `<state_update>`.
2. **Dataset loader**
   - Stream `data/processed/srl/train.jsonl` with fields `prompt` (system + state + user), `teacher_think`, `teacher_action`, `teacher_state_update`.
   - Target output = concatenated tagged blocks (matches teacher trace order).
3. **Reward function `reward_trace` (paper-aligned components)**
   - Parse student output into blocks; malformed → reward = -0.2 (paper’s penalty for invalid trajectory).
   - `R_action`: field-level F1 + edit distance vs teacher action (weight highest per paper emphasis on action fidelity).
   - `R_state`: Jaccard overlap on list fields in `state_update`, with higher weight on `constraints/decisions` to reflect state-faithfulness term.
   - `R_think`: semantic similarity (MiniLM embeddings) between `<think>` blocks with brevity penalty if length >1.5× teacher (mirrors paper’s compression regularizer).
   - Combine as `R_total = 0.5*R_action + 0.3*R_state + 0.2*R_think`, clip to [−0.2, 1.0].
   - **KL anchor**: add λ·KL(student || base) as in GRPO to prevent divergence (paper’s stability requirement); tune λ via dev set.
4. **Optimization loop (GRPO-style)**
   - For each batch: generate student trace with stop tokens at `</state_update>`; compute `R_total`; compute **generalized advantage** using paper’s advantage estimator (reward minus KL-adjusted baseline); update via PPO-style clipped objective.
   - Gradient accumulation to reach effective batch ≈64; sequence length 4k; LR 5e-6 (LoRA) or 1e-5 (full fine-tune); cosine decay, warmup 5%.
   - Log reward components, KL, and token usage to `reports/srl/` (or W&B/MLflow).
5. **Evaluation during training**
   - Periodically score on `data/processed/srl/dev.jsonl` using the same reward and sandbox execution success; save best checkpoint by `R_total` + success.
6. **Checkpointing**
   - Save to `models/srl_stage2/step_{N}` with a `README.md` describing data version, reward weights, and hardware.

## 6) Evaluation & Reporting
- `scripts/eval_srl_traces.py`:
  - Run best student checkpoint on held-out dev tasks.
  - Metrics: `R_total` vs teacher, execution success rate, tag parsing success, average `<think>`/`<state_update>` length.
  - Compare against teacher (upper bound) and base model without SRL (lower bound).
- Summarize in `reports/training/stage2.md`: data volumes/accept rates, reward + KL curves, execution success, token budgets; lessons for Stage 3 online GRPO.

## 7) One-Command Entry Points
- Teacher batch (cloud):
  - `python scripts/run_teacher_batch.py --config configs/teacher.yaml --tasks data/processed/train/tasks.jsonl --out trajectories/raw/teacher/$(date +%F)/`
- Trace cleaning:
  - `python -m src.srl.make_trajs --in trajectories/raw/teacher/$(date +%F) --out data/processed/srl --report reports/teacher/metrics.md`
- SRL training:
  - `accelerate launch --config_file configs/accelerate.yaml -m src.srl.train_trace_srl --data data/processed/srl/train.jsonl --dev data/processed/srl/dev.jsonl --output models/srl_stage2`
- Evaluation:
  - `python scripts/eval_srl_traces.py --model models/srl_stage2/best --data data/processed/srl/dev.jsonl --report reports/training/stage2.md`

## 8) Risk & Mitigation (SRL-specific)
- **Teacher drift/verbosity**: enforce token caps, regex validation; auto-truncate `<think>`; reject missing tags.
- **Low-quality traces**: strict execution + quality gates; manual spot checks on rejections to tune heuristics.
- **Student overfitting to `<think>` style**: KL anchor + brevity penalty; shuffle prompts to reduce positional bias.
- **Tool failures**: sandbox timeouts treated as hard negatives; add retry + jitter for teacher calls.

## 9) Checklist for Stage 3 Readiness
- SRL datasets versioned; schema frozen in `src/srl/schema.py`.
- Best SRL checkpoint exports tokenizer + special tokens; inference parses tags correctly.
- Reports show stable reward/KL and successful execution; token budgets respected.
- Actor/sandbox stack ready for online GRPO rollouts.
