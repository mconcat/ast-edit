"""Download all configured datasets sequentially.

This module looks at ``configs/datasets.yaml`` to determine which datasets
are available, then invokes each dataset's ``download.py`` module:

    python -m dataset.<name>.download

Use ``--metadata-only`` to run them in dry-run / metadata mode.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from typing import Mapping, Optional

import yaml

from src.data.schemas import repo_root


def _datasets_config() -> Mapping[str, Mapping[str, object]]:
    cfg_path = repo_root() / "configs" / "datasets.yaml"
    if not cfg_path.exists():
        return {}
    data = yaml.safe_load(cfg_path.read_text()) or {}
    if not isinstance(data, dict):
        return {}
    return data


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m src.dataset.download_all",
        description="Download all datasets listed in configs/datasets.yaml.",
    )
    parser.add_argument(
        "--metadata-only",
        action="store_true",
        help="Pass --metadata-only to each dataset downloader (dry-run/metadata mode).",
    )
    args = parser.parse_args(argv)

    cfg = _datasets_config()
    if not cfg:
        raise SystemExit("No datasets found in configs/datasets.yaml")

    for name in sorted(cfg.keys()):
        module = f"dataset.{name}.download"
        cmd = [sys.executable, "-m", module]
        if args.metadata_only:
            cmd.append("--metadata-only")

        print(f"==> [{name}] running: {' '.join(cmd)}")
        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as exc:
            print(
                f"[ERROR] Dataset {name!r} failed with exit code {exc.returncode}",
                file=sys.stderr,
            )


if __name__ == "__main__":
    main()

