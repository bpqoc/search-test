"""Run git with settings that suit unattended bulk syncing."""

import os
import subprocess
from pathlib import Path

# A repo that 404s makes git ask for credentials, which would hang an unattended sync.
_ENV = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}


class GitError(RuntimeError):
    pass


def git(cwd: Path | None, *args: str | Path) -> str:
    """Run a git command and return its stdout.

    Args:
        cwd: Directory to run in (a repo, bare repo or worktree), or None for remote-only
            commands like `ls-remote`.
        *args: Arguments after `git`.

    Returns:
        The command's stdout.

    Raises:
        GitError: If git exits non-zero, carrying its stderr.
    """
    # Explicit UTF-8: text mode otherwise decodes with the locale's code page on Windows.
    result = subprocess.run(
        ["git", *map(str, args)],
        cwd=cwd,
        env=_ENV,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode:
        raise GitError(f"git {' '.join(map(str, args[:2]))}: {result.stderr.strip()}")
    return result.stdout
