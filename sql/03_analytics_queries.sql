-- Olist E-Commerce Analytics — analytical queries (PostgreSQL)
-- Run after 01_schema.sql and 02_load_data.sql:
--   psql -U postgres -d olist_ecommerce -f sql/03_analytics_queries.sql
--
-- Conventions (identical to scripts/run_analysis.py, so the numbers match):
--   * scope          — orders with status 'delivered';
--   * GMV / revenue  — SUM(order_items.price), freight excluded;
--   * customer       — customers.customer_unique_id (customer_id is issued per order!);
--   * late delivery  — delivered DATE > estimated DATE (the estimate has no time part,
--                      so a same-day delivery is on time).

-- =============================================================================
-- 1. Core KPIs: GMV, orders, customers, AOV
-- =============================================================================

-- 1.1 Overall KPIs
WITH delivered AS (
    SELECT o.order_id, c.customer_unique_id, oi.price, oi.freight_value
    FROM orders o
    JOIN customers c    ON c.customer_id = o.customer_id
    JOIN order_items oi ON oi.order_id = o.order_id
    WHERE o.order_status = 'delivered'
)
SELECT
    ROUND(SUM(price), 2)                                  AS gmv,
    ROUND(SUM(price + freight_value), 2)                  AS gmv_incl_freight,
    COUNT(DISTINCT order_id)                              AS orders,
    COUNT(DISTINCT customer_unique_id)                    AS customers,
    ROUND(SUM(price) / COUNT(DISTINCT order_id), 2)       AS aov
FROM delivered;

-- 1.2 Payment-based GMV (alternative definition: what customers actually paid, incl. freight)
SELECT
    ROUND(SUM(op.payment_value), 2) AS payment_gmv,
    COUNT(DISTINCT o.order_id)      AS paid_orders
FROM orders o
JOIN order_payments op ON op.order_id = o.order_id
WHERE o.order_status = 'delivered';


-- =============================================================================
-- 2. Sales dynamics by month + month-over-month growth (LAG)
-- =============================================================================

WITH monthly AS (
    SELECT
        DATE_TRUNC('month', o.order_purchase_timestamp)::date AS month,
        COUNT(DISTINCT o.order_id)                            AS orders,
        SUM(oi.price)                                         AS revenue
    FROM orders o
    JOIN order_items oi ON oi.order_id = o.order_id
    WHERE o.order_status = 'delivered'
    GROUP BY 1
)
SELECT
    month,
    orders,
    ROUND(revenue, 2)          AS revenue,
    ROUND(revenue / orders, 2) AS aov,
    ROUND(100.0 * (revenue / LAG(revenue) OVER (ORDER BY month) - 1), 1) AS revenue_mom_pct
FROM monthly
ORDER BY month;


-- =============================================================================
-- 3. Sales by category (window functions: share of total + ranking)
-- =============================================================================

SELECT
    COALESCE(ct.product_category_name_english, p.product_category_name, 'unknown') AS category,
    ROUND(SUM(oi.price), 2)      AS revenue,
    COUNT(DISTINCT oi.order_id)  AS orders,
    ROUND(SUM(oi.price) / COUNT(DISTINCT oi.order_id), 2) AS aov,
    ROUND(100.0 * SUM(oi.price) / SUM(SUM(oi.price)) OVER (), 2) AS revenue_share_pct,
    ROUND(100.0 * SUM(SUM(oi.price)) OVER (ORDER BY SUM(oi.price) DESC)
                / SUM(SUM(oi.price)) OVER (), 2)                AS cumulative_share_pct,
    RANK()       OVER (ORDER BY SUM(oi.price) DESC)              AS revenue_rank,
    DENSE_RANK() OVER (ORDER BY COUNT(DISTINCT oi.order_id) DESC) AS orders_rank
FROM order_items oi
JOIN orders o   ON o.order_id = oi.order_id
JOIN products p ON p.product_id = oi.product_id
LEFT JOIN category_translation ct ON ct.product_category_name = p.product_category_name
WHERE o.order_status = 'delivered'
GROUP BY 1
ORDER BY revenue DESC
LIMIT 20;


-- =============================================================================
-- 4. Sales by region (customer state)
-- =============================================================================

SELECT
    c.customer_state,
    COUNT(DISTINCT o.order_id)           AS orders,
    COUNT(DISTINCT c.customer_unique_id) AS customers,
    ROUND(SUM(oi.price), 2)              AS revenue,
    ROUND(SUM(oi.price) / COUNT(DISTINCT o.order_id), 2) AS aov,
    ROUND(100.0 * SUM(oi.price) / SUM(SUM(oi.price)) OVER (), 2) AS revenue_share_pct
FROM orders o
JOIN order_items oi ON oi.order_id = o.order_id
JOIN customers c    ON c.customer_id = o.customer_id
WHERE o.order_status = 'delivered'
GROUP BY c.customer_state
ORDER BY revenue DESC;


-- =============================================================================
-- 5. Delivery time & late deliveries
-- =============================================================================

