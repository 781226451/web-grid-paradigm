from __future__ import annotations

from web_grid_paradigm.app.provenance import (
    format_code_version,
    parse_git_status_v2,
)


def test_parse_clean_status_v2() -> None:
    text = (
        "# branch.oid 0123456789abcdef0123456789abcdef01234567\n"
        "# branch.head dev\n"
    )
    version = parse_git_status_v2(text)
    assert version["branch"] == "dev"
    assert version["commit"] == "0123456789abcdef0123456789abcdef01234567"
    assert version["commit_short"] == "0123456"
    assert version["dirty"] is False
    assert version["changes"] == []


def test_parse_dirty_status_v2() -> None:
    text = (
        "# branch.oid abcdef0123456789abcdef0123456789abcdef01\n"
        "# branch.head feature/x\n"
        "1 .M N... 100644 100644 100644 aaaaaaa bbbbbbb src/app.py\n"
        "? notes.txt\n"
    )
    version = parse_git_status_v2(text)
    assert version["branch"] == "feature/x"
    assert version["dirty"] is True
    assert len(version["changes"]) == 2


def test_parse_detached_status_v2() -> None:
    text = (
        "# branch.oid abcdef0123456789abcdef0123456789abcdef01\n"
        "# branch.head (detached)\n"
    )
    version = parse_git_status_v2(text)
    assert version["branch"] is None
    assert version["commit_short"] == "abcdef0"


def test_format_code_version_states() -> None:
    base = {"branch": "dev", "commit_short": "86e4301"}
    assert format_code_version({**base, "dirty": False}) == "dev@86e4301 (clean)"
    assert format_code_version({**base, "dirty": True}) == "dev@86e4301 (dirty)"
    assert format_code_version({**base, "dirty": None}) == "dev@86e4301 (unknown)"
    assert (
        format_code_version({"branch": None, "commit_short": None, "dirty": None})
        == "detached@unknown (unknown)"
    )
