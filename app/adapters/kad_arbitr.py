from __future__ import annotations

import re
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from app.domain.errors import (
    BlockedByUpstreamError,
    MalformedResponseError,
    NotFoundError,
    TemporaryNetworkError,
)
from app.domain.schemas import KadArbitrDocument, KadArbitrResult
from app.parsers.kad import KadParser


class KadArbitrParserAdapter:
    """Thin adapter that hides KAD parser response details from the app layer.

    Assumptions:
    - parser search and card retrieval logic remain inside ``KadParser``
    - case metadata can be normalized from the card HTML with lightweight parsing
    - anti-bot pages should be surfaced as a dedicated domain exception
    """

    _DATE_RE = re.compile(r"\b\d{2}\.\d{2}\.\d{4}(?: \d{2}:\d{2}(?::\d{2})?)?\b")
    _BLOCK_MARKERS = (
        "captcha",
        "anti-bot",
        "cloudflare",
        "ddos-guard",
        "access denied",
        "suspicious activity",
    )

    def __init__(self, parser: KadParser | None = None) -> None:
        self._parser = parser or KadParser()

    def get_case_documents(self, case_number: str) -> KadArbitrResult:
        normalized_case_number = self._normalize_case_number(case_number)

        search_payload = self._translate_request_error(
            lambda: self._parser.search_by_number(normalized_case_number)
        )
        items = search_payload.get("Result", {}).get("Items")
        if not isinstance(items, list):
            raise MalformedResponseError("KAD search response is missing list field 'Result.Items'")

        card = self._pick_card(items, normalized_case_number)
        if card is None:
            search_html = search_payload.get("Html", "")
            if self._looks_blocked(search_html):
                raise BlockedByUpstreamError("KAD search response looks like an anti-bot page")
            raise NotFoundError(f"KAD returned no case for number '{normalized_case_number}'")

        card_payload = self._translate_request_error(lambda: self._parser.get_card_info(card))
        html = card_payload.get("Html")
        if not isinstance(html, str) or not html.strip():
            raise MalformedResponseError("KAD card payload is missing non-empty field 'Html'")
        if self._looks_blocked(html):
            raise BlockedByUpstreamError("KAD card page looks like an anti-bot page")

        documents = self._extract_documents(html)
        if not documents:
            result_text = card_payload.get("ResultText")
            if isinstance(result_text, str) and result_text.strip():
                documents = (
                    KadArbitrDocument(
                        document_date=None,
                        document_name=None,
                        document_title=result_text.strip(),
                    ),
                )
            else:
                raise MalformedResponseError("KAD card payload does not contain recognizable document metadata")

        latest_document = max(documents, key=lambda item: item.document_date or datetime.min)
        card_id = card_payload.get("CardId")
        card_url = card_payload.get("CardUrl")
        if not isinstance(card_id, str) or not card_id.strip():
            raise MalformedResponseError("KAD card payload is missing non-empty field 'CardId'")
        if not isinstance(card_url, str) or not card_url.strip():
            raise MalformedResponseError("KAD card payload is missing non-empty field 'CardUrl'")

        return KadArbitrResult(
            case_number=normalized_case_number,
            card_id=card_id.strip(),
            card_url=card_url.strip(),
            latest_date=latest_document.document_date,
            latest_document_name=latest_document.document_name,
            latest_document_title=latest_document.document_title,
            documents=documents,
            raw_search_payload=search_payload,
            raw_card_payload=card_payload,
        )

    @staticmethod
    def _normalize_case_number(case_number: str) -> str:
        normalized = " ".join(str(case_number).split())
        if not normalized:
            raise ValueError("case_number must be a non-empty string")
        return normalized

    @staticmethod
    def _pick_card(items: list[dict], normalized_case_number: str) -> dict | None:
        for item in items:
            if not isinstance(item, dict):
                continue
            current = " ".join(str(item.get("CaseNumber", "")).split())
            if current == normalized_case_number:
                return item
        return items[0] if items and isinstance(items[0], dict) else None

    @classmethod
    def _looks_blocked(cls, content: object) -> bool:
        if not isinstance(content, str):
            return False
        haystack = content.lower()
        return any(marker in haystack for marker in cls._BLOCK_MARKERS)

    @classmethod
    def _extract_documents(cls, html: str) -> tuple[KadArbitrDocument, ...]:
        soup = BeautifulSoup(html, "html.parser")
        documents: list[KadArbitrDocument] = []
        seen: set[tuple[datetime | None, str | None, str | None]] = set()

        selectors = (
            "tr",
            ".b-case-document",
            ".b-doc-item",
            ".document",
            "li",
        )
        for selector in selectors:
            for node in soup.select(selector):
                document = cls._extract_document_from_node(node)
                if document is None:
                    continue
                key = (document.document_date, document.document_name, document.document_title)
                if key in seen:
                    continue
                seen.add(key)
                documents.append(document)

        documents.sort(key=lambda item: item.document_date or datetime.min, reverse=True)
        return tuple(documents)

    @classmethod
    def _extract_document_from_node(cls, node) -> KadArbitrDocument | None:
        text = node.get_text(" ", strip=True)
        if not text:
            return None

        date_match = cls._DATE_RE.search(text)
        document_date = cls._parse_datetime(date_match.group(0)) if date_match else None

        name = None
        for link in node.select("a"):
            candidate = link.get_text(" ", strip=True)
            if candidate:
                name = candidate
                break

        title = cls._clean_title(text, date_match.group(0) if date_match else None)
        if title and name and title == name:
            title = None

        if not any((document_date, name, title)):
            return None

        return KadArbitrDocument(
            document_date=document_date,
            document_name=name,
            document_title=title,
        )

    @staticmethod
    def _clean_title(text: str, date_text: str | None) -> str | None:
        cleaned = text
        if date_text:
            cleaned = cleaned.replace(date_text, " ")
        cleaned = " ".join(cleaned.split())
        return cleaned or None

    @staticmethod
    def _parse_datetime(value: str | None) -> datetime | None:
        if not value:
            return None
        for fmt in ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M", "%d.%m.%Y"):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
        return None

    @staticmethod
    def _translate_request_error(func):
        try:
            return func()
        except requests.HTTPError as exc:
            status_code = exc.response.status_code if exc.response is not None else None
            if status_code in {403, 429}:
                raise BlockedByUpstreamError(
                    f"KAD request was blocked by upstream with status {status_code}"
                ) from exc
            if status_code is not None and status_code >= 500:
                raise TemporaryNetworkError(
                    f"KAD temporary upstream failure with status {status_code}"
                ) from exc
            raise TemporaryNetworkError("KAD request failed") from exc
        except (requests.ConnectionError, requests.Timeout) as exc:
            raise TemporaryNetworkError("KAD request failed due to a temporary network error") from exc
