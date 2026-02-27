from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from pathlib import Path


@dataclass
class FsStore:
    raw_dir: Path
    md_dir: Path | None = None

    def __post_init__(self) -> None:
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        if self.md_dir is not None:
            self.md_dir.mkdir(parents=True, exist_ok=True)

    def write_stream_and_hash(self, src_path: Path, chunk_size: int = 1024 * 1024) -> tuple[str, Path]:
        tmp_path = self.raw_dir / f".tmp-{uuid.uuid4().hex}{src_path.suffix}"
        hasher = hashlib.sha256()

        with src_path.open("rb") as r, tmp_path.open("wb") as w:
            while True:
                chunk = r.read(chunk_size)
                if not chunk:
                    break
                hasher.update(chunk)
                w.write(chunk)

        file_sha256 = hasher.hexdigest()
        final_path = self.raw_dir / f"{file_sha256}{src_path.suffix}"

        if final_path.exists():
            tmp_path.unlink()
        else:
            tmp_path.rename(final_path)

        return file_sha256, final_path

    def write_md(self, doc_id: str, version_id: str, md_norm: str) -> Path:
        if self.md_dir is None:
            raise ValueError("md_dir is not configured")
        out_dir = (self.md_dir / doc_id / version_id).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "md_norm.md"
        out_path.write_text(md_norm, encoding="utf-8")
        return out_path
