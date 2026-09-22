"""
simulate.py  —  Main entry point (v2)

Usage:
    python simulate.py
    python simulate.py --ticks 120 --config config/simulation_config.xlsx
    python simulate.py --ticks 120 --shock "07,supply,-0.3,24,6"
    python simulate.py --compare-shock "07,supply,-0.3,24,6"  (saves baseline + shock)

Shock format:  division,type,magnitude,start_tick,duration
  e.g.  07,supply,-0.3,24,6   = transport supply drops 30% at month 24 for 6 months
        01,demand,+0.2,1,12   = food demand surges 20% for first year
        04,cost,+0.15,36,3    = housing cost shock at month 36
"""
import argparse, random
from pathlib import Path
import pandas as pd
import numpy as np

from household_model import (
    derive_household_classes, build_households, print_household_report,
    load_bracket_config, load_population_growth_rate, evolve_households,
    save_household_snapshot,
)
from producer_model import build_all_firms, print_producer_report
from market          import MarketEngine, Shock
from product_evolution import evolve_year, save_yearly_snapshot


def load_config(config_path: Path) -> dict:
    if not config_path.exists():
        print(f"  Config not found at {config_path} — using defaults. "
              "Run create_config.py to generate it.")
        return {
            "gini": 0.35, "total_households": 500,
            "consumption_share": 0.60, "savings_rate": 0.10,
            "tax_rate": 0.22, "money_growth": 0.002,
            "population_growth_rate": 0.01,
        }
    df = pd.read_excel(config_path, sheet_name="household_config", header=1)
    df.columns = [str(c).strip().lower() for c in df.columns]
    cfg = dict(zip(df["parameter"], df["value"]))
    return {
        "gini":                   float(cfg.get("gini_coefficient",         0.35)),
        "total_households":       int(cfg.get("total_households",           500)),
        "consumption_share":      float(cfg.get("consumption_share_of_gdp", 0.60)),
        "savings_rate":           float(cfg.get("savings_rate",             0.10)),
        "tax_rate":               float(cfg.get("tax_rate",                 0.22)),
        "money_growth":           float(cfg.get("money_supply_growth",      0.002)),
        "population_growth_rate": float(cfg.get("population_growth_rate",   0.01)),
    }


def load_producer_config(config_path: Path) -> pd.DataFrame:
    if not config_path.exists():
        return None
    return pd.read_excel(config_path, sheet_name="producer_config", header=1)


def parse_shock(s: str) -> Shock:
    parts = s.split(",")
    return Shock(
        division   = str(parts[0]).strip().zfill(2),
        shock_type = str(parts[1]).strip(),
        magnitude  = float(parts[2]),
        start_tick = int(parts[3]),
        duration   = int(parts[4]),
    )


