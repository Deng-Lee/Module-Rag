from __future__ import annotations

from dataclasses import dataclass

from ....libs.interfaces.loader.base_transform import BaseTransform
from ....libs.interfaces.loader.loader import NormalizedAssets
from .base_transform import apply_pre_transform


@dataclass
class DefaultTransformPre(BaseTransform):
    profile_id: str = "default"

    def apply(self, md: str, *, ref_id_to_asset_id: dict[str, str] | None, profile_id: str) -> str:
        return apply_pre_transform(md, ref_id_to_asset_id=ref_id_to_asset_id, profile_id=profile_id)


@dataclass
class TransformPreStage:
    transformer: BaseTransform

    def run(self, md: str, normalized_assets: NormalizedAssets | None) -> str:
        ref_map = normalized_assets.ref_to_asset_id if normalized_assets else {}
        # profile_id is carried by the transformer instance
        profile_id = getattr(self.transformer, "profile_id", "default")
        return self.transformer.apply(md, ref_id_to_asset_id=ref_map, profile_id=profile_id)
