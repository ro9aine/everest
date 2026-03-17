import requests

from app.parsers import build_headers


class FedResursParser:
    """FedResurs parser."""
    BASE_URL = "https://fedresurs.ru/backend"

    def __init__(self, session: requests.Session | None = None) -> None:
        self.session = session or requests.Session()
        self.headers = build_headers()

    def get_bankruptcy_info(self, guid: str) -> dict:
        url = self.BASE_URL + f"/persons/{guid}/bankruptcy"
        headers = self.headers | {
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Referer": f"https://fedresurs.ru/persons/{guid}",
        }
        response = self.session.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()

    def find_persons(self, inn: str) -> dict:
        params = {
            "searchString": inn,
            "limit": 15,
            "offset": 0,
            "isActive": "true",
        }
        headers = self.headers | {
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Referer": (
                "https://fedresurs.ru/entities"
                f"?searchString={inn}&regionNumber=all&isActive=true&offset=0&limit=15"
            ),
        }
        response = self.session.get(
            self.BASE_URL + "/persons",
            params=params,
            headers=headers,
            timeout=30,
        )
        response.raise_for_status()
        return response.json()
