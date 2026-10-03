-- Load Olist CSV files into PostgreSQL.
-- Uses client-side \copy, so it needs no superuser rights and no absolute paths.
-- Run from the repo root (paths are relative to the current directory):
--   psql -U postgres -d olist_ecommerce -f sql/02_load_data.sql

-- Dimensions first, then facts (FK order).
TRUNCATE order_reviews, order_payments, order_items, orders,
         products, sellers, customers, geolocation, category_translation;

\copy customers            FROM 'data/olist_customers_dataset.csv'            WITH (FORMAT csv, HEADER true)
\copy geolocation          FROM 'data/olist_geolocation_dataset.csv'          WITH (FORMAT csv, HEADER true)
\copy sellers              FROM 'data/olist_sellers_dataset.csv'              WITH (FORMAT csv, HEADER true)
\copy products             FROM 'data/olist_products_dataset.csv'             WITH (FORMAT csv, HEADER true)
\copy category_translation FROM 'data/product_category_name_translation.csv' WITH (FORMAT csv, HEADER true)
\copy orders               FROM 'data/olist_orders_dataset.csv'               WITH (FORMAT csv, HEADER true)
\copy order_items          FROM 'data/olist_order_items_dataset.csv'          WITH (FORMAT csv, HEADER true)
\copy order_payments       FROM 'data/olist_order_payments_dataset.csv'       WITH (FORMAT csv, HEADER true)
\copy order_reviews        FROM 'data/olist_order_reviews_dataset.csv'        WITH (FORMAT csv, HEADER true)

ANALYZE;

-- Sanity checks
SELECT 'customers' AS table_name, COUNT(*) AS n FROM customers
UNION ALL SELECT 'orders', COUNT(*) FROM orders
UNION ALL SELECT 'order_items', COUNT(*) FROM order_items
UNION ALL SELECT 'order_payments', COUNT(*) FROM order_payments
UNION ALL SELECT 'products', COUNT(*) FROM products
UNION ALL SELECT 'sellers', COUNT(*) FROM sellers
UNION ALL SELECT 'order_reviews', COUNT(*) FROM order_reviews
UNION ALL SELECT 'category_translation', COUNT(*) FROM category_translation;
