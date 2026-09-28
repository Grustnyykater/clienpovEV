-- Load Olist CSV files into PostgreSQL
-- Adjust the path below to your local project path before running.
-- Example: \set data_path '/Users/hekhatul/Desktop/EV/data'

\c olist_ecommerce;

-- Disable FK checks temporarily is not needed if we load in dependency order.
-- Load order: dimensions first, then facts.

COPY customers
FROM '/Users/hekhatul/Desktop/EV/data/olist_customers_dataset.csv'
DELIMITER ',' CSV HEADER;

COPY geolocation
FROM '/Users/hekhatul/Desktop/EV/data/olist_geolocation_dataset.csv'
DELIMITER ',' CSV HEADER;

COPY sellers
FROM '/Users/hekhatul/Desktop/EV/data/olist_sellers_dataset.csv'
DELIMITER ',' CSV HEADER;

COPY products
FROM '/Users/hekhatul/Desktop/EV/data/olist_products_dataset.csv'
DELIMITER ',' CSV HEADER;

COPY category_translation
FROM '/Users/hekhatul/Desktop/EV/data/product_category_name_translation.csv'
DELIMITER ',' CSV HEADER;

COPY orders
FROM '/Users/hekhatul/Desktop/EV/data/olist_orders_dataset.csv'
DELIMITER ',' CSV HEADER;

COPY order_items
FROM '/Users/hekhatul/Desktop/EV/data/olist_order_items_dataset.csv'
DELIMITER ',' CSV HEADER;

COPY order_payments
FROM '/Users/hekhatul/Desktop/EV/data/olist_order_payments_dataset.csv'
DELIMITER ',' CSV HEADER;

COPY order_reviews
FROM '/Users/hekhatul/Desktop/EV/data/olist_order_reviews_dataset.csv'
DELIMITER ',' CSV HEADER;

-- Quick sanity checks
SELECT 'customers' AS table_name, COUNT(*) AS n FROM customers
UNION ALL SELECT 'orders', COUNT(*) FROM orders
UNION ALL SELECT 'order_items', COUNT(*) FROM order_items
UNION ALL SELECT 'order_payments', COUNT(*) FROM order_payments
UNION ALL SELECT 'products', COUNT(*) FROM products
UNION ALL SELECT 'sellers', COUNT(*) FROM sellers
UNION ALL SELECT 'order_reviews', COUNT(*) FROM order_reviews
UNION ALL SELECT 'category_translation', COUNT(*) FROM category_translation;
