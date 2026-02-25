"""Sprout MCP server — model-tiered research with provenance tracking."""

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastmcp import FastMCP

from sprout import db
from sprout.models import Chunk, Confidence, Provenance, ScheduledTask
from sprout.router import confidence_for_model, recommend_model as _recommend_model
from sprout.scheduler import run_scheduler_loop

_scheduler_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncIterator[None]:
    global _scheduler_task
    _scheduler_task = asyncio.create_task(run_scheduler_loop())
    try:
        yield
    finally:
        if _scheduler_task and not _scheduler_task.done():
            _scheduler_task.cancel()


mcp = FastMCP(
    "Sprout",
    instructions="Model-tiered research MCP server — cheap models seed, expensive models verify",
    lifespan=lifespan,
)


@mcp.tool()
async def submit_chunk(
    project: str,
    node_id: str,
    node_type: str,
    field: str,
    content: str,
    produced_by: str,
    task_type: str,
    sources: list[str] | None = None,
) -> str:
    """Store content with provenance tracking.

    Args:
        project: Project name (e.g. "theology")
        node_id: Node identifier (e.g. "cath-person-001")
        node_type: Node type (e.g. "Person", "Council", "Document")
        field: Field name (e.g. "biography", "description")
        content: The actual content
        produced_by: Model that produced it (e.g. "haiku-4.5", "sonnet-4.6", "opus-4.6")
        task_type: Type of task (e.g. "biography_synthesis")
        sources: URLs used as sources
    """
    confidence = confidence_for_model(produced_by)
    chunk = Chunk(
        project=project,
        node_id=node_id,
        node_type=node_type,
        field=field,
        content=content,
        provenance=Provenance(
            produced_by=produced_by,
            task_type=task_type,
            sources=sources or [],
            confidence=Confidence(confidence),
        ),
    )
    await db.insert_chunk(chunk)
    await db.record_token_usage(chunk.id, produced_by, content)
    return f"Stored chunk {chunk.id} [{confidence}] for {node_id}.{field}"


@mcp.tool()
async def get_review_queue(
    project: str | None = None,
    node_type: str | None = None,
    confidence: str | None = None,
    limit: int = 50,
) -> str:
    """List chunks needing review.

    Args:
        project: Filter by project
        node_type: Filter by node type
        confidence: Filter by confidence level (seed, watered)
        limit: Max results (default 50)
    """
    chunks = await db.get_review_queue(project, node_type, confidence, limit)
    if not chunks:
        return "No chunks in review queue."
    lines = [f"## Review Queue ({len(chunks)} chunks)\n"]
    for c in chunks:
        sources = ", ".join(c.provenance.sources[:2]) if c.provenance.sources else "none"
        lines.append(
            f"- **{c.id[:8]}** | {c.node_id}.{c.field} [{c.provenance.confidence.value}] "
            f"by {c.provenance.produced_by} | sources: {sources}"
        )
    return "\n".join(lines)


@mcp.tool()
async def mark_reviewed(
    chunk_id: str,
    verified_by: str,
    new_confidence: str,
    review_notes: str | None = None,
) -> str:
    """Promote or reject a chunk after review.

    Args:
        chunk_id: UUID of the chunk
        verified_by: Model or person that reviewed (e.g. "sonnet-4.6", "opus-4.6")
        new_confidence: New confidence level (watered, sprouted, rejected)
        review_notes: Optional rejection reason or reviewer comments
    """
    valid = {"watered", "sprouted", "rejected"}
    if new_confidence not in valid:
        return f"Invalid confidence. Must be one of: {valid}"
    chunk = await db.mark_reviewed(chunk_id, verified_by, new_confidence, review_notes)
    if not chunk:
        return f"Chunk {chunk_id} not found."
    return f"Chunk {chunk_id} → {new_confidence} (verified by {verified_by})"


@mcp.tool()
async def recommend_model(task_type: str) -> str:
    """Get model recommendation for a task type.

    Args:
        task_type: The type of task (e.g. "biography_synthesis", "fact_check_final")
    """
    rec = _recommend_model(task_type)
    return (
        f"**{rec['task_type']}**: use **{rec['recommended_model']}** ({rec['tier']})\n"
        f"Reason: {rec['reason']}"
    )


