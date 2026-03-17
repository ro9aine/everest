from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

import requests

from app.domain.errors import (
    BlockedByUpstreamError,
    MalformedResponseError,
    NotFoundError,
    TemporaryNetworkError,
)
from app.domain.schemas import FedresursResult
from app.parsers.fedresurs import FedResursParser


class FedresursParserAdapter:
    """Thin adapter that normalizes Fedresurs parser output for the app layer.

    Assumptions:
    - parser transport and scraping logic are already correct
    - the parser returns JSON-like dict payloads
    - a matching person is identified by normalized INN equality
    """

    _DATE_KEYS = (
        "date",
        "publishDate",
        "publicationDate",
        "lastDate",
        "lastMessageDate",
        "caseDate",
        "startDate",
        "endDate",
    )

    def __init__(self, parser: FedResursParser | None = None) -> None:
        self._parser = parser or FedResursParser()

    def get_bankruptcy_info(self, inn: str) -> FedresursResult:
        normalized_inn = self._normalize_inn(inn)

        persons_payload = self._translate_request_error(
            lambda: self._parser.find_persons(normalized_inn)
        )
        page_data = persons_payload.get("pageData")
        if not isinstance(page_data, list):
            raise MalformedResponseError("Fedresurs persons response is missing list field 'pageData'")

        person = self._pick_person(page_data, normalized_inn)
        if person is None:
            raise NotFoundError(f"Fedresurs returned no person for INN '{normalized_inn}'")

        guid = person.get("guid")
        if not isinstance(guid, str) or not guid.strip():
            raise MalformedResponseError("Fedresurs person payload is missing non-empty field 'guid'")

        bankruptcy_payload = self._translate_request_error(
            lambda: self._parser.get_bankruptcy_info(guid.strip())
        )
        case_number = self._extract_case_number(bankruptcy_payload)
        if case_number is None:
            raise NotFoundError(f"Fedresurs returned no bankruptcy case for INN '{normalized_inn}'")

        latest_date = self._extract_latest_date(bankruptcy_payload)

        return FedresursResult(
            inn=normalized_inn,
            person_guid=guid.strip(),
            bankruptcy_case_number=case_number,
            latest_date=latest_date,
            raw_person_payload=person,
            raw_bankruptcy_payload=bankruptcy_payload,
        )

    @staticmethod
    def _normalize_inn(inn: str) -> str:
        normalized = str(inn).strip()
        if not normalized:
            raise ValueError("INN must be a non-empty string")
        return normalized

    @staticmethod
    def _pick_person(page_data: list[dict], normalized_inn: str) -> dict | None:
        for person in page_data:
            if not isinstance(person, dict):
                continue
            person_inn = str(person.get("inn", "")).strip()
            if person_inn == normalized_inn:
                return person
        return page_data[0] if page_data and isinstance(page_data[0], dict) else None

    def _extract_case_number(self, payload: dict) -> str | None:
        direct_case = payload.get("bankruptcyCaseNumber")
        if isinstance(direct_case, str) and direct_case.strip():
            return direct_case.strip()

        legal_cases = payload.get("legalCases")
        if not isinstance(legal_cases, list):
            return None

        dated_cases: list[tuple[datetime | None, str]] = []
        for case in legal_cases:
            if not isinstance(case, dict):
                continue
            case_number = case.get("number") or case.get("caseNumber")
            if isinstance(case_number, str) and case_number.strip():
                dated_cases.append((self._extract_latest_date(case), case_number.strip()))

        if not dated_cases:
            return None

        dated_cases.sort(key=lambda item: item[0] or datetime.min, reverse=True)
        return dated_cases[0][1]

    def _extract_latest_date(self, payload: dict | list | tuple) -> datetime | None:
        dates = list(self._collect_dates(payload))
        return max(dates) if dates else None

    def _collect_dates(self, value: object) -> Iterable[datetime]:
        if isinstance(value, dict):
            for key, nested_value in value.items():
                if key in self._DATE_KEYS:
                    parsed = self._parse_datetime(nested_value)
                    if parsed is not None:
                        yield parsed
                yield from self._collect_dates(nested_value)
        elif isinstance(value, (list, tuple)):
            for item in value:
                yield from self._collect_dates(item)

    @staticmethod
    def _parse_datetime(value: object) -> datetime | None:
        if isinstance(value, datetime):
            return value
        if not isinstance(value, str):
            return None

        candidate = value.strip()
        if not candidate:
            return None

        formats = (
            None,
            "%d.%m.%Y",
            "%d.%m.%Y %H:%M:%S",
            "%d.%m.%Y %H:%M",
        )
        for fmt in formats:
            try:
                if fmt is None:
                    return datetime.fromisoformat(candidate.replace("Z", "+00:00"))
                return datetime.strptime(candidate, fmt)
            except ValueError:
                continue
        return None

    @staticmethod
    def _translate_request_error(func):
        try:
            return func()
        except requests.HTTPError as exc:
            status_code = exc.response.status_code if exc.response is not None else None
            if status_code in {403, 429}:
                raise BlockedByUpstreamError(
                    f"Fedresurs request was blocked by upstream with status {status_code}"
                ) from exc
            if status_code is not None and status_code >= 500:
                raise TemporaryNetworkError(
                    f"Fedresurs temporary upstream failure with status {status_code}"
                ) from exc
            raise TemporaryNetworkError("Fedresurs request failed") from exc
        except (requests.ConnectionError, requests.Timeout) as exc:
            raise TemporaryNetworkError("Fedresurs request failed due to a temporary network error") from exc
