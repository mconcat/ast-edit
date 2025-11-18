# State subsystem

This package holds the structured, persistent state used by actors and teachers to track goals, history, and next focus for each task.

## Files

- `manager.py` – state persistence and rendering:
  - `State` dataclass with fields: `goals`, `constraints`, `decisions`, `hypotheses`, `history`, `open_issues`, `next_focus`.
  - `load(task_id) -> State`: loads state from a SQLite database or returns an empty `State` if none exists.
  - `save(task_id, state)`: persists state as a JSON blob, applying caps before writing.
  - `merge(existing, update) -> State`: concatenates list fields from two states and overrides `next_focus` when provided, then enforces caps.
  - `render(state) -> str`: converts a `State` into a compact, human‑readable block suitable for prompt injection.
  - CLI entrypoint: `python -m src.state.manager dump <task_id>` prints the rendered state to stdout.

## Architecture

- **Storage**:
  - A single SQLite database lives at `data/state.sqlite3`, created on demand.
  - The schema is intentionally simple: a `state` table with `task_id TEXT PRIMARY KEY` and `blob TEXT NOT NULL`, where `blob` is JSON produced from the `State` dataclass.
  - `_db_path()` derives the DB location from `repo_root()`, ensuring the path is stable regardless of current working directory.

- **Caps and normalization**:
  - `_MAX_HISTORY_ITEMS` (3) limits how many recent history entries are kept; older entries are discarded when the history list grows.
  - `_MAX_TEXT_LEN` (256) truncates all string fields (including history entries and `next_focus`) to bound prompt size.
  - `_apply_caps` applies both the text truncation and history‑length limit, and is used by both `save` and `merge`.

- **Merge semantics**:
  - `merge` treats state updates as deltas:
    - List fields (`goals`, `constraints`, `decisions`, `hypotheses`, `history`, `open_issues`) are concatenated.
    - `next_focus` prefers the update’s value if it is non‑empty, otherwise keeps the existing value.
  - The result is passed through `_apply_caps` so caps are always respected even if an update attempts to add many entries or long text.

- **Prompt rendering**:
  - `render` produces a stable, sectioned text format:
    - Optional sections like `Goals:`, `Constraints:`, `History:`, etc., only appear when they have content.
    - Each list field is shown as `- item` lines under its section; `next_focus` is appended as its own block.
  - Actors use this rendering to embed the current state into prompts via a `<state>...</state>` block.

The state subsystem is designed to be small, deterministic, and easily testable while providing enough structure and caps to keep prompts within budget and the actor’s reasoning consistent across steps.

