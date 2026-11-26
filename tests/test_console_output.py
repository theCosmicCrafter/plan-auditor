"""Regression tests for legacy-terminal console output."""

from __future__ import annotations

import io
import json
import sys

from scripts.console import configure_console_output
from supervisor.cli import _json


def _cp1252_stream() -> tuple[io.BytesIO, io.TextIOWrapper]:
    buffer = io.BytesIO()
    return buffer, io.TextIOWrapper(buffer, encoding="cp1252", errors="strict")


def test_console_configuration_prevents_unicode_encode_crash(monkeypatch) -> None:
    stdout_buffer, stdout = _cp1252_stream()
    stderr_buffer, stderr = _cp1252_stream()
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", stderr)

    configure_console_output()
    print("Türkçe: doğrulama — tamam")

    stdout.flush()
    stderr.flush()
    rendered = stdout_buffer.getvalue().decode("cp1252")
    assert "\\u011f" in rendered
    assert "—" in rendered
    assert stderr_buffer.getvalue() == b""


def test_supervisor_json_output_is_ascii_on_cp1252(monkeypatch) -> None:
    stdout_buffer, stdout = _cp1252_stream()
    monkeypatch.setattr(sys, "stdout", stdout)

    _json({"message": "Türkçe: doğrulama", "nested": {"dotless": "ı"}})
    stdout.flush()

    raw = stdout_buffer.getvalue()
    assert all(byte < 128 for byte in raw)
    document = json.loads(raw.decode("ascii"))
    assert document["message"] == "Türkçe: doğrulama"
    assert document["nested"]["dotless"] == "ı"
