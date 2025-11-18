Below is a complete architectural design + implementation plan for your project: a Qwen3‑14B–based, ast‑grep refactoring agent trained with SRL → GRPO (TRL) and instrumented with interleaved thinking (persisted reasoning state). It’s structured so you can hand it to a coding agent and start building.

Key external facts we rely on
	•	Interleaved thinking (carry forward the prior step’s reasoning) improves multi‑step, tool‑heavy tasks; MiniMax M2 reports sizable gains when prior-round “thinking” is preserved across turns.
	•	TRL supports GRPO and a vLLM integration so you can run training on one set of GPUs and generation on others.
	•	Code editing datasets you can use immediately: CommitPackFT (filtered commits ≈ NL instructions), OCEDataFT (20k curated edit triplets), CanItEdit benchmark (+ its EditPackFT training set), AgentPack (1.3M agent/human co‑authored code edits), MaRV (693 validated Java refactors), SmellyCodeDataset (smelly→fixed code in multiple languages).
	•	ast‑grep supports structural pattern + rewrite via CLI and YAML rules; we can call it deterministically in a sandbox.

⸻

1) Business Goal & Scope

Goal
Given a natural language edit/refactor instruction + code context, produce one (or a few) executable ast‑grep rules/commands that, when applied, transform the code correctly—preferably fewer tool calls than diff-based editing.

Non‑goals
	•	Large multi‑file refactors that need global semantic analysis beyond AST patterns (could be added later via adapters).
	•	Complex build systems or networked toolchains during training (keep env sandboxed and local for now).

⸻

2) Target Hardware & Deployment Topology
	•	On‑prem box (training): 2× 5090 (learner) + 3× 3090 (actors).
	•	Learner (2×5090): Qwen3‑14B FP16 + LoRA/QLoRA; TRL GRPOTrainer; DeepSpeed ZeRO‑3.
	•	Actors (3×3090): vLLM serving quantized policy for fast rollouts (4‑ or 8‑bit), plus ast‑grep sandbox runner.
	•	TRL’s vLLM integration lets rollouts run on different GPUs / processes from the learner.
	•	Cloud box (teacher SRL data): Spin up GPU instance(s) to host GLM‑4.6 / MiniMax M2 / MiniMax K2 Thinking (open weights) for generating teacher trajectories (see §6). (Confirm license terms for distillation before large‑scale use.)

⸻

3) System Overview (High‑Level)

┌─────────────────────────────────────────────────────────────────────┐
│                          DATA & ORCHESTRATION                       │
│  (sources → cleaning → splits → schemas → versioning → governance)  │
└───────────────┬─────────────────────────────┬────────────────────────┘
                │                             │
           SRL (offline)                   RLVR/GRPO (online)
           (teacher traces)                (TRL + vLLM + ast-grep)
      ┌────────┴─────────┐                ┌──────────┴──────────┐
      │  SRL Learner     │                │   GRPO Learner      │
      │  Qwen3‑14B       │                │   Qwen3‑14B         │
      │  (2×5090)        │                │   (2×5090)          │
      └────────┬─────────┘                └──────────┬──────────┘
               │  reward_srl()                       │  reward_env()
               │  (action-similarity)                │  (apply & score)
      ┌────────▼─────────┐                ┌──────────▼──────────┐
      │ Trajectory Store │                │  Actors (3×3090)     │
      │ (JSONL/Parquet)  │                │  vLLM + ast-grep     │
      └──────────────────┘                └──────────────────────┘

Interleaved thinking is implemented as a persistent <state> block (structured, compact), carried across steps in both SRL and GRPO loops (see §5). This mirrors M2’s “preserve reasoning between tool calls” guidance.

⸻

4) Data Plan

4.1 Public datasets (training & eval)
	•	CommitPackFT: 2GB filtered commit messages ≈ instructional edits. Use for SFT pretraining of edit behavior.
	•	OpenCodeEdit / OCEDataFT: ~20k (pre, instruction, post) curated triplets; high quality for SFT + RL prompts.
	•	CanItEdit (benchmark) + EditPackFT (training): 105 Python problems benchmark; EditPackFT is derived from filtering CommitPackFT; use EditPackFT for SFT/RL, reserve CanItEdit for eval.
	•	AgentPack: 1.3M code edits co‑authored by agent/human (Claude Code, Codex, Cursor). Downsample to small patches.
	•	MaRV (Java refactors): 693 curated code pairs, 4 refactor types—great for structural refactor training/eval.
	•	SmellyCodeDataset: smelly → clean snippets (Java, Python, JS, C++); for smell→refactor tasks.

