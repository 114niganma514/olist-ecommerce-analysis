"""
Reads output/tables/*.csv -> writes output/charts/*.png and output/report.md
Can be run on its own after the SQL step: python src/make_report.py
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

plt.rcParams.update({
    "font.sans-serif": ["Segoe UI", "Helvetica", "Arial", "DejaVu Sans"],
    "axes.unicode_minus": False, "figure.dpi": 150, "savefig.bbox": "tight",
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.edgecolor": "#8a8984", "axes.labelcolor": "#52514e",
    "xtick.color": "#52514e", "ytick.color": "#52514e",
    "axes.grid": True, "grid.color": "#e6e5e0", "grid.linewidth": .6, "axes.axisbelow": True,
    "figure.facecolor": "#fcfcfb", "axes.facecolor": "#fcfcfb",
    "axes.titlesize": 11, "axes.titleweight": "bold", "axes.titlecolor": "#0b0b0b",
})
BLUE, ORANGE, MUTED, INK = "#2a78d6", "#eb6834", "#b9b8b2", "#0b0b0b"
DOW = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
pct = lambda x, d=1: f"{x * 100:.{d}f}%"
brl = lambda x: f"R$ {x:,.0f}"


def big(v, ref):
    if ref >= 1e6:
        return f"{v / 1e6:,.1f}M"
    if ref >= 1e4:
        return f"{v / 1e3:,.0f}K"
    return f"{v:,.0f}"


def month_label(idx):
    idx = int(idx)
    return f"{(idx - 1) // 12}-{(idx - 1) % 12 + 1:02d}"


def build(out: Path):
    T = lambda n: pd.read_csv(out / "tables" / f"{n}.csv")
    save = lambda fig, name: (fig.savefig(out / "charts" / name, facecolor=fig.get_facecolor()), plt.close(fig))
    (out / "charts").mkdir(exist_ok=True)

    cl, ov = T("clean_log").iloc[0], T("overview").iloc[0]
    mo, yoy, dh, top = T("monthly"), T("yoy"), T("dow_hour"), T("top_days")
    rs, gap, rfr = T("repeat_summary").iloc[0], T("second_order_gap"), T("repeat_by_first_review")
    coh, rfm = T("cohort_retention"), T("rfm_summary")
    do, db, lm, sp = T("delivery_overview").iloc[0], T("delay_buckets"), T("late_monthly"), T("state_perf")
    cat, par, srs = T("category_perf"), T("seller_pareto"), T("seller_risk_summary").iloc[0]
    pm, ins, st = T("payment_mix"), T("installments"), T("stats_tests")
    avg_daily = T("daily_stats").iloc[0].avg_daily_orders

    # 1 Monthly GMV and AOV (two panels, no dual axis)
    fig, ax = plt.subplots(2, 1, figsize=(9, 5.4), sharex=True)
    ax[0].bar(mo.order_month, mo.gmv, color=BLUE, width=.7)
    ax[0].yaxis.set_major_formatter(lambda v, _: big(v, mo.gmv.max()))
    ax[0].set_title("Monthly GMV (R$, valid orders)")
    ax[0].set_ylim(0, mo.gmv.max() * 1.15)
    nov = mo.index[mo.order_month == "2017-11"]
    if len(nov):
        i = nov[0]
        ax[0].annotate("Black Friday", (i, mo.gmv[i]), xytext=(0, 6), textcoords="offset points",
                       ha="center", fontsize=8, color=INK)
    ax[1].plot(mo.order_month, mo.aov, color=BLUE, lw=2, marker="o", ms=4)
    ax[1].set_title("Average order value (R$)")
    ax[1].tick_params(axis="x", rotation=60, labelsize=8)
    save(fig, "01_monthly_gmv.png")

    # 2 Weekday x hour heatmap
    piv = dh.pivot(index="purchase_dow", columns="purchase_hour", values="orders").reindex(range(7)).fillna(0)
    fig, ax = plt.subplots(figsize=(9, 3.2))
    im = ax.imshow(piv.values, cmap="Blues", aspect="auto")
    ax.set_yticks(range(7), DOW)
    ax.set_xticks(range(0, 24, 2), [f"{h}:00" for h in range(0, 24, 2)], fontsize=8)
    ax.grid(False)
    ax.set_title("Orders by weekday and hour (2017-01 to 2018-08)")
    fig.colorbar(im, ax=ax, fraction=.025)
    save(fig, "02_weekday_hour.png")

    # 3 Review score by delivery delay
    db["label"] = db.delay_bucket.str.split("_", n=1).str[1]
    late_mask = db.delay_bucket.str[0].astype(int) >= 5
    fig, ax = plt.subplots(1, 2, figsize=(10, 3.6))
    ax[0].bar(db.label, db.avg_review, color=np.where(late_mask, ORANGE, BLUE), width=.65)
    ax[0].set_ylim(1, 5)
    ax[0].set_title("Average review score")
    ax[1].bar(db.label, db.low_review_rate, color=np.where(late_mask, ORANGE, BLUE), width=.65)
    ax[1].yaxis.set_major_formatter(lambda v, _: pct(v, 0))
    ax[1].set_title("Share of 1-2 star reviews")
    for a in ax:
        a.tick_params(axis="x", rotation=45, labelsize=8)
        for lab in a.get_xticklabels():
            lab.set_ha("right")
        a.grid(axis="x", visible=False)
    fig.suptitle("Delivery vs promised date (blue = on time or early, orange = late)", fontsize=11,
                 fontweight="bold", y=1.04)
    save(fig, "03_delay_vs_review.png")

    # 4 States: delivery speed vs satisfaction
    s = sp[sp.delivered_orders >= 100]
    fig, ax = plt.subplots(figsize=(8, 4.6))
    ax.scatter(s.avg_delivery_days, s.avg_review, s=np.sqrt(s.delivered_orders) * 3, color=BLUE, alpha=.6,
               linewidths=0)
    for r in s.itertuples():
        ax.annotate(r.customer_state, (r.avg_delivery_days, r.avg_review), fontsize=7, ha="center", va="center",
                    color=INK)
    ax.set_xlabel("Average delivery time (days)")
    ax.set_ylabel("Average review score")
    ax.set_title("Customer states: slower delivery, lower reviews (bubble = orders)")
    save(fig, "04_state_delivery_review.png")

    # 5 Cohort retention (months 1-6), cohorts 2017-01 .. 2018-02
    c = coh[(coh.months_since >= 1) & (coh.months_since <= 6)].copy()
    first, last = 2017 * 12 + 1, 2018 * 12 + 2
    c = c[(c.cohort_idx >= first) & (c.cohort_idx <= last)]
    hp = c.pivot(index="cohort_idx", columns="months_since", values="retention").reindex(
        index=range(first, last + 1), columns=range(1, 7)).fillna(0)
    fig, ax = plt.subplots(figsize=(7.5, 5))
    im = ax.imshow(hp.values, cmap="Blues", aspect="auto", vmin=0)
    for (i, j), v in np.ndenumerate(hp.values):
        ax.text(j, i, f"{v * 100:.1f}", ha="center", va="center", fontsize=7,
                color="white" if v > hp.values.max() * .6 else INK)
    sizes = coh[coh.months_since == 0].set_index("cohort_idx").cohort_size
    ax.set_yticks(range(len(hp)), [f"{month_label(i)} ({int(sizes.get(i, 0)):,})" for i in hp.index], fontsize=8)
    ax.set_xticks(range(6), [f"M{m}" for m in range(1, 7)])
    ax.grid(False)
    ax.set_title("Monthly cohort retention (% of cohort ordering again)")
    save(fig, "05_cohort_retention.png")

    # 6 RFM segments
    order = ["Champions", "Loyal, lapsing", "New, high value", "New, low value", "At risk, high value", "Cooling", "Lost"]
    r = rfm.set_index("segment").reindex([o for o in order if o in set(rfm.segment)]).reset_index()
    x = np.arange(len(r))
    fig, ax = plt.subplots(figsize=(9, 3.4))
    ax.bar(x - .2, r.customer_share, .38, color=BLUE, label="Share of customers")
    ax.bar(x + .2, r.gmv_share, .38, color=ORANGE, label="Share of GMV")
    ax.set_xticks(x, r.segment, fontsize=8)
    ax.yaxis.set_major_formatter(lambda v, _: pct(v, 0))
    ax.grid(axis="x", visible=False)
    ax.legend(frameon=False)
    ax.set_title("RFM segments: share of customers vs share of GMV")
    save(fig, "06_rfm_segments.png")

    # 7 Top categories by GMV with review and late rate
    tc = cat.head(15).iloc[::-1]
    fig, ax = plt.subplots(figsize=(8.5, 5.2))
    ax.barh(tc.category, tc.gmv, color=BLUE, height=.65)
    for i, rr in enumerate(tc.itertuples()):
        ax.text(rr.gmv, i, f"  {rr.avg_review:.2f} stars, {pct(rr.late_rate)} late", va="center", fontsize=7.5,
                color=INK)
    ax.set_xlim(0, tc.gmv.max() * 1.45)
    ax.xaxis.set_major_formatter(lambda v, _: big(v, tc.gmv.max()))
    ax.grid(axis="y", visible=False)
    ax.tick_params(axis="y", labelsize=8)
    ax.set_title("Top 15 categories by GMV (R$)")
    save(fig, "07_top_categories.png")

    # 8 Seller Pareto curve
    par["seller_pct"] = par.gmv_rank / par.n_sellers
    top10 = par.loc[par.seller_pct <= .10, "cum_gmv_share"].max()
    top20 = par.loc[par.seller_pct <= .20, "cum_gmv_share"].max()
    fig, ax = plt.subplots(figsize=(6.5, 4))
    ax.plot(par.seller_pct, par.cum_gmv_share, color=BLUE, lw=2)
    ax.plot([0, 1], [0, 1], color=MUTED, lw=1, ls="--")
    for p_, v in [(.10, top10), (.20, top20)]:
        ax.scatter([p_], [v], color=ORANGE, zorder=3, s=25)
        ax.annotate(f"Top {p_:.0%} of sellers = {pct(v, 0)} of GMV", (p_, v), xytext=(8, -12),
                    textcoords="offset points", fontsize=8, color=INK)
    ax.xaxis.set_major_formatter(lambda v, _: pct(v, 0))
    ax.yaxis.set_major_formatter(lambda v, _: pct(v, 0))
    ax.set_xlabel("Sellers ranked by GMV")
    ax.set_ylabel("Cumulative share of GMV")
    ax.set_title("Seller concentration (Pareto curve)")
    save(fig, "08_seller_pareto.png")

    # 9 Instalments vs order value
    ins["label"] = ins.installment_bucket.str.split("_", n=1).str[1]
    fig, ax = plt.subplots(figsize=(6.5, 3.2))
    ax.bar(ins.label, ins.aov, color=BLUE, width=.6)
    for i, rr in enumerate(ins.itertuples()):
        ax.text(i, rr.aov, f"R$ {rr.aov:,.0f}", ha="center", va="bottom", fontsize=8, color=INK)
    ax.grid(axis="x", visible=False)
    ax.set_title("Credit-card orders: average order value by instalments")
    save(fig, "09_installments.png")

    # ---------------- numbers for the report ----------------
    y17, y18 = yoy.set_index("year").gmv.get(2017, np.nan), yoy.set_index("year").gmv.get(2018, np.nan)
    o17, o18 = yoy.set_index("year").orders.get(2017, np.nan), yoy.set_index("year").orders.get(2018, np.nan)
    bf = top.iloc[0]
    peak = dh.groupby("purchase_hour").orders.sum().idxmax()
    dow_tot = dh.groupby("purchase_dow").orders.sum()
    weekday_avg, weekend_avg = dow_tot[[1, 2, 3, 4, 5]].mean(), dow_tot[[0, 6]].mean()

    late_orders = do.delivered_orders * do.late_rate
    avoided = late_orders * .5 * (do.low_review_rate_late - do.low_review_rate_on_time)
    worst = s.sort_values("late_rate", ascending=False).head(5)
    rfm_i = rfm.set_index("segment")
    seg = lambda n, c: rfm_i.loc[n, c] if n in rfm_i.index else 0
    gain_repeat = rs.customers * .01 * ov.aov
    far = s.sort_values("freight_share", ascending=False).head(5)
    risky_share = srs.risky_seller_orders / max(do.delivered_orders, 1)
    mw = st.iloc[0]
    chi = st.iloc[1]
    sp_row = st[st.test.str.startswith("States: late rate")].iloc[0]
    fr_row = st[st.test.str.startswith("Repeat rate")]
    fr_txt = (f"Customers whose first order got 4-5 stars vs 1-2 stars come back at {fr_row.iloc[0].compared} "
              f"(p = {fr_row.iloc[0].p_value:.2g}); "
              + ("the difference is significant." if fr_row.iloc[0].p_value < .05 else
                 "the difference is **not** statistically significant, so a bad first review is not what keeps "
                 "customers away; almost nobody comes back either way.")) if len(fr_row) else ""
    gap = gap.set_index("gap_bucket").customers
    same_day = gap.get("1_same day", 0)
    within90 = gap[[g for g in gap.index if g[0] in "23"]].sum() / max(gap.sum() - same_day, 1)
    risky_late_share = srs.risky_seller_late_orders / max(srs.all_seller_late_orders, 1)
    is_real = cl.raw_orders > 90_000
    src_file = out / "tables" / "data_source.csv"
    src_label = pd.read_csv(src_file).source.iloc[0] if src_file.exists() else "local files"
    best_pay = pm.iloc[0]

    md = f"""# Olist Brazilian E-commerce Analysis

