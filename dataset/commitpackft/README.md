# CommitPackFT

- **Upstream source:** [bigcode/commitpackft](https://huggingface.co/datasets/bigcode/commitpackft)
- **License:** BigCode OpenRAIL-M
- **Languages:** Python, JavaScript/TypeScript, Java, Go, Rust, C/C++, plus long-tail languages.
- **Recommended split:** Keep CommitPackFT for large-scale SFT/RL, but filter for repositories that align with ast-grep-supported ecosystems.

## Upstream Schema
Each record in the filtered Hugging Face export contains:

| Field | Type | Description |
| --- | --- | --- |
| `repo` | `str` | Fully-qualified GitHub repository name. |
| `sha` | `str` | Commit hash used to pull diffs. |
| `message` | `str` | Human authored commit message / intent. |
| `files` | `List[object]` | File-level metadata. |
| `files[].path` | `str` | File path relative to repo root. |
| `files[].language` | `str` | Detected language (guesslang + tree-sitter). |
| `files[].diff` | `str` | Unified diff showing the edit. |

## Mapping to Project Schema
We normalize CommitPackFT into `{instruction, pre, post, language, tags}` as follows:

| Project Field | Source | Notes |
| --- | --- | --- |
| `instruction` | `message` | Commit message already summarizes the intent; optionally add repo name for additional context. |
| `pre` | `files[].diff` (minus additions) | Use `unidiff` to reconstruct original snippet per file and concatenate when multiple files participate. |
| `post` | `files[].diff` (applied patch) | Apply patch to the `pre` snippet or reconstruct by applying the diff. |
| `language` | `files[].language` | Collapse `c++`, `c` into canonical values (see `NormalizedRecord`). |
| `tags` | `["commitpackft", repo, language, diff_stats]` | Attach dataset name, repo slug, and heuristics such as `small_patch`. |

`download.py` stores the raw Hugging Face snapshot under `dataset/commitpackft/content/` and emits `_meta.json` with the required contract.