Keep language‑balanced splits (Python / JS/TS / Java). Use repo‑level disjoint splits to avoid leakage.

4.2 Synthetic ast‑grep pairs
	•	Author a library of simple codemods (rename func/import; wrap call; optional chaining; etc.).
	•	Apply to permissive code snippets → generate (pre, instruction, post, gold_action).
	•	Keep rules and tasks short & atomic to fit one ast‑grep rule.

4.3 Storage & Versioning
	•	Raw → data/raw/… (immutable).
	•	Processed → data/processed/{train,dev,test}/… (JSONL/Parquet).
	•	Track with DVC or Git‑LFS + manifest; experiment metrics in W&B/MLflow.

⸻

5) Interleaved Thinking (Persistent State)

Why: Per MiniMax M2, preserving prior‑round “thinking” across tool calls boosts planning & reliability for multi‑step agent tasks. We adopt this with a structured state (not free‑form CoT) to keep tokens bounded and the RL signal clean.

5.1 State schema (portable JSON)

{
  "goals": ["high-level objective…"],
  "constraints": ["language=python", "only /src", "exclude generated/*", "..."],
  "decisions": ["we will rename foo→bar globally in .py"],
  "hypotheses": ["pattern A likely matches helpers only"],
  "history": [
    {"step": 1, "action_id": "R001", "summary": "rename foo→bar", "outcome": "12 matches"}
  ],
  "open_issues": ["test X failed due to shadowed name"],
  "next_focus": ["narrow pattern to def foo only"]
}

	•	Bound to ≤ 400–800 tokens; keep last 2–3 history items, deduplicate lists.
	•	Internal only—never shown to end‑users.

5.2 Prompt contract (actors & learner)

[system] You are an ast-grep refactoring agent. Produce exactly ONE action.
[state]  <structured JSON state from previous step (summarized)>
[user]   <instruction + pre_code + feedback/diff/tests from last step>
[assistant] Must output:
<think>optional brief notes</think>
<action>{"action": { ... normalized ast_grep action ... }}</action>
<state_update>{"decisions":[...], "constraints":[...], "open_issues":[...], "next_focus":[...]}</state_update>

	•	The agent loop merges <state_update> into <state> post‑execution.
	•	SRL reward & GRPO reward only use <action> (and its code outcome), not the <think> text—prevents verbosity gaming.

⸻

6) Teacher‑Student SRL (Offline)

6.1 Teacher setup
	•	Host GLM‑4.6 / MiniMax‑M2 / K2 Thinking on cloud GPUs or via API. (Both GLM‑4.6 and M2 advertise open weights for self‑hosting; verify licenses.)
	•	Force teacher to the same output schema: <think>…</think> + <action>{…}</action> + <state_update>{…}</state_update>.
	•	Environment loop per step:
	1.	Teacher proposes one ast‑grep action.
	2.	Sandbox runner applies it; returns diff/test results.
	3.	Save step to Trajectory Store if action parses and changes code; else discard/repair.
	•	Target scale: few thousand successful trajectories → tens of thousands step samples (quality > quantity).

6.2 SRL data model

{
  "task_id": "…", "lang": "python",
  "instruction": "Refactor foo(x) → bar(x)…",
  "pre_code": "...",
  "step_k": 3,
  "state_prev": {...},               // compact
  "teacher": {
    "think": "…",
    "action": {"action": { /* normalized ast-grep action */ }},
    "state_update": {...}
  },
  "env": {"apply_ok": true, "diff": "...", "tests": {"passed": 5, "failed": 0}}
}

6.3 SRL training objective
	•	Student outputs both think and action, but loss/reward is computed on action only via sequence/structure similarity (fields match + string sim).
	•	Implement as a TRL custom trainer (or GRPO variant with dense per‑step rewards). The paper you referenced frames SRL as offline RL with step‑wise advantage shaped by action similarity.

