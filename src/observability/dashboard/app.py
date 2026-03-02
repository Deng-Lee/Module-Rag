from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from ...core.strategy import load_settings
from .api import router as api_router


def create_app(settings: Any | None = None) -> FastAPI:
    if settings is None:
        settings = load_settings("config/settings.yaml")

    app = FastAPI(title="MODULE-RAG Dashboard API", version="0.1.0")
    app.state.settings = settings
    app.include_router(api_router)
    return app
