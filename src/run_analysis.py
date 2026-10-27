"""
One-click pipeline for the Olist project:
load the 8 CSV files -> run sql/01-07 -> save every query result to output/tables/
-> statistical tests -> charts and report.

Usage:
    python src/run_analysis.py                      # auto-detect data, DuckDB if installed
    python src/run_analysis.py --engine sqlite      # no DuckDB needed
    python src/run_analysis.py --data data/sample   # synthetic test data

SQL files are split into blocks with "-- @name xxx"; if the last statement of a block is a query,
its result is saved as output/tables/xxx.csv
"""
import argparse
import re
import shutil
import time
import zipfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SQL_DIR, OUT = ROOT / "sql", ROOT / "output"

# file name -> (table name, timestamp columns, numeric columns)
FILES = {
    "olist_orders_dataset": ("orders", ["order_purchase_timestamp", "order_approved_at",
                                        "order_delivered_carrier_date", "order_delivered_customer_date",
                                        "order_estimated_delivery_date"], []),
    "olist_customers_dataset": ("customers", [], []),
    "olist_order_items_dataset": ("items", ["shipping_limit_date"], ["order_item_id", "price", "freight_value"]),
    "olist_order_payments_dataset": ("payments", [], ["payment_sequential", "payment_installments", "payment_value"]),
    "olist_order_reviews_dataset": ("reviews", ["review_creation_date", "review_answer_timestamp"], ["review_score"]),
    "olist_products_dataset": ("products", [], ["product_name_lenght", "product_description_lenght",
                                                "product_photos_qty", "product_weight_g", "product_length_cm",
                                                "product_height_cm", "product_width_cm"]),
    "olist_sellers_dataset": ("sellers", [], []),
    "product_category_name_translation": ("cat_trans", [], []),
}
SQL_FILES = ["02_sales.sql", "03_customers.sql", "04_rfm.sql", "05_delivery.sql",
             "06_category_seller.sql", "07_payment.sql"]


def kagglehub_download():
    """Official route: download the latest Kaggle release with kagglehub (cached after the first run)."""
    try:
        import kagglehub
    except Exception as e:
        print(f"  kagglehub not available ({type(e).__name__}: {e}); using local files")
        return None
    try:
        print("Downloading olistbr/brazilian-ecommerce with kagglehub ...")
        path = Path(kagglehub.dataset_download("olistbr/brazilian-ecommerce"))
    except Exception as e:  # no internet, Kaggle down, etc.
        print(f"  kagglehub failed ({type(e).__name__}: {e}); falling back to local files")
        return None
    hits = list(path.rglob("olist_orders_dataset.csv"))
    return hits[0].parent if hits else None


def find_data(arg):
    """Returns a folder containing the Olist CSVs. Accepts a folder or a zip; if nothing is given,
    searches data/ and the folder above the project (e.g. Downloads) for the CSVs or a zip holding them."""
    need = "olist_orders_dataset.csv"
    if arg == "kaggle":
        p = kagglehub_download()
        if p:
            return p
        raise SystemExit("[ERROR] kagglehub download failed")
    if not arg:
        p = kagglehub_download()
        if p:
            return p
    if arg:
        p = Path(arg)
        if p.is_dir() and (p / need).exists():
            return p
        if p.suffix.lower() == ".zip":
            return unzip(p)
        raise SystemExit(f"[ERROR] {p} is not a folder with {need} or a zip file")
    for folder in [ROOT / "data" / "olist", ROOT / "data"]:
        if (folder / need).exists():
            return folder
    for z in sorted((ROOT / "data").glob("*.zip")) + sorted(ROOT.parent.glob("*.zip")):
        try:
            with zipfile.ZipFile(z) as zf:
                if any(n.endswith(need) for n in zf.namelist()):
                    return unzip(z)
        except zipfile.BadZipFile:
            continue
    z = try_kaggle_download()
    if z:
        return unzip(z)
    raise SystemExit(
        "[ERROR] Olist data not found.\n"
        "Download 'Brazilian E-Commerce Public Dataset by Olist' from\n"
        "  https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce\n"
        "and put the zip (or the CSV files) in the data folder, then run again.\n"
        "To test the code only: python src/run_analysis.py --data data/sample --engine sqlite")


def try_kaggle_download():
    """If the kaggle package and an API token (kaggle.json) are available, download the dataset."""
    try:
        from kaggle.api.kaggle_api_extended import KaggleApi
        api = KaggleApi()
        api.authenticate()
    except Exception:
        return None
    print("Downloading olistbr/brazilian-ecommerce from Kaggle ...")
    (ROOT / "data").mkdir(exist_ok=True)
    api.dataset_download_files("olistbr/brazilian-ecommerce", path=str(ROOT / "data"), unzip=False)
    zips = sorted((ROOT / "data").glob("*.zip"))
    return zips[0] if zips else None


def unzip(z: Path):
    target = ROOT / "data" / "olist"
    if not (target / "olist_orders_dataset.csv").exists():
        print(f"Unzipping {z.name} ...")
        target.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(z) as zf:
            for n in zf.namelist():
                if n.endswith(".csv"):
                    (target / Path(n).name).write_bytes(zf.read(n))
    return target


