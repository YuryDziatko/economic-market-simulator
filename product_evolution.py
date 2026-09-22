"""
product_evolution.py  —  Annual product catalogue evolution

Each simulated year:
  1. PRICE CHANGES  — each product independently rolls:
       - no_change_prob (default 90%) → price stays the same
       - if change happens, direction depends on market structure:
           monopoly    : 80% up / 20% down
           oligopoly   : 65% up / 35% down
           competitive : 35% up / 65% down
       - magnitude drawn from Uniform(price_change_min, price_change_max)

  2. NEW PRODUCTS  — each product independently rolls new_product_prob (default 2%).
       If triggered, a clone is created:
           product_name  → original name + " #N" auto-incrementing suffix
           price_usd     → original price × Uniform(new_product_price_min, new_product_price_max)
           quantity      → random from same division range as original
           all other fields copied from parent

Market structure and quantity ranges are read from simulation_config.xlsx.
"""

import random
import sqlite3
from pathlib import Path
from typing import Dict

import pandas as pd


# ── Market structure → price-rise probability ─────────────────────────────────
RISE_PROB = {
    "competitive": 0.35,
    "oligopoly":   0.65,
    "monopoly":    0.80,
}


def load_evolution_config(config_path: Path) -> dict:
    """Read evolution_config sheet; return dict of parameters (with safe defaults)."""
    defaults = {
        "no_change_prob":        0.90,
        "price_change_min":      0.01,
        "price_change_max":      0.12,
        "new_product_prob":      0.02,
        "new_product_price_min": 0.80,
        "new_product_price_max": 1.25,
    }
    if not Path(config_path).exists():
        return defaults
    try:
        df = pd.read_excel(config_path, sheet_name="evolution_config", header=1)
        for _, r in df.iterrows():
            key = str(r.get("parameter", "")).strip()
            if key in defaults:
                try:
                    defaults[key] = float(r["value"])
                except Exception:
                    pass
    except Exception:
        pass
    return defaults


def load_market_structures(config_path: Path) -> Dict[str, str]:
    """Returns dict: coicop_division -> market_structure."""
    if not Path(config_path).exists():
        return {}
    df = pd.read_excel(config_path, sheet_name="producer_config", header=1)
    result = {}
    for _, r in df.iterrows():
        try:
            div = str(int(float(r["coicop_division"]))).zfill(2)
            result[div] = str(r["market_structure"]).strip().lower()
        except Exception:
            continue
    return result


def load_quantity_maxes(config_path: Path) -> Dict[str, int]:
    """Returns dict: coicop_division -> max_quantity_per_good."""
    if not Path(config_path).exists():
        return {}
    df = pd.read_excel(config_path, sheet_name="quantity_config", header=1)
    result = {}
    for _, r in df.iterrows():
        try:
            div = str(int(float(r["coicop_division"]))).zfill(2)
            result[div] = int(float(r["max_quantity_per_good"]))
        except Exception:
            continue
    return result


def evolve_year(
    goods_db: pd.DataFrame,
    year: int,
    config_path: Path,
    rng: random.Random,
) -> pd.DataFrame:
    """
    Apply one year of evolution to goods_db.
    Returns a NEW DataFrame — the original is left untouched.
    """
    cfg        = load_evolution_config(config_path)
    mkt_struct = load_market_structures(config_path)
    qty_maxes  = load_quantity_maxes(config_path)

    db = goods_db.copy()
    new_rows  = []
    price_ups = 0
    price_dns = 0
    price_nc  = 0
    new_count = 0

    if "_clone_count" not in db.columns:
        db["_clone_count"] = 0

    for idx, row in db.iterrows():
        div = str(row["coicop_division"]).zfill(2)
        ms  = mkt_struct.get(div, "competitive")

        # ── 1. Price change ───────────────────────────────────────────────────
        if rng.random() >= cfg["no_change_prob"]:
            rise_p    = RISE_PROB.get(ms, 0.50)
            magnitude = rng.uniform(cfg["price_change_min"], cfg["price_change_max"])
            if rng.random() < rise_p:
                db.at[idx, "price_usd"] *= (1 + magnitude)
                price_ups += 1
            else:
                db.at[idx, "price_usd"] *= (1 - magnitude)
                price_dns += 1
        else:
            price_nc += 1

        db.at[idx, "gdp_contribution"] = db.at[idx, "price_usd"] * db.at[idx, "quantity"]

        # ── 2. New product spawn ──────────────────────────────────────────────
        if rng.random() < cfg["new_product_prob"]:
            clone   = row.to_dict()
            clone_n = int(db.at[idx, "_clone_count"]) + 1
            db.at[idx, "_clone_count"] = clone_n

            clone["product_name"] = f"{row['product_name']} #{clone_n}"
            price_factor = rng.uniform(cfg["new_product_price_min"], cfg["new_product_price_max"])
            clone["price_usd"]    = round(float(row["price_usd"]) * price_factor, 2)

            qty_max            = qty_maxes.get(div, 1000)
            clone["quantity"]  = rng.randint(max(1, qty_max // 10), qty_max)
            clone["gdp_contribution"] = clone["price_usd"] * clone["quantity"]
            clone["source_sheet"]     = f"evolved_year_{year}"
            clone["_clone_count"]     = 0
            new_rows.append(clone)
            new_count += 1

    if new_rows:
        new_df = pd.DataFrame(new_rows)
        db     = pd.concat([db, new_df], ignore_index=True)

    db = db.reset_index(drop=True)
    db["good_id"]   = range(1, len(db) + 1)
    db["price_usd"] = db["price_usd"].round(2)

    print(f"  Year {year:>2} evolution: "
          f"prices ↑{price_ups} ↓{price_dns} ={price_nc}  |  "
          f"+{new_count} new products  |  "
          f"catalogue size: {len(db)}  |  "
          f"catalogue GDP: ${db['gdp_contribution'].sum():,.0f}")

    return db


def save_yearly_snapshot(db: pd.DataFrame, year: int, out_dir: Path, sqlite_path: Path):
    """Save this year's catalogue as a CSV snapshot and refresh the SQLite DB."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    csv_path = out_dir / f"goods_year_{year:02d}.csv"
    db.to_csv(csv_path, index=False)

    con = sqlite3.connect(sqlite_path)
    db.to_sql("goods", con, if_exists="replace", index=False)
    snap = db.copy()
    snap["sim_year"] = year
    snap.to_sql(f"goods_year_{year:02d}", con, if_exists="replace", index=False)
    con.commit()
    con.close()

    return csv_path
