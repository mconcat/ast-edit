"""Manage per-machine dataset storage via symlinks.

This tool reads a YAML config (not committed to git) that maps dataset names
to absolute or base-relative storage locations (e.g. on a large HDD), and
creates ``dataset/<name>/content`` symlinks pointing at those locations.

Example YAML (store as ``configs/dataset_storage.local.yaml`` and gitignore it):

    base_dir: /mnt/18tb/ast-edit-datasets
    datasets:
      commitpackft: commitpackft
      agentpack: agentpack

On each machine you can point ``base_dir`` at a different disk while keeping
the repository structure unchanged.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Dict, Mapping, Optional

import yaml

from src.data.schemas import repo_root


DEFAULT_CONFIG_NAME = "dataset_storage.local.yaml"


def _load_config(path: Path) -> Mapping[str, object]:
    if not path.exists():
        raise SystemExit(
            f"Config file not found: {path}. Create a YAML file describing dataset storage mappings."
        )
    data = yaml.safe_load(path.read_text()) or {}
    if not isinstance(data, dict):
        raise SystemExit(f"Expected a mapping at root of {path}, got {type(data).__name__}")
    return data


def _resolve_target(base_dir: Optional[Path], value: object) -> Path:
    if isinstance(value, str):
        target = Path(value)
    else:
        raise SystemExit(f"Dataset mapping must be a string path; got {value!r}")
    if not target.is_absolute():
        if base_dir is None:
            raise SystemExit(f"Relative dataset path {target} requires a base_dir in the config")
        target = base_dir / target
    return target


def _ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _create_symlink(link_path: Path, target: Path, *, dry_run: bool = False) -> None:
    if link_path.is_symlink():
        current = Path(os.readlink(link_path))
        if current == target:
            return
        if dry_run:
            print(f"[DRY-RUN] Would update symlink {link_path} -> {target} (was {current})")
            return
        print(f"Updating symlink {link_path} -> {target} (was {current})")
        link_path.unlink()
    elif link_path.exists():
        # Do not remove real directories or files automatically.
        raise SystemExit(f"{link_path} exists and is not a symlink; remove or rename it and re-run.")
    else:
        if dry_run:
            print(f"[DRY-RUN] Would create symlink {link_path} -> {target}")
            return
        print(f"Creating symlink {link_path} -> {target}")

    if not dry_run:
        _ensure_parent_dir(link_path)
        target.mkdir(parents=True, exist_ok=True)
        link_path.symlink_to(target, target_is_directory=True)


def _apply_mappings(mapping: Mapping[str, object], *, dry_run: bool = False) -> None:
    root = repo_root()
    dataset_root = root / "dataset"

    base_dir = mapping.get("base_dir")
    base_dir_path: Optional[Path]
    if base_dir is None:
        base_dir_path = None
    elif isinstance(base_dir, str):
        base_dir_path = Path(base_dir)
        if not base_dir_path.is_absolute():
            base_dir_path = root / base_dir_path
    else:
        raise SystemExit("base_dir must be a string path if provided")

    datasets = mapping.get("datasets") or {}
    if not isinstance(datasets, dict):
        raise SystemExit("`datasets` must be a mapping of dataset name -> path")

    for name, value in datasets.items():
        if not isinstance(name, str):
            raise SystemExit(f"Dataset key must be a string, got {name!r}")
        dataset_dir = dataset_root / name
        if not dataset_dir.exists():
            print(f"Skipping unknown dataset {name!r} (directory {dataset_dir} not found)")
            continue
        target = _resolve_target(base_dir_path, value)
        link_path = dataset_dir / "content"
        _create_symlink(link_path, target, dry_run=dry_run)


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.manage_dataset_storage",
        description="Create per-dataset content symlinks based on a YAML config.",
    )
    parser.add_argument(
        "--config",
        default=None,
        help=f"Path to YAML config (default: configs/{DEFAULT_CONFIG_NAME})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned changes without creating or updating symlinks.",
    )
    args = parser.parse_args(argv)

    cfg_path = Path(args.config) if args.config else repo_root() / "configs" / DEFAULT_CONFIG_NAME
    mapping = _load_config(cfg_path)
    _apply_mappings(mapping, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
