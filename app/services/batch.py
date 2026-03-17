from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from sqlalchemy.orm import Session, sessionmaker

from app.adapters import (
    BlockedByUpstreamError,
    FedresursParserAdapter,
    KadArbitrParserAdapter,
    MalformedResponseError,
    NotFoundError,
    TemporaryNetworkError,
)
from app.config import ExecutionSettings
from app.excel import ExcelInputReader
from app.execution import ExecutionPolicy, RateLimiter, RetryPolicy, execute_with_retry
from app.repositories.lookup_results import (
    FedresursLookupPayload,
    FedresursLookupRepository,
    KadArbitrLookupPayload,
    KadArbitrLookupRepository,
)


class BatchSource(StrEnum):
    FEDRESURS = "fedresurs"
    KAD = "kad"


class ProcessingStatus(StrEnum):
    PROCESSING = "processing"
    SUCCESS = "success"
    NOT_FOUND = "not_found"
    TEMPORARY_FAILURE = "temporary_failure"
    PERMANENT_FAILURE = "permanent_failure"


@dataclass(slots=True)
class BatchProcessingSummary:
    total: int = 0
    success: int = 0
    not_found: int = 0
    temporary_failures: int = 0
    permanent_failures: int = 0
    skipped: int = 0

    def record(self, outcome: ProcessingStatus | None) -> None:
        if outcome == ProcessingStatus.SUCCESS:
            self.success += 1
        elif outcome == ProcessingStatus.NOT_FOUND:
            self.not_found += 1
        elif outcome == ProcessingStatus.TEMPORARY_FAILURE:
            self.temporary_failures += 1
        elif outcome == ProcessingStatus.PERMANENT_FAILURE:
            self.permanent_failures += 1
        elif outcome is None:
            self.skipped += 1


