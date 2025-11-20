# Stage 2 Research Notes — Supervised Reinforcement Learning for AST-grab

These notes expand the implementation plan in `PLAN_STAGE_2.md` with a research-first view of **Supervised Reinforcement Learning (SRL)** as presented in the 2024 SRL paper (trace imitation via Generalized Reinforcement Policy Optimization, GRPO). The goal is to spell out why SRL fits the AST-grab task, how the algorithm works mathematically, and what design levers matter when reproducing it. Length is intentionally verbose to preserve context for future readers.

## 1. Why SRL (not SFT or pure RL) for AST-grab?
- **Trace supervision is the signal**: AST-grab tasks hinge on *structured reasoning* (selecting patterns, anticipating diffs, planning retries). SRL uses teacher trajectories with `<think>/<action>/<state_update>` so the student learns intermediate control states, not just terminal code.
- **Avoids reward sparsity**: Pure RL on execution success yields sparse rewards (pass/fail). SRL injects dense shaping by rewarding alignment to the teacher’s intermediate steps (action fields, state updates, concise rationale) before touching the sandbox.
- **KL anchoring stabilizes policy**: SRL’s GRPO objective adds a KL-to-base regularizer, preventing drift when the reward is shaped from teacher traces rather than ground-truth labels.
- **Compression of teacher verbosity**: The paper emphasizes brevity; SRL rewards matching the *information* in `<think>` while penalizing overlong thoughts, helping the student stay inside AST-grab token budgets.

## 2. Teacher Trajectories: What the paper prescribes
- **Trajectory form**: Each step is a triple of `<think>`, `<action>`, `<state_update>` (paper §3). The teacher emits *justifications* that map to concrete edits and updates to a latent planner state.
- **Determinism vs entropy**: The paper advises low temperature (≈0.3) to reduce multimodality in traces; diversity comes from task sampling, not stochastic verbosity.
- **Validity as a gate**: Invalid or malformed tags are treated as *negative reward* during student training; thus we should pre-filter to avoid teaching the model to cope with noise.
- **Execution alignment**: The teacher’s action should be validated against the sandbox so reward components correspond to something that is actually executable.

## 3. SRL Objective (GRPO-style) in detail
- **Base distribution**: Student policy \(\pi_\theta\) is initialized from a base LM \(\pi_0\); SRL optimizes \(\theta\) while penalizing divergence via \(\mathrm{KL}(\pi_\theta \Vert \pi_0)\).
- **Reward decomposition (paper §4)**:
  - \(R_\text{action}\): similarity between student action JSON and teacher action; weighted highest because actions map to environment transitions.
  - \(R_\text{state}\): overlap between student `<state_update>` and teacher’s state fields; encourages faithful planner updates.
  - \(R_\text{think}\): semantic similarity of rationale with brevity penalty; prevents verbosity spirals.
  - Invalid formatting yields \(R=-0.2\) (paper’s minimum penalty) to discourage malformed traces.
- **Overall reward**: Weighted sum clipped to \([-0.2, 1.0]\); we mirror the weights (0.5/0.3/0.2) to privilege actions.
- **Advantage estimation**: GRPO uses the reward minus a KL-adjusted baseline. Practically, we compute \(A = R_\text{total} - \lambda \cdot \mathrm{KL}\) and feed it to a PPO-style clipped surrogate objective.
- **Why GRPO instead of naive MLE**: GRPO balances imitation (reward components) with conservatism (KL anchor) and handles off-policy trajectories better than pure maximum likelihood because the reward is not just log-prob of the teacher tokens—it explicitly encodes structural correctness.

## 4. How SRL fits AST-grab state/action spaces
- **Action space is structured**: ast-grep actions include pattern, replacement, file scope, and optional constraints; SRL’s action reward can operate on fields (edit distance + field F1) rather than treating the action as opaque text.
- **State updates mirror planner needs**: The `<state_update>` lists decisions, constraints, open issues, and next focus. Rewarding overlap ensures the student tracks latent TODOs and risk checks, matching the paper’s emphasis on *state faithfulness*.
- **Rationales gate risk**: AST-grab requires safety (avoid over-editing). Concise `<think>` rationales with explicit preconditions help prevent unsafe patterns; SRL incentivizes those rationales via \(R_\text{think}\).

