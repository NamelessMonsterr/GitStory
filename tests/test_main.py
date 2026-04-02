"""Regression tests for CLI output safety."""

from __future__ import annotations

import io

from main import _safe_for_stream


def test_safe_for_stream_preserves_utf8_output() -> None:
    stream = io.TextIOWrapper(io.BytesIO(), encoding="utf-8", errors="strict")

    text = "risk marker 🟡 stays intact"

    assert _safe_for_stream(text, stream) == text


def test_safe_for_stream_replaces_unencodable_characters() -> None:
    stream = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict")

    text = "risk marker 🟡 ⚠️ █ degrades safely"

    assert _safe_for_stream(text, stream) == "risk marker  RISK # degrades safely"
