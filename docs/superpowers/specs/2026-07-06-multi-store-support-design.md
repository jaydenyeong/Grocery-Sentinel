# Multi-Store Support — Design Spec

**Date:** 2026-07-06
**Status:** Approved (design), awaiting implementation plan

## Goal

Track products from multiple Malaysian grocery stores in the same Grocery-Sentinel pipeline and dashboard, without breaking the existing Jayagrocer data or workflow.

## Scope

**In scope for v1:**

- Add a `store` field to products, backfilling existing rows.
- Introduce a per-store scraper registry keyed by URL domain.
- Route each product URL to the correct parser at scrape time and at sync time.
- Show store in the frontend as a chip filter above the existing table.
- Include store name in Telegram alerts.
- Target 5–10 stores over time, all Malaysian (RM), added by dropping in one parser file each.

**Out of scope for v1:**

- Cross-store canonical products (linking "the same real item" across stores).
- Multi-currency handling.
- Broader `main.py` module split — kept as a separate future spec.
- Google Sheet input format changes.

## Approach

Each store's listing is an independent product row (no cross-store canonicalization). The store is identified by URL domain via a small scraper registry — one Python module per store, registered by domain. The Google Sheet stays as `item, url`. The `products` table gets a `store` column, backfilled to `jayagrocer`. Frontend adds a chip-filter row above the existing table. Telegram alerts include the store name. `main.py` gets a minimum refactor: only the `fetch_price` bit is pulled into the registry — sync, alerts, and orchestration stay in place.

## Data Model

**Migration (Supabase SQL):**

```sql
ALTER TABLE products
  ADD COLUMN store TEXT;

UPDATE products SET store = 'jayagrocer' WHERE store IS NULL;

ALTER TABLE products
  ALTER COLUMN store SET NOT NULL;

CREATE INDEX idx_products_store ON products(store);
```

- `store` is a lowercase slug (`jayagrocer`, `village_grocer`, `cold_storage`, `mercato`, …). Slug is what's stored; a human display name (`"Village Grocer"`) lives in the scraper registry.
- The existing `url UNIQUE` constraint stays — URLs are inherently unique across stores, so no change is needed.
- `price_history` needs no changes (it references `products.id`, so store joins through the product).
- Index on `store` supports per-store filtering at the API layer.

**Backfill:** the single `UPDATE` above covers all existing rows.

**No changes to the Google Sheet input format** — it remains `item, url`.

## Scraper Registry

**Structure — adds to the existing `scraper/` folder, does not touch `main.py`'s orchestration:**

```
scraper/
  main.py                    # unchanged entry point
  parsers/
    __init__.py              # imports all parser modules to trigger registration
    base.py                  # StoreParser interface + registry
    jayagrocer.py            # existing selector logic moved here
    village_grocer.py        # new stores added as files here
    cold_storage.py
```

**Interface (`scraper/parsers/base.py`):**

```python
class StoreParser:
    slug: str          # e.g. "jayagrocer" — matches products.store
    display_name: str  # e.g. "JayaGrocer" — used in UI/alerts
    domains: list[str] # e.g. ["jayagrocer.com", "www.jayagrocer.com"]

    def parse_price(self, html: str) -> Decimal | None: ...

_REGISTRY: dict[str, StoreParser] = {}      # domain -> parser
_BY_SLUG: dict[str, StoreParser] = {}       # slug -> parser

def register(parser: StoreParser) -> None: ...
def resolve_by_url(url: str) -> StoreParser | None: ...
def resolve_by_slug(slug: str) -> StoreParser | None: ...
```

Each parser file calls `register(JayaGrocerParser())` at import time. `scraper/parsers/__init__.py` imports all parser modules so registration happens on first use.

If two parsers accidentally register the same domain, `register()` raises at import time (fail-loud safeguard).

**In `main.py` — the only edit is `fetch_price`:**

```python
def fetch_price(self, url: str) -> Optional[Decimal]:
    parser = resolve_by_url(url)
    if parser is None:
        logger.error(f"No parser registered for URL: {url}")
        return None
    # ... existing Crawl4AI fetch ...
    return parser.parse_price(result.html)
```

**Store attribution during sync (`sync_products_from_sheets`):**

When inserting a new product, `resolve_by_url(url)` gives the parser. Set `products.store = parser.slug`. If no parser matches, log an error and skip the row (fail loud — matches the "no silent guessing" decision).

**Adding a new store = one file + one line:**

1. Create `scraper/parsers/mercato.py` with a `MercatoParser` class that calls `register(MercatoParser())`.
2. Add `from . import mercato` to `scraper/parsers/__init__.py`.

No config changes, no schema changes, no sheet changes.

## API Changes (`backend/main.py`)

1. **Remove** the hardcoded `STORE_NAME = "JayaGrocer"` constant. Store now comes from `products.store` (slug) and is converted to display name via the parser registry.

2. **New helper — slug → display name:**

   ```python
   from scraper.parsers import resolve_by_slug

   def _display_name(slug: str) -> str:
       parser = resolve_by_slug(slug)
       return parser.display_name if parser else slug
   ```

   Falls back to the raw slug if a parser was removed but data remains — defensive, avoids crashes.

3. **Include `store` in the products query:**

   ```python
   supabase.table("products").select("id, name, url, store").order("name").execute()
   ```

4. **Pass store into `_build_item_summary`:** set `ItemSummary.store = _display_name(product["store"])` and also expose `ItemSummary.store_slug = product["store"]`.

