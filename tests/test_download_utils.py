import io
import tarfile
import zipfile

import pytest

from src.data.download_utils import (
    DownloadError,
    compute_directory_sha256,
    download_http_resource,
    extract_archive,
)


class DummyResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False


def test_download_http_resource_rejects_invalid_scheme(tmp_path):
    with pytest.raises(DownloadError):
        download_http_resource("ftp://example.com/file.txt", tmp_path / "file.txt")


def test_download_http_resource_validates_checksum(monkeypatch, tmp_path):
    payload = b"hello world"

    def fake_urlopen(request_obj, timeout=300):  # noqa: ANN001 - signature defined by urllib
        return DummyResponse(payload)

    monkeypatch.setattr("src.data.download_utils.request.urlopen", fake_urlopen)
    target = tmp_path / "payload.bin"
    # wrong checksum should fail
    with pytest.raises(DownloadError):
        download_http_resource("https://example.com/file", target, expected_sha256="deadbeef")

    # correct checksum passes
    import hashlib

    digest = hashlib.sha256(payload).hexdigest()
    download_http_resource("https://example.com/file", target, expected_sha256=digest)
    assert target.read_bytes() == payload


def test_extract_archive_blocks_zip_path_traversal(tmp_path):
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("../evil.txt", "boom")
    with pytest.raises(DownloadError):
        extract_archive(archive, tmp_path / "out")


def test_extract_archive_blocks_tar_symlinks(tmp_path):
    archive = tmp_path / "bad.tar"
    with tarfile.open(archive, "w") as tf:
        info = tarfile.TarInfo(name="payload.txt")
        data = b"safe"
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data))
        link = tarfile.TarInfo(name="sym")
        link.type = tarfile.SYMTYPE
        link.linkname = "../evil"
        tf.addfile(link)
    with pytest.raises(DownloadError):
        extract_archive(archive, tmp_path / "out")


def test_compute_directory_sha256_ignores_symlinks(tmp_path):
    root = tmp_path / "tree"
    (root / "nested").mkdir(parents=True)
    (root / "nested" / "file.txt").write_text("hello")
    (root / "loop").symlink_to(root)

    clone = tmp_path / "clone"
    (clone / "nested").mkdir(parents=True)
    (clone / "nested" / "file.txt").write_text("hello")

    assert compute_directory_sha256(root) == compute_directory_sha256(clone)

