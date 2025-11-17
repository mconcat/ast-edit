# MaRV (Massive Refactoring of Variables)

- **Upstream source:** `amazon-science/marv` on Hugging Face (mirrors the MaRV GitHub release).
- **License:** Apache-2.0.
- **Languages:** Java only (693 curated refactor examples).
- **Usage:** Great for structural refactoring tasks (rename/move/inline) and evaluation of AST-heavy edits.

## Upstream Schema
MaRV ships as JSON objects with explicit refactor descriptions:

| Field | Type | Description |
| --- | --- | --- |
| `id` | `str` | Stable identifier. |
| `before` | `str` | Pre-refactor code. |
| `after` | `str` | Post-refactor code. |
| `refactor_type` | `str` | One of `rename_field`, `rename_method`, `rename_variable`, `extract_constant`. |
| `project` | `str` | Original project slug. |
| `context` | `str` | Additional commentary/instruction. |

## Mapping to Project Schema

| Project Field | Source | Notes |
| --- | --- | --- |
| `instruction` | `context` + `refactor_type` | Compose as `"Apply <refactor_type>: <context>"`. |
| `pre` | `before` | | 
| `post` | `after` | | 
| `language` | Fixed to `java` | | 
| `tags` | `["marv", refactor_type, project]` | |

