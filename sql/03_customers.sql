-- =====================================================================
-- 03 Customers: repeat purchase and monthly cohort retention
-- Business question: do customers come back? How much revenue depends on returning customers?
-- Olist issues a new customer_id for every order; the real person is customer_unique_id.
-- =====================================================================

-- @name build_customer_orders
DROP TABLE IF EXISTS customer_orders;
CREATE TABLE customer_orders AS
SELECT customer_unique_id,
       COUNT(*)            AS n_orders,
       COUNT(DISTINCT purchase_date) AS n_order_days,
       MIN(month_idx)      AS first_month_idx,
       MIN(purchase_ts)    AS first_ts,
       MAX(purchase_ts)    AS last_ts,
       SUM(gmv)            AS total_gmv
FROM orders_clean
WHERE is_valid = 1
GROUP BY customer_unique_id;

-- @name repeat_summary
SELECT COUNT(*)                                                          AS customers,
       SUM(CASE WHEN n_orders >= 2 THEN 1 ELSE 0 END)                    AS repeat_customers,
       ROUND(SUM(CASE WHEN n_orders >= 2 THEN 1 ELSE 0 END) * 1.0 / COUNT(*), 4) AS repeat_rate,
       -- "true" repeat: ordered on 2+ different days (same-day extra orders are usually one split basket)
       SUM(CASE WHEN n_order_days >= 2 THEN 1 ELSE 0 END)                AS true_repeat_customers,
       ROUND(SUM(CASE WHEN n_order_days >= 2 THEN 1 ELSE 0 END) * 1.0 / COUNT(*), 4) AS true_repeat_rate,
       ROUND(SUM(CASE WHEN n_orders >= 2 THEN total_gmv ELSE 0 END) / SUM(total_gmv), 4) AS repeat_gmv_share,
       ROUND(AVG(n_orders * 1.0), 3)                                     AS orders_per_customer,
       ROUND(AVG(total_gmv), 2)                                          AS gmv_per_customer
FROM customer_orders;

-- @name orders_per_customer
SELECT CASE WHEN n_orders >= 4 THEN 4 ELSE n_orders END AS n_orders_capped,
       COUNT(*) AS customers
FROM customer_orders
GROUP BY 1
ORDER BY 1;

-- @name second_order_gap
-- Days between a customer's first and second valid order
WITH seq AS (
    SELECT customer_unique_id, purchase_ts,
           ROW_NUMBER() OVER (PARTITION BY customer_unique_id ORDER BY purchase_ts) AS rn
    FROM orders_clean WHERE is_valid = 1
),
gap AS (
    SELECT a.customer_unique_id, (b.purchase_ts - a.purchase_ts) / 86400.0 AS gap_days
    FROM seq a JOIN seq b ON a.customer_unique_id = b.customer_unique_id AND a.rn = 1 AND b.rn = 2
)
SELECT CASE WHEN gap_days < 1   THEN '1_same day'
            WHEN gap_days <= 30 THEN '2_1-30 days'
            WHEN gap_days <= 90 THEN '3_31-90 days'
            WHEN gap_days <= 180 THEN '4_91-180 days'
            ELSE '5_over 180 days' END AS gap_bucket,
       COUNT(*) AS customers
FROM gap
GROUP BY 1
ORDER BY 1;

-- @name cohort_retention
-- Cohort = month of first valid order; M1 = share of the cohort that ordered again 1 month later, etc.
WITH act AS (
    SELECT DISTINCT o.customer_unique_id, o.month_idx
    FROM orders_clean o WHERE o.is_valid = 1
),
base AS (
    SELECT c.first_month_idx AS cohort_idx, COUNT(*) AS cohort_size
    FROM customer_orders c GROUP BY c.first_month_idx
)
SELECT c.first_month_idx                       AS cohort_idx,
       b.cohort_size,
       a.month_idx - c.first_month_idx         AS months_since,
       COUNT(*)                                AS active_customers,
       ROUND(COUNT(*) * 1.0 / b.cohort_size, 5) AS retention
FROM act a
JOIN customer_orders c ON a.customer_unique_id = c.customer_unique_id
JOIN base b            ON c.first_month_idx = b.cohort_idx
GROUP BY c.first_month_idx, b.cohort_size, a.month_idx - c.first_month_idx
ORDER BY cohort_idx, months_since;

-- @name repeat_by_first_review
-- Does the first experience predict coming back? Repeat rate by review score of the first order
WITH first_o AS (
    SELECT o.customer_unique_id, o.review_score, o.is_late,
           ROW_NUMBER() OVER (PARTITION BY o.customer_unique_id ORDER BY o.purchase_ts) AS rn
    FROM orders_clean o WHERE o.is_valid = 1
)
SELECT CASE WHEN f.review_score IS NULL THEN 'no review'
            WHEN f.review_score <= 2 THEN '1-2 stars'
            WHEN f.review_score < 4  THEN '3 stars'
            ELSE '4-5 stars' END                                  AS first_order_review,
       COUNT(*)                                                    AS customers,
       ROUND(AVG(CASE WHEN c.n_orders >= 2 THEN 1.0 ELSE 0 END), 4) AS repeat_rate
FROM first_o f
JOIN customer_orders c ON f.customer_unique_id = c.customer_unique_id
WHERE f.rn = 1
GROUP BY 1
ORDER BY 1;
