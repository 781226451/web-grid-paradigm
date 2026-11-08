"""Pure experiment logic and shared contracts.

Everything in this package is headless: configuration, geometry, trial state,
scoring, text and the monitoring protocol.  No module here imports PsychoPy,
the web panel or the input strategies.
"""

from __future__ import annotations
