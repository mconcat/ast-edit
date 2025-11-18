"""Run dataset downloaders on a small sample of files.

This script constructs the same command that the dataset-specific
``dataset/<name>/download.py`` modules would run, but adds ``--allow-pattern``
filters so that only a small subset of files is downloaded.

By default it runs in dry-run mode and prints the command instead of
executing it; pass ``--execute`` to actually perform the download.
"""
from __future__ import annotations

import argparse
import sys
import subprocess
from pathlib import Path
from typing import List, Mapping, Optional

import yaml

from src.data.schemas import repo_root


def _datasets_config() -> Mapping[str, object]:
    cfg_path = repo_root() / "configs" / "datasets.yaml"
    if not cfg_path.exists():
        return {}
    data = yaml.safe_load(cfg_path.read_text()) or {}
    if not isinstance(data, dict):
        return {}
    return data


def _default_patterns() -> List[str]:
    # Heuristic patterns that keep downloads small on common HF datasets.
    return [
        "**/data-00000*",
        "**/train-00000*",
    ]


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.download_dataset_sample",
        description="Run a dataset download module on a small subset of files.",
    )
    parser.add_argument(
        "dataset_name",
        help="Dataset key, e.g. commitpackft, agentpack.",
    )
    parser.add_argument(
        "--pattern",
        action="append",
        dest="patterns",
        help="Glob pattern passed as --allow-pattern to the dataset downloader. "
             "Can be specified multiple times. Defaults to a small set of heuristic patterns.",
    )
    parser.add_argument(
        "--metadata-only",
        action="store_true",
        help="Pass --metadata-only to the dataset downloader (no download, just a dry-run).",
    )
    parser.add_argument(
        "--subset",
        default=None,
        help=(
            "Override the subset argument passed to the dataset downloader. "
            "For datasets that default to a subset (e.g. 'filtered') you can "
            "pass an empty string \"\" to disable subset selection."
        ),
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually run the downloader instead of printing the command.",
    )
    args = parser.parse_args(argv)

    datasets_cfg = _datasets_config()
    if args.dataset_name not in datasets_cfg:
        raise SystemExit(
            f"Unknown dataset {args.dataset_name!r}. "
            "Check configs/datasets.yaml for available keys."
        )

    module = f"dataset.{args.dataset_name}.download"
    patterns = args.patterns or _default_patterns()

    cmd: List[str] = [sys.executable, "-m", module]
    for pat in patterns:
        cmd.extend(["--allow-pattern", pat])
    if args.metadata_only:
        cmd.append("--metadata-only")
    if args.subset is not None:
        cmd.extend(["--subset", args.subset])

    if not args.execute:
        print("[DRY-RUN] Sample download command:")
        print(" ", " ".join(cmd))
        return

    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
