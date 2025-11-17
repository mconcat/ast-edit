#!/usr/bin/env python3
"""Download helper for CommitPackFT."""
from __future__ import annotations

import argparse
from pathlib import Path

from src.data.download_utils import (
    DownloadError,
    default_content_dir,
    finalize_metadata,
    pull_from_huggingface,
)

DATASET_NAME = "CommitPackFT"
REPO_ID = "bigcode/commitpackft"
DEFAULT_REVISION = "main"
SUBSET = "filtered"
LICENSE = "BigCode-OpenRAIL-M"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", default=DEFAULT_REVISION)
    parser.add_argument("--subset", default=SUBSET)
    parser.add_argument("--metadata-only", action="store_true", help="Print expected actions without downloading")
    parser.add_argument("--num-records", type=int, default=None, help="Override num_records metadata if known")
    parser.add_argument(
        "--allow-pattern",
        action="append",
        help="Optional glob(s) passed to huggingface_hub to limit downloaded files",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    dataset_dir = Path(__file__).resolve().parent
    content_dir = default_content_dir(dataset_dir)

    if args.metadata_only:
        print(
            f"[DRY-RUN] Would download {DATASET_NAME} from {REPO_ID} (revision={args.revision}, subset={args.subset})"
        )
        print(f"Target directory: {content_dir}")
        return

    try:
        snapshot_path = pull_from_huggingface(
            repo_id=REPO_ID,
            revision=args.revision,
            target_dir=content_dir,
            subset=args.subset,
            allow_patterns=args.allow_pattern,
        )
    except DownloadError as exc:
        raise SystemExit(str(exc)) from exc

    meta_path = finalize_metadata(
        dataset_dir=dataset_dir,
        source=f"{REPO_ID}:{args.subset}",
        version=args.revision,
        license_str=LICENSE,
        artifact_dir=snapshot_path,
        num_records=args.num_records,
    )
    print(f"Saved metadata to {meta_path}")


if __name__ == "__main__":
    main()

