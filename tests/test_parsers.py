import json
from unittest.mock import Mock

import pytest
import requests

from app.parsers.fedresurs import FedResursParser
from app.parsers.kad import KadParser


@pytest.fixture(autouse=True)
def isolate_kad_cookie_dump(tmp_path, monkeypatch):
    monkeypatch.setattr(KadParser, "DEFAULT_RECORDED_COOKIES_PATH", tmp_path / "kad_web_full_cookies.json")


def make_kad_session() -> Mock:
    session = Mock()
    session.cookies = requests.Session().cookies
    return session


def test_fedresurs_parser_can_be_instantiated() -> None:
    parser = FedResursParser()

    assert isinstance(parser, FedResursParser)
    assert "User-Agent" in parser.headers


def test_find_persons() -> None:
    session = Mock()
    session.get.return_value.json.return_value = {"pageData": []}
    parser = FedResursParser(session=session)

    result = parser.find_persons("1234567890")

    session.get.assert_called_once_with(
        "https://fedresurs.ru/backend/persons",
        params={
            "searchString": "1234567890",
            "limit": 15,
            "offset": 0,
            "isActive": "true",
        },
        headers=parser.headers | {
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Referer": (
                "https://fedresurs.ru/entities"
                "?searchString=1234567890&regionNumber=all&isActive=true&offset=0&limit=15"
            ),
        },
        timeout=30,
    )
    session.get.return_value.raise_for_status.assert_called_once_with()
    assert result == {"pageData": []}


def test_find_persons_returns_real_persons_payload() -> None:
    session = Mock()
    expected_payload = {
        "pageData": [
            {
                "guid": "person-guid-1",
                "lastName": "Ivanov",
                "firstName": "Ivan",
                "middleName": "Ivanovich",
                "fullName": "Ivanov Ivan Ivanovich",
                "inn": "231138771115",
            }
        ],
        "total": 1,
    }
    session.get.return_value.json.return_value = expected_payload
    parser = FedResursParser(session=session)

    result = parser.find_persons("231138771115")

    session.get.assert_called_once()
    session.get.return_value.raise_for_status.assert_called_once_with()
    assert result == expected_payload


def test_get_bankruptcy_info() -> None:
    session = Mock()
    expected_payload = {
        "guid": "person-guid-1",
        "bankruptcyCaseNumber": "A40-12345/2024",
    }
    session.get.return_value.json.return_value = expected_payload
    parser = FedResursParser(session=session)

    result = parser.get_bankruptcy_info("person-guid-1")

    session.get.assert_called_once_with(
        "https://fedresurs.ru/backend/persons/person-guid-1/bankruptcy",
        headers=parser.headers | {
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Referer": "https://fedresurs.ru/persons/person-guid-1",
        },
        timeout=30,
    )
    session.get.return_value.raise_for_status.assert_called_once_with()
    assert result == expected_payload


def test_kad_parser_can_be_instantiated(monkeypatch) -> None:
    expected_ua = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/141.0.7390.78 Safari/537.36"
    )
    monkeypatch.setattr(KadParser, "_get_chrome_user_agent", staticmethod(lambda: expected_ua))

    parser = KadParser()

    assert isinstance(parser, KadParser)
    assert parser.headers["User-Agent"] == expected_ua
    assert parser.headers["sec-ch-ua-platform"] == '"Windows"'
    assert '"Google Chrome";v="141"' in parser.headers["sec-ch-ua"]
    assert '"Chromium";v="141"' in parser.headers["sec-ch-ua"]