def run_once(goods_db, cfg, producer_cfg, shocks, ticks, seed, label="",
             config_path: Path = None, db_dir: Path = None, evolve: bool = True):
    random.seed(seed)
    np.random.seed(seed)

    # ── Households ─────────────────────────────────────────────────────────
    base_gdp = goods_db["gdp_contribution"].sum()
    bracket_cfg = load_bracket_config(config_path) if config_path else None
    from household_model import DEFAULT_BRACKET_CONFIG
    bracket_cfg = bracket_cfg or DEFAULT_BRACKET_CONFIG

    hh_stats = derive_household_classes(
        gini              = cfg["gini"],
        total_households  = cfg["total_households"],
        base_gdp          = base_gdp,
        consumption_share = cfg["consumption_share"],
        savings_rate      = cfg["savings_rate"],
        bracket_config    = bracket_cfg,
        rng_seed          = seed,
    )
    households = build_households(hh_stats, bracket_cfg, rng_seed=seed)
    print_household_report(households, cfg["gini"])

    if db_dir is not None:
        snap_path = save_household_snapshot(households, 0, db_dir)
        print(f"  Household database → {snap_path}")

    # ── Firms ───────────────────────────────────────────────────────────────
    if producer_cfg is not None:
        firms = build_all_firms(goods_db, producer_cfg, rng_seed=seed)
    else:
        # Fallback: competitive market, 5 private medium firms per division
        rows = []
        for div in sorted(goods_db["coicop_division"].unique()):
            rows.append({"coicop_division": div, "division_name": div,
                         "market_structure": "competitive",
                         "priv_small":0,"priv_medium":5,"priv_large":1,
                         "pub_small":0,"pub_medium":0,"pub_large":0})
        firms = build_all_firms(goods_db, pd.DataFrame(rows), rng_seed=seed)

    print_producer_report(firms, goods_db)

    # ── Period-0 equilibrium summary ────────────────────────────────────────
    hh_counts = ", ".join(
        f"{b}={hh_stats['classes'][b]['count']}" for b in ["low","middle","high","top1","top01"]
    )
    print("── Period 0 — Equilibrium ─────────────────────────────────────────────────")
    print(f"  Base GDP (Σ P×Q)   : ${base_gdp:>14,.0f}")
    print(f"  Households         : {len(households):>14,}  ({hh_counts})")
    print(f"  Firms              : {len(firms):>14,}")
    print(f"  Base inflation     :  {'0.000%':>13}  (by definition — base period)")
    print(f"  CPI base           : {'1.000':>14}")
    print("───────────────────────────────────────────────────────────────────────────\n")

    # ── Engine ─────────────────────────────────────────────────────────────
    engine = MarketEngine(
        households   = households,
        firms        = firms,
        goods_db     = goods_db,
        tax_rate     = cfg["tax_rate"],
        money_growth = cfg["money_growth"],
    )
    for shock in shocks:
        engine.add_shock(shock)
        print(f"  [shock] div={shock.division} type={shock.shock_type} "
              f"magnitude={shock.magnitude:+.0%} "
              f"ticks {shock.start_tick}–{shock.start_tick+shock.duration-1}")

    years = max(1, round(ticks / 12))
    print(f"\nRunning{' ['+label+']' if label else ''}: "
          f"{ticks} ticks ({years} years)\n")

    if evolve and config_path is not None:
        evo_rng = random.Random(seed + 9001)
        population_growth_rate = cfg.get("population_growth_rate", 0.01)
        catalogue = {"db": goods_db}   # mutable holder so the closure can update it

        def _evolve_fn(year: int, mkt_engine: MarketEngine, gdp_growth_rate: float = 0.0):
            # ── Product catalogue evolution ──────────────────────────────────
            old_db = catalogue["db"]
            old_div_price = old_db.groupby("coicop_division")["price_usd"].mean()

            new_db = evolve_year(old_db, year, config_path, evo_rng)
            catalogue["db"] = new_db

            new_div_gdp   = new_db.groupby("coicop_division")["gdp_contribution"].sum()
            new_div_price = new_db.groupby("coicop_division")["price_usd"].mean()

            for div in mkt_engine.divisions:
                gdp_val = float(new_div_gdp.get(div, mkt_engine.base_div_gdp.get(div, 0)))
                old_p   = float(old_div_price.get(div, 1.0)) or 1.0
                new_p   = float(new_div_price.get(div, old_p))
                price_shift = (new_p / old_p) - 1
                mkt_engine.rebase_division(div, gdp_val, price_shift)

            if db_dir is not None:
                save_yearly_snapshot(new_db, year, db_dir, db_dir / "economics.db")

            # ── Household evolution: income growth + population growth ───────
            n_before = len(mkt_engine.households)
            mkt_engine.households, n_new, income_growth = evolve_households(
                mkt_engine.households, gdp_growth_rate, population_growth_rate,
                bracket_cfg, evo_rng,
            )
            print(f"  Year {year:>2} households: "
                  f"income growth {income_growth:+.2%} "
                  f"(GDP {gdp_growth_rate:+.2%} − pop {population_growth_rate:+.2%})  |  "
                  f"+{n_new} new  |  total: {n_before} → {len(mkt_engine.households)}")

            if db_dir is not None:
                save_household_snapshot(mkt_engine.households, year, db_dir)

        history = engine.run_with_evolution(years, evolve_fn=_evolve_fn, ticks_per_year=12)

        # Persist the final evolved catalogue as the "current" goods DB
        if db_dir is not None:
            catalogue["db"].to_csv(db_dir / "goods_db.csv", index=False)
    else:
        history = engine.run(ticks)

    # ── Final summary ───────────────────────────────────────────────────────
    first = history.iloc[0]
    final = history.iloc[-1]
    total_inf = (final["cpi"] / 1.0 - 1) * 100
    gdp_growth = (final["gdp_real"] / first["gdp_real"] - 1) * 100 if first["gdp_real"] else 0

    print(f"\n── Results{' ['+label+']' if label else ''} ──────────────────────────────────")
    print(f"  Period 0 base GDP       : ${base_gdp:>14,.0f}")
    print(f"  Period 0 inflation      : {'0.000%':>14}")
    print(f"  Final CPI               : {final['cpi']:>14.4f}")
    print(f"  Total inflation         : {total_inf:>13.1f}%")
    print(f"  Final nominal GDP       : ${final['gdp_nominal']:>14,.0f}")
    print(f"  Final real GDP          : ${final['gdp_real']:>14,.0f}")
    print(f"  Real GDP growth (total) : {gdp_growth:>13.1f}%")
    print(f"  Final Gini              : {final['gini']:>14.4f}")
    print("─────────────────────────────────────────────────────────────\n")

    return history


