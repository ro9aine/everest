"""Application-facing adapters around source-specific parsers."""

from app.adapters.fedresurs import FedresursParserAdapter
from app.adapters.kad_arbitr import KadArbitrParserAdapter
from app.domain.errors import (
    AdapterError,
    BlockedByUpstreamError,
    MalformedResponseError,
    NotFoundError,
    TemporaryNetworkError,
)
from app.domain.schemas import FedresursResult, KadArbitrDocument, KadArbitrResult

__all__ = [
    "AdapterError",
    "BlockedByUpstreamError",
    "FedresursParserAdapter",
    "FedresursResult",
    "KadArbitrDocument",
    "KadArbitrParserAdapter",
    "KadArbitrResult",
    "MalformedResponseError",
    "NotFoundError",
    "TemporaryNetworkError",
]
