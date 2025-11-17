"""Utility helpers shared by dataset download scripts."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tarfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional
from urllib import request

try:
    from huggingface_hub import snapshot_download
except ImportError:  # pragma: no cover - optional dependency
    snapshot_download = None  # type: ignore

from pydantic import ValidationError

from .schemas import DatasetMetadata, repo_root


class DownloadError(RuntimeError):
    """Raised when a dataset could not be downloaded."""


CHUNK_SIZE = 1024 * 1024


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def timestamp() -> datetime:
    return datetime.now(timezone.utc)


def compute_file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compute_directory_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    for child in sorted(p for p in path.rglob("*") if p.is_file() and not p.name.startswith(".")):
        digest.update(str(child.relative_to(path)).encode())
        digest.update(compute_file_sha256(child).encode())
    return digest.hexdigest()


def write_metadata(meta: DatasetMetadata, target: Path) -> None:
    try:
        payload = meta.dict()
    except ValidationError as exc:  # pragma: no cover - defensive
        raise DownloadError(f"Invalid metadata: {exc}") from exc
    target.write_text(json.dumps(payload, indent=2, sort_keys=True))


def pull_from_huggingface(
    repo_id: str,
    revision: str,
    target_dir: Path,
    subset: Optional[str] = None,
    allow_patterns: Optional[Iterable[str]] = None,
) -> Path:
    if snapshot_download is None:
        raise DownloadError(
            "huggingface_hub is required. Install with `pip install huggingface_hub`."
        )
    kwargs = {
        "repo_id": repo_id,
        "repo_type": "dataset",
        "revision": revision,
        "local_dir": str(target_dir),
        "local_dir_use_symlinks": False,
    }
    if allow_patterns:
        kwargs["allow_patterns"] = list(allow_patterns)
    snapshot_path = Path(snapshot_download(**kwargs))
    if subset:
        subset_path = snapshot_path / subset
        if not subset_path.exists():
            raise DownloadError(f"Subset {subset} not found in snapshot {snapshot_path}")
        return subset_path
    return snapshot_path


def copy_tree(src: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)


def resolve_repo_root() -> Path:
    root = repo_root()
    sys.path.append(str(root))
    return root


def default_content_dir(dataset_dir: Path) -> Path:
    return ensure_dir(dataset_dir / "content")


def finalize_metadata(
    *,
    dataset_dir: Path,
    source: str,
    version: str,
    license_str: str,
    artifact_dir: Path,
    num_records: Optional[int] = None,
) -> Path:
    sha = compute_directory_sha256(artifact_dir)
    metadata = DatasetMetadata(
        source=source,
        version=version,
        license=license_str,
        downloaded_at=timestamp(),
        sha256=sha,
        num_records=num_records,
    )
    meta_path = dataset_dir / "_meta.json"
    write_metadata(metadata, meta_path)
    return meta_path


__all__ = [
    "DatasetMetadata",
    "DownloadError",
    "default_content_dir",
    "finalize_metadata",
    "download_http_resource",
    "extract_archive",
    "pull_from_huggingface",
]


def download_http_resource(url: str, target: Path) -> Path:
    """Download an HTTP resource to ``target``."""

    ensure_dir(target.parent)
    with request.urlopen(url) as response, target.open("wb") as fh:
        shutil.copyfileobj(response, fh)
    return target


def extract_archive(archive_path: Path, dest_dir: Path) -> Path:
    """Extract ``archive_path`` into ``dest_dir`` and return the root path."""

    ensure_dir(dest_dir)
    if zipfile.is_zipfile(archive_path):
        with zipfile.ZipFile(archive_path) as zf:
            zf.extractall(dest_dir)
        return dest_dir
    if tarfile.is_tarfile(archive_path):
        with tarfile.open(archive_path) as tf:
            tf.extractall(dest_dir)
        return dest_dir
    raise DownloadError(f"Unsupported archive format: {archive_path}")

