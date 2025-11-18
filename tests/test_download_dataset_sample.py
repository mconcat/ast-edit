from pathlib import Path

from scripts import download_dataset_sample


def test_download_dataset_sample_builds_command(tmp_path, capsys, monkeypatch):
    # Point repo_root at a temporary directory with a small datasets config.
    monkeypatch.setattr("src.data.schemas.repo_root", lambda: tmp_path)
    monkeypatch.setattr("scripts.download_dataset_sample.repo_root", lambda: tmp_path)

    cfg_path = tmp_path / "configs" / "datasets.yaml"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(
        "commitpackft:\n"
        "  source_type: huggingface\n"
        "  uri: bigcode/commitpackft\n",
        encoding="utf-8",
    )

    download_dataset_sample.main(["commitpackft"])
    out = capsys.readouterr().out

    # Should be a dry-run and include the module invocation plus default patterns.
    assert "[DRY-RUN] Sample download command:" in out
    assert " -m dataset.commitpackft.download " in out
    assert "--allow-pattern **/data-00000*" in out
    assert "--allow-pattern **/train-00000*" in out

