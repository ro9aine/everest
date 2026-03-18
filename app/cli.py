from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.config import Settings
from app.db import create_db_engine, create_session_factory, init_db
from app.excel import ExcelInputError
from app.logging_utils import configure_logging
from app.services import BatchProcessingService


def test_unit() -> int:
    from pytest import main as pytest_main

    return pytest_main(["tests/test_parsers.py", "-s"])


def test_integration() -> int:
    from pytest import main as pytest_main

    return pytest_main(["tests/test_parsers_integration.py", "-m", "integration", "-s"])


def run_batch(argv: list[str] | None = None) -> int:
    settings = Settings.from_env()
    parser = argparse.ArgumentParser(description="Process XLSX INNs through Fedresurs and KAD parsers")
    parser.add_argument("--input", required=True, help="Path to .xlsx file")
    parser.add_argument("--column", required=True, help="Header name of the input column")
    args = parser.parse_args(argv)

    configure_logging(settings.logging.level)
    engine = create_db_engine(settings.database_url)
    init_db(engine)
    session_factory = create_session_factory(engine)
    service = BatchProcessingService(session_factory)

    try:
        summary = service.run(
            input_path=args.input,
            column=args.column,
        )
    except ExcelInputError as exc:
        parser.exit(2, f"Input validation error: {exc}\n")

    print(f"total={summary.total}")
    print(f"success={summary.success}")
    print(f"failed={summary.failed}")
    print(f"skipped={summary.skipped}")
    return 0


def _entrypoint_name() -> str:
    return Path(sys.argv[0]).stem.lower()


def main(argv: list[str] | None = None) -> int:
    entrypoint_name = _entrypoint_name()
    if entrypoint_name == "test-unit":
        return test_unit()
    if entrypoint_name == "test-integration":
        return test_integration()

    return run_batch(argv)


if __name__ == "__main__":
    sys.exit(main())
