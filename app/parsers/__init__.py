from fake_useragent import UserAgent


def build_headers() -> dict[str, str]:
    return {
        "User-Agent": UserAgent().random,
        "Accept": "application/json, text/plain, */*",
    }