## 5. Data and filtering principles grounded in the paper
- **Quality threshold**: The paper’s experiments show performance lifts only when invalid/low-quality steps are filtered aggressively. Thus, we keep `trace_quality ≥ 0.6` after schema + execution checks.
- **Balanced modality**: Over-representing one language or template can cause action overfitting; sample a balanced mix of Python/JS/Java and synthetic AST-grab variants to retain diversity (paper ablation noted robustness when task variety was preserved).
- **Brevity control**: Token caps on `<think>` (≈512 tokens) mirror the paper’s brevity regularizer, preventing the student from learning verbosity that harms downstream cost and latency.
- **Execution grounding**: Every teacher action is run in the sandbox; non-executable steps are dropped so rewards reflect executable behavior, aligning with the paper’s “grounded reward” requirement.

## 6. Reward design choices and their rationale
- **Action weight dominance (0.5)**: Empirically, correct actions directly translate to task success. The paper’s charts show reward sensitivity is highest on action fidelity, so we assign the largest coefficient.
- **State overlap weight (0.3)**: Maintaining the planner state improves multi-step success; overlap on `constraints` and `decisions` is weighted more heavily than `open_issues/next_focus` because those drive immediate safety and correctness.
- **Think similarity weight (0.2)**: Enough to encourage rationale alignment but capped to avoid teaching verbosity. Embedding-based similarity is robust to paraphrase, matching the paper’s use of semantic metrics.
- **Penalty for malformed output (-0.2)**: Strong negative reward ensures the policy learns tag correctness early; this mirrors the paper’s stabilization trick to reduce parser failures during training.
- **KL anchor (λ)**: The paper treats λ as a tunable hyperparameter controlling deviation from the base model; we sweep λ on dev traces to balance exploration vs stability.

## 7. Training mechanics (algorithm view)
- **Generation step**: For each prompt (state + user instruction), sample student trace with constrained decoding (stop at `</state_update>`). Constrained decoding aligns with the paper’s “format adherence before reward” guidance.
- **Parsing step**: Convert the student text back into structured blocks. Parser failures immediately receive the -0.2 reward and zero advantages to avoid backprop through garbage.
- **Reward computation**: Compute \(R_\text{action}\), \(R_\text{state}\), \(R_\text{think}\), combine into \(R_\text{total}\), and add KL penalty using cached base logprobs.
- **Advantage + update**: Apply PPO-style clipping with a value head or reward baseline. GRPO’s advantage is defined against the KL-adjusted baseline, which reduces variance without sacrificing the conservatism term.
- **Logging**: Track per-component rewards, KL magnitude, and tag-parse success rate. The paper reports that early KL spikes correlate with later instability; monitoring allows early stopping or λ reduction.

## 8. Architectural choices and tokenization
- **Special tokens**: Introduce dedicated tokens for `<think>`, `</think>`, `<action>`, `</action>`, `<state_update>`, `</state_update>` to minimize spurious splitting; the paper notes improved stability when tags are atomic tokens.
- **Context window**: AST-grab steps are short, but we keep ≥4k context for multi-turn tasks. Teacher uses ≥8k to ensure complete rationale; student can compress.
- **Parameterization**: LoRA/QLoRA adapters maintain a strong base prior (useful for KL anchoring). Full fine-tuning is possible but risks KL blow-up; adapters keep the KL term meaningful.

## 9. Comparison to SFT and offline RL
- **Versus SFT**: SFT maximizes likelihood of teacher tokens, implicitly over-weighting surface form. SRL optimizes structured rewards (actions/states) and penalizes verbosity, leading to better generalization under token limits.
- **Versus offline RL with sparse rewards**: SRL’s dense, component-wise rewards provide better credit assignment per tag; no need for synthetic reward models.
- **Safety**: SRL’s malformed-output penalties make the model safer in deployment because it learns to respect schemas rather than merely imitating strings.

## 10. Evaluation philosophy (paper-aligned)
- **Dual metrics**: Measure both execution success *and* reward components on held-out tasks. The paper shows that reward alignment correlates with success but can drift if KL is ignored; we therefore monitor both.
- **Upper/lower bounds**: Teacher is the upper bound; base model is the lower. Improvement over base without regressing on KL is the key criterion.
- **Trace formatting rate**: Track how often the student emits parseable tags; the paper treats this as a first-class metric because reward computation depends on it.

