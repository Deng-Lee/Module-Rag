from __future__ import annotations

from pathlib import Path

from src.core.strategy.loader import load_settings


def test_load_settings_resolves_paths(tmp_path: Path) -> None:
    repo = tmp_path
    (repo / "config").mkdir(parents=True)

    settings_yaml = repo / "config" / "settings.yaml"
    settings_yaml.write_text(
        """
paths:
  data_dir: data
  raw_dir: data/raw
  logs_dir: logs
""".strip()
        + "\n",
        encoding="utf-8",
    )

    s = load_settings(settings_yaml)
    assert s.paths.data_dir.is_absolute()
    assert s.paths.raw_dir.is_absolute()
    assert s.paths.logs_dir.is_absolute()
    assert str(s.paths.data_dir).endswith("/data")
    assert str(s.paths.raw_dir).endswith("/data/raw")
    assert str(s.paths.logs_dir).endswith("/logs")

