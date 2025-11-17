from datetime import datetime, timezone

from src.data.schemas import DatasetConfig, DatasetMetadata, NormalizedRecord


def test_normalized_record_metadata_defaults():
    record = NormalizedRecord(
        instruction="edit",
        pre="print('hi')",
        post="print('bye')",
        language="python",
    )
    assert record.metadata == {}
    enriched = record.copy(update={"metadata": {"tests": ["pytest"]}})
    assert enriched.metadata["tests"] == ["pytest"]


def test_dataset_metadata_serializes_isoformat(tmp_path):
    meta = DatasetMetadata(
        source="test",
        version="v1",
        license="MIT",
        downloaded_at=datetime.now(timezone.utc),
        sha256="deadbeef",
    )
    target = tmp_path / "meta.json"
    # Should not raise
    from src.data.download_utils import write_metadata

    write_metadata(meta, target)
    content = target.read_text()
    assert "deadbeef" in content


def test_dataset_config_lowercases_languages():
    cfg = DatasetConfig(
        name="demo",
        uri="https://example.com",
        license="MIT",
        languages=["Python", "JavaScript"],
    )
    assert cfg.languages == ["python", "javascript"]