## 11. Risk analysis rooted in paper observations
- **Teacher drift**: If teacher becomes verbose, student inherits verbosity. Mitigation: enforce token caps and rejection sampling on teacher outputs.
- **Reward hacking**: The student might game the similarity metrics (e.g., copying teacher text). KL anchor plus brevity penalties reduce this risk; random perturbations in teacher phrasing during training can further harden the reward.
- **Mode collapse under high λ**: Over-regularization can freeze learning. Sweep λ and monitor reward variance; decay λ over time if advantages vanish.
- **Parser brittleness**: Tag parsing failures stall learning; use strict regex + JSON validation and treat errors as negative reward to quickly steer the model back to valid formats.

## 12. Ablations and diagnostics worth running
- **λ sweep**: Evaluate λ ∈ {0.01, 0.05, 0.1} on dev reward and execution success to find the stability/learning trade-off.
- **Reward weight sweep**: Vary action/state/think weights to test sensitivity; the paper reports action weight dominance but gains from non-zero state rewards.
- **Brevity penalty toggle**: Remove or increase the brevity penalty to observe impact on token use and success; aligns with paper’s compression ablation.
- **Teacher temperature**: Compare T=0.2 vs 0.5 for trace diversity vs determinism.
- **Parser failure penalty**: Test -0.1 vs -0.2 to see how aggressively format adherence needs to be enforced.

## 13. Practical guidance for reproducibility
- **Version everything**: Pin teacher model hash, tokenizer, and decoding params; store in `configs/teacher.yaml` alongside the SRL reward weights to make experiments replayable.
- **Deterministic seeds**: Fix RNG seeds for batching and decoding to match paper’s reproducibility practices.
- **Logging granularity**: Keep per-component reward histograms; the paper highlights that action reward variance is the leading indicator of instability.
- **Data slices**: Maintain source slices (Python/JS/Java/synthetic) to debug regressions; SRL training can be biased if a single slice dominates.

## 14. How this informs Stage 2 implementation
- The implementation in `PLAN_STAGE_2.md` follows these research principles: structured tags, aggressive filtering, GRPO with KL, and component-wise rewards. The notes here justify each design choice with reference to the SRL paper’s findings and ablations.
- The same reward schema should power both training and evaluation to avoid objective mismatch.
- Stage 2 remains entirely SRL; no SFT pre-phase is necessary per the paper’s claim that SRL subsumes supervised fine-tuning for trajectory learning.

## 15. Glossary (paper terms mapped to AST-grab)
- **Trajectory**: one `<think>/<action>/<state_update>` triple for a task step.
- **State faithfulness**: how well the student’s `state_update` matches the teacher’s planner state fields.
- **Action fidelity**: structural similarity between student and teacher ast-grep actions.
- **Compression**: keeping `<think>` concise while retaining rationale content.
- **KL anchor**: regularizer tying the student policy to the base policy; prevents drift.

## 16. References
- *Supervised Reinforcement Learning* (2024), “trace imitation with GRPO”, available from the authors’ preprint. Use this as the canonical reference for reward design, KL anchoring, and brevity penalties.

## 17. Mathematical sketch of GRPO update
- **Objective**: Maximize \(\mathbb{E}_{x \sim D, y \sim \pi_\theta}[R(y, y^\*; x)] - \lambda \mathrm{KL}(\pi_\theta || \pi_0)\) where \(y^\*\) is the teacher trace and \(R\) is the structured reward.
- **Surrogate loss**: Use PPO-style clipped objective \(L = \mathbb{E}[\min(r_t A_t, \text{clip}(r_t, 1-\epsilon, 1+\epsilon) A_t)]\) with \(r_t = \frac{\pi_\theta(y_t|x)}{\pi_{\text{old}}(y_t|x)}\) and \(A_t = R_{\text{total}} - \lambda \cdot \mathrm{KL}\).
- **Value baseline**: Optionally train a small value head on \(R_{\text{total}}\) to reduce variance; paper reports stability gains especially when action reward variance is high.
- **Gradient flow**: Rewards are scalar; gradients flow through log-probs of the student outputs, not through the reward model, which keeps the system lightweight compared to RLHF.

