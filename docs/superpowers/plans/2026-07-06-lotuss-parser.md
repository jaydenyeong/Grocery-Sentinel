# Lotus's Parser Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Lotus's Malaysia (`lotuss.com.my`) as a second store in the Grocery-Sentinel scraper parser registry, so products from that site flow through the existing store-agnostic pipeline (sync, scrape, API, dashboard, Telegram alerts) with zero changes outside the new parser file.

**Architecture:** One new `StoreParser` subclass (`LotussParser`) registered by URL domain, following the exact shape of `scraper/parsers/jayagrocer.py`. Price extraction anchors on the product title (`<h6 class="MuiTypography-subtitle1">`) and walks forward through every subsequent `<p class="MuiTypography-body1">` element until one parses as a valid price, since MUI's `body1` class is generic and may appear on non-price text between the title and the real price.

**Tech Stack:** Python 3.11, BeautifulSoup, pytest (existing project stack — no new dependencies).

## Global Constraints

- Python 3.11.
- RM currency only — no multi-currency handling.
- Store slugs are lowercase snake_case: this store's slug is `lotuss`.
- Only create/modify: `scraper/parsers/lotuss.py`, `scraper/parsers/__init__.py`, `tests/fixtures/lotuss_product.html`, `tests/scraper/parsers/test_lotuss.py`. Nothing else — the registry, API, and frontend are already store-agnostic.
- Match CSS classes on the stable fragment only (e.g. `MuiTypography-subtitle1`, `MuiTypography-body1`), never on MUI's auto-generated hash suffix (e.g. `mui-1ig2233`), since those can change between deployments.
- `parse_price(html: str) -> Decimal | None` must return `None` on any failure to find or parse a price — never raise.

---

### Task 1: Lotus's Parser + Registration + Tests

**Files:**
- Create: `scraper/parsers/lotuss.py`
- Modify: `scraper/parsers/__init__.py`
- Create: `tests/fixtures/lotuss_product.html`
- Create: `tests/scraper/parsers/test_lotuss.py`

**Interfaces:**
- Consumes: `StoreParser` (base class) and `register` (registration function) from `scraper.parsers.base` — both already exist and are unchanged by this task.
- Produces: `class LotussParser(StoreParser)` with `slug = "lotuss"`, `display_name = "Lotus's"`, `domains = ["lotuss.com.my", "www.lotuss.com.my"]`, registered at import time via `register(LotussParser())`. No other task or file depends on anything new from this one — this is a leaf addition to the existing registry.

- [ ] **Step 1: Save the HTML fixture**

Create `tests/fixtures/lotuss_product.html`. This includes the real product title and price from the live site, plus a **decoy** `MuiTypography-body1` paragraph ("In stock") between the title and the real price, so the test actually exercises the "skip past a non-numeric candidate" behavior rather than assuming the first match is always correct:

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

- [ ] **Step 2: Write the failing test file**

Create `tests/scraper/parsers/test_lotuss.py`:

```python
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
```

- [ ] **Step 3: Run the tests and confirm they fail**

```bash
cd Grocery-Sentinel
python -m pytest tests/scraper/parsers/test_lotuss.py -v
```

Expected: all 6 tests fail with `ModuleNotFoundError: No module named 'scraper.parsers.lotuss'` (or similar import error).

- [ ] **Step 4: Implement the Lotus's parser**

Create `scraper/parsers/lotuss.py`:

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

- [ ] **Step 5: Register the parser in the package `__init__.py`**

Read the current `scraper/parsers/__init__.py` first — it currently imports `jayagrocer` to trigger that parser's registration at package-import time. Add a second import line for `lotuss` immediately after the existing `jayagrocer` import, e.g.:

```python
from scraper.parsers import jayagrocer  # noqa: F401
from scraper.parsers import lotuss  # noqa: F401
```

Do not otherwise modify the file — only add this one import line in the same style as the existing one.

- [ ] **Step 6: Run the Lotus's parser tests and confirm they pass**

```bash
cd Grocery-Sentinel
python -m pytest tests/scraper/parsers/test_lotuss.py -v
```

Expected: 6 passed.

- [ ] **Step 7: Run the full test suite to confirm nothing else broke**

```bash
cd Grocery-Sentinel
python -m pytest -v
```

Expected: 23 passed (17 existing + 6 new). In particular, confirm `tests/scraper/parsers/test_base.py`'s registry tests still pass — adding a second real parser to the shared registry via `scraper/parsers/__init__.py` must not conflict with any domain already registered by `JayaGrocerParser` (`jayagrocer.com`, `www.jayagrocer.com` — disjoint from `lotuss.com.my`, `www.lotuss.com.my`, so no collision is expected, but confirm the full suite is still green).

- [ ] **Step 8: Commit**

```bash
cd Grocery-Sentinel
git add scraper/parsers/lotuss.py scraper/parsers/__init__.py \
        tests/fixtures/lotuss_product.html \
        tests/scraper/parsers/test_lotuss.py
git commit -m "scraper: add Lotus's Malaysia parser"
```

---

## Post-Plan Follow-Ups (not implemented here)

- Add a Lotus's product URL to the Google Sheet to verify the parser end-to-end against the live site (sync, scrape, Telegram alert with `Lotus's` display name, dashboard chip filter). This needs live Supabase/Telegram credentials and a real browser, neither of which is available in an automated implementation pass — a human should do this after merge, the same way the original multi-store-support feature flagged its own unperformed live verification.
