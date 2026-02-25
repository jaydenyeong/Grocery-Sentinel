# 🛒 Grocery Price Sentinel

A lightweight Python automation that monitors grocery product prices, stores historical data, and sends Telegram alerts when prices change.

Built to track Jayagrocer Malaysia products using web scraping, Supabase Postgres, Google Sheets as a product catalog, and Telegram for notifications — all running daily via GitHub Actions.

## Public Website Dashboard

This project now includes a lightweight public dashboard built on top of your existing dataset (Supabase `products` + `price_history`) without rewriting the scraper.

### Folder Structure

```text
/backend
   main.py
   database.py
   models.py

/frontend
   index.html
   styles.css
   /components
      app.js

/scraper
   main.py
```

### API Endpoints

- `GET /items` → latest items with current/previous price, change and percentage
- `GET /history/{id}` → chronological history for a product

### Run Locally

Install dependencies:

```bash
pip install -r requirements.txt
```

Start backend:

```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

Serve frontend (any static server):

```bash
python -m http.server 5500 --directory frontend
```

Open:

- Frontend: `http://127.0.0.1:5500`
- API: `http://127.0.0.1:8000`

### Environment Variables (Backend)

```bash
SUPABASE_URL=
SUPABASE_SERVICE_KEY=
```

Copy `.env.example` to `.env` for local development. Never commit `.env` or credential JSON files.

### Deployment

Backend (Render / Railway):

- Build: `pip install -r requirements.txt`
- Start: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
- One-click config file for Render is included at `render.yaml`

Frontend (Vercel):

- Deploy the `frontend/` directory as a static site.
- One-click repo-root config file is included at `vercel.json`
- Set `window.API_BASE` before loading `components/app.js` so production deployments call the hosted API while local development keeps the fallback defined in `app.js`:

```html
<script>
  window.API_BASE = "https://your-backend-domain.com";
</script>
```

- Double-check for typos in the URL; Vercel deployments will silently fall back to the local default (`http://127.0.0.1:8000`) if `window.API_BASE` is undefined or misspelled.

#### Quick Deploy with Config Files

- Render: create a new Blueprint service from this repo and Render will read `render.yaml`.
- Vercel: import this repo and Vercel will apply `vercel.json` routes for the static frontend.

#### Deployment Troubleshooting

- **CORS / 503 from Vercel:** make sure the backend is awake and responding (use `curl -I -H "Origin: https://your-vercel-site.vercel.app" https://your-backend-domain.com/items`). A sleeping Render free instance answers with `503 Service Unavailable` before FastAPI can attach CORS headers, which looks like a CORS error in the browser.
- **Keep Render awake (free):** add a free uptime monitor (UptimeRobot, Better Uptime, FreshPing) that hits `/health` every few minutes so the service stays warm and the frontend always gets data.

### Upload to GitHub (Safe)

This repo includes `.gitignore` rules to prevent secret uploads (`.env`, credential JSON, `__pycache__`).

Before pushing, if secrets were ever staged/tracked, untrack them:

```bash
git rm --cached .env
git rm --cached price-sentinel-487106-d7764ac80754.json
git rm -r --cached backend/__pycache__
```

Commit and push:

```bash
git add .
git commit -m "Add public dashboard (FastAPI + frontend) and deployment configs"
git push origin main
```

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

| column | type               |
| ------ | ------------------ |
| id     | bigint / uuid (PK) |
| name   | text               |
| url    | text (unique)      |
| price  | numeric(10,2)      |

---

### price_history

| column     | type             |
| ---------- | ---------------- |
| id         | bigint / uuid    |
| product_id | FK → products.id |
| price      | numeric(10,2)    |
| scraped_at | timestamptz      |

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
