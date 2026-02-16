# 🛒 Grocery Price Sentinel

A lightweight Python automation that monitors grocery product prices, stores historical data, and sends Telegram alerts when prices change.

Built to track Jayagrocer Malaysia products using web scraping, Supabase Postgres, Google Sheets as a product catalog, and Telegram for notifications — all running daily via GitHub Actions.

---

## ✨ Features

- 📄 Product catalog managed in Google Sheets  
- 🔄 Automatic sync from Sheets → Supabase  
- 🌐 Web scraping using Crawl4AI + BeautifulSoup  
- 🗄️ Price history stored in Postgres  
- 📉 Telegram alerts on price changes  
- 🆕 Telegram alerts when new products are added  
- ⏰ Daily scheduled runs via GitHub Actions  
- ⚙️ Fully environment-variable driven (production ready)

---

## 🧱 Architecture

Google Sheets (item + URL)
→ 
main.py
→
Supabase (products + price_history)
→
Crawl4AI Scraper
→
Price Comparison Logic
→
Telegram Bot Alerts



---

## 📦 Tech Stack

- Python 3.11  
- Crawl4AI  
- BeautifulSoup  
- Supabase (Postgres)  
- Google Sheets API (gspread + google-auth)  
- Telegram Bot API  
- GitHub Actions  

---

## 🗃 Database Schema

### products

| column | type |
|--------|------|
| id | bigint / uuid (PK) |
| name | text |
| url | text (unique) |
| price | numeric(10,2) |

---

### price_history

| column | type |
|--------|------|
| id | bigint / uuid |
| product_id | FK → products.id |
| price | numeric(10,2) |
| scraped_at | timestamptz |

Index:


---

## 🚀 Execution Flow

1. Sync products from Google Sheets into Supabase (upsert by URL)
2. Load all products from Supabase
3. Scrape each product page
4. Compare new price vs last recorded price
5. Save new price to `price_history`
6. Update `products.price`
7. Send Telegram alerts if:
   - Price changed
   - New product added

---


## 🔐 Environment Variables

Set these via GitHub Secrets:

```bash
SUPABASE_URL=
SUPABASE_SERVICE_KEY=

TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

GOOGLE_SHEETS_ID=

MIN_PCT_CHANGE=0.01
LOG_LEVEL=INFO
```


