-- Olist E-Commerce Analytics — SQL queries for portfolio & interviews
-- Run after 01_schema.sql and 02_load_data.sql
\c olist_ecommerce;

-- =============================================================================
-- 1. Core KPIs: GMV / Revenue, Orders, AOV, Customers
-- =============================================================================

-- 1.1 Overall KPIs (delivered orders only — standard e-commerce practice)
WITH delivered AS (
    SELECT o.order_id, o.customer_id, oi.price, oi.freight_value
    FROM orders o
    JOIN order_items oi ON o.order_id = oi.order_id
    WHERE o.order_status = 'delivered'
)
SELECT
    ROUND(SUM(price)::numeric, 2)                         AS gmv_revenue,
    ROUND(SUM(price + freight_value)::numeric, 2)         AS gmv_incl_freight,
    COUNT(DISTINCT order_id)                              AS orders,
    COUNT(DISTINCT customer_id)                           AS customers,
    ROUND(SUM(price)::numeric / COUNT(DISTINCT order_id), 2) AS aov
FROM delivered;

-- 1.2 Payment-based GMV (alternative definition used in some dashboards)
SELECT
    ROUND(SUM(op.payment_value)::numeric, 2) AS payment_gmv,
    COUNT(DISTINCT o.order_id)               AS paid_orders
FROM orders o
JOIN order_payments op ON o.order_id = op.order_id
WHERE o.order_status NOT IN ('canceled', 'unavailable');


-- =============================================================================
-- 2. Sales dynamics by month
-- =============================================================================

SELECT
    DATE_TRUNC('month', o.order_purchase_timestamp)::date AS month,
    COUNT(DISTINCT o.order_id)                            AS orders,
    ROUND(SUM(oi.price)::numeric, 2)                      AS revenue,
    ROUND(SUM(oi.price)::numeric / COUNT(DISTINCT o.order_id), 2) AS aov
FROM orders o
JOIN order_items oi ON o.order_id = oi.order_id
WHERE o.order_status = 'delivered'
GROUP BY 1
ORDER BY 1;


-- =============================================================================
-- 3. Sales by category (with window functions: share + ranking)
-- =============================================================================

SELECT
    COALESCE(ct.product_category_name_english, p.product_category_name, 'unknown') AS category,
    ROUND(SUM(oi.price)::numeric, 2) AS revenue,
    COUNT(DISTINCT oi.order_id)      AS orders,
    ROUND(
        100.0 * SUM(oi.price) / SUM(SUM(oi.price)) OVER (),
        2
    ) AS revenue_share_pct,
    RANK() OVER (ORDER BY SUM(oi.price) DESC)       AS revenue_rank,
    DENSE_RANK() OVER (ORDER BY COUNT(DISTINCT oi.order_id) DESC) AS orders_rank
FROM order_items oi
JOIN orders o ON oi.order_id = o.order_id
JOIN products p ON oi.product_id = p.product_id
LEFT JOIN category_translation ct
    ON p.product_category_name = ct.product_category_name
WHERE o.order_status = 'delivered'
GROUP BY 1
ORDER BY revenue DESC
LIMIT 20;


-- =============================================================================
-- 4. Sales by region (state)
-- =============================================================================

SELECT
    c.customer_state,
    COUNT(DISTINCT o.order_id)       AS orders,
    COUNT(DISTINCT c.customer_unique_id) AS customers,
    ROUND(SUM(oi.price)::numeric, 2) AS revenue,
    ROUND(SUM(oi.price)::numeric / COUNT(DISTINCT o.order_id), 2) AS aov,
    ROUND(
        100.0 * SUM(oi.price) / SUM(SUM(oi.price)) OVER (),
        2
    ) AS revenue_share_pct
FROM orders o
JOIN order_items oi ON o.order_id = oi.order_id
JOIN customers c ON o.customer_id = c.customer_id
WHERE o.order_status = 'delivered'
GROUP BY c.customer_state
ORDER BY revenue DESC;


-- =============================================================================
-- 5. Delivery time & late deliveries
-- =============================================================================

