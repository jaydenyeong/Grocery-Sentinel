# Multi-Store Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable Grocery-Sentinel to track products from multiple Malaysian grocery stores through the same scraper, API, dashboard, and Telegram alerts — with zero disruption to existing Jayagrocer data.

**Architecture:** Add a `store` slug column to the `products` table. Introduce a per-store scraper registry keyed by URL domain, with one Python file per store implementing a common `StoreParser` interface. `scraper/main.py`'s `fetch_price` and `sync_products_from_sheets` route through the registry. The backend exposes a new `/stores` endpoint plus `store_slug` on responses, and the frontend adds a chip-filter row above the existing table.

**Tech Stack:** Python 3.11 · FastAPI · Supabase (Postgres) · Crawl4AI · BeautifulSoup · pytest · vanilla JS + Chart.js.

## Global Constraints

- Python **3.11** (as declared in the project README).
- **RM currency only** in v1; parsers return `Decimal` prices in RM.
- Store slugs are lowercase `snake_case` (e.g. `jayagrocer`, `village_grocer`).
- **Fail loud** on unmapped URL domains during sync (log error + skip row) and on duplicate parser domain registration (raise at import time).
- **No Google Sheet format changes.** Sheet columns remain `item, url`.
- **No cross-store canonicalization** and **no multi-currency handling** in v1.
- Backend (`backend/`) may import from `scraper.parsers` — both live in the same repo root.
- Every step ends with a passing test or a passing manual verification, then a commit.
- Do not commit `.env`, `price-sentinel-*.json`, or `__pycache__/`.

---

### Task 1: Database Migration — Add `store` Column

**Files:**
- Create: `Grocery-Sentinel/migrations/2026-07-06-add-store-to-products.sql`
- Modify: `Grocery-Sentinel/schema.sql` (append the new column so a fresh setup includes it)

**Interfaces:**
- Consumes: nothing.
- Produces: `products.store TEXT NOT NULL` column, backfilled to `'jayagrocer'` for every existing row; index `idx_products_store` on `products(store)`. Task 3 and Task 5 rely on this column existing.

- [ ] **Step 1: Create the migration file**

Create `Grocery-Sentinel/migrations/2026-07-06-add-store-to-products.sql`:

```sql
-- 2026-07-06: Add store attribution to products.
-- Idempotent: safe to re-run.

ALTER TABLE products
  ADD COLUMN IF NOT EXISTS store TEXT;

UPDATE products
  SET store = 'jayagrocer'
  WHERE store IS NULL;

ALTER TABLE products
  ALTER COLUMN store SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_products_store
  ON products(store);
```

- [ ] **Step 2: Update `schema.sql` so fresh setups include `store`**

In `Grocery-Sentinel/schema.sql`, replace the `products` table block (lines 5-12) with:

```sql
-- Products table: stores product information from Google Sheets
CREATE TABLE IF NOT EXISTS products (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    price NUMERIC(10, 2),
    store TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

And append immediately after the existing `idx_products_url` index (around line 27):

```sql
CREATE INDEX IF NOT EXISTS idx_products_store ON products(store);
```

- [ ] **Step 3: Run the migration against Supabase**

Open Supabase SQL Editor and paste the contents of `migrations/2026-07-06-add-store-to-products.sql`. Run it.

- [ ] **Step 4: Verify the column and backfill**

In Supabase SQL Editor, run:

```sql
SELECT COUNT(*) AS total,
       COUNT(store) AS with_store,
       COUNT(*) FILTER (WHERE store = 'jayagrocer') AS jayagrocer
