"""SQLite persistence for Sprout."""

import json
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

from sprout.models import Chunk, Confidence, Provenance, ScheduledTask, TokenUsage

DB_PATH = Path(__file__).parent.parent / "sprout.db"

_db: aiosqlite.Connection | None = None


async def get_db() -> aiosqlite.Connection:
    global _db
    if _db is None:
        _db = await aiosqlite.connect(DB_PATH)
        _db.row_factory = aiosqlite.Row
        await _db.execute("PRAGMA journal_mode=WAL")
        await _init_tables(_db)
    return _db


async def _init_tables(db: aiosqlite.Connection) -> None:
    await db.executescript("""
        CREATE TABLE IF NOT EXISTS chunks (
            id TEXT PRIMARY KEY,
            project TEXT NOT NULL,
            node_id TEXT NOT NULL,
            node_type TEXT NOT NULL,
            field TEXT NOT NULL,
            content TEXT NOT NULL,
            produced_by TEXT NOT NULL,
            produced_at TEXT NOT NULL,
            task_type TEXT NOT NULL,
            sources TEXT,
            verified_by TEXT,
            verified_at TEXT,
            confidence TEXT NOT NULL DEFAULT 'seed',
            review_notes TEXT,
            UNIQUE(project, node_id, field)
        );
        CREATE INDEX IF NOT EXISTS idx_confidence ON chunks(confidence);
        CREATE INDEX IF NOT EXISTS idx_project ON chunks(project);

        CREATE TABLE IF NOT EXISTS scheduled_tasks (
            id TEXT PRIMARY KEY,
            task_name TEXT NOT NULL,
            task_params TEXT,
            run_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            status TEXT DEFAULT 'pending'
        );

        CREATE TABLE IF NOT EXISTS task_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            task_name TEXT NOT NULL,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            status TEXT NOT NULL,
            result TEXT
        );

        CREATE TABLE IF NOT EXISTS token_usage (
            id TEXT PRIMARY KEY,
            chunk_id TEXT REFERENCES chunks(id),
            model TEXT NOT NULL,
            estimated_tokens INTEGER NOT NULL,
            recorded_at TEXT NOT NULL
        );
    """)


def _row_to_chunk(row: aiosqlite.Row) -> Chunk:
    return Chunk(
        id=row["id"],
        project=row["project"],
        node_id=row["node_id"],
        node_type=row["node_type"],
        field=row["field"],
        content=row["content"],
        review_notes=row["review_notes"],
        provenance=Provenance(
            produced_by=row["produced_by"],
            produced_at=datetime.fromisoformat(row["produced_at"]),
            task_type=row["task_type"],
            sources=json.loads(row["sources"]) if row["sources"] else [],
            verified_by=row["verified_by"],
            verified_at=datetime.fromisoformat(row["verified_at"]) if row["verified_at"] else None,
            confidence=Confidence(row["confidence"]),
        ),
    )


