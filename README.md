# ast-edit

Infrastructure for normalizing multi-source code-edit datasets plus scaffolding for sandbox/state/actor/teacher components referenced in `PLAN_STAGE_1.md`.

## Repository layout

- `dataset/<name>/download.py` – dataset-specific download entrypoints
- `configs/` – dataset catalog, sandbox/actors/teacher configs, local dataset storage mappings
- `configs/datasets.yaml` – curated metadata for every upstream corpus we plan to ingest
- `src/data` – shared schemas and download utilities
- `scripts/` – orchestration / reporting helpers
- `reports/` – generated dataset notes and checkpoints

## Setup (with uv)

This repo assumes Python 3.10+ and uses a `src/` layout. The easiest way to set up a local environment is with [`uv`](https://github.com/astral-sh/uv):

```bash
cd /path/to/ast-edit

# 1) Create a virtual environment
uv venv

# 2) Activate it (bash/zsh)
source .venv/bin/activate

# 3) Install runtime and dev dependencies
uv pip install -e ".[dev]"

# 4) Run tests to sanity-check the setup
pytest -q
```

After this, commands like `pytest` and the `python -m ...` entrypoints below should work as-is.

## Running dataset downloaders

All dataset helpers live inside Python packages under `dataset/`. Execute them as modules so imports stay isolated from `sys.path` hacks:

```bash
python -m dataset.commitpackft.download --help
python -m dataset.agentpack.download
```

Each downloader stages files under `dataset/<name>/content/` and writes `_meta.json` describing provenance and checksums.

### Using external storage (e.g., 18TB HDD)

To keep large corpora off the main disk, you can manage dataset storage locations via a local YAML config and symlinks:

1. Create `configs/dataset_storage.local.yaml` (this file is gitignored), for example:

   ```yaml
   base_dir: /mnt/18tb/ast-edit-datasets
   datasets:
     commitpackft: commitpackft
     agentpack: agentpack
   ```

2. Generate/update the `dataset/<name>/content` symlinks:

   ```bash
   python -m scripts.manage_dataset_storage
   ```

## Stage 1: end-to-end setup checklist

To finalize Stage 1 on a new machine, run the following (from the repo root):

1. **Create and activate the venv**

   ```bash
   uv venv
   source .venv/bin/activate
   uv pip install -e ".[dev]"
   pytest -q
   ```

2. **Configure Hugging Face auth (for gated/hosted datasets)**

   ```bash
   cat > .env.local << 'EOF'
   HF_TOKEN=hf_xxx_your_token_here
   EOF

   set -a
   . ./.env.local
   set +a
   ```

3. **Point datasets at the large HDD**

   ```bash
   # Ensure configs/dataset_storage.local.yaml points at your HDD,
   # e.g. base_dir: /mnt/seagate_18tb/ast-edit-dataset
   python -m scripts.manage_dataset_storage
   ```

4. **Dry-run dataset downloads**

   ```bash
   python -m src.dataset.download_all --metadata-only
   ```

5. **Run full downloads (as needed)**

   ```bash
   # All datasets sequentially
   python -m src.dataset.download_all

   # Or one-by-one
   python -m dataset.commitpackft.download
   python -m dataset.editpackft.download
   python -m dataset.canitedit.download
   python -m dataset.agentpack.download
   python -m dataset.smellycode.download
   ```

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