⸻

7) Online RL: GRPO (TRL) with vLLM

7.1 Why GRPO?

Critic‑free, stable, and a good fit for long reasoning/edit tasks; natively supported in TRL with vLLM rollout acceleration.

7.2 Process
	•	Policy/Ref: Qwen3‑14B (LoRA) on 2×5090; FP16; ZeRO‑3; gradient checkpointing.
	•	Actors: vLLM on 3×3090 with 4/8‑bit weights; server mode; TRL connects via endpoints.
	•	Prompts: High‑quality instructional edits (OCEDataFT, EditPackFT, curated CommitPackFT/AgentPack, MaRV/Smelly).
	•	K samples/prompt: 2–4.
	•	Reward reward_env() per sample:
	1.	Parse <action>; reject if schema invalid.
	2.	Run ast‑grep on pre_code in sandbox; capture after_code, status, logs.
	3.	Match: token or AST similarity vs post_code if available; or test pass/fail if tests exist.
	4.	Conciseness penalty: −0.05×max(0, rules‑1) − 0.001×action_tokens.
	5.	Optional state‑consistency micro‑bonus if action respects constraints/decisions.

7.3 Config (pseudocode)

from trl import GRPOTrainer, GRPOConfig

cfg = GRPOConfig(
  model_name="Qwen/Qwen3-14B",
  torch_dtype="float16",
  gradient_checkpointing=True,
  per_device_train_batch_size=1,
  gradient_accumulation_steps=16,
  max_length=2048,
  num_generations=3,         # K
  kl_coeff=0.01,
  use_vllm=True,
  vllm_endpoints=["http://actor1:8001", "http://actor2:8002", "http://actor3:8003"] # 3090s
)

trainer = GRPOTrainer(
  config=cfg,
  train_dataset=rl_prompts,     # JSONL with {instruction, pre_code, (post_code|tests), state}
  reward_fn=reward_env,         # executes ast-grep, returns scalar reward
)
trainer.train()

TRL’s docs show vLLM integration for online methods like GRPO and how to run rollouts on separate GPUs.

⸻

8) (Later) REINFORCE++

When you’re ready, swap GRPO for REINFORCE++ (critic‑free with global advantage normalization) in a framework that supports it (e.g., OpenRLHF). Keep the same reward function & state design.

⸻

9) Sandbox Execution & Security
	•	Per‑task ephemeral workspace under /work/{task_id}/.
	•	No network, low ulimits, seccomp/default Docker profile, read‑only base image; write only to /work.
	•	Allowlisted binaries: ast‑grep, python -m unittest/pytest (optional), basic shell.
	•	Timeouts: 2–5s per action; hard kill on overuse.
	•	Capture stdout/stderr, unified JSON report:

{"ok": true, "changed_files": 3, "diff": "...", "tests": {"passed": 12, "failed": 0}}


⸻

10) Code & Repo Layout (for your coding agent)

repo/
  orchestration/
    agent_loop.py              # plan→act→reflect with persistent state
    state_manager.py           # summarize/merge/bound <state> (token budget)
    schemas.py                 # Pydantic: Action, State, TrajectoryStep
    sandbox/
      runner.py                # ast-grep exec, test runner, safety
      docker/                  # container spec, entrypoint
  data/
    raw/                       # immutable source datasets
    processed/{train,dev,test}/
    scripts/ingest_{commitpackft,editpackft,smelly}.py
  srl/
    make_trajs.py              # teacher loop (GLM-4.6/M2...)
    reward_srl.py              # action-similarity reward (fields+string)
    train_srl.py               # offline SRL trainer (TRL custom or simple RL loop)
  rl/
    reward_env.py              # apply ast-grep, compute reward
    train_grpo.py              # TRL GRPOTrainer wiring
    vllm_client.py             # endpoint pool, retry/backoff
  eval/
    eval_canitedit.py          # hold-out exact/AST/test metrics
    eval_refactor.py           # MaRV/Smelly metrics
  configs/
    accelerate.yaml
    deepspeed_zero3.json
    grpo.yaml
  infra/
    compose.yml                # vLLM actors + sandbox orchestrator
    k8s/                       # optional manifests
  scripts/
    launch_actors.sh           # start vLLM on 3090s
    launch_learner.sh
  docs/
    ADRs/


