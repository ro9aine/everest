from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_DATABASE_URL = "sqlite:///./everest.db"
DEFAULT_LOG_LEVEL = "INFO"


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
class HttpClientSettings:
    """Optional HTTP client configuration shared across parsers."""

    user_agent: str | None = None


@dataclass(slots=True, frozen=True)
class LoggingSettings:
    """Logging configuration for CLI and container execution."""

    level: str = "INFO"


@dataclass(slots=True, frozen=True)
class RetrySettings:
    """Retry configuration for transient parser request failures."""

    attempts: int = 3
    backoff_seconds: float = 1.0
    backoff_multiplier: float = 2.0


@dataclass(slots=True, frozen=True)
class Settings:
    """Centralized application settings loaded from environment variables."""

    database_url: str = DEFAULT_DATABASE_URL
    logging: LoggingSettings = field(default_factory=LoggingSettings)
    http: HttpClientSettings = field(default_factory=HttpClientSettings)
    retry: RetrySettings = field(default_factory=RetrySettings)

    @classmethod
    def from_env(cls, *, dotenv_path: str = ".env") -> "Settings":
        _load_dotenv(dotenv_path)
        return cls(
            database_url=_get_env_str("DATABASE_URL", DEFAULT_DATABASE_URL),
            logging=LoggingSettings(
                level=_get_env_str("LOG_LEVEL", DEFAULT_LOG_LEVEL).upper(),
            ),
            http=HttpClientSettings(
                user_agent=os.getenv("USER_AGENT"),
            ),
            retry=RetrySettings(
                attempts=_get_env_int("RETRY_ATTEMPTS", 3, minimum=1),
                backoff_seconds=_get_env_float("RETRY_BACKOFF_SECONDS", 1.0, minimum=0.0),
                backoff_multiplier=_get_env_float("RETRY_BACKOFF_MULTIPLIER", 2.0, minimum=1.0),
            ),
        )
