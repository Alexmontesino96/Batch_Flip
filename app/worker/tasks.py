"""PG-backed job queue — polling loop con FOR UPDATE SKIP LOCKED.

No usa Redis, no usa Celery, no usa asyncio.create_task para jobs.
Los jobs se encolan en PostgreSQL (status='queued') y un polling loop
los reclama con lock exclusivo. Sobrevive recycles de Render.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.job import Job
from app.models.job_item import JobItem

logger = logging.getLogger(__name__)

# ID único de esta instancia — previene doble procesamiento
INSTANCE_ID = str(uuid4())[:12]

# Config
POLL_INTERVAL = 5          # segundos entre polls
STALE_LOCK_TIMEOUT = 600   # 10 min — si locked_at > esto, liberar lock
HEARTBEAT_INTERVAL = 30    # segundos entre heartbeats


async def enqueue_job(job_id: str) -> None:
    """Encola un job en PostgreSQL. NO crea asyncio task."""
    async with async_session() as db:
        await db.execute(
            update(Job)
            .where(Job.id == UUID(job_id))
            .values(
                status="queued",
                queued_at=datetime.now(timezone.utc),
                locked_by=None,
                locked_at=None,
            )
        )
        await db.commit()
    logger.info("QUEUE: Job %s enqueued (status=queued)", job_id)


async def job_queue_worker() -> None:
    """Polling loop — busca jobs queued y los procesa uno a uno.

    Corre como asyncio.create_task en el lifespan.
    Si Render recicla, el próximo boot lo reinicia.
    """
    logger.info("QUEUE: Worker started (instance=%s), polling every %ds", INSTANCE_ID, POLL_INTERVAL)

    while True:
        try:
            await _release_stale_locks()
            job_id = await _claim_next_job()

            if job_id:
                await _process_claimed_job(job_id)
            else:
                await asyncio.sleep(POLL_INTERVAL)

        except asyncio.CancelledError:
            logger.info("QUEUE: Worker cancelled (shutdown)")
            break
        except Exception as e:
            logger.error("QUEUE: Worker error: %s", e)
            await asyncio.sleep(POLL_INTERVAL)


async def _claim_next_job() -> str | None:
    """Busca el próximo job queued y lo reclama con FOR UPDATE SKIP LOCKED."""
    async with async_session() as db:
        # FOR UPDATE SKIP LOCKED: si otro worker ya lo tiene, lo salta
        result = await db.execute(text("""
            UPDATE jobs SET
                status = 'processing',
                locked_by = :instance_id,
                locked_at = now()
            WHERE id = (
                SELECT id FROM jobs
                WHERE status = 'queued'
                ORDER BY queued_at
                LIMIT 1
                FOR UPDATE SKIP LOCKED
            )
            RETURNING id
        """), {"instance_id": INSTANCE_ID})

        row = result.fetchone()
        await db.commit()

        if row:
            job_id = str(row[0])
            logger.info("QUEUE: Claimed job %s (locked_by=%s)", job_id, INSTANCE_ID)
            return job_id
        return None


async def _release_stale_locks() -> None:
    """Libera jobs que llevan más de STALE_LOCK_TIMEOUT procesando.

    Si una instancia murió sin completar, el job queda en 'processing'
    con locked_at viejo. Lo reseteamos a 'queued'.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=STALE_LOCK_TIMEOUT)
    async with async_session() as db:
        result = await db.execute(text("""
            UPDATE jobs SET status = 'queued', locked_by = NULL, locked_at = NULL
            WHERE status = 'processing'
              AND locked_at IS NOT NULL
              AND locked_at < :cutoff
            RETURNING id
        """), {"cutoff": cutoff})

        released = result.fetchall()
        await db.commit()

        for row in released:
            logger.warning("QUEUE: Released stale lock on job %s", row[0])


async def _heartbeat(job_id: str, stop_event: asyncio.Event) -> None:
    """Actualiza locked_at cada HEARTBEAT_INTERVAL para evitar stale lock detection."""
    while not stop_event.is_set():
        try:
            async with async_session() as db:
                await db.execute(text("""
                    UPDATE jobs SET locked_at = now() WHERE id = :job_id
                """), {"job_id": job_id})
                await db.commit()
        except Exception:
            pass
        await asyncio.sleep(HEARTBEAT_INTERVAL)


async def _process_claimed_job(job_id: str) -> None:
    """Procesa un job reclamado. Heartbeat mantiene el lock vivo."""
    stop_heartbeat = asyncio.Event()
    heartbeat_task = asyncio.create_task(_heartbeat(job_id, stop_heartbeat))

    try:
        async with async_session() as db:
            job = await db.get(Job, UUID(job_id))
            if not job:
                logger.error("QUEUE: Job %s not found after claim", job_id)
                return

            logger.info("QUEUE: Processing job %s (mode=%s, items=%d)", job_id, job.scan_mode, job.total_items)

            # Cargar items
            result = await db.execute(
                select(JobItem).where(JobItem.job_id == job.id).order_by(JobItem.input_row)
            )
            items = list(result.scalars().all())

            if not items:
                job.status = "completed"
                job.locked_by = None
                job.locked_at = None
                await db.commit()
                logger.info("QUEUE: Job %s completed (0 items)", job_id)
                return

            # Dispatch
            if job.scan_mode == "deep":
                from app.services.batch_processor import process_job
                await process_job(job_id, db)
            else:
                from app.services.fast_scan_processor import fast_scan_process
                await fast_scan_process(job, items, db)

            # Limpiar lock
            job.locked_by = None
            job.locked_at = None
            await db.commit()

            logger.info("QUEUE: Job %s finished successfully", job_id)

    except Exception as e:
        logger.error("QUEUE: Job %s FAILED: %s", job_id, e)
        import traceback
        logger.error("QUEUE: Traceback:\n%s", traceback.format_exc())
        try:
            async with async_session() as db:
                await db.execute(text("""
                    UPDATE jobs SET status = 'failed', locked_by = NULL, locked_at = NULL
                    WHERE id = :job_id
                """), {"job_id": job_id})
                await db.commit()
        except Exception:
            pass

    finally:
        stop_heartbeat.set()
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass
