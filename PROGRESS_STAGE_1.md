# Week 1–2 Progress Report

## 0. Scope & Objectives
- ✅ Repository skeleton created with directories for data, scripts, src modules, datasets, and configs exactly as outlined in PLAN_STAGE_1.
- ✅ Dataset ingestion groundwork landed (metadata schema, download utilities, dataset READMEs) so we can start collecting structured trajectories once raw corpora are downloaded locally.
- ⏳ Remaining week-1 objectives include sandbox prototype, state manager stub, and vLLM actor configs.

## 1. Environment & Hardware
- ⚙️ Hardware assumptions unchanged; no infra automation yet. Still need to document concrete hostnames/IPs plus secrets bootstrap before deploying actors/teacher stack.

## 2. Repository Layout (Week 1–2 additions)
- ✅ Added `.gitignore` rules + `.gitkeep` placeholders to keep raw/processed data, logs, and dataset contents out of Git while preserving directory structure.
- ✅ Created `configs/datasets.yaml` plus `src/data/schemas.py` and `src/data/download_utils.py` to centralize metadata + download helpers.
- ✅ Stubbed ingestion & reporting scripts under `scripts/` to match the planned tree (logic will land once we have raw payloads).
- ⏳ Need to implement remaining src modules (`state/`, `sandbox/`, `actors/`, `teachers/`) and populate configs beyond dataset metadata.

## 3. Data Ingestion & Processing
### 3.1 Dataset Metadata Contract
- ✅ `DatasetMetadata` and `NormalizedRecord` pydantic models implemented; download scripts emit `_meta.json` using this contract.
- ✅ Introduced shared helper to emit metadata + stage archives under `dataset/<name>/content/`.
- ⚠️ Schema gap: CanItEdit ships executable tests per task, and CommitPackFT/EditPackFT expose repo/commit provenance. Recommend extending `NormalizedRecord` with an optional `metadata: Dict[str, Any]` (or dedicated `tests` / `provenance` fields) so we do not lose structured evaluation assets; currently this info only survives as free-form tags.

### 3.2 Ingestion Steps (per dataset)
- ✅ Auth-agnostic download scripts for CommitPackFT, OCEDataFT, EditPackFT, AgentPack, MaRV, SmellyCodeDataset, and CanItEdit following the `dataset/<name>/download.py` convention (use Hugging Face snapshot_download or HTTP streaming as appropriate).
- ⏳ Actual downloads + SHA validation blocked until we can hit upstream endpoints (intentionally deferred per instructions).
- ⏳ Normalization scripts currently stubbed (`raise NotImplementedError`); need raw payloads to implement diff reconstruction, deduplication, and language filtering.

### 3.3 Synthetic ast-grep Rule Generation
- ⏳ Placeholder `scripts/synth_astgrep_rules.py` exists; still need to implement rule templates + sample generation logic.

### 3.4 Data Versioning & Governance
- ⏳ DVC wiring + ingestion manifest pending (requires actual data artifacts).

## 4. Sandbox Runner
- ⏳ No implementation yet; `src/sandbox/runner.py` still needs to be created per spec.

## 5. Structured State Manager
- ⏳ Not started; no `src/state/manager.py` scaffold yet.

## 6. Actor Infrastructure (vLLM + sandbox)
- ⏳ Unimplemented; need configs + actor loop code plus observability wiring.

## 7. Trajectory Store
- ⏳ Trajectory schema only described in PLAN; code + storage layout still pending.

## 8. SRL Teacher PoC
- ⏳ Pending teacher prompt config + orchestration code; no progress yet.

## 9. Security & Compliance Checklist
- ⏳ Outstanding items: sandbox jailer decision, license manifest automation, secrets management doc.

## 10. Week-1/Week-2 Timeline
- Week 1 deliverables partially met (dataset scaffolding). Sandbox/state/actors/teacher tasks roll over to remaining Week‑1 bandwidth.

## 11. Open Questions / Clarifications Needed
1. Confirm whether extending `NormalizedRecord` with structured `metadata` (tests, repo SHA, smell_type) is acceptable so downstream consumers can access evaluation-specific assets without parsing `tags`.
2. Need confirmation on preferred tool (DVC vs. git-annex) for local-only artifact tracking before wiring ingestion scripts to call it automatically.
