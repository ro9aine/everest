from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv(path: str = ".env") -> None:
    """Load simple KEY=VALUE pairs from a local .env file into the environment.

    Existing environment variables win over .env values so Docker and runtime
    overrides behave predictably.
    """

    dotenv_path = Path(path)
    if not dotenv_path.exists():
        return

    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        os.environ.setdefault(key, value)


def _get_env_str(name: str, default: str) -> str:
    return os.getenv(name, default)


def _get_env_int(name: str, default: int, *, minimum: int | None = None) -> int:
    value = int(os.getenv(name, str(default)))
    if minimum is not None:
        value = max(minimum, value)
    return value


def _get_env_float(name: str, default: float, *, minimum: float | None = None) -> float:
    value = float(os.getenv(name, str(default)))
    if minimum is not None:
        value = max(minimum, value)
    return value


@dataclass(slots=True, frozen=True)
class ExecutionSettings:
    """Execution controls for batch processing."""

    worker_count: int = 1
    retry_attempts: int = 3
    retry_backoff_base_seconds: float = 1.0
    retry_backoff_multiplier: float = 2.0
    request_delay_seconds: float = 0.0


@dataclass(slots=True, frozen=True)
class HttpClientSettings:
    """Optional HTTP client configuration shared across sources."""

    proxy_url: str | None = None
    user_agent: str | None = None


@dataclass(slots=True, frozen=True)
class LoggingSettings:
    """Logging configuration for CLI and container execution."""

    level: str = "INFO"


@dataclass(slots=True, frozen=True)
class Settings:
    """Centralized application settings loaded from environment variables.

    Configuration strategy:
    - ``DATABASE_URL`` controls the SQLAlchemy engine target
    - ``SOURCE_MODE`` can provide a default batch source for the CLI
    - execution controls come from ``WORKER_COUNT``, ``REQUEST_DELAY_SECONDS``,
      ``RETRY_ATTEMPTS``, ``RETRY_BACKOFF_BASE_SECONDS``, and
      ``RETRY_BACKOFF_MULTIPLIER``
    - ``LOG_LEVEL`` controls stdout-friendly structured logging
    - ``PROXY_URL`` and ``USER_AGENT`` provide optional HTTP overrides
    """

    database_url: str = "sqlite:///./everest.db"
    source_mode: str = "fedresurs"
    execution: ExecutionSettings = field(default_factory=ExecutionSettings)
    logging: LoggingSettings = field(default_factory=LoggingSettings)
    http: HttpClientSettings = field(default_factory=HttpClientSettings)

    @classmethod
    def from_env(cls, *, dotenv_path: str = ".env") -> "Settings":
        _load_dotenv(dotenv_path)
        return cls(
            database_url=_get_env_str("DATABASE_URL", cls.database_url),
            source_mode=_get_env_str("SOURCE_MODE", cls.source_mode),
            execution=ExecutionSettings(
                worker_count=_get_env_int("WORKER_COUNT", 1, minimum=1),
                retry_attempts=_get_env_int("RETRY_ATTEMPTS", 3, minimum=1),
                retry_backoff_base_seconds=_get_env_float(
                    "RETRY_BACKOFF_BASE_SECONDS",
                    1.0,
                    minimum=0.0,
                ),
                retry_backoff_multiplier=_get_env_float(
                    "RETRY_BACKOFF_MULTIPLIER",
                    2.0,
                    minimum=1.0,
                ),
                request_delay_seconds=_get_env_float("REQUEST_DELAY_SECONDS", 0.0, minimum=0.0),
            ),
            logging=LoggingSettings(
                level=_get_env_str("LOG_LEVEL", "INFO").upper(),
            ),
            http=HttpClientSettings(
                proxy_url=os.getenv("PROXY_URL"),
                user_agent=os.getenv("USER_AGENT"),
            ),
        )
