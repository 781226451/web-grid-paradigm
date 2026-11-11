"""Record the exact code revision used for a session.

The branch alone is not enough for reproducibility: a branch is mutable and a
dirty worktree has code that no commit describes.  This module collects the
full commit, the branch, and whether tracked or untracked files differ from
``HEAD``.  ``git status --porcelain=v2 --branch`` does all three in one
cross-platform subprocess; there is no shell and no GitPython dependency.

If Git is unavailable, the branch is still recovered from ``.git/HEAD`` via
:func:`web_grid_paradigm.app.log.git_branch`; the commit and clean/dirty state
are then unknown.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .log import git_branch


def _repo_root() -> Path:
    """Find the checkout containing this source file, or the working directory."""
    for start in (Path(__file__).resolve(), Path.cwd().resolve()):
        for parent in (start, *start.parents):
            if (parent / ".git").exists():
                return parent
    return Path.cwd()


def _git_env() -> dict[str, str]:
    env = os.environ.copy()
    env["GIT_OPTIONAL_LOCKS"] = "0"
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


def _git(root: Path, *args: str, timeout: float = 5.0) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        cwd=str(root),
        env=_git_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )


def parse_git_status_v2(text: str) -> dict[str, Any]:
    """Parse ``git status --porcelain=v2 --branch`` output."""
    branch: str | None = None
    commit: str | None = None
    changes: list[str] = []
    for line in text.splitlines():
        if line.startswith("# branch.oid "):
            value = line[len("# branch.oid ") :].strip()
            if value not in ("", "(initial)"):
                commit = value
        elif line.startswith("# branch.head "):
            value = line[len("# branch.head ") :].strip()
            if value not in ("", "(detached)", "(unknown)"):
                branch = value
        elif line.startswith("#"):
            continue
        elif line.strip():
            changes.append(line)
    return {
        "branch": branch,
        "commit": commit,
        "commit_short": commit[:7] if commit else None,
        "dirty": bool(changes),
        "changes": changes,
        "git": True,
    }


def _fallback(error: str | None = None) -> dict[str, Any]:
    branch = git_branch()
    return {
        "branch": None if branch == "unknown" else branch,
        "commit": None,
        "commit_short": None,
        "dirty": None,
        "changes": [],
        "git": False,
        "error": error,
    }


def collect_code_version() -> dict[str, Any]:
    """Snapshot branch, commit and dirty state at session start.

    ``dirty`` is ``True`` when tracked or untracked files differ from ``HEAD``,
    ``False`` only when Git could prove the worktree is clean, and ``None``
    when Git is unavailable.
    """
    root = _repo_root()
    try:
        result = _git(
            root,
            "status",
            "--porcelain=v2",
            "--branch",
            "--untracked-files=normal",
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return _fallback(str(exc))
    if result.returncode != 0:
        return _fallback(result.stderr.strip() or f"git exited {result.returncode}")
    version = parse_git_status_v2(result.stdout)
    version["repository"] = str(root)
    return version


def format_code_version(version: dict[str, Any]) -> str:
    """One-line label such as ``dev@86e4301 (clean)``."""
    branch = version.get("branch") or "detached"
    short = version.get("commit_short") or "unknown"
    dirty = version.get("dirty")
    state = "clean" if dirty is False else "dirty" if dirty is True else "unknown"
    return f"{branch}@{short} ({state})"


def write_code_version(
    directory: Path, version: dict[str, Any], *, include_diff: bool = True
) -> Path:
    """Write ``code_version.json`` (and, when dirty, ``code.diff``)."""
    directory.mkdir(parents=True, exist_ok=True)
    payload = dict(version)
    payload["recorded_at"] = datetime.now(timezone.utc).isoformat()
    diff = ""
    if include_diff and version.get("dirty"):
        try:
            result = _git(
                Path(version.get("repository") or _repo_root()),
                "diff",
                "HEAD",
                "--binary",
                "--no-ext-diff",
            )
        except (OSError, subprocess.SubprocessError):
            result = None
        if result is not None and result.returncode == 0:
            diff = result.stdout
    if diff:
        payload["diff_sha256"] = hashlib.sha256(diff.encode("utf-8")).hexdigest()
        (directory / "code.diff").write_text(diff, encoding="utf-8", newline="\n")
    path = directory / "code_version.json"
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path
