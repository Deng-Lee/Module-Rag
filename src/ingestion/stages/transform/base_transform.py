from __future__ import annotations

import re


_IMG_RE = re.compile(
    r"!\[(?P<alt>[^\]]*)\]\((?P<url>[^)\s]+)(?P<tail>(?:\s+\"[^\"]*\")?)\)"
)


def rewrite_image_links(md: str, ref_id_to_asset_id: dict[str, str]) -> str:
    """
    Rewrite Markdown image links to `asset://{asset_id}` when ref_id matches.

    The ref_id is computed the same way as MarkdownLoader: sha256("{url}|{line}|{col}"),
    where col is 1-based and points to the start of the image token (`!`).
    """
    if not ref_id_to_asset_id:
        return md

    out_lines: list[str] = []
    for line_no, line in enumerate(md.splitlines(), start=1):
        cursor = 0
        parts: list[str] = []
        for m in _IMG_RE.finditer(line):
            parts.append(line[cursor : m.start()])

            url = m.group("url")
            col = m.start() + 1
            ref_id = _compute_md_ref_id(url, line_no, col)
            asset_id = ref_id_to_asset_id.get(ref_id)

            if asset_id:
                rewritten = f"![{m.group('alt')}](asset://{asset_id}{m.group('tail')})"
                parts.append(rewritten)
            else:
                parts.append(m.group(0))

            cursor = m.end()

        parts.append(line[cursor:])
        out_lines.append("".join(parts))
    return "\n".join(out_lines)


def normalize_markdown(md: str, *, profile_id: str = "default") -> str:
    """
    Pre-normalize Markdown for stable splitting (does not change semantics).

    This is intentionally weaker than canonical(chunk_text): it operates at the
    document level to stabilize section/chunk boundaries across platforms.
    """
    _ = profile_id  # reserved for versioned profiles

    # BOM + newline normalization
    if md.startswith("\ufeff"):
        md = md[1:]
    md = md.replace("\r\n", "\n").replace("\r", "\n")

    # Strip trailing whitespace on each line
    lines = [ln.rstrip(" \t") for ln in md.split("\n")]

    # Collapse multiple blank lines into a single blank line.
    out: list[str] = []
    blank_run = 0
    for ln in lines:
        if ln.strip() == "":
            blank_run += 1
            if blank_run <= 1:
                out.append("")
            continue
        blank_run = 0
        out.append(ln)

    norm = "\n".join(out).strip("\n")
    return norm + "\n" if norm else ""


def apply_pre_transform(md: str, *, ref_id_to_asset_id: dict[str, str] | None, profile_id: str) -> str:
    rewritten = rewrite_image_links(md, ref_id_to_asset_id or {})
    return normalize_markdown(rewritten, profile_id=profile_id)


def _compute_md_ref_id(url: str, line: int, col: int) -> str:
    import hashlib

    key = f"{url}|{line}|{col}".encode("utf-8")
    return hashlib.sha256(key).hexdigest()