def main():
    parser = argparse.ArgumentParser(description="Economics Simulation v2")
    parser.add_argument("--ticks",          type=int, default=120)
    parser.add_argument("--config",         default="config/simulation_config.xlsx")
    parser.add_argument("--db",             default="db/goods_db.csv")
    parser.add_argument("--out",            default="results/history.csv")
    parser.add_argument("--shock",          type=str, default=None,
                        help="div,type,magnitude,start_tick,duration")
    parser.add_argument("--compare-shock",  type=str, default=None,
                        help="Run baseline + shocked scenario and save both")
    parser.add_argument("--seed",           type=int, default=42)
    parser.add_argument("--no-evolution",   action="store_true",
                        help="Disable yearly product catalogue evolution (price drift + new products)")
    args = parser.parse_args()

    # Load goods DB
    db_path = Path(args.db)
    if not db_path.exists():
        raise FileNotFoundError(f"Run build_goods_db.py first. Not found: {db_path}")
    goods_db = pd.read_csv(db_path, dtype={"coicop_division": str, "coicop_code": str})
    print(f"Loaded goods DB: {len(goods_db)} goods, "
          f"base GDP = ${goods_db['gdp_contribution'].sum():,.0f}\n")

    cfg          = load_config(Path(args.config))
    producer_cfg = load_producer_config(Path(args.config))
    out_dir      = Path(args.out).parent
    out_dir.mkdir(parents=True, exist_ok=True)
    config_path  = Path(args.config)
    evolve       = not args.no_evolution

    if args.compare_shock:
        # Run baseline
        hist_base = run_once(goods_db, cfg, producer_cfg, [], args.ticks, args.seed, "baseline",
                             config_path=config_path, db_dir=db_path.parent / "baseline_db",
                             evolve=evolve)
        base_path = out_dir / "baseline.csv"
        hist_base.to_csv(base_path, index=False)
        print(f"Baseline saved → {base_path}")

        # Run with shock (re-load goods_db fresh so both runs start from the same catalogue)
        goods_db_shock = pd.read_csv(db_path, dtype={"coicop_division": str, "coicop_code": str})
        shock = parse_shock(args.compare_shock)
        hist_shock = run_once(goods_db_shock, cfg, producer_cfg, [shock], args.ticks, args.seed, "shock",
                              config_path=config_path, db_dir=db_path.parent / "shock_db",
                              evolve=evolve)
        shock_path = out_dir / "shock.csv"
        hist_shock.to_csv(shock_path, index=False)
        print(f"Shock run saved → {shock_path}")

    else:
        shocks = [parse_shock(args.shock)] if args.shock else []
        history = run_once(goods_db, cfg, producer_cfg, shocks, args.ticks, args.seed,
                           config_path=config_path, db_dir=db_path.parent, evolve=evolve)
        history.to_csv(args.out, index=False)
        print(f"Results saved → {args.out}")


if __name__ == "__main__":
    main()