> Data: {"Kaggle 'Brazilian E-Commerce Public Dataset by Olist' (real data); source: " + src_label if is_real else "WARNING: synthetic sample for testing the pipeline only. Re-run on the real data before quoting any number."}
> {int(cl.raw_orders):,} orders from {cl.first_date} to {cl.last_date}; {int(cl.valid_orders):,} valid (not canceled/unavailable), {int(cl.delivered_orders):,} delivered.
> Trends use 2017-01 to 2018-08 only; months outside that window have too few orders.

## 0. Executive summary

| Area | Key numbers | Interpretation |
|---|---|---|
| Scale | {int(ov.orders):,} orders, {int(ov.customers):,} customers, {int(ov.sellers):,} sellers, GMV {brl(ov.gmv)} | AOV {brl(ov.aov)}; freight is {pct(ov.freight_share_of_gmv)} of GMV |
| Growth | Jan-Aug 2018 vs Jan-Aug 2017: orders {o18 / o17 - 1:+.0%}, GMV {y18 / y17 - 1:+.0%} | Strong growth; peak day {bf.purchase_date} with {int(bf.orders):,} orders vs a daily average of {avg_daily:,.0f} |
| Retention | Only {pct(rs.repeat_rate)} of customers order twice, and only {pct(rs.true_repeat_rate)} on a different day; repeat customers bring {pct(rs.repeat_gmv_share)} of GMV | Growth is almost entirely new-customer acquisition |
| Delivery | {pct(do.late_rate)} of orders arrive late; on average orders arrive {do.avg_days_early:.1f} days before the promised date | Promised dates are heavily padded, yet late orders still happen |
| Satisfaction | Avg review {do.avg_review_on_time:.2f} on time vs {do.avg_review_late:.2f} late; 1-2 star share {pct(do.low_review_rate_on_time)} vs {pct(do.low_review_rate_late)} | A late order is {chi.effect.split()[2]}x as likely (odds) to get a 1-2 star review |
| Sellers | Top 10% of sellers = {pct(top10, 0)} of GMV; {int(srs.risky_sellers)} sellers (30+ orders) are late at 2x+ the platform rate | They handle {pct(risky_share)} of delivered orders but cause {pct(risky_late_share)} of late orders |
| Payment | {best_pay.payment_type.replace("_", " ")} is used for {pct(best_pay.share, 0)} of orders | {"Orders paid in 11+ instalments are " + f"{ins.aov.iloc[-1] / ins.aov.iloc[0]:.1f}x the value of 1x orders" if len(ins) > 1 else ""} |

