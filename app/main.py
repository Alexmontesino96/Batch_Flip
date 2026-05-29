import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.core.security_config import SECURITY_HEADERS

REQUIRED_CORS_ORIGINS = {
    "https://flipiqbatch.com",
    "https://www.flipiqbatch.com",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Agrega security headers a todas las responses (OWASP + Amazon DPP)."""

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        for header, value in SECURITY_HEADERS.items():
            response.headers[header] = value
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(settings.upload_dir, exist_ok=True)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )

    # Security headers middleware
    app.add_middleware(SecurityHeadersMiddleware)

    # CORS — whitelist explícita, no wildcard. Required production origins are
    # included in code so a stale Render env var cannot block auth preflights.
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
