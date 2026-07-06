from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend import main as api
from scraper.parsers import base as parsers_base
from scraper.parsers.jayagrocer import JayaGrocerParser


class _FakeVillageParser(parsers_base.StoreParser):
    slug = "village_grocer"
    display_name = "Village Grocer"
    domains = ["villagegrocer.com.my"]

    def parse_price(self, html):  # pragma: no cover - not exercised here
        return None


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, rows):
        self._rows = rows
        self._filter_slug: str | None = None

    def select(self, *_, **__):
        return self

    def order(self, *_, **__):
        return self

    def eq(self, column, value):
        if column == "store":
            self._filter_slug = value
        elif column == "id":
            self._rows = [r for r in self._rows if r.get("id") == value]
        elif column == "product_id":
            self._rows = [r for r in self._rows if r.get("product_id") == value]
        return self

    def limit(self, *_):
        return self

    def execute(self):
        rows = self._rows
        if self._filter_slug is not None:
            rows = [r for r in rows if r.get("store") == self._filter_slug]
        return _Result(rows)


class _FakeSupabase:
    def __init__(self, tables):
        self._tables = tables

    def table(self, name):
        return _Query(list(self._tables[name]))


PRODUCTS = [
    {"id": 1, "name": "Milk", "url": "https://jayagrocer.com/milk", "store": "jayagrocer"},
    {"id": 2, "name": "Bread", "url": "https://villagegrocer.com.my/bread", "store": "village_grocer"},
]

HISTORY = [
    {"product_id": 1, "price": 9.20, "scraped_at": "2026-07-05T10:00:00+00:00"},
    {"product_id": 1, "price": 8.50, "scraped_at": "2026-07-04T10:00:00+00:00"},
    {"product_id": 2, "price": 3.10, "scraped_at": "2026-07-05T10:00:00+00:00"},
]


@pytest.fixture
def client():
    fake = _FakeSupabase({"products": PRODUCTS, "price_history": HISTORY})
    # Ensure the Village Grocer parser is registered for /stores to include it.
    if parsers_base.resolve_by_slug("village_grocer") is None:
        parsers_base.register(_FakeVillageParser())
    with patch("backend.main.get_supabase_client", return_value=fake):
        yield TestClient(api.app)


def test_get_items_includes_store_display_name_and_slug(client):
    response = client.get("/items")
    assert response.status_code == 200
    items = response.json()
    by_id = {item["id"]: item for item in items}

    assert by_id[1]["store"] == "JayaGrocer"
    assert by_id[1]["store_slug"] == "jayagrocer"
    assert by_id[2]["store"] == "Village Grocer"
    assert by_id[2]["store_slug"] == "village_grocer"


def test_get_items_filters_by_store_query_param(client):
    response = client.get("/items?store=village_grocer")
    assert response.status_code == 200
    items = response.json()

    assert len(items) == 1
    assert items[0]["store_slug"] == "village_grocer"


def test_get_stores_returns_only_stores_with_products(client):
    response = client.get("/stores")
    assert response.status_code == 200
    stores = response.json()

    slugs = {s["slug"] for s in stores}
    assert slugs == {"jayagrocer", "village_grocer"}
    names = {s["slug"]: s["display_name"] for s in stores}
    assert names["jayagrocer"] == "JayaGrocer"
    assert names["village_grocer"] == "Village Grocer"


def test_get_history_uses_db_store(client):
    response = client.get("/history/1")
    assert response.status_code == 200
    body = response.json()

    assert body["store"] == "JayaGrocer"
