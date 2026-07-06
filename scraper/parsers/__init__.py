from scraper.parsers.base import (
    StoreParser,
    all_parsers,
    register,
    resolve_by_slug,
    resolve_by_url,
)

# Importing each parser module registers it via a top-level register() call.
from scraper.parsers import jayagrocer  # noqa: F401
from scraper.parsers import lotuss  # noqa: F401

__all__ = [
    "StoreParser",
    "all_parsers",
    "register",
    "resolve_by_slug",
    "resolve_by_url",
]
