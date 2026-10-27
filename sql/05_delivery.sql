-- =====================================================================
-- 05 Delivery and satisfaction
-- Business question: how reliable is delivery, and how much does a late delivery hurt the review?
-- Scope: delivered orders with a customer delivery date
-- =====================================================================

-- @name delivery_overview
SELECT COUNT(*)                                                            AS delivered_orders,
       ROUND(AVG(delivery_days), 2)                                        AS avg_delivery_days,
       ROUND(AVG(promised_days), 2)                                        AS avg_promised_days,
       ROUND(AVG(promised_days - delivery_days), 2)                        AS avg_days_early,
       ROUND(AVG(is_late * 1.0), 4)                                        AS late_rate,
       ROUND(AVG(CASE WHEN is_late = 0 THEN review_score END), 3)          AS avg_review_on_time,
       ROUND(AVG(CASE WHEN is_late = 1 THEN review_score END), 3)          AS avg_review_late,
       ROUND(AVG(CASE WHEN is_late = 0 AND review_score IS NOT NULL
                      THEN CASE WHEN review_score <= 2 THEN 1.0 ELSE 0 END END), 4) AS low_review_rate_on_time,
       ROUND(AVG(CASE WHEN is_late = 1 AND review_score IS NOT NULL
                      THEN CASE WHEN review_score <= 2 THEN 1.0 ELSE 0 END END), 4) AS low_review_rate_late,
       ROUND(AVG(handover_days), 2)                                        AS avg_seller_handover_days
FROM orders_clean
WHERE is_delivered = 1;

-- @name delay_buckets
-- Review score by how early / late the order arrived versus the promised date
SELECT CASE WHEN late_days <= -15 THEN '1_15+ days early'
            WHEN late_days <= -8  THEN '2_8-14 days early'
            WHEN late_days <= -1  THEN '3_1-7 days early'
            WHEN is_late = 0      THEN '4_on the day'
            WHEN late_days <= 3   THEN '5_1-3 days late'
            WHEN late_days <= 7   THEN '6_4-7 days late'
            WHEN late_days <= 14  THEN '7_8-14 days late'
            ELSE '8_15+ days late' END                                   AS delay_bucket,
       COUNT(*)                                                           AS orders,
       ROUND(AVG(review_score), 3)                                        AS avg_review,
       ROUND(AVG(CASE WHEN review_score IS NULL THEN NULL
                      WHEN review_score <= 2 THEN 1.0 ELSE 0 END), 4)     AS low_review_rate
FROM orders_clean
WHERE is_delivered = 1
GROUP BY 1
ORDER BY 1;

-- @name review_by_late
-- Score distribution by late flag (input to the statistical tests in src/stats_tests.py)
SELECT is_late, CAST(ROUND(review_score, 0) AS INTEGER) AS review_score, COUNT(*) AS orders
FROM orders_clean
WHERE is_delivered = 1 AND review_score IS NOT NULL
GROUP BY is_late, CAST(ROUND(review_score, 0) AS INTEGER)
ORDER BY is_late, review_score;

-- @name late_monthly
SELECT order_month,
       COUNT(*)                     AS delivered_orders,
       ROUND(AVG(is_late * 1.0), 4) AS late_rate,
       ROUND(AVG(delivery_days), 2) AS avg_delivery_days,
       ROUND(AVG(review_score), 3)  AS avg_review
FROM orders_clean
WHERE is_delivered = 1 AND in_window = 1
GROUP BY order_month
ORDER BY order_month;

-- @name state_perf
-- Customer state: speed, reliability, satisfaction, and how much of the bill is freight
SELECT customer_state,
       COUNT(*)                                          AS delivered_orders,
       ROUND(AVG(delivery_days), 2)                      AS avg_delivery_days,
       ROUND(AVG(is_late * 1.0), 4)                      AS late_rate,
       ROUND(AVG(review_score), 3)                       AS avg_review,
       ROUND(AVG(CASE WHEN review_score IS NULL THEN NULL
                      WHEN review_score <= 2 THEN 1.0 ELSE 0 END), 4) AS low_review_rate,
       ROUND(SUM(freight_value) / SUM(gmv), 4)           AS freight_share
FROM orders_clean
WHERE is_delivered = 1
GROUP BY customer_state
ORDER BY delivered_orders DESC;
