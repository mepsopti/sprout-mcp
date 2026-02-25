"""Background task scheduler with asyncio loop + optional daemon mode."""

import asyncio
import json
import logging
import sys
from datetime import datetime, timezone

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("sprout.scheduler")

CHECK_INTERVAL = 60  # seconds


async def _execute_task(task_name: str, task_params: dict | None) -> str:
    """Execute a scheduled task by name. Returns result string."""
    # Import here to avoid circular imports
    from sprout import db

    if task_name == "opus_test":
        # Generate review summary
        chunks = await db.get_review_queue()
        by_type: dict[str, list] = {}
        for c in chunks:
            by_type.setdefault(c.provenance.task_type, []).append(c)

        lines = [f"## OpusTest Review Summary\n"]
        for task_type, type_chunks in sorted(by_type.items()):
            lines.append(f"### {task_type} ({len(type_chunks)} chunks)")
            for c in type_chunks:
                sources = ", ".join(c.provenance.sources[:3]) if c.provenance.sources else "none"
                lines.append(f"- **{c.node_id}** [{c.provenance.confidence.value}] sources: {sources}")
            lines.append("")
        return "\n".join(lines)

    elif task_name == "export_chunks":
        project = (task_params or {}).get("project")
        min_conf = (task_params or {}).get("min_confidence", "watered")
        result = await db.export_chunks(project=project, min_confidence=min_conf)
        return json.dumps(result, indent=2)

    elif task_name == "get_stats":
        stats = await db.get_stats()
        return json.dumps(stats, indent=2)

    else:
        return f"Unknown task: {task_name}"


async def run_scheduler_loop():
    """Check for due tasks every CHECK_INTERVAL seconds."""
    from sprout import db as db_mod

    log.info("Scheduler loop started")
    while True:
        try:
            pending = await db_mod.get_pending_tasks()
            now = datetime.now(timezone.utc)
            for task in pending:
                run_at = task.run_at if task.run_at.tzinfo else task.run_at.replace(tzinfo=timezone.utc)
                if run_at <= now:
                    log.info(f"Executing task {task.id}: {task.task_name}")
                    await db_mod.update_task_status(task.id, "running")
                    try:
                        result = await _execute_task(task.task_name, task.task_params)
                        await db_mod.update_task_status(task.id, "completed")
                        await db_mod.record_task_run(task.id, task.task_name, "completed", result)
                        log.info(f"Task {task.id} completed")
                    except Exception as e:
                        await db_mod.update_task_status(task.id, "failed")
                        await db_mod.record_task_run(task.id, task.task_name, "failed", str(e))
                        log.error(f"Task {task.id} failed: {e}")
        except Exception as e:
            log.error(f"Scheduler error: {e}")
        await asyncio.sleep(CHECK_INTERVAL)


def run_daemon():
    """Entry point for standalone daemon mode."""
    log.info("Sprout scheduler daemon starting")
    asyncio.run(run_scheduler_loop())


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "daemon":
        run_daemon()
    else:
        print("Usage: python -m sprout.scheduler daemon")
