from __future__ import annotations

from pathlib import Path

from web_grid_paradigm.app.log import _branch_from_head, _find_git_dir


def test_reads_symbolic_head_without_git(tmp_path: Path) -> None:
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "HEAD").write_text("ref: refs/heads/feature/mouse\n", encoding="utf-8")

    assert _find_git_dir(tmp_path) == git_dir
    assert _branch_from_head(git_dir) == "feature/mouse"


def test_reads_worktree_gitdir_file(tmp_path: Path) -> None:
    real_git_dir = tmp_path / "real-git"
    real_git_dir.mkdir()
    (real_git_dir / "HEAD").write_text("ref: refs/heads/dev\n", encoding="utf-8")
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    (worktree / ".git").write_text(f"gitdir: {real_git_dir}\n", encoding="utf-8")

    assert _find_git_dir(worktree) == real_git_dir
    assert _branch_from_head(real_git_dir) == "dev"


def test_detached_head_has_no_branch_name(tmp_path: Path) -> None:
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "HEAD").write_text("0123456789abcdef\n", encoding="utf-8")

    assert _branch_from_head(git_dir) == "HEAD"
