from pathlib import Path

from src.dataset import download_all


def test_download_all_datasets_invokes_each_downloader(tmp_path, monkeypatch, capsys):
    # Point repo_root at a temporary directory with a small datasets config.
    monkeypatch.setattr("src.data.schemas.repo_root", lambda: tmp_path)
    monkeypatch.setattr("src.dataset.download_all.repo_root", lambda: tmp_path)

    cfg_path = tmp_path / "configs" / "datasets.yaml"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(
        "foo:\n"
        "  source_type: huggingface\n"
        "  uri: foo/bar\n"
        "bar:\n"
        "  source_type: http\n"
        "  uri: https://example.com/archive.zip\n",
        encoding="utf-8",
    )

    calls = []

    def fake_run(cmd, check):  # type: ignore[override]
        calls.append(cmd)

    monkeypatch.setattr("src.dataset.download_all.subprocess.run", fake_run)

    download_all.main(["--metadata-only"])
    out = capsys.readouterr().out

    # We should have invoked both modules in sorted order with --metadata-only.
    assert calls[0][1:] == ["-m", "dataset.bar.download", "--metadata-only"]
    assert calls[1][1:] == ["-m", "dataset.foo.download", "--metadata-only"]
    assert "==> [bar] running:" in out
    assert "==> [foo] running:" in out
