from __future__ import annotations

import io
import sys
import unittest
from unittest.mock import patch

from console_output import ensure_utf8_console, safe_print


class _Cp1252Stream(io.StringIO):
    """Mimics a Windows console code page that cannot encode Cyrillic text."""

    encoding = "cp1252"

    def write(self, text):
        text.encode(self.encoding)  # raises UnicodeEncodeError for Cyrillic
        return super().write(text)


class ConsoleOutputTests(unittest.TestCase):
    def test_safe_print_replaces_unencodable_characters(self):
        stream = _Cp1252Stream()
        with patch.object(sys, "stdout", stream):
            safe_print(r"Автоматическая резервная копия: C:\data\backup.zip")
        written = stream.getvalue()
        self.assertTrue(written.strip())
        self.assertIn("backup.zip", written)
        self.assertTrue(written.isascii())

    def test_safe_print_does_not_raise_without_a_console(self):
        with patch.object(sys, "stdout", None):
            safe_print("Автоматическая резервная копия")  # must not raise

    def test_ensure_utf8_console_tolerates_streams_without_reconfigure(self):
        with (
            patch.object(sys, "stdout", io.StringIO()),
            patch.object(sys, "stderr", io.StringIO()),
        ):
            ensure_utf8_console()  # must not raise


if __name__ == "__main__":
    unittest.main()