5. **Optional query param on `GET /items`:**

   ```python
   @app.get("/items")
   def get_items(store: str | None = None) -> list[ItemSummary]:
       # If store is provided, filter products by that slug at the DB level.
   ```

   The frontend does not use this in v1 (client-side chip filter is instant on a small dataset), but the param is defined so we don't need an API change when we do.

6. **New endpoint `GET /stores`:**

   ```python
   @app.get("/stores", response_model=list[StoreInfo])
   def get_stores() -> list[StoreInfo]:
       # Returns [{slug, display_name}] for every registered store
       # that has at least one product in the DB.
   ```

   Frontend uses this to build the chip filter — avoids hardcoding the store list in JS.

7. **New Pydantic model `StoreInfo`:**

   ```python
   class StoreInfo(BaseModel):
       slug: str
       display_name: str
   ```

8. **`ItemHistoryResponse.store`** — pulled from `products.store`, converted to display name (same treatment as `ItemSummary`).

**Cross-import note:** `backend/main.py` will import from `scraper/parsers`. Both live under the same repo root, so this is a normal package import — no path gymnastics. The scraper parsers depend only on `bs4` and stdlib, so importing them in the API doesn't drag heavy runtime dependencies.

## Frontend Changes

**`frontend/index.html` — add a chip row above the table:**

```html
<div id="storeFilters" class="store-filters">
  <button class="chip chip-active" data-slug="">All</button>
  <!-- chips injected dynamically from GET /stores -->
</div>
```

**`frontend/components/app.js` — additions:**

1. **New state:** `let activeStore = "";` (empty means show all).

2. **Fetch and render chips on load:**

   ```javascript
   async function loadStores() {
     const stores = await fetchJson("/stores");
     const container = document.getElementById("storeFilters");
     const chips = stores.map(s =>
       `<button class="chip" data-slug="${s.slug}">${s.display_name}</button>`
     );
     container.insertAdjacentHTML("beforeend", chips.join(""));
   }
   ```

3. **Extend `filteredItems()` to also filter by `activeStore`:**

   ```javascript
   function filteredItems() {
     const keyword = searchInput.value.trim().toLowerCase();
     return items
       .filter(i => !activeStore || i.store_slug === activeStore)
       .filter(i => i.product_name.toLowerCase().includes(keyword)
                 || i.store.toLowerCase().includes(keyword))
       .sort(compare);
   }
   ```

4. **Click handler on `#storeFilters`** using event delegation: toggle `chip-active`, update `activeStore`, re-render.

5. **Load order at bottom of file:** call `loadStores()` alongside `loadItems()` on page load.

**`frontend/styles.css` — new classes:**

- `.store-filters` — flex row, wraps on narrow screens, ~8px gap.
- `.chip` — pill button, subtle border, hover state.
- `.chip-active` — filled background using the existing `#4a7c59` accent already used in the chart.

**Client-side filtering only in v1.** The dataset is small; the `?store=` API param exists for future scale but is unused today.

**No other frontend changes** — the existing "Store" column already renders `item.store`, and the search box already searches store names.

## Telegram Alerts

Both alert messages include the store's display name.

- **Price change alert** fires from `check_prices`. Fetch `store` alongside `id, name, url` when loading products, look up the display name once with `resolve_by_slug`, and pass it into `send_telegram_alert`.
- **New product alert** fires from `sync_products_from_sheets`, where `resolve_by_url(url)` is already being called to attribute the store. Reuse that parser to get the display name and pass it into `send_new_product_alert`.

**Price change alert:**

```
📈 JayaGrocer: Farm Fresh Full Cream Milk 1L

Old Price: RM 8.50
New Price: RM 9.20
Change: +8.24%

[View Product]
```

**New product alert:**

```
🆕 New product added (Village Grocer)

Farm Fresh Full Cream Milk 1L

<url>
```

## Testing

The project currently has no test suite. Plan is pragmatic:

1. **Parser unit tests** — for each parser (including JayaGrocer, to freeze existing behavior during the extract), one test with a saved HTML fixture asserting the extracted price. Fixtures live under `tests/fixtures/<store>.html`.
2. **Registry tests** — `resolve_by_url` matches expected domains, unknown URL returns `None`, `resolve_by_slug` round-trips, duplicate domain registration raises.
3. **API smoke test** — hit `/stores` and `/items` with a mocked Supabase client; verify multi-store rows come through with correct display names and slugs.
4. **Manual end-to-end** — add one Village Grocer URL to the sheet, run `python main.py` locally, confirm: (a) new-product Telegram alert fires with store name, (b) row appears in the dashboard under a new chip, (c) `/history/{id}` returns correctly.

## Rollout

Each step is independently deployable and reversible.

1. Ship the migration (`store` column + backfill). App keeps working unchanged.
2. Ship the parser registry with JayaGrocer as the only parser and wire `main.py` to use it. Behavior identical to today — this is the safety-net step.
3. Ship API changes (`/stores`, store slug + name on `ItemSummary`, store on `ItemHistoryResponse`). Frontend still works because the "Store" column just reads what the API returns.
4. Ship the frontend chip filter.
5. Add the second store's parser + a sheet row for it. Verify end to end.

## Risks & Notes

- **Crawl4AI variability across stores.** Some stores may be JS-heavier or gate content. If a store needs different crawler options, the `StoreParser` interface can be extended later to expose a `crawler_config`. Not adding preemptively.
- **Duplicate domain registration** raises at import time to prevent silent misrouting.
- **Deploy coupling.** `backend/` importing from `scraper/parsers/` means the API's cold start requires those files on the deploy target (Render). They live in the same repo, so this is expected and worth noting.
- **Sheet without a store column** relies entirely on URL domain matching. An unknown domain is an error the user sees in logs, not silent success.