⸻

11) Schemas (Pydantic-ish)

11.1 Action (normalized)

{
  "action": {
    "type": "ast_grep",
    "language": "python",
    "mode": "yaml",                    // or "cli"
    "rule_yaml": "id: rename_foo ...", // if yaml
    "cli": "ast-grep run -p 'foo($A)' --rewrite 'bar($A)' --lang python -U", // if cli
    "notes": "optional brief note"
  }
}

11.2 Trajectory Step

{
  "task_id":"…","step":2,"state_prev":{…},"instruction":"…","pre_code":"…",
  "model_out":{"think":"…","action":{…},"state_update":{…}},
  "env_out":{"ok":true,"diff":"…","tests":{"passed":5,"failed":0}}
}


⸻

12) Reward Functions

12.1 SRL (action similarity only)
	•	Parse both teacher & student action.
	•	Field match score (type/lang/mode, pattern keys) + string sim (Levenshtein/LCS/Jaccard on rule_yaml|cli).
	•	Return R_srl = 0.7 * S_field + 0.3 * S_str (clip [−0.2, +1.0]); −0.2 if invalid.

12.2 GRPO (environment)
	•	Parse & run action; base penalties for invalid/no‑op.
	•	S_code: token/AST similarity vs post_code if present; else 0.
	•	test_bonus: +0.5 if provided tests pass.
	•	Conciseness penalties (rules>1, long action).
	•	R = base + 1.5*S_code + test_bonus − penalties.
	•	Tune coefficients by pilot runs.

⸻

13) Training Curriculum & Runbooks

13.1 Stage 0 — SFT (text edits)
	•	Data mix: CommitPackFT (60%) + OCEDataFT (20%) + EditPackFT (15%) + MaRV/Smelly (5%).
	•	Output = edited code (no ast‑grep yet).

13.2 Stage 1 — SFT (ast‑grep format)
	•	Train on: ast‑grep docs examples + synthetic codemods + simple OCE tasks mapped to rules.
	•	Output = YAML/CLI rule; validate by actually applying rule offline pre‑train.

13.3 Stage 2 — SRL (teacher trajectories)
	•	Collect trajectories with schema in §6; filter to verified successes.
	•	Train with action‑only reward.

13.4 Stage 3 — GRPO (online)
	•	Start with K=2–3, context 2k, batch size 1 + grad‑accum ~16; FP16 on learner.
	•	Observe KL, reward stats, success rate; increase K or prompt difficulty gradually.

13.5 Stage 4 — REINFORCE++ (optional)
	•	Switch in OpenRLHF (or your own trainer) with same reward & prompts.

⸻

14) Evaluation (Definition of Done)
	•	Primary
	•	Exact/AST match on held‑out tasks (OCE/CanItEdit) ≥ agreed target.
	•	Tests pass rate where available.
	•	Avg rules per task ≤ 2.0; tokens per step below budget.
	•	Benchmarks
	•	CanItEdit: do not train on it; report success rate & ExcessCode metric.
	•	MaRV, SmellyCodeDataset: refactor success / smell removal.
	•	Ablations
	•	With vs without interleaved state (expect improvements in success & fewer retries).

⸻

15) Observability & Ops
	•	Metrics: reward components, success rate, steps‑to‑solve, rules count, tokens/step, actor queue depth, vLLM latency.
	•	Logs: per‑step inputs/outputs, action JSON, sandbox results, diffs.
	•	Tracing: trajectory IDs propagate across services.
	•	Dashboards in W&B/MLflow + Prometheus/Grafana for runtime.

⸻

16) Risk & Mitigation
	•	License & compliance: confirm teacher model & dataset licenses (CommitPackFT & CanItEdit releases are permissive; confirm for teacher weights).
	•	Prompt drift / verbosity: keep rewards action‑centric; cap prompt & state length.
	•	Security: sandbox strict; no network; timeouts; allowlist binaries.
	•	Heterogeneous GPUs: learner on 5090s; actors on 3090s; scale actors if the learner waits.
	•	State bloat: state manager enforces caps & summarization each step.

