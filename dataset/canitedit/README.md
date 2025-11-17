# CanItEdit Benchmark

- **Upstream source:** `opencodeinterpreter/canitedit` on Hugging Face; derived from the 105 Python program suite.
- **License:** Apache-2.0 (mirrors OpenAI's original benchmark terms).
- **Languages:** Python-only (each task ships reference tests + oracle patch).
- **Usage:** Held-out evaluation benchmark; do **not** train on this set.

## Upstream Schema
Each benchmark entry contains structured metadata:

| Field | Type | Description |
| --- | --- | --- |
| `task_id` | `str` | Stable identifier used by previous papers. |
| `prompt` | `str` | Description of the desired change. |
| `starter_code` | `str` | The initial buggy implementation. |
| `tests` | `List[str]` | Pytest snippets executed for evaluation. |
| `reference_patch` | `str` | Canonical patch/diff. |
| `language` | `str` | Always `python`. |

## Mapping to Project Schema
We treat each benchmark as a single-step editing task:

| Project Field | Source | Notes |
| --- | --- | --- |
| `instruction` | `prompt` | Append `task_id` to make evaluation deterministic. |
| `pre` | `starter_code` | Provided as-is. |
| `post` | Apply `reference_patch` | When constructing evaluation, we keep `post` for reward computation only. |
| `language` | `language` | Always `python`. |
| `tags` | `["canitedit", task_id]` | Allows grouping results per benchmark. |

