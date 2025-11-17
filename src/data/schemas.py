"""Pydantic schemas shared across ingestion and runtime components."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, HttpUrl, validator


class DatasetMetadata(BaseModel):
    """Metadata tracked for every dataset artifact."""

    source: str = Field(..., description="Canonical dataset name or URL")
    version: str = Field(..., description="Semantic version, commit hash, or timestamp")
    license: str = Field(..., description="SPDX identifier or URL")
    downloaded_at: datetime = Field(..., description="UTC timestamp of download")
    sha256: Optional[str] = Field(None, description="SHA256 of archive or deterministic directory hash")
    num_records: Optional[int] = Field(None, description="Count of normalized records available")

    class Config:
        json_encoders: ClassVar[Dict[type, Any]] = {datetime: lambda v: v.isoformat()}


class NormalizedRecord(BaseModel):
    """Unified schema for instruction-edit datasets."""

    instruction: str
    pre: str
    post: str
    language: Literal["python", "javascript", "typescript", "java", "cpp", "c", "go", "rust", "other"]
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Dataset-specific structured metadata (tests, provenance, etc.).",
    )


class DatasetConfig(BaseModel):
    """Runtime configuration describing where to retrieve upstream data."""

    name: str
    source_type: Literal["huggingface", "http", "manual"] = "huggingface"
    uri: str = Field(..., description="HuggingFace repo id or HTTP URL")
    subset: Optional[str] = Field(None, description="Optional subset/split identifier")
    revision: str = Field("main", description="Revision or version tag to download")
    license: str = Field(...)
    approx_size_gb: Optional[float] = None
    approx_records: Optional[int] = None
    languages: List[str] = Field(default_factory=list)
    homepage: Optional[HttpUrl] = None

    @validator("languages", pre=True)
    def _lowercase_languages(cls, value: Optional[List[str]]):  # type: ignore[override]
        if value is None:
            return []
        return [lang.lower() for lang in value]


def repo_root() -> Path:
    """Return repository root regardless of entrypoint location."""

    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "PLAN_STAGE_1.md").exists():
            return parent
    return current.parents[-1]

