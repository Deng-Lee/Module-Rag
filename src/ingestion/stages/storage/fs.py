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

    def delete_md(self, doc_id: str, version_id: str | None = None) -> int:
        if self.md_dir is None:
            return 0
        base = (self.md_dir / doc_id).resolve()
        if version_id:
            targets = [base / version_id]
        else:
            targets = list(base.glob("*"))
        removed = 0
        for t in targets:
            if t.exists() and t.is_dir():
                for p in t.rglob("*"):
                    if p.is_file():
                        try:
                            p.unlink()
                            removed += 1
                        except Exception:
                            pass
                try:
                    t.rmdir()
                except Exception:
                    pass
        # Attempt to clean doc dir if empty.
        try:
            if base.exists() and base.is_dir() and not any(base.iterdir()):
                base.rmdir()
        except Exception:
            pass
        return removed

    def delete_raw_by_hash(self, file_sha256: str) -> int:
        # Raw files are stored as "<sha256>.<ext>".
        removed = 0
        for p in self.raw_dir.glob(f"{file_sha256}.*"):
            if p.is_file():
                try:
                    p.unlink()
                    removed += 1
                except Exception:
                    pass
        return removed

    def delete_asset(self, asset_id: str, assets_dir: Path) -> int:
        removed = 0
        for p in assets_dir.glob(f"{asset_id}.*"):
            if p.is_file():
                try:
                    p.unlink()
                    removed += 1
                except Exception:
                    pass
        return removed