FROM products;
```

Expected: `total = with_store = jayagrocer` (every row is `jayagrocer`).

Also verify the index exists:

```sql
SELECT indexname FROM pg_indexes WHERE tablename = 'products';
```

Expected output includes `idx_products_store`.

- [ ] **Step 5: Commit**

```bash
cd Grocery-Sentinel
git add migrations/2026-07-06-add-store-to-products.sql schema.sql
git commit -m "db: add store column to products with jayagrocer backfill"
```

---

### Task 2: Scraper Registry Infrastructure + Test Harness

**Files:**
- Create: `Grocery-Sentinel/scraper/parsers/__init__.py`
- Create: `Grocery-Sentinel/scraper/parsers/base.py`
- Create: `Grocery-Sentinel/tests/__init__.py`
- Create: `Grocery-Sentinel/tests/conftest.py`
- Create: `Grocery-Sentinel/tests/scraper/__init__.py`
- Create: `Grocery-Sentinel/tests/scraper/parsers/__init__.py`
- Create: `Grocery-Sentinel/tests/scraper/parsers/test_base.py`
- Create: `Grocery-Sentinel/requirements-dev.txt`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `class StoreParser` in `scraper.parsers.base` with attributes `slug: str`, `display_name: str`, `domains: list[str]` and method `parse_price(html: str) -> Decimal | None`.
  - `scraper.parsers.base.register(parser: StoreParser) -> None`
  - `scraper.parsers.base.resolve_by_url(url: str) -> StoreParser | None`
  - `scraper.parsers.base.resolve_by_slug(slug: str) -> StoreParser | None`
  - `scraper.parsers.base.all_parsers() -> list[StoreParser]`
  - `scraper.parsers.base.reset_registry() -> None` (test-only helper)
  - `scraper.parsers` package re-exports the four public functions above.
  - pytest is installed as a dev dependency.
- Task 3 registers `JayaGrocerParser`; Task 4 and Task 5 call `resolve_by_url` / `resolve_by_slug` / `all_parsers`.

- [ ] **Step 1: Create the dev requirements file**

Create `Grocery-Sentinel/requirements-dev.txt`:

```
pytest>=8.0.0
```

Install it:

```bash
cd Grocery-Sentinel
pip install -r requirements-dev.txt
```

- [ ] **Step 2: Create test package skeleton**

Create empty files (no content):
- `Grocery-Sentinel/tests/__init__.py`
- `Grocery-Sentinel/tests/scraper/__init__.py`
- `Grocery-Sentinel/tests/scraper/parsers/__init__.py`

Create `Grocery-Sentinel/tests/conftest.py`:

```python
import sys
from pathlib import Path

# Make the project root importable so tests can `from scraper.parsers ...`
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
```

- [ ] **Step 3: Write the failing registry tests**

Create `Grocery-Sentinel/tests/scraper/parsers/test_base.py`:

```python
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
```

- [ ] **Step 4: Run the tests and confirm they fail**

```bash
cd Grocery-Sentinel
pytest tests/scraper/parsers/test_base.py -v
```

Expected: all tests fail with `ModuleNotFoundError: No module named 'scraper.parsers'` (or similar import error).

- [ ] **Step 5: Implement `scraper/parsers/base.py`**

Create `Grocery-Sentinel/scraper/parsers/base.py`:

```python
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
    for domain in parser.domains:
        key = domain.lower()
        existing = _BY_DOMAIN.get(key)
        if existing is not None and existing is not parser:
            raise ValueError(
                f"Domain {key!r} is already registered by {existing.slug!r}",
            )
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
```

- [ ] **Step 6: Create `scraper/parsers/__init__.py` (registry re-exports only for now)**

Create `Grocery-Sentinel/scraper/parsers/__init__.py`:

```python
from scraper.parsers.base import (
    StoreParser,
    all_parsers,
    register,
    resolve_by_slug,
    resolve_by_url,
)

__all__ = [
    "StoreParser",
    "all_parsers",
    "register",
    "resolve_by_slug",
    "resolve_by_url",
]
```

Task 3 will add `from scraper.parsers import jayagrocer  # noqa: F401` here to trigger JayaGrocer's registration.

- [ ] **Step 7: Run the tests and confirm they pass**

```bash
cd Grocery-Sentinel
pytest tests/scraper/parsers/test_base.py -v
```

Expected: 6 passed.

- [ ] **Step 8: Commit**

```bash
cd Grocery-Sentinel
git add scraper/parsers/__init__.py scraper/parsers/base.py \
        tests/__init__.py tests/conftest.py tests/scraper/__init__.py \
        tests/scraper/parsers/__init__.py tests/scraper/parsers/test_base.py \
        requirements-dev.txt
git commit -m "scraper: add per-store parser registry with tests"
```

---

### Task 3: Extract JayaGrocer Parser into the Registry

**Files:**
- Create: `Grocery-Sentinel/scraper/parsers/jayagrocer.py`
- Modify: `Grocery-Sentinel/scraper/parsers/__init__.py` (import jayagrocer to trigger registration)
- Create: `Grocery-Sentinel/tests/fixtures/jayagrocer_product.html`
- Create: `Grocery-Sentinel/tests/scraper/parsers/test_jayagrocer.py`

