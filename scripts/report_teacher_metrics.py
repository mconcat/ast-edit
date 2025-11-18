"""Compute simple metrics over teacher-labeled trajectories.

This script scans JSONL files under ``trajectories/raw/`` and writes a small
Markdown report to ``reports/teacher/metrics.md`` (paths are derived from
``repo_root()`` by default).
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from src.data.schemas import repo_root


@dataclass
class ModelStats:
    steps: int = 0
    reward_sum: float = 0.0
    reward_count: int = 0
    verified: int = 0


def _trajectories_root(override: Optional[str] = None) -> Path:
    if override:
        return Path(override)
    return repo_root() / "trajectories" / "raw"


def _output_path(override: Optional[str] = None) -> Path:
    root = repo_root()
    if override:
        out = Path(override)
        if not out.is_absolute():
            out = root / out
        return out
    return root / "reports" / "teacher" / "metrics.md"


def _scan_trajectories(root: Path) -> Dict[str, ModelStats]:
    stats: Dict[str, ModelStats] = {}
    if not root.exists():
        return stats

    for path in sorted(root.glob("*.jsonl")):
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue

                teacher = record.get("teacher") or {}
                model_name = teacher.get("model") or "unknown"
                reward = record.get("reward")
                # Only count steps with an explicit numeric reward.
                if reward is None:
                    continue
                try:
                    reward_val = float(reward)
                except (TypeError, ValueError):
                    continue

                model_stats = stats.get(model_name)
                if model_stats is None:
                    model_stats = ModelStats()
                    stats[model_name] = model_stats

                model_stats.steps += 1
                model_stats.reward_sum += reward_val
                model_stats.reward_count += 1
                if reward_val > 0:
                    model_stats.verified += 1

    return stats


def _write_markdown(path: Path, stats: Dict[str, ModelStats]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Teacher Metrics", ""]

    if not stats:
        lines.append("No teacher-labeled trajectories with rewards were found.")
        path.write_text("\n".join(lines), encoding="utf-8")
        return

    total_steps = sum(m.steps for m in stats.values())
    total_verified = sum(m.verified for m in stats.values())

    lines.append(f"Total teacher-labeled steps: **{total_steps}**")
    lines.append(f"Total verified steps (reward > 0): **{total_verified}**")
    lines.append("")
    lines.append("## Per-model metrics")
    lines.append("")
    lines.append("| Model | Steps | Verified | Precision | Avg reward |")
    lines.append("|-------|-------|----------|-----------|------------|")

    for model_name in sorted(stats.keys()):
        m = stats[model_name]
        if m.reward_count > 0:
            precision = m.verified / m.reward_count
            avg_reward = m.reward_sum / m.reward_count
        else:
            precision = 0.0
            avg_reward = 0.0
        lines.append(
            f"| {model_name} | {m.steps} | {m.verified} | "
            f"{precision:.3f} | {avg_reward:.3f} |"
        )

    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.report_teacher_metrics",
        description="Compute simple metrics from teacher-labeled trajectories.",
    )
    parser.add_argument(
        "--traj-root",
        default=None,
        help="Override path to trajectories/raw directory (default: repo_root()/trajectories/raw).",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Override output path for metrics markdown (default: reports/teacher/metrics.md).",
    )
    args = parser.parse_args(argv)

    traj_root = _trajectories_root(args.traj_root)
    output_path = _output_path(args.output)

    stats = _scan_trajectories(traj_root)
    _write_markdown(output_path, stats)


if __name__ == "__main__":
    main()