-- 5.1 Overall
SELECT
    COUNT(*) AS delivered_orders,
    ROUND(AVG(EXTRACT(EPOCH FROM order_delivered_customer_date - order_purchase_timestamp) / 86400), 2)
        AS avg_delivery_days,
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (
        ORDER BY EXTRACT(EPOCH FROM order_delivered_customer_date - order_purchase_timestamp) / 86400
    )::numeric, 2) AS median_delivery_days,
    ROUND(100.0 * AVG((order_delivered_customer_date::date > order_estimated_delivery_date::date)::int), 2)
        AS late_delivery_rate_pct
FROM orders
WHERE order_status = 'delivered'
  AND order_delivered_customer_date IS NOT NULL;

-- 5.2 Late delivery rate by state (states with >= 100 orders)
SELECT
    c.customer_state,
    COUNT(*) AS orders,
    ROUND(AVG(EXTRACT(EPOCH FROM o.order_delivered_customer_date - o.order_purchase_timestamp) / 86400), 2)
        AS avg_delivery_days,
    ROUND(100.0 * AVG((o.order_delivered_customer_date::date > o.order_estimated_delivery_date::date)::int), 2)
        AS late_rate_pct
FROM orders o
JOIN customers c ON c.customer_id = o.customer_id
WHERE o.order_status = 'delivered'
  AND o.order_delivered_customer_date IS NOT NULL
GROUP BY c.customer_state
HAVING COUNT(*) >= 100
ORDER BY late_rate_pct DESC
LIMIT 15;


-- =============================================================================
-- 6. Review score vs delivery delay
--    Reviews are averaged per order first: some orders have several reviews,
--    and joining them directly would double-count those orders.
-- =============================================================================

WITH order_review AS (
    SELECT order_id, AVG(review_score) AS review_score
    FROM order_reviews
    GROUP BY order_id
),
delays AS (
    SELECT
        o.order_id,
        o.order_delivered_customer_date::date - o.order_estimated_delivery_date::date AS delay_days
    FROM orders o
    WHERE o.order_status = 'delivered'
      AND o.order_delivered_customer_date IS NOT NULL
)
SELECT
    CASE
        WHEN d.delay_days <= 0 THEN '0. on time'
        WHEN d.delay_days <= 3 THEN '1. 1-3 days late'
        WHEN d.delay_days <= 7 THEN '2. 4-7 days late'
        ELSE                        '3. 8+ days late'
    END                              AS delay_bucket,
    COUNT(*)                         AS orders,
    ROUND(AVG(r.review_score), 2)    AS avg_review_score,
    ROUND(100.0 * AVG((r.review_score <= 2)::int), 1) AS negative_review_pct
FROM delays d
JOIN order_review r ON r.order_id = d.order_id
GROUP BY 1
ORDER BY 1;


-- =============================================================================
-- 7. Repeat purchases & CLV proxy
-- =============================================================================

-- 7.1 Repeat purchase rate
WITH customer_orders AS (
    SELECT
        c.customer_unique_id,
        COUNT(DISTINCT o.order_id) AS order_cnt,
        SUM(oi.price)              AS lifetime_revenue
    FROM customers c
    JOIN orders o       ON o.customer_id = c.customer_id
    JOIN order_items oi ON oi.order_id = o.order_id
    WHERE o.order_status = 'delivered'
    GROUP BY c.customer_unique_id
)
SELECT
    COUNT(*)                                AS customers,
    COUNT(*) FILTER (WHERE order_cnt >= 2)  AS repeat_customers,
    ROUND(100.0 * COUNT(*) FILTER (WHERE order_cnt >= 2) / COUNT(*), 2) AS repeat_purchase_rate_pct,
    ROUND(AVG(lifetime_revenue), 2)         AS avg_clv,
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lifetime_revenue)::numeric, 2) AS median_clv,
    ROUND(AVG(order_cnt), 3)                AS avg_orders_per_customer
FROM customer_orders;

-- 7.2 Time to the second order (LAG over a customer's order history)
WITH customer_orders AS (
    SELECT
        c.customer_unique_id,
        o.order_purchase_timestamp,
        ROW_NUMBER() OVER w AS order_no,
        o.order_purchase_timestamp - LAG(o.order_purchase_timestamp) OVER w AS gap
    FROM orders o
    JOIN customers c ON c.customer_id = o.customer_id
    WHERE o.order_status = 'delivered'
    WINDOW w AS (PARTITION BY c.customer_unique_id ORDER BY o.order_purchase_timestamp)
)
SELECT
    COUNT(*)                                                                  AS second_orders,
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM gap) / 86400)::numeric, 1)
                                                                              AS median_days_to_2nd,
    ROUND(100.0 * AVG((gap <= INTERVAL '1 day')::int), 1)                     AS within_1_day_pct,
    ROUND(100.0 * AVG((gap <= INTERVAL '90 days')::int), 1)                   AS within_90_days_pct
FROM customer_orders
WHERE order_no = 2;

-- 7.3 Top customers by lifetime revenue
SELECT
    c.customer_unique_id,
    COUNT(DISTINCT o.order_id) AS order_cnt,
    ROUND(SUM(oi.price), 2)    AS lifetime_revenue
