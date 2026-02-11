#!/usr/bin/env python3
"""
Grocery Price Sentinel
Monitors prices from Jayagrocer Malaysia and sends Telegram alerts on price changes.
"""

import os
import json
import logging
import sys
import asyncio
import re
from decimal import Decimal
from typing import Optional, Dict, List
from datetime import datetime

import httpx
from supabase import create_client, Client
from crawl4ai import AsyncWebCrawler
import gspread
from google.oauth2.service_account import Credentials
from bs4 import BeautifulSoup

# Configure logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class GroceryPriceSentinel:
    """Main class for price monitoring and alerting."""
    
    def __init__(self):
        """Initialize with environment variables."""
        # Supabase configuration
        self.supabase_url = os.getenv("SUPABASE_URL")
        self.supabase_key = os.getenv("SUPABASE_SERVICE_KEY")
        if not self.supabase_url or not self.supabase_key:
            raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
        
        self.supabase: Client = create_client(self.supabase_url, self.supabase_key)
        
        # Telegram configuration
        self.telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")
        if not self.telegram_token or not self.telegram_chat_id:
            raise ValueError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set")
        
        # Google Sheets configuration
        self.sheets_id = os.getenv("GOOGLE_SHEETS_ID")
        self.sheets_tab = os.getenv("GOOGLE_SHEETS_TAB") or "Sheet1"
        sheets_creds_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
        if not self.sheets_id or not sheets_creds_json:
            raise ValueError("GOOGLE_SHEETS_ID and GOOGLE_SERVICE_ACCOUNT_JSON must be set")
        
        # Initialize Google Sheets client
        try:
            creds_dict = json.loads(sheets_creds_json)
            creds = Credentials.from_service_account_info(
                creds_dict,
                scopes=['https://www.googleapis.com/auth/spreadsheets.readonly']
            )
            self.gc = gspread.authorize(creds)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid GOOGLE_SERVICE_ACCOUNT_JSON: {e}")
        
        # Price change threshold (minimum percentage change to trigger alert)
        min_pct_str = os.getenv("MIN_PCT_CHANGE")
        self.min_pct_change = float(min_pct_str) if min_pct_str else 0.01
    
    def sync_products_from_sheets(self) -> None:
        """Sync products from Google Sheets into Supabase."""
        logger.info(f"Syncing products from Google Sheets (ID: {self.sheets_id}, Tab: {self.sheets_tab})")
        
        try:
            sheet = self.gc.open_by_key(self.sheets_id).worksheet(self.sheets_tab)
            rows = sheet.get_all_records()
            
            synced_count = 0
            skipped_count = 0
            
            for row in rows:
                item_name = row.get("item", "").strip()
                url = row.get("URL", "").strip()
                
                if not url:
                    logger.warning(f"Skipping row with missing URL: {row}")
                    skipped_count += 1
                    continue
                
                if not item_name:
                    logger.warning(f"Skipping row with missing item name for URL: {url}")
                    skipped_count += 1
                    continue
                
                # Upsert product by URL
                try:
                    # Check if product exists
                    existing = self.supabase.table("products").select("id, name").eq("url", url).execute()
                    
                    if existing.data:
                        # Update if name changed
                        product_id = existing.data[0]["id"]
                        if existing.data[0]["name"] != item_name:
                            self.supabase.table("products").update({"name": item_name}).eq("id", product_id).execute()
                            logger.info(f"Updated product: {item_name} ({url})")
                        else:
                            logger.debug(f"Product already exists: {item_name}")
                    else:
                        # Insert new product
                        self.supabase.table("products").insert({
                            "name": item_name,
                            "url": url
                        }).execute()
                        logger.info(f"Added new product: {item_name} ({url})")
                    
                    synced_count += 1
                except Exception as e:
                    logger.error(f"Error upserting product {item_name} ({url}): {e}")
                    skipped_count += 1
            
            logger.info(f"Sync complete: {synced_count} products synced, {skipped_count} skipped")
        
        except Exception as e:
            logger.error(f"Error syncing from Google Sheets: {e}")
            raise
    
    def fetch_price(self, url: str) -> Optional[Decimal]:
        """Fetch current price from Jayagrocer product page using Crawl4AI."""
        logger.debug(f"Fetching price from: {url}")
        
        try:
            async def scrape_price():
                async with AsyncWebCrawler(verbose=False) as crawler:
                    result = await crawler.arun(url=url)
                    
                    if not result.success or not result.html:
                        logger.warning(f"Failed to fetch page: {url}")
                        return None
                    
                    # Try multiple common price selectors for e-commerce sites
                    # Adjust these selectors based on Jayagrocer's actual HTML structure
                    price_selectors = [
                        # Common e-commerce price selectors
                        'span[class*="price"]',
                        'div[class*="price"]',
                        '.price',
                        '[data-price]',
                        'span.price',
                        'div.price',
                        # Malaysian currency format
                        'span:contains("RM")',
                        'div:contains("RM")',
                    ]
                    
                    soup = BeautifulSoup(result.html, 'html.parser')
                    
                    # Try to find price text
                    price_text = None
                    for selector in price_selectors:
                        elements = soup.select(selector)
                        if elements:
                            price_text = elements[0].get_text(strip=True)
                            break
                    
                    # If no selector worked, search for RM pattern in text
                    if not price_text:
                        # Look for patterns like "RM 10.50" or "RM10.50" or "10.50"
                        price_pattern = r'RM\s*(\d+\.?\d*)|\b(\d+\.?\d*)\s*RM'
                        matches = re.findall(price_pattern, result.html, re.IGNORECASE)
                        if matches:
                            # Get the first match, prefer the first group
                            price_text = matches[0][0] if matches[0][0] else matches[0][1]
                    
                    if not price_text:
                        logger.warning(f"Could not find price on page: {url}")
                        return None
                    
                    # Extract numeric value
                    # Remove currency symbols and extract numbers
                    numbers = re.findall(r'\d+\.?\d*', price_text.replace(',', ''))
                    if numbers:
                        try:
                            price_value = Decimal(numbers[0])
                            logger.info(f"Found price: RM {price_value} for {url}")
                            return price_value
                        except (ValueError, Exception) as e:
                            logger.warning(f"Could not parse price '{price_text}': {e}")
                            return None
                    
                    logger.warning(f"Could not extract price from text: {price_text}")
                    return None
            
            # Run async function
            import asyncio
            return asyncio.run(scrape_price())
        
        except Exception as e:
            logger.error(f"Error fetching price from {url}: {e}")
            return None
    
    def get_latest_price(self, product_id: int) -> Optional[Decimal]:
        """Get the latest price from price_history for a product."""
        try:
            result = self.supabase.table("price_history").select("price").eq(
                "product_id", product_id
            ).order("scraped_at", desc=True).limit(1).execute()
            
            if result.data:
                return Decimal(str(result.data[0]["price"]))
            return None
        except Exception as e:
            logger.error(f"Error getting latest price for product {product_id}: {e}")
            return None
    
    def save_price(self, product_id: int, price: Decimal) -> None:
        """Save price to price_history and update products table."""
        try:
            # Insert into price_history
            self.supabase.table("price_history").insert({
                "product_id": product_id,
                "price": float(price)
            }).execute()
            
            # Update products.price
            self.supabase.table("products").update({
                "price": float(price)
            }).eq("id", product_id).execute()
            
            logger.debug(f"Saved price {price} for product {product_id}")
        except Exception as e:
            logger.error(f"Error saving price for product {product_id}: {e}")
            raise
    
    def send_telegram_alert(self, product_name: str, old_price: Decimal, new_price: Decimal, 
                           pct_change: float, url: str) -> None:
        """Send Telegram notification about price change."""
        direction = "📈 Increased" if new_price > old_price else "📉 Decreased"
        emoji = "📈" if new_price > old_price else "📉"
        
        message = (
            f"{emoji} *Price Alert: {product_name}*\n\n"
            f"Old Price: RM {old_price:.2f}\n"
            f"New Price: RM {new_price:.2f}\n"
            f"Change: {pct_change:+.2f}%\n\n"
            f"[View Product]({url})"
        )
        
        url_api = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
        payload = {
            "chat_id": self.telegram_chat_id,
            "text": message,
            "parse_mode": "Markdown",
            "disable_web_page_preview": False
        }
        
        try:
            response = httpx.post(url_api, json=payload, timeout=10)
            response.raise_for_status()
            logger.info(f"Sent Telegram alert for {product_name}")
        except Exception as e:
            logger.error(f"Error sending Telegram alert: {e}")
    
    def check_prices(self) -> None:
        """Main function to check prices for all products."""
        logger.info("Starting price check...")
        
        # Get all products
        try:
            result = self.supabase.table("products").select("id, name, url, price").execute()
            products = result.data
        except Exception as e:
            logger.error(f"Error fetching products: {e}")
            raise
        
        if not products:
            logger.warning("No products found in database")
            return
        
        logger.info(f"Checking prices for {len(products)} products")
        
        checked_count = 0
        changed_count = 0
        error_count = 0
        
        for product in products:
            product_id = product["id"]
            product_name = product["name"]
            product_url = product["url"]
            
            logger.info(f"Checking {product_name}...")
            
            # Fetch current price
            new_price = self.fetch_price(product_url)
            
            if new_price is None:
                logger.warning(f"Could not fetch price for {product_name}")
                error_count += 1
                continue
            
            # Get old price
            old_price = self.get_latest_price(product_id)
            
            # Save new price
            self.save_price(product_id, new_price)
            checked_count += 1
            
            # Compare and alert if changed
            if old_price is not None and old_price > 0:
                price_diff = abs(new_price - old_price)
                pct_change = ((new_price - old_price) / old_price) * 100
                
                # Check if change is significant
                if price_diff > Decimal("0.01") and abs(pct_change) >= self.min_pct_change:
                    self.send_telegram_alert(
                        product_name, old_price, new_price, pct_change, product_url
                    )
                    changed_count += 1
                    logger.info(
                        f"Price changed for {product_name}: "
                        f"RM {old_price:.2f} -> RM {new_price:.2f} ({pct_change:+.2f}%)"
                    )
                else:
                    logger.debug(f"No significant price change for {product_name}")
            else:
                logger.info(f"Initial price recorded for {product_name}: RM {new_price:.2f}")
        
        logger.info(
            f"Price check complete: {checked_count} checked, "
            f"{changed_count} changed, {error_count} errors"
        )
    
    def run(self) -> None:
        """Run the complete monitoring cycle."""
        try:
            # Step 1: Sync products from Google Sheets
            self.sync_products_from_sheets()
            
            # Step 2: Check prices
            self.check_prices()
            
            logger.info("Monitoring cycle completed successfully")
        
        except Exception as e:
            logger.error(f"Fatal error in monitoring cycle: {e}")
            raise


def main():
    """Main entry point."""
    try:
        sentinel = GroceryPriceSentinel()
        sentinel.run()
        sys.exit(0)
    except Exception as e:
        logger.error(f"Application error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
