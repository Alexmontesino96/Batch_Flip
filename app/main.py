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
    """Reset jobs stuck en 'processing' a 'queued' para que el polling loop los retome."""
    from sqlalchemy import text
    from app.database import async_session

    try:
        async with async_session() as db:
            result = await db.execute(text("""
                UPDATE jobs SET status = 'queued', locked_by = NULL, locked_at = NULL
                WHERE status = 'processing'
                RETURNING id
            """))
            resumed = result.fetchall()
            await db.commit()

            for row in resumed:
                logger.info("STARTUP: Reset stuck job %s → queued", row[0])

            if resumed:
                logger.info("STARTUP: %d stuck jobs reset to queued", len(resumed))
    except Exception as e:
        logger.error("STARTUP: Failed to resume stuck jobs: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    os.makedirs(settings.upload_dir, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logger.info("STARTUP: Batch Flip API starting")

    # Reset stuck jobs
    await _resume_stuck_jobs()

    # Start PG queue worker
    from app.worker.tasks import job_queue_worker
    worker_task = asyncio.create_task(job_queue_worker())
    logger.info("STARTUP: Job queue worker started")

    yield

    # Shutdown
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass
    logger.info("SHUTDOWN: Batch Flip API stopped")


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
