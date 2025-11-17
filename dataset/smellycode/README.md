# SmellyCodeDataset

- **Upstream source:** `smellycode/SmellyCodeDataset` GitHub release mirrored to Hugging Face.
- **License:** GNU GPLv3 (original research release). Keep dataset local only.
- **Languages:** Java, Python, JavaScript, C++ snippets annotated with smell types (Long Method, Feature Envy, etc.).
- **Usage:** Smell classification + refactor suggestions.

## Upstream Schema
Each entry is stored in CSV/JSONL format depending on language split:

| Field | Type | Description |
| --- | --- | --- |
| `id` | `str` | Unique sample identifier. |
| `language` | `str` | Programming language. |
| `smell_type` | `str` | Taxonomy label (e.g., `LongMethod`). |
| `smelly_code` | `str` | Code snippet before refactor. |
| `clean_code` | `str` | Suggested refactoring / smell-free version. |
| `notes` | `str` | Optional textual description or heuristics. |

## Mapping to Project Schema

| Project Field | Source | Notes |
| --- | --- | --- |
| `instruction` | Template `"Remove <smell_type> smell"` optionally plus `notes`. |
| `pre` | `smelly_code` |
| `post` | `clean_code` |
| `language` | `language` (normalized) |
| `tags` | `["smellycode", smell_type]` |

