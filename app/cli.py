from __future__ import annotations

from pytest import main


def test_unit() -> int:
    return main(["tests/test_parsers.py", "-s"])


def test_integration() -> int:
    return main(["tests/test_parsers_integration.py", "-m", "integration", "-s"])

