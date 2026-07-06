from decimal import Decimal
from pathlib import Path

import pytest

from scraper.parsers.jayagrocer import JayaGrocerParser


FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


@pytest.fixture
def parser() -> JayaGrocerParser:
    return JayaGrocerParser()


def test_parse_price_from_fixture(parser: JayaGrocerParser) -> None:
    html = (FIXTURES / "jayagrocer_product.html").read_text(encoding="utf-8")
    assert parser.parse_price(html) == Decimal("9.20")


def test_parse_price_returns_none_without_h1(parser: JayaGrocerParser) -> None:
    html = '<html><body><span class="price">RM 9.20</span></body></html>'
    assert parser.parse_price(html) is None


def test_parse_price_returns_none_without_price_span(parser: JayaGrocerParser) -> None:
    html = "<html><body><h1>Title</h1><p>No price here.</p></body></html>"
    assert parser.parse_price(html) is None


def test_parser_metadata(parser: JayaGrocerParser) -> None:
    assert parser.slug == "jayagrocer"
    assert parser.display_name == "JayaGrocer"
    assert "jayagrocer.com" in parser.domains
    assert "www.jayagrocer.com" in parser.domains


def test_parse_price_strips_commas(parser: JayaGrocerParser) -> None:
    html = '<html><body><h1>X</h1><span class="price">RM 1,234.56</span></body></html>'
    assert parser.parse_price(html) == Decimal("1234.56")
