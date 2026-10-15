"""The team's oca-index.toml."""

import tomllib
from collections.abc import Iterable
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path

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

    def repo_selected(self, repo: str) -> bool:
        """Not matched by `exclude_repos`, or rescued by `keep_repos`."""
        return _matches(repo, self.keep_repos) or not _matches(repo, self.exclude_repos)

    def module_selected(self, module: str) -> bool:
        return not _matches(module, self.exclude_modules)


def _matches(name: str, patterns: Iterable[str]) -> bool:
    # Case-sensitive so a pattern means the same on every platform, like GitHub repo names
    return any(fnmatchcase(name, p) for p in patterns)


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
