#!/usr/bin/env python3
"""Download helper for OCEDataFT."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT))

from src.data.download_utils import (  # noqa: E402
    DownloadError,
    default_content_dir,
    finalize_metadata,
    pull_from_huggingface,
)

DATASET_NAME = "OCEDataFT"
REPO_ID = "opencodeinterpreter/oce-edit-data"
DEFAULT_REVISION = "main"
SUBSET = "OCEDataFT"
LICENSE = "Apache-2.0"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", default=DEFAULT_REVISION)
    parser.add_argument("--subset", default=SUBSET)
    parser.add_argument("--metadata-only", action="store_true")
    parser.add_argument("--num-records", type=int, default=None)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    dataset_dir = Path(__file__).resolve().parent
    content_dir = default_content_dir(dataset_dir)

    if args.metadata_only:
        print(f"[DRY-RUN] Would download {DATASET_NAME} subset {args.subset} from {REPO_ID}")
        print(f"Target directory: {content_dir}")
        return

    try:
        snapshot_path = pull_from_huggingface(
            repo_id=REPO_ID,
            revision=args.revision,
            target_dir=content_dir,
            subset=args.subset,
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