def test_kad_init_loads_cookie_dump_and_runtime_cookies(tmp_path) -> None:
    session = make_kad_session()
    cookies_path = tmp_path / "kad_web_full_cookies.json"
    cookies_path.write_text(
        json.dumps(
            {
                "cookies": [
                    {
                        "name": "ASP.NET_SessionId",
                        "value": "session-cookie",
                        "domain": "kad.arbitr.ru",
                        "path": "/",
                    },
                    {
                        "name": "__ddg1_",
                        "value": "ddg-cookie",
                        "domain": ".arbitr.ru",
                        "path": "/",
                    },
                    {
                        "name": "foreign",
                        "value": "cookie",
                        "domain": ".vk.com",
                        "path": "/",
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    parser = KadParser(session=session, browser_cookies_path=cookies_path)

    parser.init()

    session.get.assert_called_once_with(
        "https://kad.arbitr.ru/",
        headers=parser._document_headers(),
        timeout=30,
    )
    session.get.return_value.raise_for_status.assert_called_once_with()
    assert session.cookies.get("ASP.NET_SessionId", domain="kad.arbitr.ru", path="/") == "session-cookie"
    assert session.cookies.get("__ddg1_", domain=".arbitr.ru", path="/") == "ddg-cookie"
    assert session.cookies.get("foreign", domain=".vk.com", path="/") is None
    assert session.cookies.get("pr_fp", domain=".arbitr.ru", path="/") == KadParser.DEFAULT_RUNTIME_COOKIES["pr_fp"]
    assert session.cookies.get("wasm", domain=".arbitr.ru", path="/") == KadParser.DEFAULT_RUNTIME_COOKIES["wasm"]


def test_kad_parse_search_instances_html() -> None:
    result = KadParser._parse_search_instances_html(
        """
        <a href="https://kad.arbitr.ru/Card/test-card-id" target="_blank" class="num_case">
            Ð32-28873/2024
        </a>
        <input type="hidden" id="documentsTotalCount" value="1" />
        """
    )

    assert result["Result"]["Items"] == [
        {
            "CaseNumber": "Ð32-28873/2024",
            "CardUrl": "https://kad.arbitr.ru/Card/test-card-id",
            "CardId": "test-card-id",
        }
    ]
    assert result["Result"]["Count"] == 1


def test_kad_search_by_number() -> None:
    session = make_kad_session()
    suggest_response = Mock()
    search_response = Mock()
    search_response.text = """
        <a href="https://kad.arbitr.ru/Card/test-card-id" target="_blank" class="num_case">
            Ð32-28873/2024
        </a>
        <input type="hidden" id="documentsTotalCount" value="1" />
    """
    session.post.side_effect = [suggest_response, search_response]
    parser = KadParser(session=session)
    parser.init = Mock()

    result = parser.search_by_number("Ð32-28873/2024")

    parser.init.assert_called_once_with()
    assert session.post.call_count == 2

    suggest_call, search_call = session.post.call_args_list
    assert suggest_call.args[0] == KadParser.SUGGEST_CASE_URL
    assert suggest_call.kwargs["json"]["CaseNumbers"] == ["Ð32-28873/2024"]
    assert suggest_call.kwargs["json"]["Cases"] == ["Ð32-28873/2024"]
    assert suggest_call.kwargs["timeout"] == 30

    assert search_call.args[0] == KadParser.SEARCH_URL
    assert search_call.kwargs["json"]["CaseNumbers"] == ["Ð32-28873/2024"]
    assert search_call.kwargs["json"]["Count"] == 25
    assert search_call.kwargs["headers"]["X-Date-Format"] == "iso"
    assert search_call.kwargs["timeout"] == 30

    suggest_response.raise_for_status.assert_called_once_with()
    search_response.raise_for_status.assert_called_once_with()
    assert result["Result"]["Items"][0]["CardId"] == "test-card-id"
    assert result["Result"]["Count"] == 1


@pytest.mark.parametrize(
    ("card_input", "expected_url"),
    [
        ("test-card-id", "https://kad.arbitr.ru/Card/test-card-id"),
        ("https://kad.arbitr.ru/Card/test-card-id", "https://kad.arbitr.ru/Card/test-card-id"),
        (
            {
                "CaseNumber": "Ð32-28873/2024",
                "CardUrl": "https://kad.arbitr.ru/Card/test-card-id",
                "CardId": "test-card-id",
            },
            "https://kad.arbitr.ru/Card/test-card-id",
        ),
    ],
)
def test_kad_get_card_info(card_input, expected_url) -> None:
    session = make_kad_session()
    response = Mock()
    response.text = """
        <h2 class="b-case-result">
            <a target="_blank" href="https://kad.arbitr.ru/Kad/PdfDocument/test">
                <i class="b-icon pdf"><i></i></i>
                Ðž Ð·Ð°Ð²ÐµÑ€ÑˆÐµÐ½Ð¸Ð¸ Ñ€ÐµÐ°Ð»Ð¸Ð·Ð°Ñ†Ð¸Ð¸ Ð¸Ð¼ÑƒÑ‰ÐµÑÑ‚Ð²Ð° Ð³Ñ€Ð°Ð¶Ð´Ð°Ð½Ð¸Ð½Ð° Ð¸ Ð¾ÑÐ²Ð¾Ð±Ð¾Ð¶Ð´ÐµÐ½Ð¸Ð¸ Ð³Ñ€Ð°Ð¶Ð´Ð°Ð½Ð¸Ð½Ð° Ð¾Ñ‚ Ð¸ÑÐ¿Ð¾Ð»Ð½ÐµÐ½Ð¸Ñ Ð¾Ð±ÑÐ·Ð°Ñ‚ÐµÐ»ÑŒÑÑ‚Ð²
            </a>
        </h2>
    """
    session.get.return_value = response
    parser = KadParser(session=session)
    parser.init = Mock()

    result = parser.get_card_info(card_input)

    parser.init.assert_called_once_with()
    session.get.assert_called_once_with(
        expected_url,
        headers=parser._document_headers(),
        timeout=30,
    )
    response.raise_for_status.assert_called_once_with()
    assert result["CardId"] == "test-card-id"
    assert result["CardUrl"] == expected_url
    assert (
        result["ResultText"]
        == "Ðž Ð·Ð°Ð²ÐµÑ€ÑˆÐµÐ½Ð¸Ð¸ Ñ€ÐµÐ°Ð»Ð¸Ð·Ð°Ñ†Ð¸Ð¸ Ð¸Ð¼ÑƒÑ‰ÐµÑÑ‚Ð²Ð° Ð³Ñ€Ð°Ð¶Ð´Ð°Ð½Ð¸Ð½Ð° Ð¸ Ð¾ÑÐ²Ð¾Ð±Ð¾Ð¶Ð´ÐµÐ½Ð¸Ð¸ Ð³Ñ€Ð°Ð¶Ð´Ð°Ð½Ð¸Ð½Ð° Ð¾Ñ‚ Ð¸ÑÐ¿Ð¾Ð»Ð½ÐµÐ½Ð¸Ñ Ð¾Ð±ÑÐ·Ð°Ñ‚ÐµÐ»ÑŒÑÑ‚Ð²"
    )
    assert result["Html"] == response.text


def test_kad_get_card_info_without_result_text() -> None:
    session = make_kad_session()
    response = Mock()
    response.text = "<html>card</html>"
    session.get.return_value = response
    parser = KadParser(session=session)
    parser.init = Mock()

    result = parser.get_card_info(
        {
            "CaseNumber": "Ð32-28873/2024",
            "CardUrl": "https://kad.arbitr.ru/Card/test-card-id",
            "CardId": "test-card-id",
        }
    )

    assert result["CardId"] == "test-card-id"
    assert result["CardUrl"] == "https://kad.arbitr.ru/Card/test-card-id"
    assert result["ResultText"] is None
    assert result["Html"] == "<html>card</html>"
