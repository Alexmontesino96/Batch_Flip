"""Worker tasks — routing entre Fast Scan y Deep Scan."""

import asyncio
import logging
import traceback
from uuid import UUID

from sqlalchemy import select

from app.database import async_session
from app.models.job import Job
from app.models.job_item import JobItem

logger = logging.getLogger(__name__)

# Configure logging to stdout for Render
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


async def enqueue_job(job_id: str) -> None:
    """Encola un job para procesamiento background."""
    logger.info("WORKER: Enqueuing job %s", job_id)
    asyncio.create_task(_run_job_background(job_id))


async def _run_job_background(job_id: str) -> None:
    """Ejecuta el job — elige Fast o Deep scan según job.scan_mode."""
    logger.info("WORKER: Starting background job %s", job_id)
    try:
        async with async_session() as db:
            job = await db.get(Job, UUID(job_id))
            if not job:
                logger.error("WORKER: Job %s not found in DB", job_id)
                return

            logger.info("WORKER: Job %s loaded — mode=%s, items=%d", job_id, job.scan_mode, job.total_items)

            # Cargar items
            result = await db.execute(
                select(JobItem).where(JobItem.job_id == job.id).order_by(JobItem.input_row)
            )
            items = list(result.scalars().all())
            logger.info("WORKER: Loaded %d items for job %s", len(items), job_id)

            if not items:
                job.status = "completed"
                await db.commit()
                logger.info("WORKER: Job %s completed (0 items)", job_id)
                return

            if job.scan_mode == "deep":
                logger.info("WORKER: Running DEEP scan for job %s", job_id)
                from app.services.batch_processor import process_job
                await process_job(job_id, db)
            else:
                logger.info("WORKER: Running FAST scan for job %s", job_id)
                from app.services.fast_scan_processor import fast_scan_process
                await fast_scan_process(job, items, db)

            logger.info("WORKER: Job %s finished successfully", job_id)

    except Exception as e:
        logger.error("WORKER: Job %s FAILED: %s", job_id, str(e))
        logger.error("WORKER: Traceback:\n%s", traceback.format_exc())
        try:
            async with async_session() as db:
                job = await db.get(Job, UUID(job_id))
                if job and job.status == "processing":
                    job.status = "failed"
                    await db.commit()
                    logger.info("WORKER: Job %s marked as failed", job_id)
        except Exception as inner:
            logger.error("WORKER: Could not mark job %s as failed: %s", job_id, inner)
