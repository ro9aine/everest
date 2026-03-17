import requests

from app.parsers import build_headers


class FedResursParser:
    """FedResurs parser."""
    BASE_URL = "https://fedresurs.ru/backend"

    def __init__(self, session: requests.Session | None = None) -> None:
        self.session = session or requests.Session()
        self.headers = build_headers()

    def find_persons(self, inn: str) -> dict:
        url = self.BASE_URL + f"/persons?searchString={inn}"
        response = self.session.get(url, headers=self.headers, timeout=30)
        return response.text
