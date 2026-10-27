-- =====================================================================
-- 07 Payments
-- Business question: how do customers pay, and do instalments go with bigger baskets?
-- =====================================================================

-- @name payment_mix
SELECT COALESCE(payment_type, 'unknown')                         AS payment_type,
       COUNT(*)                                                   AS orders,
       ROUND(COUNT(*) * 1.0 / (SELECT COUNT(*) FROM orders_clean WHERE is_valid = 1), 4) AS share,
       ROUND(AVG(gmv), 2)                                         AS aov
FROM orders_clean
WHERE is_valid = 1
GROUP BY COALESCE(payment_type, 'unknown')
ORDER BY orders DESC;

-- @name installments
-- Credit-card orders only (other methods are always 1 instalment)
SELECT CASE WHEN installments <= 1 THEN '1_1x'
            WHEN installments <= 3 THEN '2_2-3x'
            WHEN installments <= 6 THEN '3_4-6x'
            WHEN installments <= 10 THEN '4_7-10x'
            ELSE '5_11x+' END                   AS installment_bucket,
       COUNT(*)                                 AS orders,
       ROUND(AVG(gmv), 2)                       AS aov
FROM orders_clean
WHERE is_valid = 1 AND payment_type = 'credit_card'
GROUP BY 1
ORDER BY 1;