**Interfaces:**
- Consumes: `StoreParser`, `register` from Task 2.
- Produces: `class JayaGrocerParser(StoreParser)` registered under `slug="jayagrocer"`, `display_name="JayaGrocer"`, `domains=["jayagrocer.com", "www.jayagrocer.com"]`. Task 4 relies on `resolve_by_url("https://www.jayagrocer.com/…")` returning this parser.

- [ ] **Step 1: Save an HTML fixture**

Create `Grocery-Sentinel/tests/fixtures/jayagrocer_product.html` with minimal HTML that matches the selector logic currently in `main.py:163-178` (an `<h1>` followed by a `<span class="price">`):

```html
<!doctype html>
<html>
  <body>
    <div class="product">
      <h1 class="product-title">Farm Fresh Full Cream Milk 1L</h1>
      <div class="price-block">
        <span class="price">RM 9.20</span>
      </div>
    </div>
  </body>
</html>
```

- [ ] **Step 2: Write the failing parser test**

Create `Grocery-Sentinel/tests/scraper/parsers/test_jayagrocer.py`:

```python
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
```

- [ ] **Step 3: Run the test and confirm it fails**

```bash
cd Grocery-Sentinel
pytest tests/scraper/parsers/test_jayagrocer.py -v
```

Expected: import error on `scraper.parsers.jayagrocer`.

- [ ] **Step 4: Implement the JayaGrocer parser**

Create `Grocery-Sentinel/scraper/parsers/jayagrocer.py`:

```python
from decimal import Decimal

from bs4 import BeautifulSoup

from scraper.parsers.base import StoreParser, register


class JayaGrocerParser(StoreParser):
    slug = "jayagrocer"
    display_name = "JayaGrocer"
    domains = ["jayagrocer.com", "www.jayagrocer.com"]

    def parse_price(self, html: str) -> Decimal | None:
        soup = BeautifulSoup(html, "html.parser")
        h1 = soup.find("h1")
        if h1 is None:
            return None
        price_el = h1.find_next("span", class_="price")
        if price_el is None:
            return None
        raw = price_el.get_text(strip=True)
        text = raw.replace("RM", "").replace(",", "").strip()
        return Decimal(text)


register(JayaGrocerParser())
```

- [ ] **Step 5: Wire JayaGrocer into the parsers package**

Modify `Grocery-Sentinel/scraper/parsers/__init__.py` to import the jayagrocer module (triggering registration on package import). Replace the file's contents with:

```python
from scraper.parsers.base import (
    StoreParser,
    all_parsers,
    register,
    resolve_by_slug,
    resolve_by_url,
)

# Importing each parser module registers it via a top-level register() call.
from scraper.parsers import jayagrocer  # noqa: F401

__all__ = [
    "StoreParser",
    "all_parsers",
    "register",
    "resolve_by_slug",
    "resolve_by_url",
]
```

- [ ] **Step 6: Run the parser tests and confirm they pass**

```bash
cd Grocery-Sentinel
pytest tests/scraper/parsers/test_jayagrocer.py -v
```

Expected: 5 passed.

- [ ] **Step 7: Run the full test suite to confirm nothing else broke**

```bash
cd Grocery-Sentinel
pytest -v
```

Expected: 11 passed (6 from Task 2, 5 from Task 3).

- [ ] **Step 8: Commit**

```bash
cd Grocery-Sentinel
git add scraper/parsers/jayagrocer.py scraper/parsers/__init__.py \
        tests/fixtures/jayagrocer_product.html \
        tests/scraper/parsers/test_jayagrocer.py
git commit -m "scraper: port JayaGrocer to the parser registry"
```

---

### Task 4: Wire `main.py` to the Registry (fetch_price, sync, alerts)

**Files:**
- Modify: `Grocery-Sentinel/main.py`
  - `fetch_price` (currently lines 147-187) — route price parsing through the registry.
  - `sync_products_from_sheets` (currently lines 82-145) — attribute store on insert, skip URLs with no parser.
  - `check_prices` (currently lines 272-339) — load `store` from DB and pass display name into alerts.
  - `send_telegram_alert` and `send_new_product_alert` signatures — accept a `store_display_name` parameter.

