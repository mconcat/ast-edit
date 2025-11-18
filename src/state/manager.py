from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List

from src.data.schemas import repo_root


@dataclass
class State:
    goals: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    decisions: List[str] = field(default_factory=list)
    hypotheses: List[str] = field(default_factory=list)
    history: List[str] = field(default_factory=list)
    open_issues: List[str] = field(default_factory=list)
    next_focus: str = ""


_MAX_HISTORY_ITEMS = 3
_MAX_TEXT_LEN = 256


def _db_path() -> Path:
    root = repo_root()
    db_dir = root / "data"
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / "state.sqlite3"


def _get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.execute(
        "CREATE TABLE IF NOT EXISTS state ("
        " task_id TEXT PRIMARY KEY,"
        " blob TEXT NOT NULL"
        ")"
    )
    return conn


def _truncate_text(value: str) -> str:
    if len(value) <= _MAX_TEXT_LEN:
        return value
    return value[:_MAX_TEXT_LEN]


def _apply_caps(state: State) -> State:
    def trim_list(values: List[str]) -> List[str]:
        return [_truncate_text(v) for v in values]

    # History is capped in length as well as text.
    history_trimmed = trim_list(state.history)
    if len(history_trimmed) > _MAX_HISTORY_ITEMS:
        history_trimmed = history_trimmed[-_MAX_HISTORY_ITEMS:]

    return State(
        goals=trim_list(state.goals),
        constraints=trim_list(state.constraints),
        decisions=trim_list(state.decisions),
        hypotheses=trim_list(state.hypotheses),
        history=history_trimmed,
        open_issues=trim_list(state.open_issues),
        next_focus=_truncate_text(state.next_focus),
    )


def load(task_id: str) -> State:
    """Load state for a task_id, or return a default empty State."""
    with _get_connection() as conn:
        cur = conn.execute("SELECT blob FROM state WHERE task_id = ?", (task_id,))
        row = cur.fetchone()
    if row is None:
        return State()
    payload = json.loads(row[0])
    return State(
        goals=list(payload.get("goals", [])),
        constraints=list(payload.get("constraints", [])),
        decisions=list(payload.get("decisions", [])),
        hypotheses=list(payload.get("hypotheses", [])),
        history=list(payload.get("history", [])),
        open_issues=list(payload.get("open_issues", [])),
        next_focus=str(payload.get("next_focus", "")),
    )


def save(task_id: str, state: State) -> None:
    """Persist state for a task_id, applying caps before writing."""
    capped = _apply_caps(state)
    blob = json.dumps(asdict(capped), ensure_ascii=False)
    with _get_connection() as conn:
        conn.execute(
            "INSERT INTO state(task_id, blob) VALUES (?, ?)"
            " ON CONFLICT(task_id) DO UPDATE SET blob=excluded.blob",
            (task_id, blob),
        )
        conn.commit()


def merge(existing: State, update: State) -> State:
    """Merge two states, extending list fields and overriding next_focus.

    List fields are concatenated; caps are applied when saving or can be
    applied explicitly via _apply_caps if needed.
    """
    merged = State(
        goals=existing.goals + update.goals,
        constraints=existing.constraints + update.constraints,
        decisions=existing.decisions + update.decisions,
        hypotheses=existing.hypotheses + update.hypotheses,
        history=existing.history + update.history,
        open_issues=existing.open_issues + update.open_issues,
        next_focus=update.next_focus or existing.next_focus,
    )
    return _apply_caps(merged)


def render(state: State) -> str:
    """Render state as a compact, human-readable block for prompts."""
    parts = []
    if state.goals:
        parts.append("Goals:\n" + "\n".join(f"- {g}" for g in state.goals))
    if state.constraints:
        parts.append("Constraints:\n" + "\n".join(f"- {c}" for c in state.constraints))
    if state.decisions:
        parts.append("Decisions:\n" + "\n".join(f"- {d}" for d in state.decisions))
    if state.hypotheses:
        parts.append("Hypotheses:\n" + "\n".join(f"- {h}" for h in state.hypotheses))
    if state.history:
        parts.append("History:\n" + "\n".join(f"- {h}" for h in state.history))
    if state.open_issues:
        parts.append("Open issues:\n" + "\n".join(f"- {i}" for i in state.open_issues))
    if state.next_focus:
        parts.append("Next focus:\n" + state.next_focus)
    return "\n\n".join(parts).strip()


def _cli_dump(task_id: str) -> None:
    state = load(task_id)
    print(render(state))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m src.state.manager")
    subparsers = parser.add_subparsers(dest="command", required=True)

    dump_parser = subparsers.add_parser("dump", help="Dump state for a task_id")
    dump_parser.add_argument("task_id")

    args = parser.parse_args(argv)
    if args.command == "dump":
        _cli_dump(args.task_id)


if __name__ == "__main__":
    main()

