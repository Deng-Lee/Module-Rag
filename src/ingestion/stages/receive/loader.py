from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ....libs.interfaces.loader import BaseLoader, LoaderOutput


@dataclass
class LoaderStage:
    loaders: dict[str, BaseLoader]

    def run(self, file_path: str | Path, *, doc_id: str | None = None, version_id: str | None = None) -> LoaderOutput:
        p = Path(file_path)
        ftype = detect_file_type(p)
        loader = self.loaders.get(ftype)
        if loader is None:
            raise ValueError(f"no loader for type: {ftype}")
        return loader.load(str(p), doc_id=doc_id, version_id=version_id)


def detect_file_type(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in {".md", ".markdown"}:
        return "md"
    if ext == ".pdf":
        return "pdf"
    raise ValueError(f"unsupported file type: {ext or path.name}")
