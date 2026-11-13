"""FastAPI application entrypoint.

`create_app()` keeps the factory pattern so tests can build a fresh app per
test. Database tables are created on startup; the transcription engine loads
lazily on first use.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sokhan import __version__
from sokhan.config import get_settings
from sokhan.db import configure, create_all

logger = logging.getLogger("sokhan")


def create_app() -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure()
        create_all()
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
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from sokhan.api import routes_auth, routes_jobs, routes_misc, routes_openai

    app.include_router(routes_auth.router)
    app.include_router(routes_jobs.router)
    app.include_router(routes_misc.router)
    app.include_router(routes_openai.router)

    @app.get("/")
    def root() -> dict:
        return {"name": "Sokhan API", "version": __version__, "docs": "/docs"}

    return app


app = create_app()
