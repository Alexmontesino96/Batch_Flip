"""Worker tasks — routing entre Fast Scan y Deep Scan."""

import asyncio
import logging
from uuid import UUID

from sqlalchemy import select

from app.database import async_session
from app.models.job import Job
from app.models.job_item import JobItem

logger = logging.getLogger(__name__)


async def enqueue_job(job_id: str) -> None:
    """Encola un job para procesamiento background."""
    asyncio.create_task(_run_job_background(job_id))


async def _run_job_background(job_id: str) -> None:
    """Ejecuta el job — elige Fast o Deep scan según job.scan_mode."""
    try:
        async with async_session() as db:
            job = await db.get(Job, UUID(job_id))
            if not job:
                logger.error("Job %s no encontrado", job_id)
                return

            # Cargar items
            result = await db.execute(
                select(JobItem).where(JobItem.job_id == job.id).order_by(JobItem.input_row)
            )
            items = list(result.scalars().all())

            if not items:
                job.status = "completed"
                await db.commit()
                return

            if job.scan_mode == "deep":
                from app.services.batch_processor import process_job
                await process_job(job_id, db)
            else:
                from app.services.fast_scan_processor import fast_scan_process
                await fast_scan_process(job, items, db)

    except Exception:
        logger.exception("Error en background job %s", job_id)
        # Marcar como failed
        try:
            async with async_session() as db:
                job = await db.get(Job, UUID(job_id))
                if job:
                    job.status = "failed"
                    await db.commit()
        except Exception:
            pass