FROM customers c
JOIN orders o       ON o.customer_id = c.customer_id
JOIN order_items oi ON oi.order_id = o.order_id
WHERE o.order_status = 'delivered'
GROUP BY c.customer_unique_id
ORDER BY lifetime_revenue DESC
LIMIT 20;


-- =============================================================================
-- 8. Monthly cohort retention
-- =============================================================================

WITH activity AS (
    SELECT DISTINCT
        c.customer_unique_id,
        DATE_TRUNC('month', o.order_purchase_timestamp)::date AS activity_month
    FROM customers c
    JOIN orders o ON o.customer_id = c.customer_id
    WHERE o.order_status = 'delivered'
),
first_order AS (
    SELECT customer_unique_id, MIN(activity_month) AS cohort_month
    FROM activity
    GROUP BY customer_unique_id
),
cohort_size AS (
    SELECT cohort_month, COUNT(*) AS cohort_customers
    FROM first_order
    GROUP BY cohort_month
),
retention AS (
    SELECT
        f.cohort_month,
        (EXTRACT(YEAR  FROM AGE(a.activity_month, f.cohort_month)) * 12
       + EXTRACT(MONTH FROM AGE(a.activity_month, f.cohort_month)))::int AS period_number,
        COUNT(*) AS active_customers
    FROM first_order f
    JOIN activity a ON a.customer_unique_id = f.customer_unique_id
    GROUP BY 1, 2
)
SELECT
    r.cohort_month,
    cs.cohort_customers,
    r.period_number,
    r.active_customers,
    ROUND(100.0 * r.active_customers / cs.cohort_customers, 2) AS retention_pct
FROM retention r
JOIN cohort_size cs ON cs.cohort_month = r.cohort_month
WHERE r.period_number BETWEEN 0 AND 6
  AND r.cohort_month BETWEEN '2017-01-01' AND '2018-06-01'
ORDER BY r.cohort_month, r.period_number;


-- =============================================================================
-- 9. RFM segmentation
--    ~97% of customers have exactly one order, so frequency quintiles would be
--    random tie-breaking among one-time buyers. F is therefore the actual order
--    count (one-time vs repeat); R and M are quintiles (NTILE(5)).
--    Ties are broken by customer_unique_id so the result is deterministic and
--    matches scripts/run_analysis.py exactly.
-- =============================================================================

WITH base AS (
    SELECT
        c.customer_unique_id,
        MAX(o.order_purchase_timestamp)::date AS last_order_date,
        COUNT(DISTINCT o.order_id)            AS frequency,
        SUM(oi.price)                         AS monetary
    FROM customers c
    JOIN orders o       ON o.customer_id = c.customer_id
    JOIN order_items oi ON oi.order_id = o.order_id
    WHERE o.order_status = 'delivered'
    GROUP BY c.customer_unique_id
),
snapshot AS (
    SELECT MAX(last_order_date) + 1 AS snapshot_date FROM base
),
scored AS (
    SELECT
        b.customer_unique_id,
        s.snapshot_date - b.last_order_date AS recency_days,
        b.frequency,
        b.monetary,
        NTILE(5) OVER (ORDER BY s.snapshot_date - b.last_order_date DESC, b.customer_unique_id) AS r_score,
        NTILE(5) OVER (ORDER BY b.monetary, b.customer_unique_id)                              AS m_score
    FROM base b CROSS JOIN snapshot s
),
segmented AS (
    SELECT
        *,
        CASE
            WHEN frequency >= 2 AND r_score >= 3 THEN 'Champions'
            WHEN frequency >= 2                  THEN 'At Risk'
            WHEN r_score >= 4 AND m_score >= 4   THEN 'New High-Value'
            WHEN r_score >= 4                    THEN 'New'
            WHEN m_score >= 4                    THEN 'Lapsed High-Value'
            ELSE                                      'Lapsed'
        END AS segment
    FROM scored
)
SELECT
    segment,
    COUNT(*)                                                     AS customers,
    ROUND(SUM(monetary), 2)                                      AS revenue,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2)           AS customer_share_pct,
    ROUND(100.0 * SUM(monetary) / SUM(SUM(monetary)) OVER (), 2) AS revenue_share_pct,
    ROUND(AVG(monetary), 2)                                      AS avg_monetary,
    ROUND(AVG(recency_days), 1)                                  AS avg_recency_days
FROM segmented
GROUP BY segment
ORDER BY revenue DESC;


-- =============================================================================
-- 10. Payment type mix
-- =============================================================================

SELECT
    op.payment_type,
    COUNT(*)                                AS payments,
    ROUND(SUM(op.payment_value), 2)         AS payment_value,
    ROUND(100.0 * SUM(op.payment_value) / SUM(SUM(op.payment_value)) OVER (), 2) AS value_share_pct,
    ROUND(AVG(op.payment_installments), 2)  AS avg_installments
FROM order_payments op
JOIN orders o ON o.order_id = op.order_id
WHERE o.order_status = 'delivered'
GROUP BY op.payment_type
ORDER BY payment_value DESC;