**Interfaces:**
- Consumes: `resolve_by_url` and `resolve_by_slug` from Task 2/3.
- Produces: `main.py` inserts new products with `store = parser.slug` and includes the store display name in every Telegram alert. Behaviour for existing rows is unchanged (they already have `store='jayagrocer'` from Task 1).

- [ ] **Step 1: Add the registry import at the top of `main.py`**

In `Grocery-Sentinel/main.py`, immediately after the existing `from bs4 import BeautifulSoup` (line 23), add:

```python
from scraper.parsers import resolve_by_slug, resolve_by_url
```

- [ ] **Step 2: Replace `fetch_price` body with a registry-routed version**

In `Grocery-Sentinel/main.py`, replace the entire `fetch_price` method (lines 147-187) with:

```python
    def fetch_price(self, url: str) -> Optional[Decimal]:
        """Fetch current price using the parser registered for this URL's domain."""
        logger.debug(f"Fetching price from: {url}")

        parser = resolve_by_url(url)
        if parser is None:
            logger.error(f"No parser registered for URL: {url}")
            return None

        try:
            async def scrape_price():
                async with AsyncWebCrawler(verbose=False) as crawler:
                    result = await crawler.arun(url=url)

                    if not result.success or not result.html:
                        logger.warning(f"Failed to fetch page: {url}")
                        return None

                    return parser.parse_price(result.html)

            return asyncio.run(scrape_price())

        except Exception as e:
            logger.error(f"Error fetching price from {url}: {e}")
            return None
```

Note: the nested `import asyncio` in the original method is removed because `asyncio` is already imported at the top of the file (line 12). `BeautifulSoup` is no longer used here — leave the top-level import in place since other future scraping code could use it, and removing an import that touches package initialisation is orthogonal to this feature.

- [ ] **Step 3: Update `sync_products_from_sheets` to attribute the store**

In `Grocery-Sentinel/main.py`, inside the `for row in rows:` loop of `sync_products_from_sheets`, locate the block that inserts a new product (currently around lines 125-134):

```python
                    else:
                        # Insert new product
                        self.supabase.table("products").insert({
                            "name": item_name,
                            "url": url
                        }).execute()
                        logger.info(f"Added new product: {item_name} ({url})")

                        # Telegram alert for new product
                        self.send_new_product_alert(item_name, url)
```

Replace it with:

```python
                    else:
                        # Attribute store from URL domain via the parser registry.
                        parser = resolve_by_url(url)
                        if parser is None:
                            logger.error(
                                f"No parser for URL, skipping product: {item_name} ({url})"
                            )
                            skipped_count += 1
                            continue

                        self.supabase.table("products").insert({
                            "name": item_name,
                            "url": url,
                            "store": parser.slug,
                        }).execute()
                        logger.info(f"Added new product: {item_name} ({url})")

                        # Telegram alert for new product (with store display name).
                        self.send_new_product_alert(item_name, url, parser.display_name)
```

- [ ] **Step 4: Update `send_new_product_alert` signature and message body**

In `Grocery-Sentinel/main.py`, replace the entire `send_new_product_alert` method (currently lines 251-270) with:

```python
    def send_new_product_alert(self, product_name: str, url: str, store_display_name: str) -> None:
        message = (
            f"🆕 <b>New product added</b> ({store_display_name})\n\n"
            f"{product_name}\n\n"
            f"{url}"
        )

        url_api = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"

        payload = {
            "chat_id": self.telegram_chat_id,
            "text": message,
            "disable_web_page_preview": False,
        }

        try:
            httpx.post(url_api, json=payload, timeout=10).raise_for_status()
            logger.info(f"Telegram new product alert sent: {product_name}")
        except Exception as e:
            logger.error(f"Telegram new product alert error: {e}")
```

- [ ] **Step 5: Update `send_telegram_alert` signature and message body**

In `Grocery-Sentinel/main.py`, replace the entire `send_telegram_alert` method (currently lines 222-249) with:

