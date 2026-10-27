# Olist Brazilian E-commerce Analysis (9-table relational dataset)

End-to-end analysis of about 100k orders from Olist, a Brazilian marketplace (2016-2018). Raw CSVs are modelled into an order-level fact table with SQL, then analysed for **growth, retention, RFM value, delivery reliability, customer satisfaction, categories, sellers and payments**. Findings are backed by statistical tests and turned into sized recommendations.

Compared with project 1 (Taobao behaviour logs) this dataset has **money, delivery dates and reviews**, so it supports full RFM, cohort retention, and a causal-style question: *how much does a late delivery hurt satisfaction?*

## 1. Business questions

| # | Question | Method | File |
|---|---|---|---|
| Q1 | How fast is the business growing and when do people buy? | Monthly GMV/AOV, YoY, weekday x hour heatmap, peak days | `sql/02_sales.sql` |
| Q2 | Do customers come back? | Repeat rate, time to 2nd order, monthly cohort retention | `sql/03_customers.sql` |
| Q3 | Who are the valuable customers and how should each group be treated? | RFM with NTILE scoring and rule-based segments | `sql/04_rfm.sql` |
| Q4 | How reliable is delivery and how much does lateness hurt reviews? | Delay buckets, state view, Mann-Whitney U, chi-square, odds ratio | `sql/05_delivery.sql`, `src/stats_tests.py` |
| Q5 | Which categories and sellers drive revenue or problems? | Category performance, seller Pareto, late-seller list | `sql/06_category_seller.sql` |
| Q6 | How do customers pay? | Payment mix, instalments vs order value | `sql/07_payment.sql` |

## 2. Data

- Source: Kaggle [Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) (free Kaggle account needed; zip about 45 MB). Downloaded with `kagglehub` (latest release: 99,441 orders, 112,650 items, 103,886 payments, 99,224 reviews, 32,951 products, 3,095 sellers). `data/olist/` holds an offline copy used only if Kaggle cannot be reached; its review table has 100,000 rows (an earlier release), and the report states which source was used.
- Tables used: orders, customers, order_items, order_payments, order_reviews, products, sellers, category name translation (geolocation is not needed)
- Modelling choices (all in `sql/01_clean.sql`):
  - one row per order; items, payments and reviews aggregated to order level first
  - real customer = `customer_unique_id` (Olist creates a new `customer_id` for every order)
  - valid order = not canceled/unavailable; delivered order = delivered with a delivery date
  - late = delivered on a calendar day after the promised date
  - trends limited to 2017-01 to 2018-08 (months outside have very few orders)
  - Portuguese category names translated to English, including two missing from the official table

## 3. How to run

**Windows:** put the downloaded zip in `data\` (or leave it in the folder above this project, e.g. Downloads) and double-click `run_windows.bat`. It finds Anaconda, installs DuckDB if needed, unzips the data and runs everything in under a minute.

**Command line:**
```bash
pip install duckdb pandas matplotlib scipy
python src/run_analysis.py                         # auto-detects data and engine
python src/run_analysis.py --engine sqlite         # without DuckDB
python data/generate_sample.py && python src/run_analysis.py --data data/sample   # synthetic test data
```

Data source order: (1) `kagglehub` downloads the latest official release (installed automatically by the Windows runner); (2) otherwise local CSVs or a zip in `data/` or the folder above the project. The report states which source was used.

Outputs: `output/tables/*.csv` (one per query), `output/charts/*.png` (9 charts), `output/report.md` (report filled in automatically).

**Portable SQL:** every timestamp also gets a Unix-seconds column at load time, so all date maths is arithmetic and the same SQL runs on DuckDB, SQLite, MySQL 8, Hive and Spark SQL.

## 4. Project structure

```
data/generate_sample.py      synthetic data with the exact Olist schema (for testing)
sql/01_clean.sql             data model: cat_map, items_clean, orders_clean
sql/02_sales.sql             growth and seasonality
sql/03_customers.sql         repeat purchase, cohorts
sql/04_rfm.sql               RFM scoring and segments
sql/05_delivery.sql          delivery reliability and reviews
sql/06_category_seller.sql   categories, seller concentration, late sellers
sql/07_payment.sql           payment methods and instalments
src/run_analysis.py          loads data, runs all SQL, exports results
src/stats_tests.py           Mann-Whitney U, chi-square, odds ratio, Spearman
src/make_report.py           charts and report
run_windows.bat              one-click runner for Windows
```

## 5. Metric definitions

- **GMV** = item price + freight of valid orders; **AOV** = GMV / valid orders
- **Repeat rate** = customers (unique id) with 2+ valid orders / all customers
- **Cohort retention Mn** = share of a first-order-month cohort that orders again n months later
- **RFM**: R = days since last order, F = orders, M = total GMV; R and M scored 1-5 by NTILE; F = 1 vs 2+
- **Late rate** = delivered orders arriving after the promised date / delivered orders
- **Low review rate** = 1-2 star reviews / orders with a review
- **Risky seller** = 30+ orders and a late rate at least 2x the platform average

## 6. Key findings (real data; full numbers in `output/report.md`)

1. **Late delivery drives bad reviews.** Late orders average 2.27 stars vs 4.29 on time; 62% of late orders get 1-2 stars vs 9.2% on time (Mann-Whitney U and chi-square p < 0.001, odds ratio 16.3). The effect grows with the delay, and across states late rate and average review correlate at rho = -0.91.
2. **Growth is acquisition-only.** Orders grew 137% (Jan-Aug 2018 vs 2017) while AOV stayed flat; only 3.0% of customers order twice, and only 2.2% on a different day (same-day second orders are split baskets).
3. **Value sits in one-time customers.** "At risk, high value" customers (one order, long ago, top-40% spend) hold 40% of GMV, the biggest win-back pool.
4. **A few sellers cause a disproportionate share of lateness.** 54 high-volume sellers handle 4.6% of delivered orders but 11.2% of late orders; the top 10% of sellers make 67% of GMV.
5. **Promised dates are padded by ~11 days** on average, yet remote north-eastern states still see late rates of 14-21% and pay ~20% of the bill in freight.

## 7. Limitations
- Observational data: recommendations are sized from correlations and need A/B tests or pilots
- Reviews are optional; orders without a review are excluded from satisfaction metrics
- GMV is price + freight; payment value differs slightly because of vouchers and instalment interest
