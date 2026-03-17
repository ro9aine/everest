"""Backward-compatible DTO re-exports for adapter consumers."""

from app.domain.schemas import FedresursResult, KadArbitrDocument, KadArbitrResult

__all__ = [
    "FedresursResult",
    "KadArbitrDocument",
    "KadArbitrResult",
]
