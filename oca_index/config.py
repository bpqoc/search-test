"""The team's oca-index.toml, and the oca-reference Config it implies."""

import tomllib
from dataclasses import dataclass
from pathlib import Path

from oca_reference.config import Config as RefConfig
from oca_reference.config import load_defaults

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "oca-index.toml"
DATA = ROOT / "data"
WORK = ROOT / "work"
SUMMARIES_PATH = DATA / "summaries.jsonl"
MIGRATIONS_PATH = DATA / "migrations.jsonl"


@dataclass(frozen=True)
class Settings:
    versions: tuple[str, ...]
    exclude_repos: tuple[str, ...]
    keep_repos: tuple[str, ...]
    exclude_modules: tuple[str, ...]
    data_dir: Path
    summary_model: str
    batch_size: int
    migrations_url: str

    def ref_config(self) -> RefConfig:
        """oca-reference settings for sync and parsing; the rest keep its shipped defaults."""
        defaults = load_defaults()
        return RefConfig(
            org="OCA",
            versions=self.versions,
            default_version=self.versions[-1],
            exclude_repos=self.exclude_repos,
            keep_repos=self.keep_repos,
            exclude_modules=self.exclude_modules,
            sparse_exclude=tuple(defaults["sparse_exclude"]),
            parallel=defaults["parallel"],
            embed_model=defaults["embed_model"],
            auto_sync=False,
            auto_sync_days=defaults["auto_sync_days"],
        )


def parse_settings(raw: dict) -> Settings:
    summaries = raw.get("summaries", {})
    return Settings(
        versions=tuple(raw["versions"]),
        exclude_repos=tuple(raw.get("exclude_repos", ())),
        keep_repos=tuple(raw.get("keep_repos", ())),
        exclude_modules=tuple(raw.get("exclude_modules", ())),
        data_dir=Path(raw["data_dir"]).expanduser(),
        summary_model=summaries.get("model", "claude-haiku-5-5"),
        batch_size=summaries.get("batch_size", 220),
        migrations_url=raw.get("skill", {}).get("migrations_url", ""),
    )


def load_settings(path: Path = CONFIG_PATH) -> Settings:
    with path.open("rb") as f:
        return parse_settings(tomllib.load(f))