async def insert_chunk(chunk: Chunk) -> None:
    db = await get_db()
    p = chunk.provenance
    await db.execute(
        """INSERT OR REPLACE INTO chunks
           (id, project, node_id, node_type, field, content,
            produced_by, produced_at, task_type, sources,
            verified_by, verified_at, confidence, review_notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            chunk.id, chunk.project, chunk.node_id, chunk.node_type,
            chunk.field, chunk.content,
            p.produced_by, p.produced_at.isoformat(), p.task_type,
            json.dumps(p.sources),
            p.verified_by,
            p.verified_at.isoformat() if p.verified_at else None,
            p.confidence.value,
            chunk.review_notes,
        ),
    )
    await db.commit()


async def get_review_queue(
    project: str | None = None,
    node_type: str | None = None,
    confidence: str | None = None,
    limit: int = 50,
) -> list[Chunk]:
    db = await get_db()
    clauses = []
    params: list = []
    if project:
        clauses.append("project = ?")
        params.append(project)
    if node_type:
        clauses.append("node_type = ?")
        params.append(node_type)
    if confidence:
        clauses.append("confidence = ?")
        params.append(confidence)
    else:
        clauses.append("confidence IN ('seed', 'watered')")

    where = " AND ".join(clauses) if clauses else "1=1"
    query = f"SELECT * FROM chunks WHERE {where} ORDER BY produced_at LIMIT ?"
    params.append(limit)
    async with db.execute(query, params) as cursor:
        rows = await cursor.fetchall()
    return [_row_to_chunk(r) for r in rows]


async def mark_reviewed(
    chunk_id: str,
    verified_by: str,
    new_confidence: str,
    review_notes: str | None = None,
) -> Chunk | None:
    db = await get_db()
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        """UPDATE chunks SET verified_by = ?, verified_at = ?,
           confidence = ?, review_notes = ? WHERE id = ?""",
        (verified_by, now, new_confidence, review_notes, chunk_id),
    )
    await db.commit()
    async with db.execute("SELECT * FROM chunks WHERE id = ?", (chunk_id,)) as cursor:
        row = await cursor.fetchone()
    return _row_to_chunk(row) if row else None


async def get_stats(project: str | None = None) -> dict:
    db = await get_db()
    where = "WHERE project = ?" if project else ""
    params = [project] if project else []

    stats: dict = {"by_confidence": {}, "by_project": {}, "by_type": {}, "total": 0}

    query = f"SELECT confidence, COUNT(*) as cnt FROM chunks {where} GROUP BY confidence"
    async with db.execute(query, params) as cursor:
        for row in await cursor.fetchall():
            stats["by_confidence"][row["confidence"]] = row["cnt"]
            stats["total"] += row["cnt"]

    query = f"SELECT project, COUNT(*) as cnt FROM chunks {where} GROUP BY project"
    async with db.execute(query, params) as cursor:
        for row in await cursor.fetchall():
            stats["by_project"][row["project"]] = row["cnt"]

    query = f"SELECT task_type, COUNT(*) as cnt FROM chunks {where} GROUP BY task_type"
    async with db.execute(query, params) as cursor:
        for row in await cursor.fetchall():
            stats["by_type"][row["task_type"]] = row["cnt"]

    # Token usage stats
    token_query = """
        SELECT model, SUM(estimated_tokens) as total_tokens, COUNT(*) as count
        FROM token_usage GROUP BY model
    """
    async with db.execute(token_query) as cursor:
        token_stats = {}
        for row in await cursor.fetchall():
            token_stats[row["model"]] = {
                "total_tokens": row["total_tokens"],
                "count": row["count"],
            }
        stats["token_usage"] = token_stats

    return stats


async def export_chunks(
    project: str | None = None,
    min_confidence: str = "watered",
) -> list[dict]:
    db = await get_db()
    confidence_levels = {"seed": 0, "watered": 1, "sprouted": 2}
    min_level = confidence_levels.get(min_confidence, 1)
    allowed = [k for k, v in confidence_levels.items() if v >= min_level]
    placeholders = ",".join("?" * len(allowed))

    clauses = [f"confidence IN ({placeholders})"]
    params: list = list(allowed)
    if project:
        clauses.append("project = ?")
        params.append(project)

    where = " AND ".join(clauses)
    async with db.execute(f"SELECT * FROM chunks WHERE {where}", params) as cursor:
        rows = await cursor.fetchall()

    results = []
    for row in rows:
        results.append({
            "nodeId": row["node_id"],
            "nodeType": row["node_type"],
            "field": row["field"],
            "content": row["content"],
            "confidence": row["confidence"],
            "producedBy": row["produced_by"],
            "sources": json.loads(row["sources"]) if row["sources"] else [],
            "verifiedBy": row["verified_by"],
        })
    return results


async def record_token_usage(chunk_id: str, model: str, content: str) -> None:
    db = await get_db()
    word_count = len(content.split())
    estimated = int(word_count * 1.3)  # ~1.3 tokens/word for output
    usage = TokenUsage(chunk_id=chunk_id, model=model, estimated_tokens=estimated)
    await db.execute(
        "INSERT INTO token_usage (id, chunk_id, model, estimated_tokens, recorded_at) VALUES (?, ?, ?, ?, ?)",
        (usage.id, usage.chunk_id, usage.model, usage.estimated_tokens, usage.recorded_at.isoformat()),
    )
    await db.commit()


# --- Scheduled tasks ---

async def insert_scheduled_task(task: ScheduledTask) -> None:
    db = await get_db()
    await db.execute(
        "INSERT INTO scheduled_tasks (id, task_name, task_params, run_at, created_at, status) VALUES (?, ?, ?, ?, ?, ?)",
        (task.id, task.task_name, json.dumps(task.task_params) if task.task_params else None,
         task.run_at.isoformat(), task.created_at.isoformat(), task.status),
    )
    await db.commit()


async def get_pending_tasks() -> list[ScheduledTask]:
    db = await get_db()
    async with db.execute(
        "SELECT * FROM scheduled_tasks WHERE status = 'pending' ORDER BY run_at"
    ) as cursor:
        rows = await cursor.fetchall()
    return [
        ScheduledTask(
            id=r["id"], task_name=r["task_name"],
            task_params=json.loads(r["task_params"]) if r["task_params"] else None,
            run_at=datetime.fromisoformat(r["run_at"]),
            created_at=datetime.fromisoformat(r["created_at"]),
            status=r["status"],
        )
        for r in rows
    ]


async def update_task_status(task_id: str, status: str) -> None:
    db = await get_db()
    await db.execute("UPDATE scheduled_tasks SET status = ? WHERE id = ?", (status, task_id))
    await db.commit()


async def record_task_run(task_id: str, task_name: str, status: str, result: str | None = None) -> None:
    db = await get_db()
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO task_runs (task_id, task_name, started_at, status, result) VALUES (?, ?, ?, ?, ?)",
        (task_id, task_name, now, status, result),
    )
    await db.commit()


async def cancel_scheduled_task(task_id: str) -> bool:
    db = await get_db()
    cursor = await db.execute(
        "UPDATE scheduled_tasks SET status = 'cancelled' WHERE id = ? AND status = 'pending'",
        (task_id,),
    )
    await db.commit()
    return cursor.rowcount > 0
