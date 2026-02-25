"""Pydantic models for Sprout."""

from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field


class Confidence(str, Enum):
    SEED = "seed"
    WATERED = "watered"
    SPROUTED = "sprouted"
    REJECTED = "rejected"


class Provenance(BaseModel):
    produced_by: str  # "haiku-4.5" | "sonnet-4.6" | "opus-4.6"
    produced_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    task_type: str  # "biography" | "council_description" | "synopsis"
    sources: list[str] = Field(default_factory=list)
    verified_by: str | None = None
    verified_at: datetime | None = None
    confidence: Confidence = Confidence.SEED


class Chunk(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    project: str
    node_id: str
    node_type: str
    field: str
    content: str
    provenance: Provenance
    review_notes: str | None = None


class ScheduledTask(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    task_name: str
    task_params: dict | None = None
    run_at: datetime
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: str = "pending"  # pending | running | completed | failed


class TokenUsage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    chunk_id: str
    model: str
    estimated_tokens: int
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
