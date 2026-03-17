from app.parsers.fedresurs import FedResursParser
from app.parsers.kad import KadParser


def test_fedresurs_parser_can_be_instantiated() -> None:
    parser = FedResursParser()

    assert isinstance(parser, FedResursParser)


def test_kad_parser_can_be_instantiated() -> None:
    parser = KadParser()

    assert isinstance(parser, KadParser)
