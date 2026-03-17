import requests

from app.parsers import build_headers


class KadParser:
    def __init__(self, session: requests.Session | None = None) -> None:
        self.session = session or requests.Session()
        self.headers = build_headers()
