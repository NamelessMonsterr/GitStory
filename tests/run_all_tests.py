#!/usr/bin/env python3
"""
GitStory - Master Test Runner
Runs all tests across every module with detailed reporting.

Usage:
    python tests/run_all_tests.py
    python tests/run_all_tests.py -v           # verbose
    python tests/run_all_tests.py -k midnight  # run only tests matching 'midnight'
"""

from __future__ import annotations

import os
import sys
import time

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


def _safe_print(text: str = "") -> None:
    encoding = getattr(sys.stdout, "encoding", None)
    if not encoding:
        print(text)
        return

    try:
        print(text)
    except UnicodeEncodeError:
        safe = text.encode(encoding, errors="replace").decode(
            encoding, errors="replace"
        )
        print(safe)


def main() -> int:
    try:
        import pytest
    except ImportError:
        _safe_print("ERROR: pytest not installed. Run: pip install pytest")
        return 1

    tests_dir = os.path.dirname(os.path.abspath(__file__))

    _safe_print("=" * 78)
    _safe_print("  GitStory - Complete Test Suite")
    _safe_print("=" * 78)
    _safe_print()
    _safe_print(f"  Project Root : {_PROJECT_ROOT}")
    _safe_print(f"  Tests Dir    : {tests_dir}")
    _safe_print()

    test_files = sorted(
        f for f in os.listdir(tests_dir) if f.startswith("test_") and f.endswith(".py")
    )
    _safe_print(f"  Test Files   : {len(test_files)}")
    for tf in test_files:
        _safe_print(f"    - {tf}")
    _safe_print()
    _safe_print("=" * 78)
    _safe_print()

    start = time.time()

    args = [
        tests_dir,
        "-v",
        "--tb=short",
        "--no-header",
        "-rA",
    ]
    args.extend(sys.argv[1:])

    exit_code = pytest.main(args)

    elapsed = time.time() - start

    _safe_print()
    _safe_print("=" * 78)
    result_text = "ALL TESTS PASSED" if exit_code == 0 else "SOME TESTS FAILED"
    _safe_print(f"  {result_text}")
    _safe_print(f"  Elapsed: {elapsed:.2f}s")
    _safe_print("=" * 78)

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
