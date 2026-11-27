"""FastAPI application entrypoint.

`create_app()` keeps the factory pattern so tests can build a fresh app per
test. Database tables are created on startup; the transcription engine loads
lazily on first use.
"""

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from sokhan import __version__
from sokhan.api.body_limit import MULTIPART_OVERHEAD_BYTES, BodySizeLimitMiddleware
from sokhan.config import get_settings
from sokhan.core.audio import StorageUnavailableError, audio_dir
from sokhan.db import configure, create_all

logger = logging.getLogger("sokhan")


def create_app() -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure()
        create_all()
        try:
            audio_dir()
        except OSError as exc:
            logger.error(
                "DATA_DIR is not writable (%s) - uploads will fail with 503 until "
                "it is; in Docker check the volume is owned by the app user",
                exc,
            )
        if not settings.celery_enabled:
            logger.warning(
                "CELERY_ENABLED=false - jobs run inline in the API process; "
                "set it to true and run the worker in production"
            )
        yield

    app = FastAPI(
        title="Sokhan API",
        description="Persian-first speech-to-text: transcripts, summaries and exports.",
        version=__version__,
        lifespan=lifespan,
        license_info={
            "name": "MIT",
            "url": "https://github.com/Abolfazlrwm/sokhan/blob/main/LICENSE",
        },
    )
    # Browsers only hit the API from the web app, so the default is the
    # local dev front-end instead of a wildcard. Deployments set
    # SOKHAN_CORS_ORIGINS (comma-separated) to the real public origins.
    cors_origins = [
        origin.strip()
        for origin in os.getenv("SOKHAN_CORS_ORIGINS", "").split(",")
        if origin.strip()
    ] or ["http://localhost:3000", "http://127.0.0.1:3000"]
    app.add_middleware(
        BodySizeLimitMiddleware,
        max_body_bytes=settings.max_upload_mb * 1024 * 1024 + MULTIPART_OVERHEAD_BYTES,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from sokhan.api import routes_admin, routes_auth, routes_jobs, routes_misc, routes_openai

    app.include_router(routes_auth.router)
    app.include_router(routes_jobs.router)
    app.include_router(routes_misc.router)
    app.include_router(routes_openai.router)
    app.include_router(routes_admin.router)

    @app.exception_handler(StorageUnavailableError)
    async def storage_unavailable(request: Request, exc: StorageUnavailableError) -> JSONResponse:
        logger.error("upload storage failed for %s %s: %s", request.method, request.url.path, exc)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": "upload storage is unavailable, try again later"},
        )

    @app.get("/")
    def root() -> dict:
        return {"name": "Sokhan API", "version": __version__, "docs": "/docs"}

    return app


app = create_app()
