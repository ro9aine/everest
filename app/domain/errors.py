"""Domain-level exceptions exposed by the adapter layer."""


class AdapterError(Exception):
    """Base adapter error."""


class NotFoundError(AdapterError):
    """Raised when an upstream source has no matching entity."""


class TemporaryNetworkError(AdapterError):
    """Raised for retryable transport and transient upstream failures."""


class BlockedByUpstreamError(AdapterError):
    """Raised when a source appears to block automation or show anti-bot checks."""


class MalformedResponseError(AdapterError):
    """Raised when parser output is structurally different from expectations."""