## 18. Reward component metrics (operational definitions)
- **Action similarity**: Weighted sum of field-level F1 (presence/absence of pattern, replacement, path constraints) and normalized Levenshtein distance on string fields. Normalize to [0,1].
- **State overlap**: Jaccard similarity for list fields (`constraints`, `decisions`, `open_issues`, `next_focus`). Weight `constraints` and `decisions` by 1.5× to reflect safety-critical info.
- **Think similarity**: Embedding cosine similarity between student and teacher `<think>` concatenated text. Apply brevity penalty: \(\text{penalty} = \max(0, \frac{\text{len}_\text{student}}{1.5 \cdot \text{len}_\text{teacher}} - 1)\); final score is \(\text{cosine} - 0.2 \cdot \text{penalty}\).
- **Malformed penalty**: If any tag is missing, misordered, or invalid JSON, set \(R=-0.2\) regardless of other scores.
- **Clipping**: Clip combined reward to [-0.2, 1.0] to keep PPO stable as in the paper.

## 19. Teacher policy and prompt engineering rationale
- **System role**: Position the teacher as a refactoring expert constrained by AST semantics; primes the model to emit precise patterns rather than prose.
- **Few-shot anchors**: Include 2–3 short exemplars with correct tags; the paper notes few-shot anchors reduce malformed outputs for new domains.
- **Temperature vs diversity**: Favor T≈0.3; use dataset diversity (different repos, languages, error types) rather than decoding entropy to widen coverage.
- **Streaming and truncation**: Stream outputs to enforce ordering `<think>` then `<action>` then `<state_update>`; truncate any extra commentary to avoid polluting tags.

## 20. Trace parsing robustness
- **Regex + JSON validation**: Extract tags with strict regex; parse `<action>` as JSON and verify required keys. Reject on any failure.
- **Round-trip check**: Re-serialize the parsed action/state and ensure textually equivalent to enforce determinism.
- **Noise handling**: The paper suggests rejecting noisy traces rather than trying to clean them; aligns with our choice to drop rather than patch malformed steps.
- **Schema drift detection**: Track rejection reasons; if a new pattern of errors appears, adjust the teacher prompt instead of relaxing validators.

## 21. Scaling expectations and compute notes
- **Sample efficiency**: Paper reports strong gains with tens of thousands of steps. For AST-grab, target ≥10k validated steps to avoid overfitting to template artifacts.
- **Batch sizing**: Effective batch ≈64 tokens-per-step balanced against 4k context; accumulation helps fit 2×5090 cards while maintaining PPO stability.
- **Learning rate**: Start 5e-6 (LoRA) with cosine decay; higher rates caused KL spikes in the paper’s ablations.
- **Generation budget**: Keep max new tokens ≈1k to bound compute; brevity penalties further discourage overlong generations.

## 22. Mapping to AST-grab error taxonomy
- **Pattern wrong**: Action reward catches mismatched patterns/replacements.
- **Scope wrong**: Include file/path scope in action similarity to penalize global edits when local is expected.
- **Safety checks missing**: State and think rewards encourage explicit constraints and preconditions.
- **Plan drift**: State faithfulness reward anchors the student to previously declared decisions, reducing oscillations.

## 23. Sandbox feedback integration
- **Env report**: Each teacher action is executed; the resulting diff/tests are stored as `env_report`. Use this to drop steps where execution failed, ensuring rewards correspond to feasible actions.
- **Student evaluation**: During eval, execute student actions too; compare success rate and reward to measure both behavior and outcomes.
- **Iterative tasks**: For multi-step tasks, feed back the new state to the next prompt; SRL’s state reward helps the student maintain continuity.

## 24. Relation to chain-of-thought imitation
- **Structured CoT**: Unlike free-form CoT, SRL enforces tagged reasoning; this reduces ambiguity and aligns better with AST tools.
- **Distillation vs RLHF**: SRL is lighter than RLHF because reward comes from teacher traces, not human preference models. The paper positions this as “supervision through structured rewards.”
- **Compression benefit**: By rewarding concise `<think>`, SRL can outperform plain CoT distillation in latency-sensitive settings.

## 25. Open research questions for this domain
- **Cross-language transfer**: How well do rewards learned on Python generalize to JS/Java? Worth ablation by withholding one language.
- **Action schema extension**: If ast-grep actions expand (e.g., add constraints), how sensitive is the reward to schema changes? Future-proof by versioning schemas.
- **Long-horizon tasks**: Paper focuses on single-step traces; multi-step AST-grab sequences may expose credit assignment limits. Investigate n-step returns or trace-level rewards.
- **Adversarial prompts**: Could the student exploit similarity metrics by injecting repeated tokens? Consider adversarial tests to harden the reward computation.

