import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.core.security_config import SECURITY_HEADERS

logger = logging.getLogger(__name__)

REQUIRED_CORS_ORIGINS = {
    "https://flipiqbatch.com",
    "https://www.flipiqbatch.com",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        for header, value in SECURITY_HEADERS.items():
            response.headers[header] = value
        return response


async def _resume_stuck_jobs():
    """Resume jobs that were processing when the instance was recycled.

    Runs on startup. Finds jobs with status='processing' and pending items,
    then re-enqueues them for background processing.
    """
    from app.database import async_session
    from sqlalchemy import select, text

    try:
        async with async_session() as db:
            result = await db.execute(text(
                "SELECT id, total_items, processed_items FROM jobs WHERE status = 'processing'"
            ))
            stuck_jobs = result.fetchall()

            if not stuck_jobs:
                return

            for job_id, total, processed in stuck_jobs:
                logger.info("STARTUP: Resuming stuck job %s (%d/%d items)", job_id, processed, total)
                from app.worker.tasks import enqueue_job
                await enqueue_job(str(job_id))

            logger.info("STARTUP: Resumed %d stuck jobs", len(stuck_jobs))
    except Exception as e:
        logger.error("STARTUP: Failed to resume stuck jobs: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    os.makedirs(settings.upload_dir, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logger.info("STARTUP: Batch Flip API starting")

    # Resume stuck jobs after a small delay (let DB connections warm up)
    await asyncio.sleep(2)
    await _resume_stuck_jobs()

    yield
    # Shutdown
    logger.info("SHUTDOWN: Batch Flip API stopping")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(SecurityHeadersMiddleware)

    origins = sorted({
        o.strip()
        for o in settings.cors_origins.split(",")
        if o.strip()
    } | REQUIRED_CORS_ORIGINS)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
        allow_headers=["*"],
    )

    from app.api.v1.router import v1_router
    app.include_router(v1_router, prefix="/api/v1")

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


app = create_app()
