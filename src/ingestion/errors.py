from __future__ import annotations

from dataclasses import dataclass


@dataclass
class IngestionError(Exception):
    stage: str
    message: str

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.stage}: {self.message}"


class StageExecutionError(IngestionError):
    def __init__(self, stage: str, message: str | None = None) -> None:
        super().__init__(stage=stage, message=message or "stage failed")
