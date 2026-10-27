-- =====================================================================
-- 04 RFM segmentation (full R, F and M, unlike the Taobao data)
-- R = days since last valid order (reference date = day after the last order in the data)
-- F = number of valid orders, M = total GMV
-- R and M are scored 1-5 with NTILE (5 = most recent / highest spend).
-- F is NOT quintiled: about 97% of customers ordered once, so quintiles would be meaningless;
-- it is used as "1 order" vs "2+ orders".
-- =====================================================================

-- @name build_rfm
DROP TABLE IF EXISTS rfm;
CREATE TABLE rfm AS
WITH ref AS (SELECT MAX(last_ts) + 86400 AS ref_ts FROM customer_orders),
base AS (
    SELECT c.customer_unique_id,
           (r.ref_ts - c.last_ts) / 86400.0 AS recency_days,
           c.n_orders                       AS frequency,
           c.total_gmv                      AS monetary
    FROM customer_orders c CROSS JOIN ref r
),
scored AS (
    SELECT *,
           NTILE(5) OVER (ORDER BY recency_days DESC) AS r_score,
           NTILE(5) OVER (ORDER BY monetary)          AS m_score
    FROM base
)
SELECT *,
       CASE WHEN frequency >= 2 AND r_score >= 4 THEN 'Champions'
            WHEN frequency >= 2                  THEN 'Loyal, lapsing'
            WHEN r_score >= 4 AND m_score >= 4   THEN 'New, high value'
            WHEN r_score >= 4                    THEN 'New, low value'
            WHEN m_score >= 4                    THEN 'At risk, high value'
            WHEN r_score = 3                     THEN 'Cooling'
            ELSE 'Lost' END AS segment
FROM scored;

-- @name rfm_summary
SELECT segment,
       COUNT(*)                                                       AS customers,
       ROUND(COUNT(*) * 1.0 / (SELECT COUNT(*) FROM rfm), 4)          AS customer_share,
       ROUND(SUM(monetary), 2)                                        AS gmv,
       ROUND(SUM(monetary) / (SELECT SUM(monetary) FROM rfm), 4)      AS gmv_share,
       ROUND(AVG(recency_days), 1)                                    AS avg_recency_days,
       ROUND(AVG(frequency * 1.0), 2)                                 AS avg_frequency,
       ROUND(AVG(monetary), 2)                                        AS avg_monetary
FROM rfm
GROUP BY segment
ORDER BY gmv DESC;

-- @name rfm_score_grid
SELECT r_score, m_score, COUNT(*) AS customers, ROUND(SUM(monetary), 2) AS gmv
FROM rfm
GROUP BY r_score, m_score
ORDER BY r_score, m_score;
