from __future__ import annotations

import argparse
import sys

from pytest import main

from app.config import ExecutionSettings, Settings
from app.db import create_db_engine, create_session_factory, init_db
from app.excel import ExcelInputError
from app.logging_utils import configure_logging
from app.services import BatchProcessingService, BatchSource


def test_unit() -> int:
    return main(["tests/test_parsers.py", "-s"])


def test_integration() -> int:
    return main(["tests/test_parsers_integration.py", "-m", "integration", "-s"])


def run_batch(argv: list[str] | None = None) -> int:
    settings = Settings.from_env()
    parser = argparse.ArgumentParser(description="Process XLSX identifiers via source adapters")
    parser.add_argument(
        "--source",
        choices=[source.value for source in BatchSource],
        default=settings.source_mode,
        help="Batch source mode. Defaults to SOURCE_MODE or fedresurs.",
    )
    parser.add_argument("--input", required=True, help="Path to .xlsx file")
    parser.add_argument("--sheet", help="Worksheet name. Defaults to the first sheet.")
    parser.add_argument("--column", required=True, help="Header name of the input column")
    parser.add_argument("--resume", action="store_true", help="Skip rows with terminal DB status")
    parser.add_argument("--limit", type=int, help="Optional max number of non-empty rows to process")
    parser.add_argument("--worker-count", type=int, help="Override conservative worker count")
    parser.add_argument("--retry-attempts", type=int, help="Override retry attempts for transient failures")
    parser.add_argument("--retry-backoff-base-seconds", type=float, help="Override retry backoff base delay")
    parser.add_argument("--retry-backoff-multiplier", type=float, help="Override retry backoff multiplier")
    parser.add_argument("--request-delay-seconds", type=float, help="Override minimum delay between requests")
    parser.add_argument(
        "--database-url",
        help="Optional SQLAlchemy database URL. Defaults to DATABASE_URL or sqlite:///./everest.db",
    )
    args = parser.parse_args(argv)

    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be a positive integer")
    if args.worker_count is not None and args.worker_count <= 0:
        parser.error("--worker-count must be a positive integer")
    if args.retry_attempts is not None and args.retry_attempts <= 0:
        parser.error("--retry-attempts must be a positive integer")
    if args.retry_backoff_base_seconds is not None and args.retry_backoff_base_seconds < 0:
        parser.error("--retry-backoff-base-seconds must be >= 0")
    if args.retry_backoff_multiplier is not None and args.retry_backoff_multiplier < 1:
        parser.error("--retry-backoff-multiplier must be >= 1")
    if args.request_delay_seconds is not None and args.request_delay_seconds < 0:
        parser.error("--request-delay-seconds must be >= 0")

    configure_logging(settings.logging.level)
    execution_settings = ExecutionSettings(
        worker_count=args.worker_count or settings.execution.worker_count,
        retry_attempts=args.retry_attempts or settings.execution.retry_attempts,
        retry_backoff_base_seconds=(
            args.retry_backoff_base_seconds
            if args.retry_backoff_base_seconds is not None
            else settings.execution.retry_backoff_base_seconds
        ),
        retry_backoff_multiplier=(
            args.retry_backoff_multiplier
            if args.retry_backoff_multiplier is not None
            else settings.execution.retry_backoff_multiplier
        ),
        request_delay_seconds=(
            args.request_delay_seconds
            if args.request_delay_seconds is not None
            else settings.execution.request_delay_seconds
        ),
    )

    engine = create_db_engine(args.database_url or settings.database_url)
    init_db(engine)
    session_factory = create_session_factory(engine)
    service = BatchProcessingService(session_factory, execution_settings=execution_settings)

    try:
        summary = service.run(
            source=BatchSource(args.source),
            input_path=args.input,
            sheet=args.sheet,
            column=args.column,
            resume=args.resume,
            limit=args.limit,
        )
    except ExcelInputError as exc:
        parser.exit(2, f"Input validation error: {exc}\n")

    print(f"total={summary.total}")
    print(f"success={summary.success}")
    print(f"not_found={summary.not_found}")
    print(f"temporary_failures={summary.temporary_failures}")
    print(f"permanent_failures={summary.permanent_failures}")
    print(f"skipped={summary.skipped}")
    return 0


def main(argv: list[str] | None = None) -> int:
    return run_batch(argv)


if __name__ == "__main__":
    sys.exit(main())
