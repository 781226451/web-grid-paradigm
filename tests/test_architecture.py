"""Guard the package layout and import direction introduced by the refactor."""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "src" / "web_grid_paradigm"
PACKAGE = "web_grid_paradigm"

# Each subsystem may only import from the packages allowed to be below it.
FORBIDDEN = {
    "core": {"app", "panel", "presentation", "recording", "reward", "velocity_inputs"},
    "presentation": {"app", "panel", "recording", "reward", "velocity_inputs"},
    "velocity_inputs": {"app", "panel", "presentation", "recording", "reward"},
    "recording": {"app", "panel", "presentation", "velocity_inputs"},
    "reward": {"app", "panel", "presentation", "recording", "velocity_inputs"},
    "panel": {"app", "presentation", "velocity_inputs"},
}

# The headless core must stay free of display and hardware libraries.
CORE_FORBIDDEN_EXTERNAL = {"psychopy", "pylsl", "serial", "loguru"}


def _package_name(path: Path) -> str:
    relative = path.relative_to(PACKAGE_ROOT).with_suffix("")
    return ".".join((PACKAGE, *relative.parts[:-1]))


def _absolute_import(node: ast.AST, package: str) -> str | None:
    if isinstance(node, ast.Import):
        return node.names[0].name
    if not isinstance(node, ast.ImportFrom):
        return None
    if not node.level:
        return node.module or ""
    relative = "." * node.level + (node.module or "")
    try:
        return importlib.util.resolve_name(relative, package)
    except (ImportError, ValueError):
        return None


def _target(module: str) -> str | None:
    if module == PACKAGE:
        return None
    prefix = PACKAGE + "."
    if not module.startswith(prefix):
        return None
    return module[len(prefix) :].split(".", 1)[0]


def _violations() -> list[str]:
    problems: list[str] = []
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        relative = path.relative_to(PACKAGE_ROOT)
        top = relative.parts[0] if len(relative.parts) > 1 else None
        if top is None:
            continue
        package = _package_name(path)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            module = _absolute_import(node, package)
            if not module:
                continue
            if top == "core" and module.split(".", 1)[0] in CORE_FORBIDDEN_EXTERNAL:
                problems.append(f"{relative}: core imports {module}")
                continue
            target = _target(module)
            if target and target in FORBIDDEN.get(top, set()):
                problems.append(f"{relative}: {top} imports {target} ({module})")
    return problems


def test_root_has_only_package_metadata() -> None:
    root_modules = {path.name for path in PACKAGE_ROOT.glob("*.py")}
    assert root_modules == {"__init__.py", "__main__.py"}


def test_subsystem_imports_follow_the_layering_rules() -> None:
    problems = _violations()
    assert not problems, "import direction violations:\n" + "\n".join(problems)
