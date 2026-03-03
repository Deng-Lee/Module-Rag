from __future__ import annotations

import base64
import json
import mimetypes
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from ....ingestion.stages.transform.transform_post import Enricher


_ASSET_LINK_RE = re.compile(r"asset://(?P<asset_id>[a-f0-9]{64})")


@dataclass
class OpenAICompatibleVisionEnricher(Enricher):
    """Generate OCR + caption snippets for images referenced in chunk text.

    This enricher scans for `asset://{sha256}` links in the facts layer and calls an
    OpenAI-compatible vision endpoint to produce a compact JSON payload.
    """

    base_url: str
    api_key: str
    model: str
    assets_dir: str = "data/assets"
    timeout_s: float = 60.0
    max_assets_per_chunk: int = 3

    def enrich(self, chunk):  # type: ignore[override]
        text = getattr(chunk, "text", "") or ""
        asset_ids = list(dict.fromkeys(_ASSET_LINK_RE.findall(text)))
        if not asset_ids:
            return {}
        asset_ids = asset_ids[: max(0, int(self.max_assets_per_chunk))]
        if not asset_ids:
            return {}

        snippets: list[str] = []
        for asset_id in asset_ids:
            payload = self._caption_and_ocr(asset_id)
            if not payload:
                continue
            caption = (payload.get("caption") or "").strip()
            ocr = (payload.get("ocr_text") or "").strip()
            if caption:
                snippets.append(f"[image_caption asset_id={asset_id}] {caption}")
            if ocr:
                snippets.append(f"[image_ocr asset_id={asset_id}] {ocr}")

        if not snippets:
            return {}
        return {"vision_snippets": snippets}

    def _caption_and_ocr(self, asset_id: str) -> dict[str, Any] | None:
        path = _resolve_asset_path(Path(self.assets_dir), asset_id)
        if path is None:
            return None

        data_url = _to_data_url(path)
        if not data_url:
            return None

        url = self._join(self.base_url, "/chat/completions")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        system = (
            "You are an OCR+caption generator for RAG ingestion. "
            "Return strict JSON with keys: caption (string), ocr_text (string). "
            "Keep both concise; ocr_text should include only visible text."
        )
        user_text = "Generate caption and OCR text for this image."

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_text},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
            "temperature": 0.0,
        }

        with httpx.Client(timeout=self.timeout_s) as client:
            res = client.post(url, headers=headers, json=payload)
            res.raise_for_status()
            data = res.json()

        content = _extract_text(data)
        if not content:
            return None
        try:
            obj = json.loads(_extract_json(content))
            if isinstance(obj, dict):
                return obj
        except Exception:
            return None
        return None

    @staticmethod
    def _join(base: str, path: str) -> str:
        base = base.rstrip("/")
        return f"{base}{path}"


def _resolve_asset_path(assets_dir: Path, asset_id: str) -> Path | None:
    if not assets_dir.exists():
        return None
    candidates = list(assets_dir.glob(f"{asset_id}.*"))
    if not candidates:
        return None
    # Prefer common image extensions.
    preferred = [".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"]
    for ext in preferred:
        for p in candidates:
            if p.suffix.lower() == ext:
                return p
    return candidates[0]


def _to_data_url(path: Path) -> str | None:
    try:
        data = path.read_bytes()
    except Exception:
        return None
    mime, _ = mimetypes.guess_type(path.name)
    if not mime:
        mime = "application/octet-stream"
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _extract_text(data: Any) -> str:
    if not isinstance(data, dict):
        return ""
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if isinstance(first, dict):
        msg = first.get("message")
        if isinstance(msg, dict) and isinstance(msg.get("content"), str):
            return msg["content"]
        if isinstance(first.get("text"), str):
            return first["text"]
    return ""


def _extract_json(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1]
    return text

