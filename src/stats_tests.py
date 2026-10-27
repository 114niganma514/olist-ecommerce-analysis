"""
Statistical tests on the SQL outputs (writes output/tables/stats_tests.csv).

1. Late vs on-time review scores: Mann-Whitney U (scores are ordinal, so no t-test assumption needed)
2. Low review (1-2 stars) vs late: chi-square test of independence + odds ratio with 95% CI
3. State level: Spearman correlation between late rate and average review
4. First-order review vs coming back: chi-square on repeat rate
"""
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats


def run_tests(out: Path):
    t = lambda n: pd.read_csv(out / "tables" / f"{n}.csv")
    rows = []

    # 1 + 2: rebuild the score samples from the count table
    rl = t("review_by_late")
    on = np.repeat(rl[rl.is_late == 0].review_score, rl[rl.is_late == 0].orders)
    late = np.repeat(rl[rl.is_late == 1].review_score, rl[rl.is_late == 1].orders)
    u = stats.mannwhitneyu(on, late, alternative="greater")
    # rank-biserial correlation as effect size
    rbc = 2 * u.statistic / (len(on) * len(late)) - 1
    rows.append(("Review score: on-time > late (Mann-Whitney U)", f"{on.mean():.2f} vs {late.mean():.2f}",
                 u.pvalue, f"rank-biserial r = {rbc:.2f}"))

    a, b = (late <= 2).sum(), (late > 2).sum()          # late: low / not low
    c, d = (on <= 2).sum(), (on > 2).sum()              # on time: low / not low
    chi2, p, _, _ = stats.chi2_contingency([[a, b], [c, d]])
    odds = (a * d) / (b * c)
    se = np.sqrt(1 / a + 1 / b + 1 / c + 1 / d)
    lo, hi = np.exp(np.log(odds) - 1.96 * se), np.exp(np.log(odds) + 1.96 * se)
    rows.append(("Low review (1-2 stars) rate: late vs on-time (chi-square)",
                 f"{a / (a + b):.1%} vs {c / (c + d):.1%}", p, f"odds ratio {odds:.1f} (95% CI {lo:.1f}-{hi:.1f})"))

    # 3: state-level correlation (states with 100+ delivered orders)
    sp = t("state_perf")
    sp = sp[sp.delivered_orders >= 100]
    rho, p = stats.spearmanr(sp.late_rate, sp.avg_review)
    rows.append(("States: late rate vs average review (Spearman)", f"{len(sp)} states", p, f"rho = {rho:.2f}"))
    rho2, p2 = stats.spearmanr(sp.avg_delivery_days, sp.freight_share)
    rows.append(("States: delivery days vs freight share of bill (Spearman)", f"{len(sp)} states", p2,
                 f"rho = {rho2:.2f}"))

    # 4: first-order experience vs repeat
    fr = t("repeat_by_first_review")
    fr = fr[fr.first_order_review.isin(["1-2 stars", "4-5 stars"])].set_index("first_order_review")
    if len(fr) == 2:
        rep = (fr.customers * fr.repeat_rate).round()
        table = [[rep["1-2 stars"], fr.customers["1-2 stars"] - rep["1-2 stars"]],
                 [rep["4-5 stars"], fr.customers["4-5 stars"] - rep["4-5 stars"]]]
        chi2, p, _, _ = stats.chi2_contingency(table)
        rows.append(("Repeat rate: first order 4-5 stars vs 1-2 stars (chi-square)",
                     f"{fr.repeat_rate['4-5 stars']:.2%} vs {fr.repeat_rate['1-2 stars']:.2%}", p, ""))

    res = pd.DataFrame(rows, columns=["test", "compared", "p_value", "effect"])
    res["significant_at_5pct"] = res.p_value < .05
    res.to_csv(out / "tables" / "stats_tests.csv", index=False, encoding="utf-8")
    for r in res.itertuples():
        print(f"  {r.test:<62} p={r.p_value:.2g}")
    return res


if __name__ == "__main__":
    run_tests(Path(__file__).resolve().parents[1] / "output")
