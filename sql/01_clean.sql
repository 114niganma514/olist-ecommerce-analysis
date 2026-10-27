-- =====================================================================
-- 01 Clean and model: build one row per order (orders_clean) and one row per item (items_clean)
-- Input tables are the raw CSVs loaded by src/run_analysis.py. Every timestamp column also has an
-- *_ts copy in Unix seconds, so date maths is plain arithmetic and this SQL runs unchanged on
-- DuckDB, SQLite, MySQL 8, Hive or Spark SQL.
-- =====================================================================

-- @name build_cat_map
-- Category names are Portuguese; translate to English. Two categories are missing from the official
-- translation table, so they are added by hand.
DROP TABLE IF EXISTS cat_map;
CREATE TABLE cat_map AS
SELECT product_category_name, product_category_name_english AS category FROM cat_trans
UNION ALL
SELECT 'pc_gamer', 'pc_gamer'
WHERE NOT EXISTS (SELECT 1 FROM cat_trans WHERE product_category_name = 'pc_gamer')
UNION ALL
SELECT 'portateis_cozinha_e_preparadores_de_alimentos', 'kitchen_portables_food_preparers'
WHERE NOT EXISTS (SELECT 1 FROM cat_trans
                  WHERE product_category_name = 'portateis_cozinha_e_preparadores_de_alimentos');

-- @name build_items_clean
DROP TABLE IF EXISTS items_clean;
CREATE TABLE items_clean AS
SELECT i.order_id, i.order_item_id, i.product_id, i.seller_id,
       s.seller_state,
       COALESCE(m.category, 'unknown') AS category,
       i.price, i.freight_value
FROM items i
LEFT JOIN products p ON i.product_id = p.product_id
LEFT JOIN cat_map m  ON p.product_category_name = m.product_category_name
LEFT JOIN sellers s  ON i.seller_id = s.seller_id;

-- @name build_orders_clean
-- Rules:
--   * one row per order; item, payment and review tables are aggregated to order level first
--   * valid order = not canceled / unavailable (used for revenue and customer analysis)
--   * delivered order = status delivered AND a customer delivery date exists (used for logistics)
--   * late = delivered on a calendar day after the estimated delivery date
--   * in_window = 2017-01 to 2018-08; months before and after have too few orders for trends
DROP TABLE IF EXISTS orders_clean;
CREATE TABLE orders_clean AS
WITH it AS (
    SELECT order_id,
           COUNT(*)                   AS n_items,
           COUNT(DISTINCT seller_id)  AS n_sellers,
           SUM(price)                 AS items_value,
           SUM(freight_value)         AS freight_value
    FROM items GROUP BY order_id
),
pay AS (
    SELECT order_id,
           SUM(payment_value)          AS payment_value,
           MAX(payment_installments)   AS installments,
           MAX(CASE WHEN payment_sequential = 1 THEN payment_type END) AS payment_type
    FROM payments GROUP BY order_id
),
rev AS (
    SELECT order_id, AVG(review_score * 1.0) AS review_score
    FROM reviews GROUP BY order_id
)
SELECT o.order_id,
       c.customer_unique_id,
       c.customer_state,
       o.order_status,
       CASE WHEN o.order_status IN ('canceled', 'unavailable') THEN 0 ELSE 1 END       AS is_valid,
       CASE WHEN o.order_status = 'delivered'
             AND o.order_delivered_customer_date_ts IS NOT NULL THEN 1 ELSE 0 END      AS is_delivered,
       o.order_purchase_timestamp_ts                                                   AS purchase_ts,
       substr(o.order_purchase_timestamp, 1, 10)                                       AS purchase_date,
       substr(o.order_purchase_timestamp, 1, 7)                                        AS order_month,
       CAST(substr(o.order_purchase_timestamp, 1, 4) AS INTEGER) * 12
         + CAST(substr(o.order_purchase_timestamp, 6, 2) AS INTEGER)                   AS month_idx,
       -- exact integer arithmetic so it behaves the same in every engine
       CAST(((o.order_purchase_timestamp_ts % 86400) - (o.order_purchase_timestamp_ts % 3600)) / 3600 AS INTEGER)       AS purchase_hour,
       CAST(((o.order_purchase_timestamp_ts - o.order_purchase_timestamp_ts % 86400) / 86400 + 4) % 7 AS INTEGER)       AS purchase_dow,  -- 0 = Sunday
       (o.order_delivered_customer_date_ts - o.order_purchase_timestamp_ts) / 86400.0                  AS delivery_days,
       (o.order_estimated_delivery_date_ts - o.order_purchase_timestamp_ts) / 86400.0                  AS promised_days,
       (o.order_delivered_customer_date_ts - o.order_estimated_delivery_date_ts) / 86400.0 AS late_days,
       (o.order_delivered_carrier_date_ts - o.order_purchase_timestamp_ts) / 86400.0                   AS handover_days,
       CASE WHEN substr(o.order_delivered_customer_date, 1, 10)
                 > substr(o.order_estimated_delivery_date, 1, 10) THEN 1 ELSE 0 END     AS is_late,
       it.n_items, it.n_sellers, it.items_value, it.freight_value,
       it.items_value + it.freight_value                                               AS gmv,
       pay.payment_value, pay.payment_type, pay.installments,
       rev.review_score,
       CASE WHEN substr(o.order_purchase_timestamp, 1, 7) BETWEEN '2017-01' AND '2018-08'
            THEN 1 ELSE 0 END                                                          AS in_window
FROM orders o
JOIN customers c ON o.customer_id = c.customer_id
LEFT JOIN it  ON o.order_id = it.order_id
LEFT JOIN pay ON o.order_id = pay.order_id
LEFT JOIN rev ON o.order_id = rev.order_id;

-- @name clean_log
SELECT (SELECT COUNT(*) FROM orders)                                  AS raw_orders,
       (SELECT COUNT(*) FROM reviews)                                 AS raw_reviews,
       (SELECT COUNT(*) FROM orders_clean)                            AS clean_orders,
       (SELECT COUNT(*) FROM orders_clean WHERE is_valid = 1)         AS valid_orders,
       (SELECT COUNT(*) FROM orders_clean WHERE is_delivered = 1)     AS delivered_orders,
       (SELECT COUNT(*) FROM orders_clean WHERE n_items IS NULL)      AS orders_without_items,
       (SELECT COUNT(*) FROM orders_clean WHERE review_score IS NULL) AS orders_without_review,
       (SELECT COUNT(*) FROM items_clean WHERE category = 'unknown')  AS items_unknown_category,
       (SELECT MIN(purchase_date) FROM orders_clean)                  AS first_date,
       (SELECT MAX(purchase_date) FROM orders_clean)                  AS last_date;