@mcp.tool()
async def get_stats(project: str | None = None) -> str:
    """Get dashboard of chunk counts by confidence level and token usage.

    Args:
        project: Optional project filter
    """
    stats = await db.get_stats(project)
    lines = [f"## Sprout Stats (total: {stats['total']})\n"]
    lines.append("### By Confidence")
    for conf, count in sorted(stats["by_confidence"].items()):
        lines.append(f"- {conf}: {count}")
    lines.append("\n### By Project")
    for proj, count in sorted(stats["by_project"].items()):
        lines.append(f"- {proj}: {count}")
    lines.append("\n### By Task Type")
    for tt, count in sorted(stats["by_type"].items()):
        lines.append(f"- {tt}: {count}")
    if stats.get("token_usage"):
        lines.append("\n### Token Usage")
        for model, info in sorted(stats["token_usage"].items()):
            lines.append(f"- {model}: ~{info['total_tokens']:,} tokens ({info['count']} chunks)")
    return "\n".join(lines)


@mcp.tool()
async def export_chunks(
    project: str | None = None,
    min_confidence: str = "watered",
) -> str:
    """Export verified chunks as JSON compatible with enrich-nodes.js.

    Args:
        project: Optional project filter
        min_confidence: Minimum confidence level (seed, watered, sprouted). Default: watered
    """
    chunks = await db.export_chunks(project, min_confidence)
    return json.dumps(chunks, indent=2)


@mcp.tool()
async def opus_test() -> str:
    """Generate structured review summary for the OpusTest workflow.

    Groups all seed/watered chunks by type with source URLs,
    ready for Sonnet first-pass then Opus final-pass.
    """
    chunks = await db.get_review_queue(limit=500)
    if not chunks:
        return "No chunks pending review."

    by_type: dict[str, list[Chunk]] = {}
    for c in chunks:
        by_type.setdefault(c.provenance.task_type, []).append(c)

    lines = ["## OpusTest Review Summary\n"]
    seed_count = sum(1 for c in chunks if c.provenance.confidence == Confidence.SEED)
    watered_count = sum(1 for c in chunks if c.provenance.confidence == Confidence.WATERED)
    lines.append(f"**{len(chunks)} chunks**: {seed_count} seed, {watered_count} watered\n")

    for task_type, type_chunks in sorted(by_type.items()):
        lines.append(f"### {task_type} ({len(type_chunks)} chunks)")
        for c in type_chunks:
            sources = " | ".join(c.provenance.sources[:3]) if c.provenance.sources else "no sources"
            lines.append(
                f"- `{c.id[:8]}` **{c.node_id}**.{c.field} "
                f"[{c.provenance.confidence.value}] — {sources}"
            )
        lines.append("")

    lines.append("### Recommended Workflow")
    lines.append("1. Spawn Sonnet agents for seed → watered (fact-check first pass)")
    lines.append("2. Spawn Opus agent for watered → sprouted (deep verification)")
    lines.append("3. Export sprouted chunks via `export_chunks`")
    return "\n".join(lines)


@mcp.tool()
async def schedule_task(
    task_name: str,
    run_at: str | None = None,
    delay_minutes: int | None = None,
    task_params: str | None = None,
) -> str:
    """Schedule a task to run at a specific time or after a delay.

    Args:
        task_name: Task to run (opus_test, export_chunks, get_stats)
        run_at: ISO datetime for when to run (e.g. "2026-02-26T02:00:00-07:00")
        delay_minutes: Minutes from now to run
        task_params: Optional JSON string of parameters
    """
    if not run_at and not delay_minutes:
        return "Provide either run_at or delay_minutes."

    if delay_minutes:
        when = datetime.now(timezone.utc) + timedelta(minutes=delay_minutes)
    else:
        when = datetime.fromisoformat(run_at)  # type: ignore
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)

    params = json.loads(task_params) if task_params else None
    task = ScheduledTask(task_name=task_name, task_params=params, run_at=when)
    await db.insert_scheduled_task(task)
    return f"Scheduled {task_name} → {when.isoformat()} (id: {task.id[:8]})"


@mcp.tool()
async def list_scheduled() -> str:
    """View pending scheduled tasks."""
    tasks = await db.get_pending_tasks()
    if not tasks:
        return "No pending scheduled tasks."
    lines = ["## Scheduled Tasks\n"]
    for t in tasks:
        lines.append(f"- `{t.id[:8]}` **{t.task_name}** at {t.run_at.isoformat()} [{t.status}]")
    return "\n".join(lines)


@mcp.tool()
async def cancel_scheduled(task_id: str) -> str:
    """Cancel a pending scheduled task.

    Args:
        task_id: Full or partial UUID of the task
    """
    # Try exact match first, then prefix match
    tasks = await db.get_pending_tasks()
    match = None
    for t in tasks:
        if t.id == task_id or t.id.startswith(task_id):
            match = t
            break
    if not match:
        return f"No pending task matching '{task_id}'."

    ok = await db.cancel_scheduled_task(match.id)
    return f"Cancelled task {match.id[:8]} ({match.task_name})" if ok else "Failed to cancel."