SELECT
    COUNT(*) AS delivered_orders,
    ROUND(AVG(
        EXTRACT(EPOCH FROM (order_delivered_customer_date - order_purchase_timestamp)) / 86400
    )::numeric, 2) AS avg_delivery_days,
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (
        ORDER BY EXTRACT(EPOCH FROM (order_delivered_customer_date - order_purchase_timestamp)) / 86400
    )::numeric, 2) AS median_delivery_days,
    ROUND(
        100.0 * AVG(
            CASE WHEN order_delivered_customer_date > order_estimated_delivery_date
                 THEN 1 ELSE 0 END
        )::numeric,
        2
    ) AS late_delivery_rate_pct
FROM orders
WHERE order_status = 'delivered'
  AND order_delivered_customer_date IS NOT NULL
  AND order_estimated_delivery_date IS NOT NULL;

-- Late delivery rate by state
SELECT
    c.customer_state,
    COUNT(*) AS orders,
    ROUND(AVG(
        EXTRACT(EPOCH FROM (o.order_delivered_customer_date - o.order_purchase_timestamp)) / 86400
    )::numeric, 2) AS avg_delivery_days,
    ROUND(
        100.0 * AVG(
            CASE WHEN o.order_delivered_customer_date > o.order_estimated_delivery_date
                 THEN 1 ELSE 0 END
        )::numeric,
        2
    ) AS late_rate_pct
FROM orders o
JOIN customers c ON o.customer_id = c.customer_id
WHERE o.order_status = 'delivered'
  AND o.order_delivered_customer_date IS NOT NULL
GROUP BY c.customer_state
HAVING COUNT(*) >= 100
ORDER BY late_rate_pct DESC
LIMIT 15;


-- =============================================================================
-- 6. Repeat purchases & customer lifetime value (CLV proxy)
-- =============================================================================

-- Repeat purchase rate
WITH customer_orders AS (
    SELECT
        c.customer_unique_id,
        COUNT(DISTINCT o.order_id) AS order_cnt,
        SUM(oi.price)              AS lifetime_revenue
    FROM customers c
    JOIN orders o ON c.customer_id = o.customer_id
    JOIN order_items oi ON o.order_id = oi.order_id
    WHERE o.order_status = 'delivered'
    GROUP BY c.customer_unique_id
)
SELECT
    COUNT(*) AS customers,
    COUNT(*) FILTER (WHERE order_cnt >= 2) AS repeat_customers,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE order_cnt >= 2) / COUNT(*),
        2
    ) AS repeat_purchase_rate_pct,
    ROUND(AVG(lifetime_revenue)::numeric, 2) AS avg_clv,
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lifetime_revenue)::numeric, 2) AS median_clv,
    ROUND(AVG(order_cnt)::numeric, 2) AS avg_orders_per_customer
FROM customer_orders;

-- Top customers by CLV
WITH customer_orders AS (
    SELECT
        c.customer_unique_id,
        COUNT(DISTINCT o.order_id) AS order_cnt,
        ROUND(SUM(oi.price)::numeric, 2) AS lifetime_revenue
    FROM customers c
    JOIN orders o ON c.customer_id = o.customer_id
    JOIN order_items oi ON o.order_id = oi.order_id
    WHERE o.order_status = 'delivered'
    GROUP BY c.customer_unique_id
)
SELECT *
FROM customer_orders
ORDER BY lifetime_revenue DESC
LIMIT 20;


-- =============================================================================
-- 7. Cohort retention (month of first purchase)
-- =============================================================================

