import json
import re
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent

from app.parsers import build_headers


class KadParser:
    BASE_URL = "https://kad.arbitr.ru"
    DEFAULT_RECORDED_COOKIES_PATH = Path("recordings") / "kad_web_full_cookies.json"
    FALLBACK_CHROME_USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/145.0.0.0 Safari/537.36"
    )
    SUGGEST_CASE_URL = BASE_URL + "/Suggest/CaseNum?count=10"
    SEARCH_URL = BASE_URL + "/Kad/SearchInstances"
    KAD_COOKIE_DOMAIN = ".arbitr.ru"
    DEFAULT_RUNTIME_COOKIES = {
        "pr_fp": "9354dd7a78ac416b4ddcf159163f4a0229067a05543bd7d08b2ae221e7bd2406",
        "wasm": "53bc69d560d077b15c1f5a7e165f39e8",
    }

    def __init__(
        self,
        session: requests.Session | None = None,
        *,
        browser_cookies_path: str | Path | None = None,
    ) -> None:
        self.session = session or requests.Session()
        self.browser_cookies_path = (
            Path(browser_cookies_path) if browser_cookies_path is not None else self.DEFAULT_RECORDED_COOKIES_PATH
        )
        self.chrome_user_agent = self._get_chrome_user_agent()
        self.headers = self._build_headers()
        self._initialized = False

    @staticmethod
    def _get_chrome_user_agent() -> str:
        try:
            return UserAgent(
                browsers=["Chrome"],
                os=["Windows"],
                platforms=["desktop"],
                fallback=KadParser.FALLBACK_CHROME_USER_AGENT,
            ).random
        except Exception:
            return KadParser.FALLBACK_CHROME_USER_AGENT

    def _build_headers(self) -> dict[str, str]:
        headers = build_headers()
        chrome_match = re.search(r"Chrome/(\d+)", self.chrome_user_agent)
        chrome_major = chrome_match.group(1) if chrome_match else "145"
        headers["User-Agent"] = self.chrome_user_agent
        headers["Accept-Language"] = "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7"
        headers["sec-ch-ua"] = (
            f'"Not:A-Brand";v="99", "Google Chrome";v="{chrome_major}", "Chromium";v="{chrome_major}"'
        )
        headers["sec-ch-ua-mobile"] = "?0"
        headers["sec-ch-ua-platform"] = '"Windows"'
        return headers

    def _document_headers(self) -> dict[str, str]:
        return self.headers | {
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,image/apng,*/*;q=0.8"
            ),
            "Upgrade-Insecure-Requests": "1",
        }

    def _xhr_headers(self, *, accept: str) -> dict[str, str]:
        return self.headers | {
            "Accept": accept,
            "Referer": self.BASE_URL + "/",
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/json",
        }

    def _resolve_card_url(self, card: str | dict[str, str]) -> tuple[str, str]:
        if isinstance(card, dict):
            card_url = card.get("CardUrl")
            if card_url:
                return card_url, card.get("CardId") or card_url.rsplit("/", 1)[-1]
            card_id = card.get("CardId")
            if card_id:
                return self.BASE_URL + "/Card/" + card_id, card_id
            raise ValueError("Card payload must contain CardUrl or CardId")

        if card.startswith("http://") or card.startswith("https://"):
            return card, card.rsplit("/", 1)[-1]

        return self.BASE_URL + "/Card/" + card, card

    def _load_recorded_cookies(self) -> None:
        if not self.browser_cookies_path.exists():
            return

        with self.browser_cookies_path.open(encoding="utf-8") as stream:
            payload = json.load(stream)

        cookies = payload.get("cookies", []) if isinstance(payload, dict) else payload
        for cookie in cookies:
            domain = cookie.get("domain", "")
            if not domain.endswith("arbitr.ru"):
                continue
            self.session.cookies.set(
                name=cookie["name"],
                value=cookie["value"],
                domain=domain or "kad.arbitr.ru",
                path=cookie.get("path", "/"),
                secure=bool(cookie.get("secure", False)),
            )

    def _seed_runtime_cookies(self) -> None:
        for name, value in self.DEFAULT_RUNTIME_COOKIES.items():
            self.session.cookies.set(
                name=name,
                value=value,
                domain=self.KAD_COOKIE_DOMAIN,
                path="/",
                secure=True,
            )

    @staticmethod
    def _parse_search_instances_html(html: str) -> dict:
        soup = BeautifulSoup(html, "html.parser")
        items: list[dict[str, str]] = []
        for link in soup.select("a.num_case[href*='/Card/']"):
            href = link.get("href")
            if not href:
                continue
            case_number = link.get_text(" ", strip=True)
            items.append(
                {
                    "CaseNumber": case_number,
                    "CardUrl": href,
                    "CardId": href.rsplit("/", 1)[-1],
                }
            )

        total_count = None
        total_count_input = soup.select_one("#documentsTotalCount")
        if total_count_input is not None:
            total_count = total_count_input.get("value")
        return {
            "Result": {
                "Items": items,
                "Count": int(total_count) if total_count and total_count.isdigit() else len(items),
            },
            "Html": html,
        }

    @staticmethod
    def _extract_card_result_text(html: str) -> str | None:
        soup = BeautifulSoup(html, "html.parser")
        result_link = soup.select_one("h2.b-case-result a")
        if result_link is None:
            return None
        return result_link.get_text(" ", strip=True)

    def init(self) -> None:
        if self._initialized:
            return

        self._load_recorded_cookies()
        self._seed_runtime_cookies()
        response = self.session.get(self.BASE_URL + "/", headers=self._document_headers(), timeout=30)
        response.raise_for_status()
        self._initialized = True

    def search_by_number(self, number: str) -> dict:
        self.init()

        suggest_payload = {
            "Page": 1,
            "Count": 10,
            "Courts": [],
            "DateFrom": None,
            "DateTo": None,
            "Sides": [],
            "Judges": [],
            "CaseNumbers": [number],
            "WithVKSInstances": False,
            "Cases": [number],
        }
        suggest_response = self.session.post(
            self.SUGGEST_CASE_URL,
            json=suggest_payload,
            headers=self._xhr_headers(accept="application/json, text/javascript, */*"),
            timeout=30,
        )
        suggest_response.raise_for_status()

        search_payload = {
            "CaseNumbers": [number],
            "Count": 25,
            "Courts": [],
            "DateFrom": None,
            "DateTo": None,
            "Judges": [],
            "Page": 1,
            "Sides": [],
            "WithVKSInstances": False,
        }
        search_response = self.session.post(
            self.SEARCH_URL,
            json=search_payload,
            headers=self._xhr_headers(accept="*/*") | {"X-Date-Format": "iso"},
            timeout=30,
        )
        search_response.raise_for_status()
        return self._parse_search_instances_html(search_response.text)

    def get_card_info(self, card: str | dict[str, str]) -> dict:
        self.init()
        card_url, card_id = self._resolve_card_url(card)
        response = self.session.get(card_url, headers=self._document_headers(), timeout=30)
        response.raise_for_status()
        return {
            "CardId": card_id,
            "CardUrl": card_url,
            "ResultText": self._extract_card_result_text(response.text),
            "Html": response.text,
        }
