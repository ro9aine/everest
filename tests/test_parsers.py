from unittest.mock import Mock

from app.parsers.fedresurs import FedResursParser
from app.parsers.kad import KadParser


def test_fedresurs_parser_can_be_instantiated() -> None:
    parser = FedResursParser()

    assert isinstance(parser, FedResursParser)
    assert "User-Agent" in parser.headers


def test_find_persons() -> None:
    session = Mock()
    session.get.return_value.text = "ok"
    parser = FedResursParser(session=session)
    result = parser.find_persons("1234567890")

    session.get.assert_called_once_with(
        "https://fedresurs.ru/backend/persons?searchString=1234567890",
        headers=parser.headers,
        timeout=30,
    )
    assert result == "ok"


def test_kad_parser_can_be_instantiated() -> None:
    parser = KadParser()

    assert isinstance(parser, KadParser)
    assert "User-Agent" in parser.headers
