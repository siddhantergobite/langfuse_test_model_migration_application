CREATE TABLE IF NOT EXISTS demo_orders (
  id TEXT PRIMARY KEY,
  customer_id TEXT NOT NULL,
  date TEXT NOT NULL,
  status TEXT NOT NULL,
  product TEXT NOT NULL,
  total REAL NOT NULL CHECK (total >= 0)
);

CREATE INDEX IF NOT EXISTS idx_demo_orders_customer_date
  ON demo_orders (customer_id, date DESC, id);
