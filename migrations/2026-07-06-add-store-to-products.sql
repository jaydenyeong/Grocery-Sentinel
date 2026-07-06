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