from decimal import Decimal
from urllib.parse import urlparse


class StoreParser:
    """Base interface every store parser implements.

    Subclasses set the three class-level attributes and implement
    ``parse_price``. Registration happens via ``register()`` at import time
    from each parser module.
    """

    slug: str = ""
    display_name: str = ""
    domains: list[str] = []

    def parse_price(self, html: str) -> Decimal | None:
        raise NotImplementedError


_BY_DOMAIN: dict[str, StoreParser] = {}
_BY_SLUG: dict[str, StoreParser] = {}


def register(parser: StoreParser) -> None:
    if not parser.slug or not parser.domains:
        raise ValueError(
            f"Parser {parser!r} must define a slug and at least one domain",
        )
    # Validate all domains for conflicts FIRST (before mutating anything)
    for domain in parser.domains:
        key = domain.lower()
        existing = _BY_DOMAIN.get(key)
        if existing is not None and existing is not parser:
            raise ValueError(
                f"Domain {key!r} is already registered by {existing.slug!r}",
            )

    # If validation passed, commit all changes atomically
    for domain in parser.domains:
        key = domain.lower()
        _BY_DOMAIN[key] = parser
    _BY_SLUG[parser.slug] = parser


def resolve_by_url(url: str) -> StoreParser | None:
    host = urlparse(url).netloc.lower()
    return _BY_DOMAIN.get(host)


def resolve_by_slug(slug: str) -> StoreParser | None:
    return _BY_SLUG.get(slug)


def all_parsers() -> list[StoreParser]:
    return list(_BY_SLUG.values())


def reset_registry() -> None:
    _BY_DOMAIN.clear()
    _BY_SLUG.clear()
