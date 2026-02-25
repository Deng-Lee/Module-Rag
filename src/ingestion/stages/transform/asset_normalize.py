from __future__ import annotations

import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from ....libs.interfaces.loader import AssetRef, NormalizedAssets
from ..storage.assets import AssetStore


@dataclass
class FsAssetNormalizer:
    asset_store: AssetStore

    def normalize(self, assets: list[AssetRef], *, raw_path: str, md: str) -> NormalizedAssets:
        ref_to_asset_id: dict[str, str] = {}
        assets_new = 0
        assets_reused = 0
        assets_failed = 0

        raw = Path(raw_path)
        raw_bytes: bytes | None = None

        for asset in assets:
            try:
                if asset.origin_ref.startswith("asset://"):
                    asset_id = asset.origin_ref.replace("asset://", "", 1)
                    ref_to_asset_id[asset.ref_id] = asset_id
                    assets_reused += 1
                    continue

                if asset.source_type == "pdf" and raw_bytes is None:
                    raw_bytes = raw.read_bytes()

                data, suffix = _load_asset_bytes(asset, raw, raw_bytes)
                if data is None:
                    assets_failed += 1
                    continue
                asset_id, _, reused = self.asset_store.write_bytes(data, suffix)
                ref_to_asset_id[asset.ref_id] = asset_id
                if reused:
                    assets_reused += 1
                else:
                    assets_new += 1
            except Exception:
                assets_failed += 1

        return NormalizedAssets(
            ref_to_asset_id=ref_to_asset_id,
            assets_new=assets_new,
            assets_reused=assets_reused,
            assets_failed=assets_failed,
        )


def _load_asset_bytes(asset: AssetRef, raw_path: Path, raw_bytes: bytes | None) -> tuple[bytes | None, str | None]:
    if asset.source_type == "markdown":
        return _load_md_asset(asset.origin_ref, raw_path)
    if asset.source_type == "pdf":
        if raw_bytes is None:
            return None, None
        obj = _parse_pdf_obj(asset.origin_ref)
        if obj is None:
            return None, None
        data = _extract_pdf_stream(raw_bytes, obj)
        if data is None:
            return None, None
        return data, ".bin"
    return None, None


def _load_md_asset(origin_ref: str, raw_path: Path) -> tuple[bytes | None, str | None]:
    if origin_ref.startswith("http://") or origin_ref.startswith("https://"):
        data = _download(origin_ref)
        suffix = Path(urllib.parse.urlparse(origin_ref).path).suffix
        return data, suffix or ".bin"

    p = Path(origin_ref)
    if not p.is_absolute():
        p = (raw_path.parent / p).resolve()
    if not p.exists():
        return None, None
    return p.read_bytes(), p.suffix or ".bin"


def _download(url: str, timeout: float = 5.0, max_bytes: int = 10 * 1024 * 1024) -> bytes | None:
    req = urllib.request.Request(url, headers={"User-Agent": "module-rag/asset-normalizer"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError("asset too large")
    return data


def _parse_pdf_obj(origin_ref: str) -> int | None:
    if not origin_ref.startswith("pdf_obj:"):
        return None
    try:
        return int(origin_ref.split(":", 1)[1])
    except Exception:
        return None


def _extract_pdf_stream(raw: bytes, obj_num: int) -> bytes | None:
    pattern = re.compile(rb"%d\s+0\s+obj(.*?)endobj" % obj_num, re.DOTALL)
    m = pattern.search(raw)
    if not m:
        return None
    body = m.group(1)
    m2 = re.search(rb"stream\r?\n(.*?)\r?\nendstream", body, re.DOTALL)
    if not m2:
        return None
    return m2.group(1)
