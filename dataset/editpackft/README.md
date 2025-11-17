# EditPackFT

- **Upstream source:** `opencodeinterpreter/editpackft` (Hugging Face, mirrored from CommitPackFT filters).
- **License:** Same as CommitPackFT (BigCode OpenRAIL-M) plus derivative notice from EditPack authors.
- **Languages:** Dominantly Python, but includes JavaScript/TypeScript, Java.
- **Usage:** Acts as curated subset for high-precision SFT/RL loops.

## Upstream Schema
The dataset extends CommitPackFT with additional annotations:

| Field | Type | Description |
| --- | --- | --- |
| `instruction` | `str` | High-quality prompt describing the edit. |
| `pre` | `str` | Pre-edit snippet. |
| `post` | `str` | Post-edit snippet. |
| `language` | `str` | Normalized language label. |
| `source_commit.repo` | `str` | Original repo (useful for deduping). |
| `source_commit.sha` | `str` | Original commit hash. |
| `quality_flags` | `List[str]` | Tags such as `tests_passed`, `lint_clean`. |

## Mapping to Project Schema
Already matches the `NormalizedRecord`. We simply append provenance tags:

| Project Field | Source |
| --- | --- |
| `instruction` | `instruction` |
| `pre` | `pre` |
| `post` | `post` |
| `language` | `language` |
| `tags` | `quality_flags + ["editpackft", source_commit.repo]` |

