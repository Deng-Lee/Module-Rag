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


def test_load_settings_qa_file_skips_implicit_local_override(tmp_path: Path) -> None:
    repo = tmp_path
    config_dir = repo / "config"
    config_dir.mkdir(parents=True)

    settings_yaml = config_dir / "settings.qa.demo.yaml"
    settings_yaml.write_text(
        """
providers:
  reranker:
    provider_id: openai_compatible_llm
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (config_dir / "local.override.yaml").write_text(
        """
providers:
  reranker:
    provider_id: openai_compatible_vision
""".strip()
        + "\n",
        encoding="utf-8",
    )

    s = load_settings(settings_yaml)
    assert ((s.raw.get("providers") or {}).get("reranker") or {}).get("provider_id") == (
        "openai_compatible_llm"
    )