```python
    def send_telegram_alert(
        self,
        product_name: str,
        store_display_name: str,
        old_price: Decimal,
        new_price: Decimal,
        pct_change: float,
        url: str,
    ) -> None:
        """Send Telegram notification about price change."""
        emoji = "📈" if new_price > old_price else "📉"

        message = (
            f"<b>{emoji} {store_display_name}: {product_name}</b>\n\n"
            f"Old Price: RM {old_price:.2f}\n"
            f"New Price: RM {new_price:.2f}\n"
            f"Change: {pct_change:+.2f}%\n\n"
            f"[View Product]({url})"
        )

        url_api = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
        payload = {
            "chat_id": self.telegram_chat_id,
            "text": message,
            "disable_web_page_preview": False,
        }

        try:
            response = httpx.post(url_api, json=payload, timeout=10)
            response.raise_for_status()
            logger.info(f"Sent Telegram alert for {product_name}")
        except Exception as e:
            logger.error(f"Telegram error: {e}")
            if hasattr(e, "response"):
                logger.error(e.response.text)
```

- [ ] **Step 6: Update `check_prices` to load `store` and pass display name to alerts**

In `Grocery-Sentinel/main.py`, locate the products query in `check_prices` (currently line 278):

```python
            result = self.supabase.table("products").select("id, name, url, price").execute()
```

Replace with:

```python
            result = self.supabase.table("products").select("id, name, url, price, store").execute()
```

Inside the `for product in products:` loop, replace the block that unpacks fields (currently lines 295-297):

```python
            product_id = product["id"]
            product_name = product["name"]
            product_url = product["url"]
```

with:

```python
            product_id = product["id"]
            product_name = product["name"]
            product_url = product["url"]
            product_store_slug = product.get("store", "")
            store_parser = resolve_by_slug(product_store_slug)
            store_display_name = store_parser.display_name if store_parser else product_store_slug
```

Then replace the call to `send_telegram_alert` (currently lines 323-325):

```python
                    self.send_telegram_alert(
                        product_name, old_price, new_price, pct_change, product_url
                    )
```

with:

```python
                    self.send_telegram_alert(
                        product_name,
                        store_display_name,
                        old_price,
                        new_price,
                        pct_change,
                        product_url,
                    )
```

- [ ] **Step 7: Manual smoke test — sanity-check the wiring**

Because `main.py` couples to Supabase, Google Sheets, Crawl4AI, and Telegram, we verify it runs end-to-end rather than unit-testing the class. Ensure your local `.env` has the usual secrets, then:

```bash
cd Grocery-Sentinel
python main.py
```

Expected:
- The script runs without stack traces.
- Log lines show `Checking <product name>...` for each existing Jayagrocer product.
- Prices are recorded in Supabase.
- If any price genuinely changed, the resulting Telegram message starts with `📈 JayaGrocer:` or `📉 JayaGrocer:`.
- If a product is genuinely new, the Telegram message reads `🆕 New product added (JayaGrocer)`.

If nothing changed, verify at least that the run completed and that in Supabase the `price_history` table gained one new row per product for this run.

- [ ] **Step 8: Commit**

```bash
cd Grocery-Sentinel
git add main.py
git commit -m "scraper: route main.py through parser registry and add store to alerts"
```

---

### Task 5: API — `store_slug` on Responses + `/stores` Endpoint

**Files:**
- Modify: `Grocery-Sentinel/backend/main.py` (remove hardcoded `STORE_NAME`, load `store` from DB, add `/stores`, add optional `?store=` filter).
- Modify: `Grocery-Sentinel/backend/models.py` (add `store_slug` to `ItemSummary`, add `StoreInfo` model).
- Create: `Grocery-Sentinel/tests/backend/__init__.py`
- Create: `Grocery-Sentinel/tests/backend/test_api.py`

**Interfaces:**
- Consumes: the parser registry from Task 2/3; the `products.store` column from Task 1.
- Produces:
  - `ItemSummary.store_slug: str` (raw slug — used by the frontend chip filter in Task 6).
  - `ItemSummary.store: str` is now the display name (unchanged type, unchanged shape).
  - `ItemHistoryResponse.store: str` now comes from DB, not a hardcoded constant.
  - `GET /stores` returns `list[StoreInfo]` where `StoreInfo = {slug: str, display_name: str}` — one entry per registered store that has at least one product in the DB.
  - `GET /items?store=<slug>` filters by slug at query time (unused by the frontend for now).

- [ ] **Step 1: Extend the Pydantic models**

Modify `Grocery-Sentinel/backend/models.py`. Replace the entire file with:

```python
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ItemSummary(BaseModel):
    id: int
    product_name: str
    store: str
    store_slug: str
    current_price: float
    previous_price: float | None
    price_change: float
    percent_change: float | None
    direction: Literal["up", "down", "same", "new"]
    last_updated: datetime


class PricePoint(BaseModel):
    price: float
    scraped_at: datetime


class ItemHistoryResponse(BaseModel):
    id: int
    product_name: str
    store: str
    history: list[PricePoint]


class StoreInfo(BaseModel):
    slug: str
    display_name: str
```

- [ ] **Step 2: Write the failing API tests**

Create `Grocery-Sentinel/tests/backend/__init__.py` (empty).

Create `Grocery-Sentinel/tests/backend/test_api.py`:

```python
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
```

- [ ] **Step 3: Run the tests and confirm they fail**

```bash
cd Grocery-Sentinel
pytest tests/backend/test_api.py -v
```

Expected: failures — `store_slug` is missing from responses and `/stores` does not exist.

- [ ] **Step 4: Update `backend/main.py`**

Replace the entire contents of `Grocery-Sentinel/backend/main.py` with:

```python
from datetime import datetime
from decimal import Decimal
import os
import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from backend.database import get_supabase_client
from backend.models import ItemHistoryResponse, ItemSummary, PricePoint, StoreInfo
from scraper.parsers import all_parsers, resolve_by_slug

logger = logging.getLogger(__name__)

ZERO = Decimal("0")

app = FastAPI(title="Price Tracker API", version="1.0.0")

allowed_origins = os.getenv(
    "CORS_ORIGINS",
    "http://127.0.0.1:5500,http://localhost:5500,http://127.0.0.1:3000,http://localhost:3000",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://grocery-sentinel.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _to_decimal(value: object) -> Decimal:
    if value is None:
        return ZERO
    return Decimal(str(value))


def _to_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        raise ValueError("Invalid datetime value")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _display_name(slug: str) -> str:
    parser = resolve_by_slug(slug)
    return parser.display_name if parser else slug


def _direction(current_price: Decimal, previous_price: Decimal | None) -> str:
    if previous_price is None:
        return "new"
    if current_price > previous_price:
        return "up"
    if current_price < previous_price:
        return "down"
    return "same"


def _group_latest_and_previous_different(rows: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    grouped: dict[int, list[dict[str, Any]]] = {}
    latest_price: dict[int, Decimal] = {}
    for row in rows:
        product_id = int(row["product_id"])
        price = _to_decimal(row["price"])
        if product_id not in grouped:
            grouped[product_id] = [row]
            latest_price[product_id] = price
        elif len(grouped[product_id]) < 2 and price != latest_price[product_id]:
            grouped[product_id].append(row)
    return grouped


def _build_item_summary(product: dict[str, Any], product_history: list[dict[str, Any]]) -> ItemSummary:
    latest = product_history[0]
    previous = product_history[1] if len(product_history) > 1 else None

    current_price = _to_decimal(latest["price"])
    previous_price = _to_decimal(previous["price"]) if previous else None
    price_change = current_price - previous_price if previous_price is not None else ZERO

    if previous_price is None or previous_price == 0:
        percent_change = None
    else:
        percent_change = (price_change / previous_price) * Decimal("100")

    store_slug = str(product.get("store", ""))

    return ItemSummary(
        id=int(product["id"]),
        product_name=str(product["name"]),
        store=_display_name(store_slug),
        store_slug=store_slug,
        current_price=float(current_price),
        previous_price=float(previous_price) if previous_price is not None else None,
        price_change=float(price_change),
        percent_change=float(percent_change) if percent_change is not None else None,
        direction=_direction(current_price, previous_price),
        last_updated=_to_datetime(latest["scraped_at"]),
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/items", response_model=list[ItemSummary])
def get_items(store: str | None = Query(default=None)) -> list[ItemSummary]:
    try:
        supabase = get_supabase_client()

        products_query = (
            supabase.table("products")
            .select("id, name, url, store")
            .order("name", desc=False)
        )
        if store is not None:
            products_query = products_query.eq("store", store)

        products_result = products_query.execute()
        products = products_result.data or []

        history_result = (
            supabase.table("price_history")
            .select("product_id, price, scraped_at")
            .order("scraped_at", desc=True)
            .execute()
        )
        rows = history_result.data or []
        history_by_product = _group_latest_and_previous_different(rows)

        items: list[ItemSummary] = []
        for product in products:
            product_id = int(product["id"])
            product_history = history_by_product.get(product_id, [])

            if not product_history:
                continue
            items.append(_build_item_summary(product, product_history))

        return items
    except Exception as e:
        logger.exception("GET /items failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/stores", response_model=list[StoreInfo])
def get_stores() -> list[StoreInfo]:
    try:
        supabase = get_supabase_client()

        products_result = (
            supabase.table("products")
            .select("store")
            .execute()
        )
        rows = products_result.data or []
        slugs_in_db = {str(row["store"]) for row in rows if row.get("store")}

        stores = [
            StoreInfo(slug=parser.slug, display_name=parser.display_name)
            for parser in all_parsers()
            if parser.slug in slugs_in_db
        ]
        stores.sort(key=lambda s: s.display_name.lower())
        return stores
    except Exception as e:
        logger.exception("GET /stores failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/history/{item_id}", response_model=ItemHistoryResponse)
def get_history(item_id: int) -> ItemHistoryResponse:
    supabase = get_supabase_client()

    product_result = (
        supabase.table("products")
        .select("id, name, store")
        .eq("id", item_id)
        .limit(1)
        .execute()
    )

    product_rows = product_result.data or []
    if not product_rows:
        raise HTTPException(status_code=404, detail="Item not found")

    product = product_rows[0]

    history_result = (
        supabase.table("price_history")
        .select("price, scraped_at")
        .eq("product_id", item_id)
        .order("scraped_at", desc=False)
        .execute()
    )
    history_rows = history_result.data or []

    return ItemHistoryResponse(
        id=int(product["id"]),
        product_name=str(product["name"]),
        store=_display_name(str(product.get("store", ""))),
        history=[
            PricePoint(
                price=float(_to_decimal(row["price"])),
                scraped_at=_to_datetime(row["scraped_at"]),
            )
            for row in history_rows
        ],
    )
```

