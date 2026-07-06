# Lotus's Parser — Design Spec

**Date:** 2026-07-06
**Status:** Approved (design), awaiting implementation plan

## Goal

Add Lotus's Malaysia (`lotuss.com.my`) as a second store in the Grocery-Sentinel scraper parser registry, following the pattern established by the multi-store-support feature (`scraper/parsers/jayagrocer.py`).

## Scope

**In scope:**

- A new `LotussParser` registered under slug `lotuss`, display name `Lotus's`, domains `lotuss.com.my` and `www.lotuss.com.my`.
- Price extraction logic tuned to Lotus's React/MUI-based markup.
- Fixture-based tests mirroring `test_jayagrocer.py`'s coverage, plus one case specific to this parser's extra robustness (skipping a non-numeric match).

**Out of scope:**

- Any change to the registry, `main.py`, the backend API, or the frontend — Task 5/6 of the multi-store-support plan already made those store-agnostic. Adding a store is purely: one new parser file + one import line + tests.
- Adding a Lotus's product row to the Google Sheet — that's the user's own action once this ships.

## Source HTML (as provided)

Product title:
```html
<h6 class="MuiTypography-root MuiTypography-subtitle1 mui-hwtvd6">LOTUSS CHOCOLATE MILK UHT 1L</h6>
```

Price:
```html
<p class="MuiTypography-root MuiTypography-body1 mui-1ig2233">4.79</p>
```

Currency label (separate sibling element, not part of the price text):
```html
<p class="MuiTypography-root MuiTypography-body2 mui-sufsah">RM</p>
```

Key observations:
- MUI generates hash-suffixed classes (`mui-hwtvd6`, `mui-1ig2233`, `mui-sufsah`) that can change between deployments — the parser must match only on the stable class fragments (`MuiTypography-subtitle1`, `MuiTypography-body1`), never the hash suffix.
- The price element's text is bare (`"4.79"`, no `"RM"` prefix) — currency is a separate DOM node. The parser still defensively strips `"RM"` and commas from the matched text as cheap insurance against a future markup change.
- Full page structure between the title and price element was not available — `MuiTypography-body1` is a generic utility class likely reused elsewhere on the page. The parser must not assume the first match after the title is necessarily the price.

## Design

**New file:** `scraper/parsers/lotuss.py`

```python
from decimal import Decimal, InvalidOperation

from bs4 import BeautifulSoup

from scraper.parsers.base import StoreParser, register


class LotussParser(StoreParser):
    slug = "lotuss"
    display_name = "Lotus's"
    domains = ["lotuss.com.my", "www.lotuss.com.my"]

    def parse_price(self, html: str) -> Decimal | None:
        soup = BeautifulSoup(html, "html.parser")
        title = soup.find("h6", class_="MuiTypography-subtitle1")
        if title is None:
            return None
        for candidate in title.find_all_next("p", class_="MuiTypography-body1"):
            raw = candidate.get_text(strip=True)
            text = raw.replace("RM", "").replace(",", "").strip()
            try:
                return Decimal(text)
            except InvalidOperation:
                continue
        return None


register(LotussParser())
```

**Behavioral contract** (matches `StoreParser`'s `parse_price(html) -> Decimal | None`):
- Returns `None` if no `<h6 class="MuiTypography-subtitle1">` title is found.
- Walks forward through every subsequent `<p class="MuiTypography-body1">` element (via `find_all_next`, not `find_next`) and returns the first one whose text parses as a `Decimal` after stripping `"RM"` and commas.
- Returns `None` if the title exists but no subsequent `body1` element parses as a valid number (covers both "no price element at all" and "every candidate is non-numeric text").

**Registration:** add one line to `scraper/parsers/__init__.py`, in the same style as the existing JayaGrocer import:

```python
from scraper.parsers import lotuss  # noqa: F401
```

## Testing

New file `tests/scraper/parsers/test_lotuss.py`, fixture `tests/fixtures/lotuss_product.html`.

The fixture must include a **decoy** `MuiTypography-body1` paragraph between the title and the real price, so the "skip past non-numeric candidates" behavior is actually exercised rather than assumed:

```html
<!doctype html>
<html>
  <body>
    <div class="product">
      <h6 class="MuiTypography-root MuiTypography-subtitle1 mui-hwtvd6">LOTUSS CHOCOLATE MILK UHT 1L</h6>
      <p class="MuiTypography-root MuiTypography-body1 mui-abc123">In stock</p>
      <p class="MuiTypography-root MuiTypography-body2 mui-sufsah">RM</p>
      <p class="MuiTypography-root MuiTypography-body1 mui-1ig2233">4.79</p>
    </div>
  </body>
</html>
```

Test cases (case 1 uses the fixture file above; the rest use small inline HTML strings built directly in the test, matching `test_jayagrocer.py`'s existing style, since the fixture already contains a valid price and can't double as a "no valid price" scenario):

1. `test_parse_price_from_fixture` — parses `4.79` correctly from the fixture, skipping the "In stock" decoy.
2. `test_parse_price_returns_none_without_title` — inline HTML with a `body1` price paragraph but no `<h6 class="MuiTypography-subtitle1">` → `None`.
3. `test_parse_price_returns_none_without_price_candidate` — inline HTML with the title but zero `body1` elements anywhere after it → `None`.
4. `test_parser_metadata` — `slug == "lotuss"`, `display_name == "Lotus's"`, both domains present.
5. `test_parse_price_strips_commas` — inline HTML, e.g. `"RM 1,234.56"` in the `body1` element (defensive case, even though real markup doesn't inline RM) → `Decimal("1234.56")`.
6. `test_parse_price_returns_none_when_all_candidates_unparseable` — inline HTML with the title followed by one or more `body1` elements, none of them numeric (e.g. `"In stock"`, `"Free delivery"`) → `None`. Distinct from case 3: here candidates exist but all fail to parse, rather than no candidates existing at all.

## Rollout

Single-step: land the new parser file, the `__init__.py` import, and the tests together. No migration, no API change, no frontend change — the registry-based design from multi-store-support already makes the rest of the system store-agnostic. Once merged, the user adds a Lotus's product URL to the Google Sheet and it flows through automatically.