WITH first_order AS (
    SELECT
        c.customer_unique_id,
        DATE_TRUNC('month', MIN(o.order_purchase_timestamp))::date AS cohort_month
    FROM customers c
    JOIN orders o ON c.customer_id = o.customer_id
    WHERE o.order_status = 'delivered'
    GROUP BY c.customer_unique_id
),
activity AS (
    SELECT
        c.customer_unique_id,
        DATE_TRUNC('month', o.order_purchase_timestamp)::date AS activity_month
    FROM customers c
    JOIN orders o ON c.customer_id = o.customer_id
    WHERE o.order_status = 'delivered'
),
cohort_size AS (
    SELECT cohort_month, COUNT(*) AS cohort_customers
    FROM first_order
    GROUP BY cohort_month
),
retention AS (
    SELECT
        f.cohort_month,
        (
            EXTRACT(YEAR FROM a.activity_month) * 12
            + EXTRACT(MONTH FROM a.activity_month)
        ) - (
            EXTRACT(YEAR FROM f.cohort_month) * 12
            + EXTRACT(MONTH FROM f.cohort_month)
        ) AS period_number,
        COUNT(DISTINCT f.customer_unique_id) AS active_customers
    FROM first_order f
    JOIN activity a ON f.customer_unique_id = a.customer_unique_id
    GROUP BY 1, 2
)
SELECT
    r.cohort_month,
    cs.cohort_customers,
    r.period_number,
    r.active_customers,
    ROUND(100.0 * r.active_customers / cs.cohort_customers, 2) AS retention_pct
FROM retention r
JOIN cohort_size cs ON r.cohort_month = cs.cohort_month
WHERE r.period_number BETWEEN 0 AND 6
  AND r.cohort_month BETWEEN '2017-01-01' AND '2018-06-01'
ORDER BY r.cohort_month, r.period_number;


-- =============================================================================
-- 8. RFM base table (for export / Power BI)
-- =============================================================================

WITH base AS (
    SELECT
        c.customer_unique_id,
        MAX(o.order_purchase_timestamp)::date AS last_order_date,
        COUNT(DISTINCT o.order_id)            AS frequency,
        SUM(oi.price)                         AS monetary
    FROM customers c
    JOIN orders o ON c.customer_id = o.customer_id
    JOIN order_items oi ON o.order_id = oi.order_id
    WHERE o.order_status = 'delivered'
    GROUP BY c.customer_unique_id
),
scored AS (
    SELECT
        customer_unique_id,
        ('2018-09-01'::date - last_order_date) AS recency_days,
        frequency,
        ROUND(monetary::numeric, 2) AS monetary,
        -- R: fewer days since last order → higher score (5 = most recent)
        NTILE(5) OVER (ORDER BY ('2018-09-01'::date - last_order_date) DESC) AS r_score,
        -- F/M: higher frequency / monetary → higher score
        NTILE(5) OVER (ORDER BY frequency ASC) AS f_score,
        NTILE(5) OVER (ORDER BY monetary ASC)  AS m_score
    FROM base
)
SELECT
    customer_unique_id,
    recency_days,
    frequency,
    monetary,
    r_score,
    f_score,
    m_score,
    (r_score::text || f_score::text || m_score::text) AS rfm_code
FROM scored
ORDER BY monetary DESC
LIMIT 50;

-- Note: for production RFM segmentation mapping see Python notebook / scripts/run_analysis.py


-- =============================================================================
-- 9. Payment type mix
-- =============================================================================

SELECT
    op.payment_type,
    COUNT(*) AS payments,
    ROUND(SUM(op.payment_value)::numeric, 2) AS payment_value,
    ROUND(AVG(op.payment_installments)::numeric, 2) AS avg_installments
FROM order_payments op
JOIN orders o ON op.order_id = o.order_id
WHERE o.order_status = 'delivered'
GROUP BY op.payment_type
ORDER BY payment_value DESC;


-- =============================================================================
-- 10. Review score vs late delivery
-- =============================================================================

SELECT
    CASE WHEN o.order_delivered_customer_date > o.order_estimated_delivery_date
         THEN 'late' ELSE 'on_time' END AS delivery_flag,
    ROUND(AVG(r.review_score)::numeric, 2) AS avg_review_score,
    COUNT(*) AS reviews
FROM orders o
JOIN order_reviews r ON o.order_id = r.order_id
WHERE o.order_status = 'delivered'
  AND o.order_delivered_customer_date IS NOT NULL
GROUP BY 1;
