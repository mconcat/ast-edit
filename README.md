# ast-edit

Infrastructure for normalizing multi-source code-edit datasets plus scaffolding for sandbox/state/actor/teacher components referenced in `PLAN_STAGE_1.md`.

## Repository layout

- `dataset/<name>/download.py` – dataset-specific download entrypoints
- `configs/datasets.yaml` – curated metadata for every upstream corpus we plan to ingest
- `src/data` – shared schemas and download utilities
- `scripts/` – orchestration / reporting helpers
- `reports/` – generated dataset notes and checkpoints

## Running dataset downloaders

All dataset helpers live inside Python packages under `dataset/`. Execute them as modules so imports stay isolated from `sys.path` hacks:

```bash
python -m dataset.commitpackft.download --help
python -m dataset.agentpack.download
```

Each downloader stages files under `dataset/<name>/content/` and writes `_meta.json` describing provenance and checksums.

## Secrets & credentials

Some download scripts require authenticated access (e.g., private Hugging Face mirrors). Provide credentials via environment variables or an untracked `.env.local` file at the repo root:

```bash
HF_TOKEN=hf_xxx
CUSTOM_S3_ENDPOINT=https://...
```

Load them before running scripts:

```bash
set -a
. ./.env.local
set +a
```

Never commit real credentials. `.env*` patterns are already ignored in `.gitignore`, and long-lived tokens should be stored in your password manager. For CI usage, rely on your provider's secret store rather than plaintext files.
