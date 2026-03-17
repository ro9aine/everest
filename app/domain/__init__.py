"""Domain-level schemas and errors shared across adapters and services."""

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
    "FedresursResult",
    "KadArbitrDocument",
    "KadArbitrResult",
    "MalformedResponseError",
    "NotFoundError",
    "TemporaryNetworkError",
]
