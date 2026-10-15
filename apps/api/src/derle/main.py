from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from derle import __version__
from derle.api.routers import router
from derle.config import Settings, get_settings
from derle.llm.base import get_provider
from derle.storage import repo
from derle.storage.db import Database


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        db = Database(settings.db_path)
        with db.transaction() as cur:
            repo.ensure_default_workspace(cur)
        app.state.db = db
        app.state.settings = settings
        app.state.llm = get_provider(settings)
        logging.getLogger("derle").info("AI provider: %s", app.state.llm.name)
        try:
            yield
        finally:
            db.close()

    app = FastAPI(title="Derle API", version=__version__, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    return app


app = create_app()
