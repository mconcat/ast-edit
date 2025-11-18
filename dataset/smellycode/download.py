#!/usr/bin/env python3
"""Download helper for the SmellyCodeDataset."""
from __future__ import annotations

import argparse
from pathlib import Path

from src.data.download_utils import (
    DownloadError,
    default_content_dir,
    download_http_resource,
    extract_archive,
    finalize_metadata,
)

DATASET_NAME = "SmellyCodeDataset"
ARCHIVE_URL = "https://github.com/HRI-EU/SmellyCodeDataset/archive/refs/heads/main.zip"
LICENSE = "GPL-3.0-only"
DEFAULT_VERSION = "github-main"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata-only", action="store_true")
    parser.add_argument("--archive-url", default=ARCHIVE_URL)
    parser.add_argument("--version", default=DEFAULT_VERSION)
    parser.add_argument("--num-records", type=int, default=None)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    dataset_dir = Path(__file__).resolve().parent
    content_dir = default_content_dir(dataset_dir)

    if args.metadata_only:
        print(f"[DRY-RUN] Would download {DATASET_NAME} archive from {args.archive_url}")
        print(f"Target directory: {content_dir}")
        return

    archive_path = dataset_dir / "smellycode_dataset.zip"
    try:
        download_http_resource(args.archive_url, archive_path)
        extract_archive(archive_path, content_dir)
    except DownloadError as exc:
        raise SystemExit(str(exc)) from exc

    meta_path = finalize_metadata(
        dataset_dir=dataset_dir,
        source=args.archive_url,
        version=args.version,
        license_str=LICENSE,
        artifact_dir=content_dir,
        num_records=args.num_records,
    )
    print(f"Saved metadata to {meta_path}")


if __name__ == "__main__":
    main()
