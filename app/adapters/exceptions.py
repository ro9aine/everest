"""Backward-compatible exception re-exports for adapter consumers."""

from app.domain.errors import (
    AdapterError,
    BlockedByUpstreamError,
    MalformedResponseError,
    NotFoundError,
    TemporaryNetworkError,
)

__all__ = [
    "AdapterError",
    "BlockedByUpstreamError",
    "MalformedResponseError",
    "NotFoundError",
    "TemporaryNetworkError",
]
