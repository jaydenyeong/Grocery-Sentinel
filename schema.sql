-- Grocery Price Sentinel Database Schema
-- Run this in your Supabase SQL editor to create the tables

-- Products table: stores product information from Google Sheets
CREATE TABLE IF NOT EXISTS products (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    price NUMERIC(10, 2),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Price history table: tracks price changes over time
CREATE TABLE IF NOT EXISTS price_history (
    id BIGSERIAL PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    price NUMERIC(10, 2) NOT NULL,
    scraped_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for efficient price history lookups by product and time
CREATE INDEX IF NOT EXISTS idx_price_history_product_scraped 
ON price_history(product_id, scraped_at DESC);

-- Index for efficient product lookups by URL
CREATE INDEX IF NOT EXISTS idx_products_url ON products(url);

-- Trigger to update updated_at timestamp on products
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_products_updated_at 
BEFORE UPDATE ON products 
FOR EACH ROW 
EXECUTE FUNCTION update_updated_at_column();
