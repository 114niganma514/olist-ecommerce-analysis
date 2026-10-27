-- =====================================================================
-- 06 Categories and sellers
-- Business question: which categories drive revenue and which hurt satisfaction?
--                    How concentrated is revenue among sellers, and which sellers cause late deliveries?
-- =====================================================================

-- @name category_perf
-- Item-level GMV by category; review and lateness are order-level, so an order with items in
-- two categories counts once in each.
WITH oc AS (
    SELECT DISTINCT order_id, category FROM items_clean
),
cat_orders AS (
    SELECT oc.category,
           ROUND(AVG(CASE WHEN o.is_valid = 1 THEN o.review_score END), 3)         AS avg_review,
           ROUND(AVG(CASE WHEN o.is_delivered = 1 THEN o.is_late * 1.0 END), 4)    AS late_rate
    FROM oc JOIN orders_clean o ON oc.order_id = o.order_id
    GROUP BY oc.category
),
cat_items AS (
    SELECT i.category,
           COUNT(DISTINCT i.order_id)                                      AS orders,
           COUNT(*)                                                        AS items,
           SUM(i.price + i.freight_value)                                  AS gmv,
           AVG(i.price)                                                    AS avg_price,
           SUM(i.freight_value) / SUM(i.price + i.freight_value)           AS freight_share
    FROM items_clean i
    JOIN orders_clean o ON i.order_id = o.order_id
    WHERE o.is_valid = 1
    GROUP BY i.category
)
SELECT ci.category, ci.orders, ci.items,
       ROUND(ci.gmv, 2)                                   AS gmv,
       ROUND(ci.gmv / (SELECT SUM(gmv) FROM cat_items), 4) AS gmv_share,
       ROUND(ci.avg_price, 2)                             AS avg_price,
       ROUND(ci.freight_share, 4)                         AS freight_share,
       co.avg_review, co.late_rate
FROM cat_items ci
LEFT JOIN cat_orders co ON ci.category = co.category
ORDER BY ci.gmv DESC;

-- @name build_seller_perf
DROP TABLE IF EXISTS seller_perf;
CREATE TABLE seller_perf AS
WITH so AS (
    SELECT i.seller_id, i.order_id,
           SUM(i.price + i.freight_value) AS seller_gmv
    FROM items_clean i
    JOIN orders_clean o ON i.order_id = o.order_id
    WHERE o.is_valid = 1
    GROUP BY i.seller_id, i.order_id
)
SELECT so.seller_id,
       COUNT(*)                                                       AS orders,
       SUM(o.is_delivered)                                            AS delivered_orders,
       SUM(CASE WHEN o.is_delivered = 1 THEN o.is_late ELSE 0 END)    AS late_orders,
       SUM(so.seller_gmv)                                             AS gmv,
       AVG(o.review_score)                                            AS avg_review,
       AVG(CASE WHEN o.is_delivered = 1 THEN o.is_late * 1.0 END)     AS late_rate,
       AVG(CASE WHEN o.is_delivered = 1 THEN o.handover_days END)     AS avg_handover_days
FROM so JOIN orders_clean o ON so.order_id = o.order_id
GROUP BY so.seller_id;

-- @name seller_pareto
-- Sellers ranked by GMV with cumulative GMV share (for the Pareto curve)
SELECT seller_id, orders, ROUND(gmv, 2) AS gmv,
       ROW_NUMBER() OVER (ORDER BY gmv DESC)                                     AS gmv_rank,
       COUNT(*) OVER ()                                                          AS n_sellers,
       ROUND(SUM(gmv) OVER (ORDER BY gmv DESC ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
             / SUM(gmv) OVER (), 5)                                              AS cum_gmv_share
FROM seller_perf
ORDER BY gmv_rank;

-- @name seller_risk
-- Sellers with enough volume (30+ orders) and a late rate at least twice the platform average
WITH avg_late AS (
    SELECT AVG(is_late * 1.0) AS platform_late FROM orders_clean WHERE is_delivered = 1
)
SELECT s.seller_id, s.orders, ROUND(s.gmv, 2) AS gmv,
       ROUND(s.late_rate, 4) AS late_rate, ROUND(s.avg_review, 3) AS avg_review,
       ROUND(s.avg_handover_days, 2) AS avg_handover_days
FROM seller_perf s CROSS JOIN avg_late a
WHERE s.orders >= 30 AND s.late_rate >= 2 * a.platform_late
ORDER BY s.orders DESC;

-- @name seller_risk_summary
WITH avg_late AS (
    SELECT AVG(is_late * 1.0) AS platform_late FROM orders_clean WHERE is_delivered = 1
)
SELECT COUNT(*)                                                   AS sellers_30plus,
       SUM(CASE WHEN s.late_rate >= 2 * a.platform_late THEN 1 ELSE 0 END) AS risky_sellers,
       SUM(CASE WHEN s.late_rate >= 2 * a.platform_late THEN s.orders ELSE 0 END) AS risky_seller_orders,
       SUM(CASE WHEN s.late_rate >= 2 * a.platform_late THEN s.late_orders ELSE 0 END) AS risky_seller_late_orders,
       (SELECT SUM(late_orders) FROM seller_perf)                 AS all_seller_late_orders,
       ROUND(MAX(a.platform_late), 4)                             AS platform_late_rate
FROM seller_perf s CROSS JOIN avg_late a
WHERE s.orders >= 30;
