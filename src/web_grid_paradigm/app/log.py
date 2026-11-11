"""Logging setup based on loguru.

All modules log through ``from loguru import logger``.  The CLI calls
:func:`setup_logging` once; a per-session file sink is attached with
:func:`add_session_log` so that every data directory carries its own log.
Records from the standard ``logging`` module (third-party libraries) are
forwarded to loguru as well.
"""

from __future__ import annotations

import inspect
import logging
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

from loguru import logger

CONSOLE_FORMAT = (
    "<green>{time:HH:mm:ss.SSS}</green> | <level>{level: <7}</level> | "
    "<level>{message}</level>"
)
DEBUG_CONSOLE_FORMAT = (
    "<green>{time:HH:mm:ss.SSS}</green> | <level>{level: <7}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
    "<level>{message}</level>"
)
FILE_FORMAT = (
    "{time:YYYY-MM-DD HH:mm:ss.SSS ZZ} | {level: <7} | "
    "{name}:{function}:{line} - {message}"
)


@lru_cache(maxsize=1)
def git_branch() -> str:
    """Best-effort current git branch, or ``unknown`` outside a checkout."""
    root = Path(__file__).resolve()
    for parent in root.parents:
        if (parent / ".git").exists():
            root = parent
            break
    else:
        root = Path.cwd()
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    branch = result.stdout.strip()
    if result.returncode != 0 or not branch:
        return "unknown"
    return branch


class InterceptHandler(logging.Handler):
    """Route standard-library logging records into loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        frame, depth = inspect.currentframe(), 0
        while frame and (depth == 0 or frame.f_code.co_filename == logging.__file__):
            frame = frame.f_back
            depth += 1
        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


class PsychoPyBridge:
    """A ``psychopy.logging`` target that forwards entries into loguru.

    PsychoPy has its own logging system (not the standard library) whose
    default console target prints lines like ``1.6930 \\tWARNING \\t...``.
    This target replaces that console so everything shares one format.
    """

    def __init__(self, level: int) -> None:
        self.level = level
        self.stream = self  # psychopy calls ``target.stream.flush()``

    def write(self, text: str) -> None:
        # psychopy formats entries as "{t:.4f} \t{levelname} \t{message}"
        for line in text.splitlines():
            if not line.strip():
                continue
            parts = line.split(" \t", 2)
            if len(parts) == 3:
                t, levelname, message = parts
            else:
                t, levelname, message = "", "INFO", line
            levelname = levelname.strip().upper()
            if levelname in ("CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"):
                level = levelname
            else:  # psychopy's custom DATA / EXP levels
                level = "DEBUG"
            suffix = f" (psychopy t={t.strip()})" if t else ""
            logger.patch(
                lambda record: record.update(
                    name="psychopy", function="logging", line=0
                )
            ).log(level, "{}{}", message.strip(), suffix)

    def flush(self) -> None:
        return None


def _bridge_psychopy(debug: bool) -> None:
    try:
        from psychopy import logging as plog
    except ImportError:  # pragma: no cover - psychopy is a hard dependency
        return
    for target in list(plog.root.targets):
        if target is plog.console or isinstance(target, PsychoPyBridge):
            plog.root.removeTarget(target)
    plog.root.addTarget(PsychoPyBridge(plog.INFO if debug else plog.WARNING))


def setup_logging(
    *, debug: bool = False, log_file: Path | None = None
) -> None:
    """Configure console (and optionally file) sinks.

    The console shows INFO and above (DEBUG with ``debug=True``).  ``log_file``
    adds a rotating DEBUG-level file sink.
    """
    logger.remove()
    logger.add(
        sys.stderr,
        level="DEBUG" if debug else "INFO",
        format=DEBUG_CONSOLE_FORMAT if debug else CONSOLE_FORMAT,
        backtrace=debug,
        diagnose=debug,
        colorize=None,
    )
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        logger.add(
            log_file,
            level="DEBUG",
            format=FILE_FORMAT,
            rotation="10 MB",
            retention=5,
            encoding="utf-8",
            enqueue=True,
            backtrace=True,
            diagnose=False,
        )
    logging.basicConfig(handlers=[InterceptHandler()], level=logging.WARNING, force=True)
    if debug:
        logging.getLogger().setLevel(logging.DEBUG)
    _bridge_psychopy(debug)


def add_session_log(directory: Path) -> int:
    """Attach a DEBUG file sink ``session.log`` inside a session directory.

    Returns the sink id; pass it to ``logger.remove`` when the session ends.
    """
    return logger.add(
        directory / "session.log",
        level="DEBUG",
        format=FILE_FORMAT,
        encoding="utf-8",
        enqueue=True,
        backtrace=True,
        diagnose=False,
    )
