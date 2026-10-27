-- =====================================================================
-- 02 Sales: scale, growth, seasonality
-- Business question: how big is the business, how fast is it growing, and when do people buy?
-- GMV = item price + freight of valid orders
-- =====================================================================

-- @name overview
SELECT COUNT(*)                                                        AS orders,
       SUM(is_valid)                                                   AS valid_orders,
       COUNT(DISTINCT customer_unique_id)                              AS customers,
       ROUND(SUM(CASE WHEN is_valid = 1 THEN gmv ELSE 0 END), 2)       AS gmv,
       ROUND(SUM(CASE WHEN is_valid = 1 THEN gmv ELSE 0 END) / SUM(is_valid), 2) AS aov,
       ROUND(AVG(CASE WHEN is_valid = 1 THEN n_items * 1.0 END), 3)    AS items_per_order,
       ROUND(SUM(CASE WHEN is_valid = 1 THEN freight_value ELSE 0 END)
             / SUM(CASE WHEN is_valid = 1 THEN gmv ELSE 0 END), 4)     AS freight_share_of_gmv,
       (SELECT COUNT(DISTINCT seller_id) FROM items_clean)             AS sellers,
       (SELECT COUNT(DISTINCT product_id) FROM items_clean)            AS products,
       (SELECT COUNT(DISTINCT category) FROM items_clean)              AS categories,
       MIN(purchase_date)                                              AS first_date,
       MAX(purchase_date)                                              AS last_date
FROM orders_clean;

-- @name status_mix
SELECT order_status, COUNT(*) AS orders,
       ROUND(COUNT(*) * 1.0 / (SELECT COUNT(*) FROM orders_clean), 4) AS share
FROM orders_clean
GROUP BY order_status
ORDER BY orders DESC;

-- @name monthly
-- New customers = customers whose first valid order falls in that month
WITH first_order AS (
    SELECT customer_unique_id, MIN(month_idx) AS first_month_idx
    FROM orders_clean WHERE is_valid = 1 GROUP BY customer_unique_id
)
SELECT o.order_month,
       COUNT(*)                                        AS orders,
       COUNT(DISTINCT o.customer_unique_id)            AS customers,
       COUNT(DISTINCT CASE WHEN o.month_idx = f.first_month_idx THEN o.customer_unique_id END) AS new_customers,
       ROUND(SUM(o.gmv), 2)                            AS gmv,
       ROUND(SUM(o.gmv) / COUNT(*), 2)                 AS aov
FROM orders_clean o
JOIN first_order f ON o.customer_unique_id = f.customer_unique_id
WHERE o.is_valid = 1 AND o.in_window = 1
GROUP BY o.order_month
ORDER BY o.order_month;

-- @name yoy
-- Same-period comparison: 2018-01..08 vs 2017-01..08
SELECT substr(order_month, 1, 4) AS year,
       COUNT(*)                  AS orders,
       ROUND(SUM(gmv), 2)        AS gmv
FROM orders_clean
WHERE is_valid = 1 AND substr(order_month, 6, 2) BETWEEN '01' AND '08'
  AND substr(order_month, 1, 4) IN ('2017', '2018')
GROUP BY substr(order_month, 1, 4)
ORDER BY year;

-- @name dow_hour
SELECT purchase_dow, purchase_hour, COUNT(*) AS orders
FROM orders_clean
WHERE is_valid = 1 AND in_window = 1
GROUP BY purchase_dow, purchase_hour
ORDER BY purchase_dow, purchase_hour;

-- @name top_days
-- Peak days (Black Friday 2017 should show up here)
SELECT purchase_date, COUNT(*) AS orders, ROUND(SUM(gmv), 2) AS gmv
FROM orders_clean
WHERE is_valid = 1
GROUP BY purchase_date
ORDER BY orders DESC
LIMIT 10;

-- @name daily_stats
SELECT ROUND(AVG(orders * 1.0), 1) AS avg_daily_orders
FROM (SELECT purchase_date, COUNT(*) AS orders FROM orders_clean
      WHERE is_valid = 1 AND in_window = 1 GROUP BY purchase_date) d;