## 1. Sales and seasonality
![monthly](charts/01_monthly_gmv.png)
- GMV grew from {brl(mo.gmv.iloc[0])} in {mo.order_month.iloc[0]} to {brl(mo.gmv.iloc[-1])} in {mo.order_month.iloc[-1]}; AOV stayed roughly flat between {brl(mo.aov.min())} and {brl(mo.aov.max())}, so growth came from **more orders, not bigger baskets**.
- Black Friday ({bf.purchase_date}) produced {bf.orders / avg_daily:.1f}x a normal day's orders.

![weekday-hour](charts/02_weekday_hour.png)
- Orders peak around {peak}:00; weekdays average {weekday_avg / weekend_avg:.2f}x the weekend volume, so campaigns and customer-service staffing should lean to weekday daytime.

## 2. Customers: almost nobody comes back
- {int(rs.customers):,} customers, {int(rs.repeat_customers):,} with 2+ orders (repeat rate {pct(rs.repeat_rate)}).
- {int(same_day):,} of them placed the second order on the **same day** as the first, which is usually one basket split into two orders, not a return visit. Counting only orders on different days, the true repeat rate is **{pct(rs.true_repeat_rate)}** ({int(rs.true_repeat_customers):,} customers). Of those genuine returns, {pct(within90, 0)} came back within 90 days, so the first three months are the window to act in.
- {fr_txt}

