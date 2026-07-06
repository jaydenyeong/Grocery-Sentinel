from decimal import Decimal

import pytest

from scraper.parsers import base


class _FakeParser(base.StoreParser):
    def __init__(self, slug: str, display_name: str, domains: list[str]) -> None:
        self.slug = slug
        self.display_name = display_name
        self.domains = domains

    def parse_price(self, html: str) -> Decimal | None:
        return Decimal("1.00")


@pytest.fixture(autouse=True)
def _reset_registry():
    # Snapshot real parsers registered at import time (e.g. JayaGrocer)
    # so tests can start from a clean slate without leaking that state
    # to other test modules.
    saved_domains = dict(base._BY_DOMAIN)
    saved_slugs = dict(base._BY_SLUG)
    base.reset_registry()
    yield
    base.reset_registry()
    base._BY_DOMAIN.update(saved_domains)
    base._BY_SLUG.update(saved_slugs)


def test_register_and_resolve_by_url() -> None:
    parser = _FakeParser("acme", "Acme", ["acme.com", "www.acme.com"])
    base.register(parser)

    assert base.resolve_by_url("https://acme.com/product/1") is parser
    assert base.resolve_by_url("https://www.acme.com/product/2") is parser


def test_resolve_by_url_unknown_returns_none() -> None:
    assert base.resolve_by_url("https://unknown.example/x") is None


def test_resolve_by_slug_roundtrips() -> None:
    parser = _FakeParser("acme", "Acme", ["acme.com"])
    base.register(parser)

    assert base.resolve_by_slug("acme") is parser
    assert base.resolve_by_slug("nope") is None


def test_all_parsers_returns_every_registered_parser() -> None:
    a = _FakeParser("acme", "Acme", ["acme.com"])
    b = _FakeParser("beta", "Beta", ["beta.com"])
    base.register(a)
    base.register(b)

    slugs = {p.slug for p in base.all_parsers()}
    assert slugs == {"acme", "beta"}


def test_duplicate_domain_registration_raises() -> None:
    base.register(_FakeParser("first", "First", ["shared.com"]))
    with pytest.raises(ValueError, match="shared.com"):
        base.register(_FakeParser("second", "Second", ["shared.com"]))


def test_resolve_by_url_is_case_insensitive_on_host() -> None:
    parser = _FakeParser("acme", "Acme", ["acme.com"])
    base.register(parser)

    assert base.resolve_by_url("https://ACME.com/p") is parser
