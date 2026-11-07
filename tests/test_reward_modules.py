"""The two reward modules must stay independent of each other."""

from __future__ import annotations

import subprocess
import sys

import pytest


def _modules_after(import_stmt: str) -> set[str]:
    code = (
        "import sys\n"
        f"{import_stmt}\n"
        "print('\\n'.join(sorted(sys.modules)))\n"
    )
    out = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert out.returncode == 0, out.stderr
    return set(out.stdout.split())


def test_policy_module_does_not_pull_in_the_sink() -> None:
    loaded = _modules_after("import web_grid_paradigm.reward.policy")
    assert "web_grid_paradigm.reward.policy" in loaded
    assert "web_grid_paradigm.reward.sink" not in loaded


def test_sink_module_does_not_pull_in_the_policy() -> None:
    loaded = _modules_after("import web_grid_paradigm.reward.sink")
    assert "web_grid_paradigm.reward.sink" in loaded
    assert "web_grid_paradigm.reward.policy" not in loaded


def test_package_import_loads_neither_module_eagerly() -> None:
    loaded = _modules_after("import web_grid_paradigm.reward")
    assert "web_grid_paradigm.reward.policy" not in loaded
    assert "web_grid_paradigm.reward.sink" not in loaded


@pytest.mark.parametrize(
    ("module", "names"),
    [
        ("web_grid_paradigm.reward.policy", ("Reward", "build_reward_policy")),
        ("web_grid_paradigm.reward.sink", ("RewardSink", "build_reward_sink")),
    ],
)
def test_public_api_of_each_module(module: str, names: tuple[str, ...]) -> None:
    loaded = _modules_after(f"from {module} import {', '.join(names)}")
    assert module in loaded
