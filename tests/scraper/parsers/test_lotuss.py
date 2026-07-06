from decimal import Decimal
from pathlib import Path

import pytest

from scraper.parsers.lotuss import LotussParser


FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


@pytest.fixture
def parser() -> LotussParser:
    return LotussParser()


def test_parse_price_from_fixture(parser: LotussParser) -> None:
    html = (FIXTURES / "lotuss_product.html").read_text(encoding="utf-8")
    assert parser.parse_price(html) == Decimal("4.79")


def test_parse_price_returns_none_without_title(parser: LotussParser) -> None:
    html = (
        '<html><body>'
        '<p class="MuiTypography-body1">4.79</p>'
        '</body></html>'
    )
    assert parser.parse_price(html) is None


def test_parse_price_returns_none_without_price_candidate(parser: LotussParser) -> None:
    html = (
        '<html><body>'
        '<h6 class="MuiTypography-subtitle1">Some Product</h6>'
        '</body></html>'
    )
    assert parser.parse_price(html) is None


def test_parser_metadata(parser: LotussParser) -> None:
    assert parser.slug == "lotuss"
    assert parser.display_name == "Lotus's"
    assert "lotuss.com.my" in parser.domains
    assert "www.lotuss.com.my" in parser.domains


def test_parse_price_strips_commas(parser: LotussParser) -> None:
    html = (
        '<html><body>'
        '<h6 class="MuiTypography-subtitle1">X</h6>'
        '<p class="MuiTypography-body1">RM 1,234.56</p>'
        '</body></html>'
    )
    assert parser.parse_price(html) == Decimal("1234.56")


def test_parse_price_returns_none_when_all_candidates_unparseable(parser: LotussParser) -> None:
    html = (
        '<html><body>'
        '<h6 class="MuiTypography-subtitle1">X</h6>'
        '<p class="MuiTypography-body1">In stock</p>'
        '<p class="MuiTypography-body1">Free delivery</p>'
        '</body></html>'
    )
    assert parser.parse_price(html) is None
