from __future__ import annotations

from unittest.mock import Mock

import pytest
import requests

from app.parsers.retrying import RetryPolicy, RetryingFedResursParser, RetryingKadParser


def make_http_error(status_code: int) -> requests.HTTPError:
    response = requests.Response()
    response.status_code = status_code
    return requests.HTTPError(response=response)


def test_retrying_fedresurs_parser_retries_connection_error(monkeypatch) -> None:
    parser = Mock()
    parser.find_persons.side_effect = [requests.ConnectionError("boom"), {"pageData": []}]
    monkeypatch.setattr("app.parsers.retrying.time.sleep", lambda _: None)
    wrapped = RetryingFedResursParser(
        parser,
        retry_policy=RetryPolicy(attempts=2, backoff_seconds=0.0, backoff_multiplier=1.0),
    )

    result = wrapped.find_persons("123")

    assert result == {"pageData": []}
    assert parser.find_persons.call_count == 2


def test_retrying_kad_parser_retries_http_500(monkeypatch) -> None:
    parser = Mock()
    parser.search_by_number.side_effect = [make_http_error(500), {"Result": {"Items": []}}]
    monkeypatch.setattr("app.parsers.retrying.time.sleep", lambda _: None)
    wrapped = RetryingKadParser(
        parser,
        retry_policy=RetryPolicy(attempts=2, backoff_seconds=0.0, backoff_multiplier=1.0),
    )

    result = wrapped.search_by_number("A40-1/2024")

    assert result == {"Result": {"Items": []}}
    assert parser.search_by_number.call_count == 2


def test_retrying_parser_does_not_retry_http_404(monkeypatch) -> None:
    parser = Mock()
    parser.get_card_info.side_effect = make_http_error(404)
    monkeypatch.setattr("app.parsers.retrying.time.sleep", lambda _: None)
    wrapped = RetryingKadParser(
        parser,
        retry_policy=RetryPolicy(attempts=3, backoff_seconds=0.0, backoff_multiplier=1.0),
    )

    with pytest.raises(requests.HTTPError):
        wrapped.get_card_info("card-1")

    assert parser.get_card_info.call_count == 1