⸻

17) Concrete Commands & Config Snippets

17.1 vLLM actors (on each 3090)

CUDA_VISIBLE_DEVICES=2 vllm serve Qwen/Qwen3-14B \
  --quantization bitsandbytes-4bit \
  --max-model-len 2048 --tensor-parallel-size 1 --port 8001
# repeat on GPUs 3/4 with ports 8002/8003

TRL vLLM server‑mode works with online GRPO.

17.2 Accelerate + DeepSpeed (learner on 2×5090)

# configs/accelerate.yaml (excerpt)
distributed_type: DEEPSPEED
mixed_precision: fp16
deepspeed_config:
  zero_stage: 3
  gradient_accumulation_steps: 16
  gradient_clipping: 1.0

17.3 ast‑grep CLI in sandbox

# YAML rule file path: /work/rule.yaml
ast-grep run --lang python -U -c /work/rule.yaml /work/code
# or
ast-grep run --pattern 'foo($A)' --rewrite 'bar($A)' --lang python -U /work/code

CLI and YAML rewrite are both supported.

⸻

18) Minimal Modules (implementation plan for a coding agent)

18.1 state_manager.py
	•	load() / save() / summarize(state, budget_tokens)
	•	merge(state, state_update): dedupe lists; cap history to last N; normalize keys.

18.2 sandbox/runner.py
	•	apply_action(pre_code, action) -> (ok, after_code, logs)
	•	run_tests(after_code, test_spec) -> (passed, failed, logs)
	•	Enforce timeouts; strip ANSI; return JSON report.

18.3 reward_env.py
	•	reward(sample, model_out) -> float
	•	Internals: parse→apply→similarity/test→penalties.

18.4 vllm_client.py
	•	Endpoint pool; health checks; exponential backoff; JSON schema validation for outputs.

18.5 agent_loop.py (actors)

while True:
  batch = pop_prompts()
  for prompt in batch:
    prompt_with_state = render(prompt, state_manager.load(prompt.id))
    out = vllm.generate(prompt_with_state, stop_tokens=["</action>"])
    action, state_upd = parse(out)
    env = sandbox.apply(action)
    new_state = state_manager.merge(state, state_upd)
    push_trajectory_step(prompt.id, out, env, new_state)

18.6 train_grpo.py
	•	Build rl_prompts (JSONL).
	•	GRPOTrainer(config, reward_fn=reward_env).
	•	Periodic eval on held‑out sets; checkpoint + artifact logging.

18.7 srl/make_trajs.py
	•	Teacher loop w/ <think>/<action>/<state_update> prompt; same sandbox; save only verified steps.

⸻

19) Schedule (suggested)
	1.	Week 1–2: data ingestion; sandbox runner; schemas; state manager; vLLM actors; SRL teacher POC (200–500 trajectories).
	2.	Week 3–4: Stage 0/1 SFT; SRL trainer; small SRL run (10–20k steps).
	3.	Week 5–6: GRPO pilot (K=2, short contexts); tune rewards/penalties; add interleaved state caps.
	4.	Week 7+: Scale SRL set; long GRPO; optional REINFORCE++ run; finalize benchmarks.

⸻

20) Acceptance Criteria (first milestone)
	•	On CanItEdit: ≥ target success rate (team to set), with avg rules ≤ 2, and tokens/step within budget.
	•	On a curated internal suite (your repos): pass rate & diffs reviewed OK by maintainers.
	•	RL training stable over ≥ 48 hours; no actor starvation; reproducible seeds.

⸻

Appendix — Key References
	•	Interleaved thinking (MiniMax M2): why preserving reasoning across tool calls matters & reported gains.
	•	TRL: GRPO & vLLM (online RL, server‑mode rollouts).
	•	Datasets: CommitPack/CommitPackFT, OCEDataFT (OpenCodeEdit), CanItEdit + EditPackFT, AgentPack, MaRV, SmellyCodeDataset.
	•	ast‑grep docs: rewrite via CLI/YAML; pattern syntax; CLI reference.
