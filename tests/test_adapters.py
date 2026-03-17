from __future__ import annotations

from datetime import datetime
from unittest.mock import Mock

import pytest
import requests

from app.adapters import (
    BlockedByUpstreamError,
    FedresursParserAdapter,
    KadArbitrParserAdapter,
    MalformedResponseError,
    NotFoundError,
    TemporaryNetworkError,
)


def make_http_error(status_code: int) -> requests.HTTPError:
    response = requests.Response()
    response.status_code = status_code
    return requests.HTTPError(response=response)


def test_fedresurs_adapter_normalizes_result() -> None:
    parser = Mock()
    parser.find_persons.return_value = {
        "pageData": [
            {
                "guid": "person-guid-1",
                "inn": "231138771115",
            }
        ]
    }
    parser.get_bankruptcy_info.return_value = {
        "legalCases": [
            {
                "number": "A40-12345/2024",
                "publishDate": "2024-01-15T10:30:00",
            },
            {
                "number": "A40-10000/2024",
                "publishDate": "2023-01-15T10:30:00",
            },
        ]
    }

    result = FedresursParserAdapter(parser=parser).get_bankruptcy_info(" 231138771115 ")

    parser.find_persons.assert_called_once_with("231138771115")
    parser.get_bankruptcy_info.assert_called_once_with("person-guid-1")
    assert result.inn == "231138771115"
    assert result.person_guid == "person-guid-1"
    assert result.bankruptcy_case_number == "A40-12345/2024"
    assert result.latest_date == datetime(2024, 1, 15, 10, 30, 0)


def test_fedresurs_adapter_raises_not_found() -> None:
    parser = Mock()
    parser.find_persons.return_value = {"pageData": []}

    with pytest.raises(NotFoundError):
        FedresursParserAdapter(parser=parser).get_bankruptcy_info("231138771115")


def test_fedresurs_adapter_maps_blocked_status() -> None:
    parser = Mock()
    parser.find_persons.side_effect = make_http_error(429)

    with pytest.raises(BlockedByUpstreamError):
        FedresursParserAdapter(parser=parser).get_bankruptcy_info("231138771115")


def test_fedresurs_adapter_maps_temporary_network_failure() -> None:
    parser = Mock()
    parser.find_persons.side_effect = requests.Timeout()

    with pytest.raises(TemporaryNetworkError):
        FedresursParserAdapter(parser=parser).get_bankruptcy_info("231138771115")


def test_fedresurs_adapter_rejects_malformed_person_response() -> None:
    parser = Mock()
    parser.find_persons.return_value = {"pageData": [{}]}

    with pytest.raises(MalformedResponseError):
        FedresursParserAdapter(parser=parser).get_bankruptcy_info("231138771115")


def test_kad_adapter_normalizes_documents() -> None:
    parser = Mock()
    parser.search_by_number.return_value = {
        "Result": {
            "Items": [
                {
                    "CaseNumber": "A40-12345/2024",
                    "CardId": "card-1",
                    "CardUrl": "https://kad.arbitr.ru/Card/card-1",
                }
            ]
        },
        "Html": "<html></html>",
    }
    parser.get_card_info.return_value = {
        "CardId": "card-1",
        "CardUrl": "https://kad.arbitr.ru/Card/card-1",
        "ResultText": "Fallback title",
        "Html": """
        <table>
            <tr>
                <td>10.02.2024 14:45</td>
                <td><a href="/doc/1">Order</a></td>
                <td>Order on accepting the application</td>
            </tr>
            <tr>
                <td>09.02.2024</td>
                <td><a href="/doc/2">Notice</a></td>
                <td>Notice to parties</td>
            </tr>
        </table>
        """,
    }

    result = KadArbitrParserAdapter(parser=parser).get_case_documents("  A40-12345/2024 ")

    parser.search_by_number.assert_called_once_with("A40-12345/2024")
    parser.get_card_info.assert_called_once()
    assert result.case_number == "A40-12345/2024"
    assert result.card_id == "card-1"
    assert result.latest_date == datetime(2024, 2, 10, 14, 45, 0)
    assert result.latest_document_name == "Order"
    assert "Order on accepting the application" in (result.latest_document_title or "")
    assert len(result.documents) >= 2


def test_kad_adapter_raises_not_found() -> None:
    parser = Mock()
    parser.search_by_number.return_value = {"Result": {"Items": []}, "Html": "<html></html>"}

    with pytest.raises(NotFoundError):
        KadArbitrParserAdapter(parser=parser).get_case_documents("A40-12345/2024")


def test_kad_adapter_detects_block_page_from_html() -> None:
    parser = Mock()
    parser.search_by_number.return_value = {
        "Result": {"Items": [{"CaseNumber": "A40-12345/2024", "CardId": "card-1"}]},
        "Html": "<html></html>",
    }
    parser.get_card_info.return_value = {
        "CardId": "card-1",
        "CardUrl": "https://kad.arbitr.ru/Card/card-1",
        "Html": "<html><body>captcha required</body></html>",
    }

    with pytest.raises(BlockedByUpstreamError):
        KadArbitrParserAdapter(parser=parser).get_case_documents("A40-12345/2024")


def test_kad_adapter_maps_temporary_network_failure() -> None:
    parser = Mock()
    parser.search_by_number.side_effect = requests.ConnectionError()

    with pytest.raises(TemporaryNetworkError):
        KadArbitrParserAdapter(parser=parser).get_case_documents("A40-12345/2024")


def test_kad_adapter_rejects_malformed_card_payload() -> None:
    parser = Mock()
    parser.search_by_number.return_value = {
        "Result": {"Items": [{"CaseNumber": "A40-12345/2024", "CardId": "card-1"}]},
        "Html": "<html></html>",
    }
    parser.get_card_info.return_value = {
        "CardId": "card-1",
        "CardUrl": "https://kad.arbitr.ru/Card/card-1",
        "Html": "<html><body>plain card without docs</body></html>",
    }

    with pytest.raises(MalformedResponseError):
        KadArbitrParserAdapter(parser=parser).get_case_documents("A40-12345/2024")
