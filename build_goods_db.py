"""
build_goods_db.py  —  Phase 1 (updated)
Merges Product_List.xlsx + reads quantity config from simulation_config.xlsx.
Adds quantity column to goods table; computes base GDP.

Usage:
    python build_goods_db.py
    python build_goods_db.py --input Product_List.xlsx --config config/simulation_config.xlsx --out-dir db
"""
import argparse, random, sqlite3
from pathlib import Path
import pandas as pd

PRODUCT_VARIANTS  = ["Product Name","Product/Service Name","Item Description","Product/Service Description"]
PRICE_VARIANTS    = ["Price (USD)","Price/Rate (USD)","Estimated Price (USD)"]
CATEGORY_VARIANTS = ["Category Name","Category"]
UNIT_VARIANTS     = ["Unit Size","Unit"]

def pick(cols, variants):
    for v in variants:
        if v in cols: return v
    return None

def load_goods(path):
    xl = pd.ExcelFile(path)
    frames = []
    for sheet in xl.sheet_names:
        df = pd.read_excel(path, sheet_name=sheet)
        cols = df.columns.tolist()
        row = pd.DataFrame()
        row["coicop_code"]   = df["COICOP Code"].astype(str).str.strip()
        row["category_name"] = df[pick(cols,CATEGORY_VARIANTS) or cols[1]]
        row["product_name"]  = df[pick(cols,PRODUCT_VARIANTS)  or cols[2]]
        row["unit_size"]     = df[pick(cols,UNIT_VARIANTS)      or ""] if pick(cols,UNIT_VARIANTS) else ""
        pc = pick(cols,PRICE_VARIANTS)
        row["price_usd"]     = pd.to_numeric(df[pc], errors="coerce") if pc else pd.NA
        row["source_sheet"]  = sheet
        frames.append(row)
    db = pd.concat(frames, ignore_index=True)
    db = db.dropna(subset=["coicop_code","product_name"])
    db = db[db["coicop_code"].str.strip().str.len() > 0]
    db["coicop_division"] = db["coicop_code"].str[:2]
    db["coicop_group"]    = db["coicop_code"].str[:4]
    db = db.drop_duplicates(subset=["coicop_code","product_name","unit_size"])
    db = db.sort_values(["coicop_division","coicop_code","product_name"]).reset_index(drop=True)
    db.insert(0, "good_id", range(1, len(db)+1))
    return db

def load_quantity_config(config_path):
    """Returns dict: coicop_division -> max_quantity_per_good"""
    df = pd.read_excel(config_path, sheet_name="quantity_config", header=1)
    result = {}
    for _, r in df.iterrows():
        div = str(int(float(r["coicop_division"]))).zfill(2)
        try:
            result[div] = int(float(r["max_quantity_per_good"]))
        except:
            result[div] = 1000
    return result

def assign_quantities(db, qty_config, seed=42):
    """Assign random quantity to each good based on division max."""
    rng = random.Random(seed)
    def get_qty(div):
        mx = qty_config.get(str(div).zfill(2), 1000)
        return rng.randint(max(1, mx // 10), mx)
    db["quantity"] = db["coicop_division"].apply(get_qty)
    return db

def save(db, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    # GDP = sum(price * quantity)
    db["gdp_contribution"] = db["price_usd"] * db["quantity"]

    csv_path = out_dir / "goods_db.csv"
    db.to_csv(csv_path, index=False)

    db_path = out_dir / "economics.db"
    con = sqlite3.connect(db_path)
    db.to_sql("goods", con, if_exists="replace", index=False)
    con.execute("CREATE INDEX IF NOT EXISTS idx_coicop   ON goods(coicop_code)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_division ON goods(coicop_division)")
    con.commit(); con.close()

    return csv_path, db_path

def summary(db):
    gdp = db["gdp_contribution"].sum()
    print("\n── Goods Database ──────────────────────────────────────")
    print(f"  Total goods         : {len(db)}")
    print(f"  COICOP divisions    : {db['coicop_division'].nunique()}")
    print(f"  Price range (USD)   : ${db['price_usd'].min():.2f} – ${db['price_usd'].max():,.2f}")
    print(f"  Quantity range      : {db['quantity'].min()} – {db['quantity'].max():,}")
    print(f"  BASE GDP (P×Q)      : ${gdp:,.0f}")
    print()
    print(f"  {'Div':<4} {'Name':<32} {'Goods':>5} {'Qty sum':>9} {'GDP share':>12}")
    print(f"  {'-'*65}")
    div_names = {"01":"Food","02":"Alcohol/Tobacco","03":"Clothing","04":"Housing",
                 "05":"Furnishings","06":"Health","07":"Transport","08":"Communication",
                 "09":"Recreation","10":"Education","11":"Restaurants","12":"Financial"}
    for div, grp in db.groupby("coicop_division"):
        div_gdp = grp["gdp_contribution"].sum()
        print(f"  {div:<4} {div_names.get(div,''):<32} {len(grp):>5} "
              f"{grp['quantity'].sum():>9,} ${div_gdp:>11,.0f}")
    print(f"  {'TOTAL':<37} {len(db):>5} {db['quantity'].sum():>9,} ${gdp:>11,.0f}")
    print("─────────────────────────────────────────────────────────\n")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input",   default="Product_List.xlsx")
    parser.add_argument("--config",  default="config/simulation_config.xlsx")
    parser.add_argument("--out-dir", default="db")
    parser.add_argument("--seed",    type=int, default=42)
    args = parser.parse_args()

    print(f"Loading goods from: {args.input}")
    db = load_goods(args.input)
    print(f"  {len(db)} goods loaded")

    print(f"Loading quantity config from: {args.config}")
    if Path(args.config).exists():
        qty_config = load_quantity_config(args.config)
    else:
        print("  Config not found — run create_config.py first. Using defaults.")
        qty_config = {str(d).zfill(2): 1000 for d in range(1,13)}

    print("Assigning quantities...")
    db = assign_quantities(db, qty_config, seed=args.seed)

    print("Saving...")
    csv_path, db_path = save(db, args.out_dir)
    print(f"  CSV    → {csv_path}")
    print(f"  SQLite → {db_path}")

    summary(db)

if __name__ == "__main__":
    main()
