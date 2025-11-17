"""Utility helpers shared by dataset download scripts."""
from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import shutil
import tarfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional
from urllib import error, parse, request
from uuid import uuid4

try:
    from huggingface_hub import snapshot_download
except ImportError:  # pragma: no cover - optional dependency
    snapshot_download = None  # type: ignore

from pydantic import ValidationError

from .schemas import DatasetMetadata


class DownloadError(RuntimeError):
    """Raised when a dataset could not be downloaded."""


CHUNK_SIZE = 1024 * 1024
SAFE_URL_SCHEMES = {"http", "https"}
MAX_ARCHIVE_BYTES = 50 * 1024 * 1024 * 1024  # 50GB safety ceiling


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
    for child in sorted(
        p for p in path.rglob("*") if p.is_file() and not p.name.startswith(".") and not p.is_symlink()
    ):
        digest.update(str(child.relative_to(path)).encode())
        digest.update(compute_file_sha256(child).encode())
    return digest.hexdigest()


def write_metadata(meta: DatasetMetadata, target: Path) -> None:
    try:
        serializer = getattr(meta, "model_dump", None)
        if serializer:
            payload = serializer(mode="json")
        else:
            payload = json.loads(meta.json())
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
    ensure_dir(dest.parent)
    temp_dest = dest.parent / f".{dest.name}.tmp-{uuid4().hex}"
    if temp_dest.exists():
        shutil.rmtree(temp_dest)
    try:
        shutil.copytree(src, temp_dest)
        os.replace(temp_dest, dest)
    finally:
        if temp_dest.exists():
            shutil.rmtree(temp_dest)


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


def _validate_url(url: str) -> parse.ParseResult:
    parsed = parse.urlparse(url)
    if parsed.scheme.lower() not in SAFE_URL_SCHEMES:
        raise DownloadError(f"Unsupported URL scheme for download: {parsed.scheme}")
    if not parsed.netloc:
        raise DownloadError("URL must include a hostname")
    host = parsed.hostname or ""
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return parsed
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
        raise DownloadError("Refusing to download from private or loopback addresses")
    return parsed


def download_http_resource(
    url: str,
    target: Path,
    *,
    timeout: int = 300,
    expected_sha256: Optional[str] = None,
) -> Path:
    """Download an HTTP resource to ``target`` with basic validation."""

    _validate_url(url)
    ensure_dir(target.parent)
    request_obj = request.Request(url, headers={"User-Agent": "ast-edit-downloader/0.1"})
    try:
        with request.urlopen(request_obj, timeout=timeout) as response, target.open("wb") as fh:
            shutil.copyfileobj(response, fh)
    except error.URLError as exc:  # pragma: no cover - network failure
        raise DownloadError(f"Failed to download {url}: {exc}") from exc

    if expected_sha256:
        actual = compute_file_sha256(target)
        if actual != expected_sha256:
            raise DownloadError(
                f"Checksum mismatch for {target}. Expected {expected_sha256}, got {actual}."
            )
    return target


def _ensure_within(target: Path, root: Path) -> None:
    try:
        target.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise DownloadError(f"Blocked path traversal attempt: {target}") from exc


def _extract_zip(archive_path: Path, dest_dir: Path) -> None:
    with zipfile.ZipFile(archive_path) as zf:
        total = sum(info.file_size for info in zf.infolist())
        if total > MAX_ARCHIVE_BYTES:
            raise DownloadError(f"Archive too large: {total} bytes")
        for info in zf.infolist():
            member_path = dest_dir / info.filename
            _ensure_within(member_path, dest_dir)
        zf.extractall(dest_dir)


def _extract_tar(archive_path: Path, dest_dir: Path) -> None:
    with tarfile.open(archive_path) as tf:
        total = 0
        for member in tf.getmembers():
            member_path = dest_dir / member.name
            _ensure_within(member_path, dest_dir)
            if member.issym() or member.islnk():
                raise DownloadError("Symbolic links are not permitted in archives")
            if member.size:
                total += member.size
        if total > MAX_ARCHIVE_BYTES:
            raise DownloadError(f"Archive too large: {total} bytes")
        tf.extractall(dest_dir)


def extract_archive(archive_path: Path, dest_dir: Path) -> Path:
    """Extract ``archive_path`` into ``dest_dir`` and return the root path."""

    ensure_dir(dest_dir)
    if zipfile.is_zipfile(archive_path):
        _extract_zip(archive_path, dest_dir)
        return dest_dir
    if tarfile.is_tarfile(archive_path):
        _extract_tar(archive_path, dest_dir)
        return dest_dir
    raise DownloadError(f"Unsupported archive format: {archive_path}")


__all__ = [
    "DatasetMetadata",
    "DownloadError",
    "default_content_dir",
    "finalize_metadata",
    "download_http_resource",
    "extract_archive",
    "pull_from_huggingface",
]