- [ ] **Step 5: Run the API tests and confirm they pass**

```bash
cd Grocery-Sentinel
pytest tests/backend/test_api.py -v
```

Expected: 4 passed.

- [ ] **Step 6: Run the full test suite**

```bash
cd Grocery-Sentinel
pytest -v
```

Expected: 15 passed (6 registry + 5 JayaGrocer + 4 API).

- [ ] **Step 7: Manual API smoke test**

Start the backend against your existing Supabase:

```bash
cd Grocery-Sentinel
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

In a browser or with `curl`:

```bash
curl http://127.0.0.1:8000/items | python -m json.tool | head -40
curl http://127.0.0.1:8000/stores | python -m json.tool
curl "http://127.0.0.1:8000/items?store=jayagrocer" | python -m json.tool | head -20
```

Expected:
- `/items` entries each have both `"store": "JayaGrocer"` and `"store_slug": "jayagrocer"`.
- `/stores` returns `[{"slug": "jayagrocer", "display_name": "JayaGrocer"}]`.
- `/items?store=jayagrocer` returns the same rows as `/items` (all existing data is Jayagrocer).

- [ ] **Step 8: Commit**

```bash
cd Grocery-Sentinel
git add backend/main.py backend/models.py \
        tests/backend/__init__.py tests/backend/test_api.py
git commit -m "api: expose store_slug on items and add /stores endpoint"
```

---

### Task 6: Frontend Chip Filter Row

**Files:**
- Modify: `Grocery-Sentinel/frontend/index.html` (add the chip container).
- Modify: `Grocery-Sentinel/frontend/components/app.js` (load `/stores`, render chips, filter by slug).
- Modify: `Grocery-Sentinel/frontend/styles.css` (styles for `.store-filters`, `.chip`, `.chip-active`).

**Interfaces:**
- Consumes: `GET /stores` and `store_slug` on `ItemSummary` from Task 5.
- Produces: user-visible chip filter row above the table. No downstream consumers.

- [ ] **Step 1: Add the chip container to `index.html`**

In `Grocery-Sentinel/frontend/index.html`, insert the following block immediately inside `<main class="container">` and before `<div class="table-wrap">`:

```html
    <div id="storeFilters" class="store-filters">
      <button class="chip chip-active" data-slug="" type="button">All</button>
    </div>
