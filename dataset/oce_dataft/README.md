# OpenCodeEdit / OCEDataFT

- **Upstream source:** `opencodeinterpreter/oce-edit-data` on Hugging Face (subset `OCEDataFT`).
- **License:** Apache-2.0 (declared by maintainers).
- **Languages:** Python (75%), JavaScript/TypeScript, Java, C++ snippets curated from IDE traces.
- **Usage:** High-quality triplets for supervised fine-tuning (SFT) and RL prompt bootstrapping.

## Upstream Schema
The dataset is already normalized into instruction-edit triplets:

| Field | Type | Description |
| --- | --- | --- |
| `instruction` | `str` | Natural language instruction or user prompt. |
| `pre` | `str` | Pre-edit code snippet. |
| `post` | `str` | Post-edit code snippet. |
| `language` | `str` | ISO-ish language string. |
| `metadata.tags` | `List[str]` | Optional quality tags (`human`, `agent`, `tests_passed`). |

## Mapping to Project Schema
Because the schema matches our `NormalizedRecord`, ingestion is a straight rename:

| Project Field | Source |
| --- | --- |
| `instruction` | `instruction` |
| `pre` | `pre` |
| `post` | `post` |
| `language` | `language` (lower-cased + remapped) |
| `tags` | `metadata.tags + ["oce_dataft"]` |

`download.py` hydrates `dataset/oce_dataft/content/` via Hugging Face `snapshot_download` (filtering to the `OCEDataFT` folder), then records `_meta.json`.