class BatchProcessingService:
    """Processes XLSX rows against one source and persists each row result."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        excel_reader: ExcelInputReader | None = None,
        fedresurs_adapter: FedresursParserAdapter | None = None,
        kad_adapter: KadArbitrParserAdapter | None = None,
        execution_settings: ExecutionSettings | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._excel_reader = excel_reader or ExcelInputReader()
        self._fedresurs_adapter = fedresurs_adapter or FedresursParserAdapter()
        self._kad_adapter = kad_adapter or KadArbitrParserAdapter()
        effective_settings = execution_settings or ExecutionSettings()
        self._execution_policy = ExecutionPolicy(
            worker_count=max(1, effective_settings.worker_count),
            request_delay_seconds=max(0.0, effective_settings.request_delay_seconds),
            retry_policy=RetryPolicy(
                max_attempts=max(1, effective_settings.retry_attempts),
                backoff_base_seconds=max(0.0, effective_settings.retry_backoff_base_seconds),
                backoff_multiplier=max(1.0, effective_settings.retry_backoff_multiplier),
            ),
        )
        self._rate_limiter = RateLimiter(self._execution_policy.request_delay_seconds)
        self._logger = logger or logging.getLogger(__name__)

    def run(
        self,
        *,
        source: BatchSource,
        input_path: str,
        sheet: str | None,
        column: str,
        resume: bool = False,
        limit: int | None = None,
    ) -> BatchProcessingSummary:
        input_batch = self._excel_reader.read(input_path, sheet=sheet, column=column)
        summary = BatchProcessingSummary(skipped=input_batch.skipped_empty)

        rows = input_batch.rows[:limit] if limit is not None else input_batch.rows
        summary.total = len(rows)

        try:
            if self._execution_policy.worker_count <= 1:
                for row in rows:
                    summary.record(self._process_row(source, row.row_number, row.value, resume))
            else:
                with ThreadPoolExecutor(max_workers=self._execution_policy.worker_count) as executor:
                    futures = [
                        executor.submit(self._process_row, source, row.row_number, row.value, resume)
                        for row in rows
                    ]
                    for future in as_completed(futures):
                        summary.record(future.result())
        finally:
            self._close_adapter(self._fedresurs_adapter)
            self._close_adapter(self._kad_adapter)

        return summary

    def _process_row(
        self,
        source: BatchSource,
        row_number: int,
        value: str,
        resume: bool,
    ) -> ProcessingStatus | None:
        if source == BatchSource.FEDRESURS:
            return self._process_fedresurs_row(row_number, value, resume)
        return self._process_kad_row(row_number, value, resume)

    def _process_fedresurs_row(
        self,
        row_number: int,
        inn: str,
        resume: bool,
    ) -> ProcessingStatus | None:
        with self._session_factory() as session:
            repository = FedresursLookupRepository(session)
            if resume and repository.has_terminal_status(inn):
                self._logger.info("row=%s value=%s status=skipped reason=resume", row_number, inn)
                return None

            repository.mark_processing(inn, source=BatchSource.FEDRESURS.value)
            session.commit()

            try:
                result = execute_with_retry(
                    lambda: self._fedresurs_adapter.get_bankruptcy_info(inn),
                    retry_policy=self._execution_policy.retry_policy,
                    rate_limiter=self._rate_limiter,
                    on_retry=lambda attempt, max_attempts, delay, exc: self._logger.warning(
                        "row=%s value=%s retry_attempt=%s/%s next_delay=%.2fs error=%s",
                        row_number,
                        inn,
                        attempt,
                        max_attempts,
                        delay,
                        exc,
                    ),
                )
                repository.upsert(
                    FedresursLookupPayload(
                        inn=result.inn,
                        case_number=result.bankruptcy_case_number,
                        latest_date=result.latest_date,
                        source=BatchSource.FEDRESURS.value,
                        parsed_at=datetime.utcnow(),
                        status=ProcessingStatus.SUCCESS.value,
                    )
                )
                session.commit()
                self._logger.info(
                    "row=%s value=%s status=success case_number=%s",
                    row_number,
                    result.inn,
                    result.bankruptcy_case_number,
                )
                return ProcessingStatus.SUCCESS
            except NotFoundError as exc:
                self._persist_fedresurs_failure(
                    session=session,
                    repository=repository,
                    inn=inn,
                    status=ProcessingStatus.NOT_FOUND,
                    error_message=str(exc),
                )
                self._logger.warning("row=%s value=%s status=not_found error=%s", row_number, inn, exc)
                return ProcessingStatus.NOT_FOUND
            except TemporaryNetworkError as exc:
                self._persist_fedresurs_failure(
                    session=session,
                    repository=repository,
                    inn=inn,
                    status=ProcessingStatus.TEMPORARY_FAILURE,
                    error_message=str(exc),
                )
                self._logger.warning(
                    "row=%s value=%s status=temporary_failure final_error=%s",
                    row_number,
                    inn,
                    exc,
                )
                return ProcessingStatus.TEMPORARY_FAILURE
            except (BlockedByUpstreamError, MalformedResponseError, ValueError) as exc:
                self._persist_fedresurs_failure(
                    session=session,
                    repository=repository,
                    inn=inn,
                    status=ProcessingStatus.PERMANENT_FAILURE,
                    error_message=str(exc),
                )
                self._logger.error(
                    "row=%s value=%s status=permanent_failure error=%s",
                    row_number,
                    inn,
                    exc,
                )
                return ProcessingStatus.PERMANENT_FAILURE
            except Exception as exc:
                self._persist_fedresurs_failure(
                    session=session,
                    repository=repository,
                    inn=inn,
                    status=ProcessingStatus.PERMANENT_FAILURE,
                    error_message=str(exc),
                )
                self._logger.exception(
                    "row=%s value=%s status=permanent_failure error=%s",
                    row_number,
                    inn,
                    exc,
                )
                return ProcessingStatus.PERMANENT_FAILURE

    def _process_kad_row(
        self,
        row_number: int,
        case_number: str,
        resume: bool,
    ) -> ProcessingStatus | None:
        with self._session_factory() as session:
            repository = KadArbitrLookupRepository(session)
            if resume and repository.has_terminal_status(case_number):
                self._logger.info("row=%s value=%s status=skipped reason=resume", row_number, case_number)
                return None

            repository.mark_processing(case_number, source=BatchSource.KAD.value)
            session.commit()

            try:
                result = execute_with_retry(
                    lambda: self._kad_adapter.get_case_documents(case_number),
                    retry_policy=self._execution_policy.retry_policy,
                    rate_limiter=self._rate_limiter,
                    on_retry=lambda attempt, max_attempts, delay, exc: self._logger.warning(
                        "row=%s value=%s retry_attempt=%s/%s next_delay=%.2fs error=%s",
                        row_number,
                        case_number,
                        attempt,
                        max_attempts,
                        delay,
                        exc,
                    ),
                )
                repository.upsert(
                    KadArbitrLookupPayload(
                        case_number=result.case_number,
                        latest_date=result.latest_date,
                        document_name=result.latest_document_name,
                        document_title_or_description=result.latest_document_title,
                        source=BatchSource.KAD.value,
                        parsed_at=datetime.utcnow(),
                        status=ProcessingStatus.SUCCESS.value,
                    )
                )
                session.commit()
                self._logger.info(
                    "row=%s value=%s status=success card_id=%s",
                    row_number,
                    result.case_number,
                    result.card_id,
                )
                return ProcessingStatus.SUCCESS
            except NotFoundError as exc:
                self._persist_kad_failure(
                    session=session,
                    repository=repository,
                    case_number=case_number,
                    status=ProcessingStatus.NOT_FOUND,
                    error_message=str(exc),
                )
                self._logger.warning(
                    "row=%s value=%s status=not_found error=%s",
                    row_number,
                    case_number,
                    exc,
                )
                return ProcessingStatus.NOT_FOUND
            except TemporaryNetworkError as exc:
                self._persist_kad_failure(
                    session=session,
                    repository=repository,
                    case_number=case_number,
                    status=ProcessingStatus.TEMPORARY_FAILURE,
                    error_message=str(exc),
                )
                self._logger.warning(
                    "row=%s value=%s status=temporary_failure final_error=%s",
                    row_number,
                    case_number,
                    exc,
                )
                return ProcessingStatus.TEMPORARY_FAILURE
            except (BlockedByUpstreamError, MalformedResponseError, ValueError) as exc:
                self._persist_kad_failure(
                    session=session,
                    repository=repository,
                    case_number=case_number,
                    status=ProcessingStatus.PERMANENT_FAILURE,
                    error_message=str(exc),
                )
                self._logger.error(
                    "row=%s value=%s status=permanent_failure error=%s",
                    row_number,
                    case_number,
                    exc,
                )
                return ProcessingStatus.PERMANENT_FAILURE
            except Exception as exc:
                self._persist_kad_failure(
                    session=session,
                    repository=repository,
                    case_number=case_number,
                    status=ProcessingStatus.PERMANENT_FAILURE,
                    error_message=str(exc),
                )
                self._logger.exception(
                    "row=%s value=%s status=permanent_failure error=%s",
                    row_number,
                    case_number,
                    exc,
                )
                return ProcessingStatus.PERMANENT_FAILURE

    @staticmethod
    def _persist_fedresurs_failure(
        *,
        session: Session,
        repository: FedresursLookupRepository,
        inn: str,
        status: ProcessingStatus,
        error_message: str,
    ) -> None:
        repository.upsert(
            FedresursLookupPayload(
                inn=inn,
                case_number=None,
                latest_date=None,
                source=BatchSource.FEDRESURS.value,
                parsed_at=datetime.utcnow(),
                status=status.value,
                error_message=error_message,
            )
        )
        session.commit()

    @staticmethod
    def _persist_kad_failure(
        *,
        session: Session,
        repository: KadArbitrLookupRepository,
        case_number: str,
        status: ProcessingStatus,
        error_message: str,
    ) -> None:
        repository.upsert(
            KadArbitrLookupPayload(
                case_number=case_number,
                latest_date=None,
                document_name=None,
                document_title_or_description=None,
                source=BatchSource.KAD.value,
                parsed_at=datetime.utcnow(),
                status=status.value,
                error_message=error_message,
            )
        )
        session.commit()

    @staticmethod
    def _close_adapter(adapter: object) -> None:
        close_method = getattr(adapter, "close", None)
        if callable(close_method):
            close_method()