```

- [ ] **Step 2: Add chip styles**

Append to `Grocery-Sentinel/frontend/styles.css`:

```css
.store-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.chip {
  padding: 6px 14px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--card);
  color: var(--text);
  font-size: 0.85rem;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.12s ease, color 0.12s ease, border-color 0.12s ease;
}

.chip:hover {
  background: var(--primary-soft);
  color: var(--primary-dark);
  border-color: var(--primary);
}

.chip-active {
  background: var(--primary);
  color: #ffffff;
  border-color: var(--primary);
}

.chip-active:hover {
  background: var(--primary-dark);
  border-color: var(--primary-dark);
  color: #ffffff;
}
```

- [ ] **Step 3: Extend `app.js` for chip loading and filtering**

In `Grocery-Sentinel/frontend/components/app.js`:

Add near the top-of-file state declarations (right after `let chart;`):

```javascript
let activeStore = "";
```

Add near the DOM-element grabs (after `const chartCanvas = document.getElementById("historyChart");`):

```javascript
const storeFilters = document.getElementById("storeFilters");
```

Replace the entire `filteredItems` function with:

```javascript
function filteredItems() {
  const keyword = searchInput.value.trim().toLowerCase();
  return items
    .filter((item) => !activeStore || item.store_slug === activeStore)
    .filter(
      (item) =>
        item.product_name.toLowerCase().includes(keyword) ||
        item.store.toLowerCase().includes(keyword),
    )
    .sort(compare);
}
```

Add the following functions above `loadItems`:

```javascript
async function loadStores() {
  try {
    const stores = await fetchJson("/stores");
    const chipsHtml = stores
      .map(
        (s) =>
          `<button class="chip" data-slug="${s.slug}" type="button">${s.display_name}</button>`,
      )
      .join("");
    storeFilters.insertAdjacentHTML("beforeend", chipsHtml);
  } catch (error) {
    console.error("Failed to load stores", error);
  }
}

function handleChipClick(event) {
  const chip = event.target.closest(".chip");
  if (!chip) return;
  activeStore = chip.dataset.slug || "";
  storeFilters
    .querySelectorAll(".chip")
    .forEach((c) => c.classList.toggle("chip-active", c === chip));
  renderTable();
}
```

Wire the click handler — add this line alongside the other event bindings (e.g. next to `searchInput.addEventListener(...)`):

```javascript
storeFilters.addEventListener("click", handleChipClick);
```

Update the bottom-of-file bootstrap. Replace:

```javascript
loadItems();
setInterval(loadItems, REFRESH_INTERVAL_MS);
```

with:

```javascript
loadStores();
loadItems();
setInterval(loadItems, REFRESH_INTERVAL_MS);
```

- [ ] **Step 4: Manual browser verification**

With the backend still running from Task 5, serve the frontend:

```bash
cd Grocery-Sentinel
python -m http.server 5500 --directory frontend
```

Open `http://127.0.0.1:5500` and verify:

1. A chip row appears above the table.
2. "All" is highlighted by default; there is one additional chip labelled "JayaGrocer".
3. Clicking "JayaGrocer" keeps the same rows visible (all existing data is Jayagrocer) and moves the highlight.
4. Clicking "All" restores the un-filtered view.
5. Typing in the search box still narrows results within the currently-selected store.
6. Clicking a table row still opens the history chart (regression check).

If your local backend does not have the Vercel-origin CORS setup, note that `backend/main.py` currently pins `allow_origins=["https://grocery-sentinel.vercel.app"]`. For local browser testing you may need to temporarily add `http://127.0.0.1:5500` to that list — but do NOT commit that change; it is orthogonal to this feature.

- [ ] **Step 5: Commit**

```bash
cd Grocery-Sentinel
git add frontend/index.html frontend/styles.css frontend/components/app.js
git commit -m "frontend: add store chip filter row above products table"
```

---

## Post-Plan Follow-Ups (not implemented here)

These are captured for future work and are intentionally out of scope:

- Adding a specific second-store parser (e.g. Village Grocer, Cold Storage, Mercato) — needs a live look at each site's HTML to design the selectors; template is `scraper/parsers/jayagrocer.py`. Adding one is: create `scraper/parsers/<slug>.py`, add `from scraper.parsers import <slug>  # noqa: F401` to `scraper/parsers/__init__.py`, add a fixture + test.
- Cross-store canonical products, multi-currency support, and the broader `main.py` module split each warrant their own spec.
