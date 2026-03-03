from __future__ import annotations

from dataclasses import dataclass

from ....ingestion.stages.transform.transform_post import Enricher


@dataclass
class NoopEnricher(Enricher):
    def enrich(self, chunk):  # type: ignore[override]
        _ = chunk
        return {}

