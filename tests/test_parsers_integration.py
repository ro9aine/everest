import os

import pytest

from app.parsers.fedresurs import FedResursParser
from app.parsers.kad import KadParser


@pytest.mark.integration
def test_find_persons_live_real_person() -> None:
    inn = os.getenv("FEDRESURS_TEST_PERSON_INN", "231138771115")
    parser = FedResursParser()

    result = parser.find_persons(inn)

    assert isinstance(result, dict)
    assert "pageData" in result
    assert isinstance(result["pageData"], list)
    assert len(result["pageData"]) == 1
    assert result["pageData"][0]["inn"] == inn


@pytest.mark.integration
def test_get_bankruptcy_info_live_real_person() -> None:
    inn = os.getenv("FEDRESURS_TEST_PERSON_INN", "231138771115")
    parser = FedResursParser()

    persons_result = parser.find_persons(inn)
    guid = persons_result["pageData"][0]["guid"]

    result = parser.get_bankruptcy_info(guid)

    assert isinstance(result, dict)
    assert len(result["legalCases"]) == 1
    assert result["legalCases"][0]["number"] == "А32-28873/2024"


@pytest.mark.integration
def test_kad_search_by_number_live() -> None:
    case_number = os.getenv("KAD_TEST_CASE_NUMBER", "А32-28873/2024")
    parser = KadParser()

    result = parser.search_by_number(case_number)
    items = result["Result"]["Items"]

    assert isinstance(result, dict)
    assert isinstance(items, list)
    assert items
    assert any(item["CaseNumber"] == case_number for item in items)


@pytest.mark.integration
def test_kad_get_card_info_live() -> None:
    case_number = os.getenv("KAD_TEST_CASE_NUMBER", "А32-28873/2024")
    parser = KadParser()

    result = parser.search_by_number(case_number)
    items = result["Result"]["Items"]

    assert isinstance(result, dict)
    assert isinstance(items, list)
    assert items
    assert len(items) == 1

    result = parser.get_card_info(items[0]["CardId"])
    assert result["ResultText"] == "О завершении реализации имущества гражданина и освобождении гражданина от исполнения обязательств"
