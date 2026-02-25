"""Basic tests for Sprout."""

import asyncio
import json
import os
import tempfile

import pytest
import pytest_asyncio

# Override DB path before importing sprout modules
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["SPROUT_DB_PATH"] = _tmp.name

import sprout.db as db

# Patch DB path for tests
db.DB_PATH = _tmp.name
db._db = None

from sprout.models import Chunk, Confidence, Provenance
from sprout.router import confidence_for_model, recommend_model


@pytest.fixture(autouse=True)
async def reset_db():
    db._db = None
    yield
    if db._db:
        await db._db.close()
        db._db = None


@pytest.mark.asyncio
async def test_recommend_model():
    rec = recommend_model("biography_synthesis")
    assert rec["tier"] == "haiku"
    assert rec["recommended_model"] == "haiku-4.5"


@pytest.mark.asyncio
async def test_confidence_for_model():
    assert confidence_for_model("haiku-4.5") == "seed"
    assert confidence_for_model("sonnet-4.6") == "watered"
    assert confidence_for_model("opus-4.6") == "sprouted"
    assert confidence_for_model("unknown") == "seed"


@pytest.mark.asyncio
async def test_insert_and_retrieve():
    chunk = Chunk(
        project="theology",
        node_id="cath-person-001",
        node_type="Person",
        field="biography",
        content="Saint Peter was the first Pope.",
        provenance=Provenance(
            produced_by="haiku-4.5",
            task_type="biography_synthesis",
            sources=["https://example.com"],
            confidence=Confidence.SEED,
        ),
    )
    await db.insert_chunk(chunk)

    queue = await db.get_review_queue(project="theology")
    assert len(queue) >= 1
    found = next((c for c in queue if c.node_id == "cath-person-001"), None)
    assert found is not None
    assert found.provenance.confidence == Confidence.SEED


@pytest.mark.asyncio
async def test_mark_reviewed():
    chunk = Chunk(
        project="theology",
        node_id="cath-person-002",
        node_type="Person",
        field="biography",
        content="Saint Paul was the Apostle to the Gentiles.",
        provenance=Provenance(
            produced_by="haiku-4.5",
            task_type="biography_synthesis",
            sources=["https://example.com/paul"],
            confidence=Confidence.SEED,
        ),
    )
    await db.insert_chunk(chunk)

    updated = await db.mark_reviewed(chunk.id, "sonnet-4.6", "watered")
    assert updated is not None
    assert updated.provenance.confidence == Confidence.WATERED
    assert updated.provenance.verified_by == "sonnet-4.6"


@pytest.mark.asyncio
async def test_export_chunks():
    chunk = Chunk(
        project="theology",
        node_id="cath-person-003",
        node_type="Person",
        field="biography",
        content="Saint John wrote the Fourth Gospel.",
        provenance=Provenance(
            produced_by="sonnet-4.6",
            task_type="biography_synthesis",
            sources=["https://example.com/john"],
            confidence=Confidence.WATERED,
        ),
    )
    await db.insert_chunk(chunk)

    exported = await db.export_chunks(project="theology", min_confidence="watered")
    assert len(exported) >= 1
    john = next((e for e in exported if e["nodeId"] == "cath-person-003"), None)
    assert john is not None
    assert john["confidence"] == "watered"


@pytest.mark.asyncio
async def test_stats():
    stats = await db.get_stats()
    assert "by_confidence" in stats
    assert "total" in stats


@pytest.mark.asyncio
async def test_scheduled_tasks():
    from datetime import datetime, timedelta, timezone
    from sprout.models import ScheduledTask

    task = ScheduledTask(
        task_name="opus_test",
        run_at=datetime.now(timezone.utc) + timedelta(hours=2),
    )
    await db.insert_scheduled_task(task)

    pending = await db.get_pending_tasks()
    assert any(t.id == task.id for t in pending)

    cancelled = await db.cancel_scheduled_task(task.id)
    assert cancelled is True
