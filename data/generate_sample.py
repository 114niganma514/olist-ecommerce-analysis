"""
Generates SYNTHETIC data with exactly the same file names and columns as the Kaggle
"Brazilian E-Commerce Public Dataset by Olist", so the pipeline can be tested without the real data.

Numbers produced from this data are meaningless; always re-run on the real dataset.
Usage: python data/generate_sample.py --orders 30000 --out data/sample
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

STATES = ["SP", "RJ", "MG", "RS", "PR", "SC", "BA", "DF", "ES", "GO", "PE", "CE", "PA", "MT", "MA",
          "MS", "PB", "PI", "RN", "AL", "SE", "TO", "RO", "AM", "AC", "AP", "RR"]
STATE_W = np.array([42, 13, 11.7, 5.5, 5.1, 3.7, 3.4, 2.1, 2.0, 2.0, 1.7, 1.3, 1.0, .9, .7,
                    .7, .5, .5, .5, .4, .4, .3, .3, .15, .08, .07, .05])
# distance-like factor: remote states get slower and later deliveries
STATE_FAR = np.array([0, .3, .3, .6, .4, .5, .9, .6, .5, .6, 1, 1.1, 1.3, .9, 1.3,
                      .8, 1.1, 1.1, 1.1, 1.3, 1.2, 1.0, 1.2, 1.4, 1.5, 1.5, 1.6])
CATS = {  # portuguese name -> (english name, mean price, weight)
    "cama_mesa_banho": ("bed_bath_table", 90, 11), "beleza_saude": ("health_beauty", 130, 9),
    "esporte_lazer": ("sports_leisure", 115, 8), "moveis_decoracao": ("furniture_decor", 85, 7),
    "informatica_acessorios": ("computers_accessories", 115, 7), "utilidades_domesticas": ("housewares", 90, 6),
    "relogios_presentes": ("watches_gifts", 200, 5), "telefonia": ("telephony", 70, 4),
    "ferramentas_jardim": ("garden_tools", 110, 4), "automotivo": ("auto", 140, 4),
    "brinquedos": ("toys", 115, 4), "cool_stuff": ("cool_stuff", 165, 3), "perfumaria": ("perfumery", 120, 3),
    "bebes": ("baby", 130, 3), "eletronicos": ("electronics", 60, 2.5), "papelaria": ("stationery", 85, 2),
    "fashion_bolsas_e_acessorios": ("fashion_bags_accessories", 65, 2),
    "pet_shop": ("pet_shop", 110, 1.7), "moveis_escritorio": ("office_furniture", 160, 1.4),
    "consoles_games": ("consoles_games", 140, 1.0), "malas_acessorios": ("luggage_accessories", 160, 1.0),
    "eletroportateis": ("small_appliances", 280, .6), "instrumentos_musicais": ("musical_instruments", 280, .6),
    "pc_gamer": (None, 170, .1),  # missing from the translation table in the real data too
    "portateis_cozinha_e_preparadores_de_alimentos": (None, 260, .1),
}


def uid(rng, n):
    return [b.hex() for b in np.frombuffer(rng.bytes(16 * n), dtype="S16")]


def main(n_orders: int, out: str, seed: int):
    rng = np.random.default_rng(seed)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    fmt = lambda s: s.dt.strftime("%Y-%m-%d %H:%M:%S")

    # ---- dimension tables ----
    cat_names = list(CATS)
    cat_w = np.array([CATS[c][2] for c in cat_names]); cat_w /= cat_w.sum()
    n_products, n_sellers = n_orders // 3, max(300, n_orders // 30)
    prod_cat = rng.choice(len(cat_names), n_products, p=cat_w)
    prod_ids = uid(rng, n_products)
    prod_price = np.array([CATS[cat_names[c]][1] for c in prod_cat]) * rng.lognormal(0, .6, n_products)
    products = pd.DataFrame({
        "product_id": prod_ids,
        "product_category_name": [cat_names[c] for c in prod_cat],
        "product_name_lenght": rng.integers(10, 70, n_products),
        "product_description_lenght": rng.integers(50, 3000, n_products),
        "product_photos_qty": rng.integers(1, 8, n_products),
        "product_weight_g": rng.integers(100, 20000, n_products),
        "product_length_cm": rng.integers(10, 100, n_products),
        "product_height_cm": rng.integers(2, 80, n_products),
        "product_width_cm": rng.integers(8, 80, n_products),
    })
    products.loc[rng.random(n_products) < .015, "product_category_name"] = np.nan

    seller_ids = uid(rng, n_sellers)
    seller_state = rng.choice(len(STATES), n_sellers, p=np.r_[.6, .08, .1, .05, .07, .04, np.full(21, .06 / 21)])
    seller_quality = rng.lognormal(0, .5, n_sellers)          # >1 = slower to ship
    seller_pop = rng.pareto(1.2, n_sellers) + 1; seller_pop /= seller_pop.sum()
    sellers = pd.DataFrame({"seller_id": seller_ids, "seller_zip_code_prefix": rng.integers(1000, 99999, n_sellers),
                            "seller_city": "city", "seller_state": [STATES[s] for s in seller_state]})
    prod_seller = rng.choice(n_sellers, n_products, p=seller_pop)
    prod_pop = rng.pareto(1.5, n_products) + 1; prod_pop /= prod_pop.sum()

    # ---- customers: ~3% buy more than once ----
    n_unique = int(n_orders * .965)
    unique_ids = uid(rng, n_unique)
    cust_state = rng.choice(len(STATES), n_unique, p=STATE_W / STATE_W.sum())
    order_owner = np.r_[np.arange(n_unique), rng.integers(0, n_unique, n_orders - n_unique)]
    rng.shuffle(order_owner)

    # ---- order dates: growth through 2017, Black Friday spike, data ends 2018-10 ----
    days = pd.date_range("2016-09-04", "2018-10-17", freq="D")
    t = np.arange(len(days))
    w = np.where(days < "2017-01-01", .02, np.clip(.25 + t / 420, 0, 1.15))
    w = np.where(days >= "2018-09-01", .01, w)
    w = w * np.where(pd.Series(days).dt.dayofweek.to_numpy() >= 5, .8, 1.05)
    w[(days >= "2017-11-24") & (days <= "2017-11-25")] *= 4.5
    w /= w.sum()
    # repeat orders of the same customer must come later than their first order
    first_idx = rng.choice(len(days), n_orders, p=w)
    hw = np.array([2, 1, .6, .4, .3, .4, 1, 2, 3.5, 5, 6, 6.2, 6, 6.2, 6.3, 6.2, 6, 5.8, 5.5, 5.6, 6, 6.3, 5.6, 4])
    hours = rng.choice(24, n_orders, p=hw / hw.sum())
    purchase = days[first_idx] + pd.to_timedelta(hours * 3600 + rng.integers(0, 3600, n_orders), unit="s")
    purchase = pd.Series(purchase)

    order_ids = uid(rng, n_orders)
    customer_ids = uid(rng, n_orders)            # Olist gives a new customer_id per order
    owner_state = cust_state[order_owner]
    far = STATE_FAR[owner_state]

    status = rng.choice(["delivered", "shipped", "canceled", "unavailable", "invoiced", "processing"],
                        n_orders, p=[.97, .011, .0063, .0061, .0032, .0034])
    late_data = purchase >= "2018-09-01"
    status = np.where(late_data & (rng.random(n_orders) < .7), "canceled", status)

    # ---- items ----
    n_items = rng.choice([1, 1, 1, 1, 1, 1, 1, 1, 2, 3], n_orders)
    item_rows = []
    for o in range(n_orders):
        p0 = rng.choice(n_products, p=prod_pop)
        for k in range(n_items[o]):
            p = p0 if (k > 0 and rng.random() < .6) else rng.choice(n_products, p=prod_pop)
            item_rows.append((o, k + 1, p))
    it = np.array(item_rows)
    items = pd.DataFrame({
        "order_id": np.array(order_ids)[it[:, 0]], "order_item_id": it[:, 1],
        "product_id": np.array(prod_ids)[it[:, 2]], "seller_id": np.array(seller_ids)[prod_seller[it[:, 2]]],
        "shipping_limit_date": fmt(purchase.iloc[it[:, 0]].reset_index(drop=True) + pd.Timedelta(days=6)),
        "price": prod_price[it[:, 2]].round(2),
        "freight_value": (8 + 12 * far[it[:, 0]] + rng.gamma(2, 3, len(it))).round(2),
    })
    order_seller_q = pd.Series(seller_quality[prod_seller[it[:, 2]]]).groupby(it[:, 0]).max().to_numpy()

    # ---- delivery: estimate is padded; slow sellers + remote states + Nov/Feb-Mar 2018 peaks run late ----
    est_days = np.round(20 + 8 * far + rng.normal(0, 4, n_orders)).clip(7, 60)
    month = purchase.dt.strftime("%Y-%m").to_numpy()
    congestion = np.isin(month, ["2017-11", "2017-12", "2018-02", "2018-03"]) * 5
    deliv_days = rng.gamma(3, (2.5 + 4 * far) / 3 * order_seller_q, n_orders) + 3 + congestion + rng.exponential(1.5, n_orders)
    approved = purchase + pd.to_timedelta(rng.exponential(10, n_orders) * 3600, unit="s")
    carrier = approved + pd.to_timedelta(rng.gamma(2, 1.2, n_orders) * order_seller_q * 86400, unit="s")
    delivered = purchase + pd.to_timedelta(deliv_days * 86400, unit="s")
    estimated = (purchase + pd.to_timedelta(est_days, unit="D")).dt.normalize()
    is_deliv = status == "delivered"
    orders = pd.DataFrame({
        "order_id": order_ids, "customer_id": customer_ids, "order_status": status,
        "order_purchase_timestamp": fmt(purchase), "order_approved_at": fmt(approved),
        "order_delivered_carrier_date": fmt(carrier).where(np.isin(status, ["delivered", "shipped"])),
        "order_delivered_customer_date": fmt(delivered).where(is_deliv),
        "order_estimated_delivery_date": fmt(estimated),
    })
    orders.loc[is_deliv & (rng.random(n_orders) < .0005), "order_delivered_customer_date"] = np.nan

    customers = pd.DataFrame({
        "customer_id": customer_ids, "customer_unique_id": np.array(unique_ids)[order_owner],
        "customer_zip_code_prefix": rng.integers(1000, 99999, n_orders), "customer_city": "city",
        "customer_state": [STATES[s] for s in owner_state]})

    # ---- payments ----
    totals = items.groupby("order_id")[["price", "freight_value"]].sum().sum(axis=1).reindex(order_ids).to_numpy()
    ptype = rng.choice(["credit_card", "boleto", "voucher", "debit_card"], n_orders, p=[.74, .195, .05, .015])
    inst = np.where(ptype == "credit_card", np.clip(rng.geometric(.28, n_orders) + (totals > 200) * 2, 1, 24), 1)
    payments = pd.DataFrame({"order_id": order_ids, "payment_sequential": 1, "payment_type": ptype,
                             "payment_installments": inst, "payment_value": totals.round(2)})

    # ---- reviews: score driven mostly by lateness ----
    late_by = (delivered - estimated).dt.total_seconds().to_numpy() / 86400
    base = np.where(~is_deliv, 1.8, np.where(late_by > 0, 2.6 - np.clip(late_by, 0, 20) * .05, 4.35))
    score = np.clip(np.round(base + rng.normal(0, 1.0, n_orders)), 1, 5).astype(int)
    review_date = np.where(is_deliv, delivered, estimated)
    reviews = pd.DataFrame({"review_id": uid(rng, n_orders), "order_id": order_ids, "review_score": score,
                            "review_comment_title": np.nan, "review_comment_message": np.nan,
                            "review_creation_date": fmt(pd.Series(pd.to_datetime(review_date)).dt.normalize() + pd.Timedelta(days=1)),
                            "review_answer_timestamp": fmt(pd.Series(pd.to_datetime(review_date)) + pd.Timedelta(days=3))})
    reviews = reviews.sample(frac=.993, random_state=seed)

    trans = pd.DataFrame([(k, v[0]) for k, v in CATS.items() if v[0]],
                         columns=["product_category_name", "product_category_name_english"])

    tables = {"olist_orders_dataset": orders, "olist_customers_dataset": customers,
              "olist_order_items_dataset": items, "olist_order_payments_dataset": payments,
              "olist_order_reviews_dataset": reviews, "olist_products_dataset": products,
              "olist_sellers_dataset": sellers}
    for name, df in tables.items():
        df.to_csv(out / f"{name}.csv", index=False)
    trans.to_csv(out / "product_category_name_translation.csv", index=False, encoding="utf-8-sig")  # real file has a BOM
    print(f"wrote {n_orders:,} orders, {len(items):,} items -> {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--orders", type=int, default=30000)
    ap.add_argument("--out", default="data/sample")
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    main(a.orders, a.out, a.seed)
