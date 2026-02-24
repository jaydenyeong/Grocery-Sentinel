from datetime import datetime
from decimal import Decimal
import os
import logging
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend.database import get_supabase_client
from backend.models import ItemHistoryResponse, ItemSummary, PricePoint

logger = logging.getLogger(__name__)

STORE_NAME = "JayaGrocer"
ZERO = Decimal("0")

app = FastAPI(title="Price Tracker API", version="1.0.0")

allowed_origins = os.getenv(
    "CORS_ORIGINS",
    "http://127.0.0.1:5500,http://localhost:5500,http://127.0.0.1:3000,http://localhost:3000"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in allowed_origins if o.strip()],
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


def _direction(current_price: Decimal, previous_price: Decimal | None) -> str:
    if previous_price is None:
        return "new"
    if current_price > previous_price:
        return "up"
    if current_price < previous_price:
        return "down"
    return "same"


def _group_latest_two_history(rows: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    grouped: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        product_id = int(row["product_id"])
        if product_id not in grouped:
            grouped[product_id] = []
        if len(grouped[product_id]) < 2:
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

    return ItemSummary(
        id=int(product["id"]),
        product_name=str(product["name"]),
        store=STORE_NAME,
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
def get_items() -> list[ItemSummary]:
    try:
        supabase = get_supabase_client()

        products_result = (
            supabase.table("products")
            .select("id, name, url")
            .order("name", desc=False)
            .execute()
        )
        products = products_result.data or []

        history_result = (
            supabase.table("price_history")
            .select("product_id, price, scraped_at")
            .order("scraped_at", desc=True)
            .execute()
        )
        rows = history_result.data or []
        history_by_product = _group_latest_two_history(rows)

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


@app.get("/history/{item_id}", response_model=ItemHistoryResponse)
def get_history(item_id: int) -> ItemHistoryResponse:
    supabase = get_supabase_client()

    product_result = (
        supabase.table("products")
        .select("id, name")
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
        store=STORE_NAME,
        history=[
            PricePoint(
                price=float(_to_decimal(row["price"])),
                scraped_at=_to_datetime(row["scraped_at"]),
            )
            for row in history_rows
        ],
    )
