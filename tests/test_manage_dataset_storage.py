from pathlib import Path

from scripts import manage_dataset_storage


def test_manage_dataset_storage_creates_symlinks(tmp_path, monkeypatch):
    # Point repo_root at a temporary directory with dummy dataset folders.
    monkeypatch.setattr("src.data.schemas.repo_root", lambda: tmp_path)
    monkeypatch.setattr("scripts.manage_dataset_storage.repo_root", lambda: tmp_path)

    dataset_root = tmp_path / "dataset"
    (dataset_root / "commitpackft").mkdir(parents=True)
    (dataset_root / "agentpack").mkdir(parents=True)

    cfg_path = tmp_path / "configs" / "dataset_storage.local.yaml"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(
        "base_dir: datasets\n"
        "datasets:\n"
        "  commitpackft: commitpackft\n"
        "  agentpack: other/agentpack\n",
        encoding="utf-8",
    )

    manage_dataset_storage.main(["--config", str(cfg_path)])

    link1 = dataset_root / "commitpackft" / "content"
    link2 = dataset_root / "agentpack" / "content"

    assert link1.is_symlink()
    assert link2.is_symlink()
    assert link1.resolve() == (tmp_path / "datasets" / "commitpackft")
    assert link2.resolve() == (tmp_path / "datasets" / "other" / "agentpack")