![cohort](charts/05_cohort_retention.png)

**Recommendation 1: build a second-purchase programme.** Every +1 percentage point of true repeat rate is about {int(rs.customers * .01):,} extra orders, or **{brl(gain_repeat)} GMV** at the current AOV. Test a post-delivery coupon for a second order within 90 days (A/B test, primary metric: 90-day repeat rate).

## 3. RFM segmentation (R, F and M all available)
![rfm](charts/06_rfm_segments.png)

| Segment | Customers | Share | GMV share | Avg recency (days) | Avg orders | Avg spend | Action |
|---|---|---|---|---|---|---|---|
""" + "\n".join(
        f"| {n} | {int(rfm_i.loc[n, 'customers']):,} | {pct(rfm_i.loc[n, 'customer_share'])} | {pct(rfm_i.loc[n, 'gmv_share'])} | "
        f"{rfm_i.loc[n, 'avg_recency_days']:.0f} | {rfm_i.loc[n, 'avg_frequency']:.2f} | {brl(rfm_i.loc[n, 'avg_monetary'])} | {act} |"
        for n, act in [("Champions", "VIP treatment, early access, referral programme"),
                       ("Loyal, lapsing", "Personal win-back offer before they go cold"),
                       ("New, high value", "Second-purchase coupon in the first 90 days; cross-sell"),
                       ("New, low value", "Low-cost onboarding emails; category recommendations"),
                       ("At risk, high value", "Highest-value win-back target: targeted discount"),
                       ("Cooling", "Reminder campaigns, low spend"),
                       ("Lost", "Exclude from paid retargeting")] if n in rfm_i.index) + f"""

