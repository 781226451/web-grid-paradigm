"""Name -> strategy registry and factory.

New input sources only have to add a module that decorates its class with
:func:`register_source`; the factory and the runner stay untouched.  This is
the extension point that makes the strategy pattern configurable: the
configuration file only names a strategy, never imports one.
"""

from __future__ import annotations

from typing import Any, TypeVar

from .base import DeviceContext, InputSource

_S = TypeVar("_S", bound=InputSource)
_SOURCES: dict[str, type[InputSource]] = {}


def register_source(name: str):
    """Class decorator registering a strategy under ``name``."""

    key = name.strip().lower()
    if not key:
        raise ValueError("input source name must not be empty")

    def _register(cls: type[_S]) -> type[_S]:
        if key in _SOURCES:
            existing = _SOURCES[key]
            raise ValueError(
                f"input source {key!r} is already registered by "
                f"{existing.__module__}.{existing.__qualname__}"
            )
        _SOURCES[key] = cls
        return cls

    return _register


def available_sources() -> tuple[str, ...]:
    """Names of all registered strategies, sorted for stable output."""
    return tuple(sorted(_SOURCES))


def get_source_class(name: str) -> type[InputSource]:
    """Return the strategy class registered under ``name``."""
    key = str(name).strip().lower()
    try:
        return _SOURCES[key]
    except KeyError:
        choices = ", ".join(available_sources()) or "(none)"
        raise ValueError(
            f"unknown input source {name!r}; available: {choices}"
        ) from None


def build_input_source(
    name: str,
    *,
    options: Any = None,
    context: DeviceContext | None = None,
) -> InputSource:
    """Instantiate the strategy selected by configuration.

    ``options`` is the strategy-specific configuration object (for example
    :class:`~web_grid_paradigm.inputs.mouse.MouseOptions`); ``context`` carries
    the shared application objects.  The factory does not open the device —
    that is the caller's explicit :meth:`InputSource.open` call.
    """
    return get_source_class(name)(options=options, context=context)
