from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import requests


@dataclass(slots=True, frozen=True)
class RetryPolicy:
    attempts: int = 3
    backoff_seconds: float = 1.0
    backoff_multiplier: float = 2.0


class _RetryingParserBase:
    def __init__(self, parser: Any, *, retry_policy: RetryPolicy) -> None:
        self._parser = parser
        self._retry_policy = retry_policy

    @property
    def session(self) -> Any:
        return getattr(self._parser, "session", None)

    def _call_with_retry(self, operation_name: str, func, *args, **kwargs):
        delay = self._retry_policy.backoff_seconds
        last_exc: Exception | None = None

        for attempt in range(1, self._retry_policy.attempts + 1):
            try:
                return func(*args, **kwargs)
            except (requests.ConnectionError, requests.Timeout) as exc:
                last_exc = exc
            except requests.HTTPError as exc:
                status_code = exc.response.status_code if exc.response is not None else None
                if status_code is None or status_code >= 500 or status_code == 429:
                    last_exc = exc
                else:
                    raise

            if attempt == self._retry_policy.attempts:
                break
            if delay > 0:
                time.sleep(delay)
            delay *= self._retry_policy.backoff_multiplier

        if last_exc is None:
            raise RuntimeError(f"{operation_name} failed without a captured exception")
        raise last_exc


class RetryingFedResursParser(_RetryingParserBase):
    def find_persons(self, inn: str) -> dict:
        return self._call_with_retry("find_persons", self._parser.find_persons, inn)

    def get_bankruptcy_info(self, guid: str) -> dict:
        return self._call_with_retry("get_bankruptcy_info", self._parser.get_bankruptcy_info, guid)


class RetryingKadParser(_RetryingParserBase):
    def search_by_number(self, number: str) -> dict:
        return self._call_with_retry("search_by_number", self._parser.search_by_number, number)

    def get_card_info(self, card: str | dict[str, str]) -> dict:
        return self._call_with_retry("get_card_info", self._parser.get_card_info, card)
