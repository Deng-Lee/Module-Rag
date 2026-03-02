from __future__ import annotations

from pathlib import Path

import uvicorn

from ...core.strategy import load_settings
from .app import create_app


def main(settings_path: str | Path = "config/settings.yaml") -> None:
    settings = load_settings(settings_path)
    app = create_app(settings)
    uvicorn.run(
        app,
        host=settings.server.dashboard_host,
        port=int(settings.server.dashboard_port),
        log_level="info",
    )


if __name__ == "__main__":
    main()
