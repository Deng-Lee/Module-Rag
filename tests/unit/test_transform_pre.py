from __future__ import annotations

from src.ingestion.stages import DefaultTransformPre, TransformPreStage
from src.libs.interfaces.loader import NormalizedAssets


def test_transform_pre_rewrite_and_norm() -> None:
    md = "Line1\r\n\r\n![a](img.png)\r\n\r\n\r\nLine2\r\n"
    # url=img.png, line=3, col=1
    import hashlib

    ref_id = hashlib.sha256(b"img.png|3|1").hexdigest()
    norm_assets = NormalizedAssets(ref_to_asset_id={ref_id: "asset123"})

    stage = TransformPreStage(transformer=DefaultTransformPre(profile_id="default"))
    md_norm = stage.run(md, norm_assets)

    assert "\r" not in md_norm
    assert "asset://asset123" in md_norm
    # collapse 3+ blank lines to 2
    assert "\n\n\n" not in md_norm
    assert md_norm.endswith("\n")


def test_transform_pre_deterministic() -> None:
    md = "A\n\n![a](img.png)\n\nB\n"
    stage = TransformPreStage(transformer=DefaultTransformPre(profile_id="default"))
    md1 = stage.run(md, None)
    md2 = stage.run(md, None)
    assert md1 == md2
