"""Trap listener lifecycle helpers.

The trap listener is a long-running subprocess started via :mod:`backend.traps.manager`.
For test runs we want a predictable lifecycle:

* start the listener right before pytest begins
* stop the listener right after pytest ends

Because the listener is global (single process), we only stop it if this context
manager actually started it.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Tuple

from .manager import start_trap_listener, stop_trap_listener


@contextmanager
def trap_listener_context() -> Iterator[Tuple[bool, dict]]:
    """Ensure the trap listener is running for the duration of the context.

    Yields:
        (started_by_this_context, start_result)
    """
    start_result = start_trap_listener()
    started = bool(start_result.get("started"))
    try:
        yield started, start_result
    finally:
        # Only stop if we started it; otherwise someone else owns the lifecycle.
        if started:
            stop_trap_listener()
