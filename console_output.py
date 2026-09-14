"""Console output helpers for cross-platform runs.

The application writes Russian user-facing messages to stdout. On Windows the
console still defaults to a legacy code page (for example cp1252), and a plain
``print()`` of Cyrillic text raises ``UnicodeEncodeError``. The packaged
windowed build has no console at all, but source runs and CI runs do, so output
is routed through :func:`safe_print` and standard streams are switched to UTF-8
where the interpreter supports it.
"""
from __future__ import annotations

import sys


def ensure_utf8_console() -> None:
    """Best-effort UTF-8 reconfiguration of the standard streams.

    Does nothing when the streams are missing (windowed frozen builds) or do
    not support reconfiguration.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass


def safe_print(message: str) -> None:
    """Print without ever failing on an unencodable console code page."""
    stream = sys.stdout
    if stream is None:
        # Windowed frozen application: there is no console to write to.
        return
    try:
        print(message)
    except UnicodeEncodeError:
        encoding = getattr(stream, "encoding", None) or "utf-8"
        stream.write(message.encode(encoding, "replace").decode(encoding, "replace") + "\n")