def load_csv(folder: Path, stem: str):
    _, ts_cols, num_cols = FILES[stem]
    df = pd.read_csv(folder / f"{stem}.csv", dtype=str, encoding="utf-8-sig", keep_default_na=False,
                     na_values=[""])
    df.columns = [c.strip() for c in df.columns]
    for c in num_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    for c in ts_cols:
        t = pd.to_datetime(df[c], errors="coerce")
        # Unix seconds; naive timestamps are treated as-is so hours match the original strings
        secs = (t - pd.Timestamp("1970-01-01")) // pd.Timedelta(seconds=1)   # works for any datetime resolution
        df[c + "_ts"] = secs.astype("Int64")
    return df


class Engine:
    def __init__(self, kind: str, db: str):
        self.kind = kind
        if kind == "duckdb":
            import duckdb
            self.con = duckdb.connect(db)
            self.con.execute(f"SET temp_directory='{Path(db).parent.as_posix()}/duckdb_tmp'")
        else:
            import sqlite3
            self.con = sqlite3.connect(db)
            self.con.execute("PRAGMA journal_mode=OFF")
            self.con.execute("PRAGMA synchronous=OFF")

    def load(self, name: str, df: pd.DataFrame):
        if self.kind == "duckdb":
            df = df.copy()
            for c in df.columns:   # make missing text values real NULLs, not float NaN
                if df[c].dtype == object or str(df[c].dtype).startswith("str"):
                    df[c] = df[c].astype(object).where(df[c].notna(), None)
            self.con.register("tmp_df", df)
            self.con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM tmp_df")
            self.con.unregister("tmp_df")
        else:
            df.to_sql(name, self.con, if_exists="replace", index=False, chunksize=50_000)

    def index(self):
        if self.kind == "sqlite":   # DuckDB does not need indexes for these joins
            for sql in ["CREATE INDEX IF NOT EXISTS ix_oc ON orders_clean(order_id)",
                        "CREATE INDEX IF NOT EXISTS ix_oc_cu ON orders_clean(customer_unique_id)",
                        "CREATE INDEX IF NOT EXISTS ix_ic ON items_clean(order_id)",
                        "CREATE INDEX IF NOT EXISTS ix_co ON customer_orders(customer_unique_id)"]:
                try:
                    self.con.execute(sql)
                except Exception:
                    pass

    def run(self, sql: str, fetch: bool):
        if self.kind == "duckdb":
            r = self.con.execute(sql)
            return r.df() if fetch else None
        if fetch:
            return pd.read_sql_query(sql, self.con)
        self.con.execute(sql)
        self.con.commit()


def parse_blocks(path: Path):
    text = path.read_text(encoding="utf-8")
    for part in re.split(r"^-- @name\s+", text, flags=re.M)[1:]:
        name, body = part.split("\n", 1)
        body = "\n".join(l for l in body.splitlines() if not l.strip().startswith("--"))
        yield name.strip(), [s.strip() for s in body.split(";") if s.strip()]


def run_file(eng: Engine, path: Path):
    for name, stmts in parse_blocks(path):
        t = time.time()
        res = None
        for s in stmts:
            res = eng.run(s, fetch=s.lstrip().upper().startswith(("SELECT", "WITH")))
        if res is not None:
            (OUT / "tables").mkdir(parents=True, exist_ok=True)
            res.to_csv(OUT / "tables" / f"{name}.csv", index=False, encoding="utf-8")
        print(f"  {path.name:<24} {name:<24} {time.time() - t:6.1f}s")
        if name.startswith("build_customer") or name == "build_orders_clean":
            eng.index()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=None,
                    help="'kaggle', a folder or a zip with the Olist CSVs (default: kagglehub, then local files)")
    ap.add_argument("--engine", choices=["auto", "duckdb", "sqlite"], default="auto")
    a = ap.parse_args()
    if a.engine == "auto":
        try:
            import duckdb  # noqa: F401
            a.engine = "duckdb"
        except ImportError:
            a.engine = "sqlite"

    folder = find_data(a.data)
    source = "Kaggle (kagglehub, latest release)" if "kagglehub" in str(folder).lower() else f"local files ({folder})"
    print(f"Data source: {source}\nEngine: {a.engine}")
    for sub in ("tables", "charts"):
        shutil.rmtree(OUT / sub, ignore_errors=True)
        (OUT / sub).mkdir(parents=True, exist_ok=True)
    db = OUT / f"olist.{a.engine}"
    db.unlink(missing_ok=True)
    eng = Engine(a.engine, str(db))

    t0 = time.time()
    print("[1/4] Load CSV files")
    for stem, (table, _, _) in FILES.items():
        df = load_csv(folder, stem)
        eng.load(table, df)
        print(f"  {stem + '.csv':<46} {len(df):>9,} rows")

    pd.DataFrame([{"source": source}]).to_csv(OUT / "tables" / "data_source.csv", index=False)
    print("[2/4] Clean and analyse (SQL)")
    run_file(eng, SQL_DIR / "01_clean.sql")
    for f in SQL_FILES:
        run_file(eng, SQL_DIR / f)

    print("[3/4] Statistical tests")
    from stats_tests import run_tests
    run_tests(OUT)

    print("[4/4] Charts and report")
    from make_report import build
    build(OUT)
    print(f"Done in {time.time() - t0:.0f}s -> {OUT}")


if __name__ == "__main__":
    main()