## 26. Replication-critical hyperparameters (from paper guidance)
- KL coefficient λ (sweep around 0.01–0.1).
- PPO clip range ε (paper uses 0.1–0.2; start with 0.2 for stability).
- Max `<think>` tokens (≈512) and overall generation cap (≈1k).
- Action/state/think reward weights (0.5 / 0.3 / 0.2).
- Malformed penalty (-0.2) and reward clipping range ([-0.2, 1.0]).
- Temperature ≈0.3 for teacher; top_p ≈0.9.

## 27. Metric definitions for reports
- **Trace parse rate**: % of model outputs with all tags valid.
- **Action fidelity**: Average \(R_\text{action}\) over dev set.
- **State faithfulness**: Average \(R_\text{state}\).
- **Think similarity**: Average \(R_\text{think}\) and average brevity penalty.
- **KL magnitude**: Mean KL per token vs base model.
- **Execution success**: % of tasks where ast-grep + tests succeed.
- **Token efficiency**: Avg tokens in `<think>` and `<state_update>`.

## 28. Narrative example (walkthrough)
1. Prompt includes prior state and user instruction.
2. Student generates:
   - `<think>`: explains choosing a pattern that matches a function call with missing argument.
   - `<action>`: JSON with pattern, replacement, and file scope.
   - `<state_update>`: notes constraint about preserving comments and a next focus on test updates.
3. Parser validates tags; sandbox applies action; tests pass.
4. Rewards: high \(R_\text{action}\) (fields match), solid \(R_\text{state}\) (constraints captured), positive \(R_\text{think}\) with small brevity penalty. KL modest.
5. PPO update uses advantage from these rewards; checkpoint improves action fidelity on similar tasks.

## 29. Why the paper argues SRL can replace SFT
- **Information density**: SRL rewards structural correctness rather than surface log-likelihood, capturing more signal per token.
- **Robustness**: By penalizing malformed tags and verbosity, SRL learns stricter formatting than SFT, reducing downstream parsing errors.
- **Generalization**: Paper reports SRL-trained models generalize better to unseen tasks with smaller token budgets because they internalize planner states rather than copying text.
- **Compute**: SRL avoids training a reward model and uses existing teacher traces; cheaper than RLHF and more targeted than SFT.

## 30. Threats to validity and mitigations
- **Mismatch between reward and true task success**: If action similarity is high but execution fails, rewards mislead. Mitigation: only reward steps whose teacher actions executed successfully.
- **Overfitting to teacher quirks**: Diversity in tasks and occasional paraphrasing of `<think>` help; KL anchor also resists drift toward overly specific teacher style.
- **Metric gaming**: Students might repeat teacher tokens to inflate similarity. Use brevity penalties and field-aware metrics to reduce string-copy gain.
- **Compute drift**: Hardware/driver differences can alter tokenization and decoding; pin versions and log environment hashes.

## 31. Future extensions
- **Online SRL**: Incorporate on-policy rollouts with the same reward to continue improving beyond offline traces.
- **Uncertainty-aware rewards**: Down-weight rewards when parser confidence is low or when action fields are ambiguous.
- **Curriculum**: Start with high-quality, short traces, then introduce harder multi-edit tasks as stability improves.
- **Ensembled teachers**: Mix outputs from multiple teacher checkpoints to broaden coverage while keeping temperature low.

## 32. Additional reading cues
- Review the paper’s appendix for exact KL coefficients and clipping thresholds used in stability studies; mirror those defaults when unsure.
- Check the reported variance of reward components to calibrate logging dashboards; match histogram bins to the paper for easier comparison.
- Revisit cited GRPO references to understand how advantage normalization interacts with KL penalties.
- Study prior trace-imitation work (e.g., stepwise CoT distillation) to borrow evaluation techniques for formatting accuracy.

## 33. Implementation tie-ins for future maintainers
- Keep tokenizer special-token definitions under version control; a mismatch between tokenizer and checkpoints will invalidate KL baselines.
- When changing the action schema, bump a dataset version tag so rewards can be recomputed consistently.
- Preserve raw teacher shards even after filtering; new reward weights may benefit from re-scoring the same trajectories.
- Document any deviations from the paper’s hyperparameters directly in `reports/training/stage2.md` so future experiments can interpret differences.
