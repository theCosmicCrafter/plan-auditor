"""Console-output helpers shared by Plan Auditor entry points."""

from __future__ import annotations

import sys


def configure_console_output() -> None:
    """Make console output non-fatal on legacy terminal encodings.

    The CLI can print user-controlled plan text, paths, and command-output tails.
    Those strings are valid Unicode but may not fit the active terminal encoding
    (notably cp1252 on Windows). Escaping unrepresentable characters keeps the
    process exit code tied to verification rather than terminal configuration.
    Streams that cannot be reconfigured, including test capture objects, are
    left unchanged.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if not callable(reconfigure):
            continue
        try:
            reconfigure(errors="backslashreplace")
        except (OSError, TypeError, ValueError):
            # A closed, detached, or nonstandard stream must never change the
            # verification result. JSON output is separately ASCII-safe.
            pass