R and M are NTILE(5) scores; F is "1 order" vs "2+ orders" because {pct(1 - rs.repeat_rate, 0)} of customers ordered only once. "At risk, high value" customers alone hold {pct(seg("At risk, high value", "gmv_share"))} of GMV.

## 4. Delivery and satisfaction
![delay](charts/03_delay_vs_review.png)
- {mw.test}: {mw.compared}, p = {mw.p_value:.2g}, {mw.effect}.
- {chi.test}: {chi.compared}, p = {chi.p_value:.2g}, {chi.effect}.
- Orders arrive {do.avg_days_early:.1f} days early on average (actual {do.avg_delivery_days:.1f} days vs promised {do.avg_promised_days:.1f}). Sellers take {do.avg_seller_handover_days:.1f} days on average to hand parcels to the carrier.

![states](charts/04_state_delivery_review.png)
- Worst late rates: {", ".join(f"{r.customer_state} {pct(r.late_rate)}" for r in worst.itertuples())}.
- {sp_row.test}: {sp_row.effect}, p = {sp_row.p_value:.2g}.
- Remote states pay more freight: {", ".join(f"{r.customer_state} {pct(r.freight_share, 0)}" for r in far.itertuples())} of the bill is freight.

**Recommendation 2: cut late deliveries.** There are about {late_orders:,.0f} late orders. Halving the late rate would avoid about **{avoided:,.0f} one- and two-star reviews** (late vs on-time low-review gap of {pct(do.low_review_rate_late - do.low_review_rate_on_time)}). Start with the states above and with the sellers below.

## 5. Categories and sellers
![categories](charts/07_top_categories.png)
![pareto](charts/08_seller_pareto.png)

**Recommendation 3: manage the late-shipping sellers.** {int(srs.risky_sellers)} of {int(srs.sellers_30plus)} sellers with 30+ orders are late at least twice as often as the platform ({pct(srs.platform_late_rate)}). They handle {int(srs.risky_seller_orders):,} orders ({pct(risky_share)} of delivered orders) but account for {pct(risky_late_share)} of all late orders. List in `tables/seller_risk.csv`; actions: handover-time SLA, ranking penalty, carrier review.

## 6. Payments
![installments](charts/09_installments.png)
""" + "\n".join(f"- {r.payment_type.replace('_', ' ')}: {pct(r.share)} of orders, AOV {brl(r.aov)}" for r in pm.itertuples()) + f"""

## 7. Limitations and next steps
1. Observational data: the recommendations are sized from correlations; each needs an A/B test or a pilot.
2. The review table has {int(cl.raw_reviews):,} rows{" (an earlier Kaggle release; the current release has 99,224)" if cl.raw_reviews == 100_000 else ""}. Reviews are optional and some orders have several; scores are averaged per order.
3. GMV uses item price + freight; payment value can differ because of vouchers and instalment interest.
4. Next: a delivery-delay model (seller handover time, distance, category, month) to predict late orders before they ship, and a churn/repeat model for the second-purchase programme.
"""
    (out / "report.md").write_text(md, encoding="utf-8")


if __name__ == "__main__":
    build(Path(__file__).resolve().parents[1] / "output")
