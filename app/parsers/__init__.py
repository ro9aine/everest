from app.config import Settings
from fake_useragent import UserAgent


def build_headers() -> dict[str, str]:
    """Build default request headers, honoring optional env overrides."""

    settings = Settings.from_env()
    return {
        "User-Agent": settings.http.user_agent or UserAgent().random,
        "Accept": "application/json, text/plain, */*",
    }
