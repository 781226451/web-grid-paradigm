"""Web control panel: enter parameters, start a session, watch it live.

One process, one URL.  The HTTP server runs in a daemon thread; the main
thread waits for a start request, runs the PsychoPy session, and then waits
again, so the page can start another session without restarting anything.

Endpoints:

======  ==================================================================
GET     ``/``            the page (parameter form + live monitoring)
GET     ``/events``      Server-Sent Events stream (live updates)
GET     ``/api/state``   full JSON snapshot (scripts, debugging)
GET     ``/api/config``  form schema, defaults and the last used values
POST    ``/api/start``   validate the submitted parameters and start a run
POST    ``/api/stop``    abort the running session (same as pressing Esc)
POST    ``/api/lsl``     enable/disable the LSL state stream
======  ==================================================================

Modules:

``schema``      parameter form description and validation
``state``       run queue, live snapshot, per-run ``SessionView``
``server``      HTTP routes, SSE stream and the page asset
``lsl_state``   the LSL state stream publisher

The render loop only ever touches in-memory state (lock + dict assignment);
serialisation and socket writes happen in the server threads, so monitoring
never disturbs stimulus timing.
"""

from __future__ import annotations

from .lsl_state import LslStatePublisher
from .schema import coerce_params, form_schema
from .server import start_station
from .state import SessionView, Station

__all__ = [
    "LslStatePublisher",
    "SessionView",
    "Station",
    "coerce_params",
    "form_schema",
    "start_station",
]
