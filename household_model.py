"""
household_model.py  —  v3: Household database with 5 income brackets.

Brackets (by income percentile): Low (0-40), Middle (40-80), High (80-99),
Top 1% (99-99.9), Top 0.1% (99.9-100). Ranges come from bracket_config sheet.

Each household carries:
  - income               (gross monthly)
  - labor_share / capital_share / transfer_share   (sum to 1.0 — where income comes from)
  - consumption_rate     (share of gross income spent; Low can exceed 1.0 = dissaving)
  - basket                (COICOP spending weights, tilted by bracket)

Every simulated year:
  - existing households' income grows by (GDP growth − population growth)
  - population_growth_rate %% of new households are added, split across
    brackets in the same proportion as the current population
"""

import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from scipy.stats import norm, lognorm


# ── COICOP basket weights (fraction of consumption spend per division) ────────
COICOP_WEIGHTS: Dict[str, float] = {
    "01": 0.136, "02": 0.014, "03": 0.030, "04": 0.175,
    "05": 0.055, "06": 0.073, "07": 0.151, "08": 0.035,
    "09": 0.055, "10": 0.030, "11": 0.065, "12": 0.035,
}

ELASTICITY: Dict[str, float] = {
    "01": -0.3, "02": -0.5, "03": -0.8, "04": -0.2,
    "05": -1.1, "06": -0.2, "07": -0.6, "08": -0.7,
    "09": -1.3, "10": -0.4, "11": -0.9, "12": -0.5,
}

BRACKET_ORDER  = ["low", "middle", "high", "top1", "top01"]
BRACKET_LABELS = {"low": "Low", "middle": "Middle", "high": "High",
                   "top1": "Top 1%", "top01": "Top 0.1%"}

# Fallback bracket config, used only if bracket_config sheet is missing/unreadable.
DEFAULT_BRACKET_CONFIG = {
    "low":    dict(pct_lower=0,    pct_upper=40,   labor=(0.25, 0.35), capital=(0.00, 0.02), transfer=(0.60, 0.70), consumption=(1.00, 1.15)),
    "middle": dict(pct_lower=40,   pct_upper=80,   labor=(0.75, 0.85), capital=(0.02, 0.05), transfer=(0.10, 0.20), consumption=(0.92, 0.97)),
    "high":   dict(pct_lower=80,   pct_upper=99,   labor=(0.80, 0.90), capital=(0.05, 0.15), transfer=(0.00, 0.05), consumption=(0.75, 0.85)),
    "top1":   dict(pct_lower=99,   pct_upper=99.9, labor=(0.35, 0.45), capital=(0.50, 0.60), transfer=(0.00, 0.01), consumption=(0.50, 0.65)),
    "top01":  dict(pct_lower=99.9, pct_upper=100,  labor=(0.15, 0.25), capital=(0.75, 0.85), transfer=(0.00, 0.01), consumption=(0.15, 0.35)),
}

# Spending-basket tilts by bracket (multiplies default COICOP weight, then renormalised)
BASKET_TILT = {
    "low":    {"01": 1.4, "04": 1.2, "09": 0.5, "12": 0.3},
    "middle": {},
    "high":   {"01": 0.7, "09": 1.5, "11": 1.4, "12": 1.6},
    "top1":   {"01": 0.4, "03": 1.4, "09": 1.8, "11": 1.6, "12": 2.5},
    "top01":  {"01": 0.2, "03": 1.8, "09": 2.2, "11": 1.8, "12": 3.5},
}


# ── Household ───────────────────────────────────────────────────────────────
@dataclass
class Household:
    hh_id:            int
    income:            float   # gross monthly income
    bracket:           str     # 'low' | 'middle' | 'high' | 'top1' | 'top01'
    labor_share:       float
    capital_share:     float
    transfer_share:    float
    consumption_rate:  float   # share of gross income spent (can exceed 1.0)
    basket:            Dict[str, float] = field(default_factory=dict)

    def __post_init__(self):
        if not self.basket:
            w = dict(COICOP_WEIGHTS)
            tilt = BASKET_TILT.get(self.bracket, {})
            for k, mult in tilt.items():
                w[k] = w.get(k, 0.0) * mult
            total = sum(w.values())
            self.basket = {k: v / total for k, v in w.items()}

    @property
    def total_spend(self) -> float:
        """Gross income × consumption_rate — total monthly spending."""
        return self.income * self.consumption_rate

    @property
    def savings_rate(self) -> float:
        return 1 - self.consumption_rate

    def demand_for(self, division: str, price_index: float, base_price_index: float = 1.0) -> float:
        base_spend = self.total_spend * self.basket.get(division, 0.0)
        if base_price_index <= 0:
            return base_spend
        ratio = price_index / base_price_index
        e = ELASTICITY.get(division, -0.5)
        adj = max(0.05, 1 + e * (ratio - 1))
        return base_spend * adj


# ── Config loaders ─────────────────────────────────────────────────────────────
def load_bracket_config(config_path: Path) -> dict:
    if not Path(config_path).exists():
        return dict(DEFAULT_BRACKET_CONFIG)
    try:
        df = pd.read_excel(config_path, sheet_name="bracket_config", header=1)
    except Exception:
        return dict(DEFAULT_BRACKET_CONFIG)

    name_map = {"low": "low", "middle": "middle", "high": "high",
                "top1": "top1", "top01": "top01"}
    cfg = {}
    for _, r in df.iterrows():
        raw = str(r.get("bracket", "")).strip().lower()
        key = name_map.get(raw)
        if key is None:
            continue
        try:
            cfg[key] = dict(
                pct_lower=float(r["pct_lower"]), pct_upper=float(r["pct_upper"]),
                labor=(float(r["labor_min"]), float(r["labor_max"])),
                capital=(float(r["capital_min"]), float(r["capital_max"])),
                transfer=(float(r["transfer_min"]), float(r["transfer_max"])),
                consumption=(float(r["consumption_min"]), float(r["consumption_max"])),
            )
        except Exception:
            continue
    for b in BRACKET_ORDER:
        cfg.setdefault(b, DEFAULT_BRACKET_CONFIG[b])
    return cfg


def load_population_growth_rate(config_path: Path) -> float:
    if not Path(config_path).exists():
        return 0.01
    try:
        df = pd.read_excel(config_path, sheet_name="household_config", header=1)
        row = df[df["parameter"].astype(str).str.strip() == "population_growth_rate"]
        if len(row):
            return float(row.iloc[0]["value"])
    except Exception:
        pass
    return 0.01


# ── Gini → log-normal helpers ────────────────────────────────────────────────
def gini_to_sigma(gini: float) -> float:
    return float(np.sqrt(2) * norm.ppf((gini + 1) / 2))


def lognormal_conditional_mean(mu_ln: float, sigma: float, lo: float, hi: float) -> float:
    mu2 = mu_ln + sigma ** 2
    inf = 1e18
    lo_safe = lo if lo > 0 else 1e-9
    if hi >= inf:
        num = norm.sf((np.log(lo_safe) - mu2) / sigma)
        den = norm.sf((np.log(lo_safe) - mu_ln) / sigma)
    else:
        num = (norm.cdf((np.log(hi) - mu2) / sigma) - norm.cdf((np.log(lo_safe) - mu2) / sigma))
        den = (norm.cdf((np.log(hi) - mu_ln) / sigma) - norm.cdf((np.log(lo_safe) - mu_ln) / sigma))
    return float(np.exp(mu_ln + sigma ** 2 / 2) * num / max(den, 1e-12))


# ── Derive the 5-bracket income distribution from Gini + GDP ──────────────────
def derive_household_classes(
    gini: float,
    total_households: int,
    base_gdp: float,
    consumption_share: float,
    savings_rate: float,
    bracket_config: dict,
    rng_seed: int = 42,
) -> dict:
    total_consumption   = base_gdp * consumption_share
    total_income        = total_consumption / (1 - savings_rate)
    avg_monthly_income  = (total_income / total_households) / 12

    sigma = gini_to_sigma(gini)
    mu_ln = np.log(avg_monthly_income) - sigma ** 2 / 2
    dist  = lognorm(s=sigma, scale=np.exp(mu_ln))

    cuts_pct = [0,
                bracket_config["low"]["pct_upper"],
                bracket_config["middle"]["pct_upper"],
                bracket_config["high"]["pct_upper"],
                bracket_config["top1"]["pct_upper"],
                100]
    thresholds = [0.0] + [float(dist.ppf(min(p, 99.999) / 100)) for p in cuts_pct[1:-1]] + [1e18]

    counts = {}
    for i, b in enumerate(BRACKET_ORDER):
        pct_share = (cuts_pct[i + 1] - cuts_pct[i]) / 100
        counts[b] = round(total_households * pct_share)
    diff = total_households - sum(counts.values())
    counts["low"] += diff   # absorb rounding remainder into the largest bucket

    rng = np.random.default_rng(rng_seed)
    incomes_by_bracket = {}
    for i, b in enumerate(BRACKET_ORDER):
        lo, hi = thresholds[i], thresholds[i + 1]
        n_b = counts[b]
        if n_b <= 0:
            incomes_by_bracket[b] = np.array([])
            continue
        mult = 10 if b in ("top1", "top01") else 5
        samp = rng.lognormal(mu_ln, sigma, n_b * mult)
        samp = samp[samp > lo]
        if hi < 1e18:
            samp = samp[samp <= hi]
        samp = np.sort(samp)[:n_b]
        if len(samp) < n_b:
            mean_b = lognormal_conditional_mean(mu_ln, sigma, lo, hi)
            extra  = rng.lognormal(np.log(max(mean_b, 1)), sigma * 0.1, n_b - len(samp))
            samp   = np.concatenate([samp, extra])
        incomes_by_bracket[b] = samp[:n_b]

    total_sampled = sum(arr.sum() for arr in incomes_by_bracket.values())
    classes = {}
    for i, b in enumerate(BRACKET_ORDER):
        arr = incomes_by_bracket[b]
        lo, hi = thresholds[i], thresholds[i + 1]
        classes[b] = {
            "count":                 counts[b],
            "avg_income":            round(float(arr.mean()), 2) if len(arr) else 0.0,
            "income_range":          (round(lo, 2), None if hi >= 1e18 else round(hi, 2)),
            "share_of_total_income": round(float(arr.sum()) / total_sampled * 100, 2) if total_sampled > 0 else 0.0,
        }

    return {
        "gini": gini, "sigma": round(sigma, 4), "base_gdp": round(base_gdp, 2),
        "total_income": round(total_income, 2), "avg_monthly_income": round(avg_monthly_income, 2),
        "classes": classes, "incomes_by_class": incomes_by_bracket,
    }


def build_households(hh_stats: dict, bracket_config: dict, rng_seed: int = 42) -> List[Household]:
    rng = random.Random(rng_seed)
    households = []
    hh_id = 0
    for b, incomes in hh_stats["incomes_by_class"].items():
        cfg = bracket_config[b]
        for income in incomes:
            labor    = rng.uniform(*cfg["labor"])
            capital  = rng.uniform(*cfg["capital"])
            transfer = rng.uniform(*cfg["transfer"])
            tot = labor + capital + transfer
            labor, capital, transfer = labor / tot, capital / tot, transfer / tot
            consumption = rng.uniform(*cfg["consumption"])
            households.append(Household(
                hh_id=hh_id, income=float(income), bracket=b,
                labor_share=labor, capital_share=capital, transfer_share=transfer,
                consumption_rate=consumption,
            ))
            hh_id += 1
    return households


# ── Annual evolution: income growth + population growth ───────────────────────
def evolve_households(
    households: List[Household],
    gdp_growth_rate: float,
    population_growth_rate: float,
    bracket_config: dict,
    rng: random.Random,
) -> Tuple[List[Household], int, float]:
    """
    Mutates incomes in place, appends new households, returns
    (households, n_new_households, income_growth_rate_applied).
    """
    income_growth = gdp_growth_rate - population_growth_rate
    for hh in households:
        hh.income = max(1.0, hh.income * (1 + income_growth))

    total_now = len(households)
    n_new = max(0, round(total_now * population_growth_rate))
    if n_new == 0:
        return households, 0, income_growth

    bracket_counts = {b: sum(1 for h in households if h.bracket == b) for b in BRACKET_ORDER}
    bracket_avg    = {
        b: (sum(h.income for h in households if h.bracket == b) / bracket_counts[b]
            if bracket_counts[b] else 1000.0)
        for b in BRACKET_ORDER
    }
    next_id  = max((h.hh_id for h in households), default=-1) + 1
    remaining = n_new
    new_hh   = []

    for i, b in enumerate(BRACKET_ORDER):
        share = bracket_counts[b] / total_now if total_now else 1 / len(BRACKET_ORDER)
        n_b = remaining if i == len(BRACKET_ORDER) - 1 else min(remaining, round(n_new * share))
        remaining -= n_b
        cfg = bracket_config[b]
        avg_income = bracket_avg[b]
        for _ in range(n_b):
            income   = max(100.0, rng.gauss(avg_income, avg_income * 0.15))
            labor    = rng.uniform(*cfg["labor"])
            capital  = rng.uniform(*cfg["capital"])
            transfer = rng.uniform(*cfg["transfer"])
            tot = labor + capital + transfer
            labor, capital, transfer = labor / tot, capital / tot, transfer / tot
            consumption = rng.uniform(*cfg["consumption"])
            new_hh.append(Household(
                hh_id=next_id, income=income, bracket=b,
                labor_share=labor, capital_share=capital, transfer_share=transfer,
                consumption_rate=consumption,
            ))
            next_id += 1

    households.extend(new_hh)
    return households, len(new_hh), income_growth


# ── Reporting & export ─────────────────────────────────────────────────────────
def households_to_dataframe(households: List[Household]) -> pd.DataFrame:
    rows = []
    for h in households:
        rows.append({
            "hh_id":            h.hh_id,
            "bracket":          BRACKET_LABELS.get(h.bracket, h.bracket),
            "income_monthly":   round(h.income, 2),
            "labor_share":      round(h.labor_share, 4),
            "capital_share":    round(h.capital_share, 4),
            "transfer_share":   round(h.transfer_share, 4),
            "consumption_rate": round(h.consumption_rate, 4),
            "savings_rate":     round(h.savings_rate, 4),
        })
    return pd.DataFrame(rows)


def save_household_snapshot(households: List[Household], year, out_dir: Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    df = households_to_dataframe(households)
    label = "households.csv" if year == 0 else f"households_year_{year:02d}.csv"
    path = out_dir / label
    df.to_csv(path, index=False)
    return path


def print_household_report(households: List[Household], gini: float):
    total_income = sum(h.income for h in households)
    n = len(households)
    print("\n── Household Database ───────────────────────────────────────────────────────────────")
    print(f"  Gini coefficient   : {gini:.3f}")
    print(f"  Total households   : {n:,}")
    print(f"  Avg monthly income : ${total_income / max(n,1):,.0f}")
    print()
    header = (f"  {'Bracket':<10}{'Count':>8}  {'Avg Income':>13}  {'Inc.Share':>10}  "
              f"{'Labor%':>7}  {'Capital%':>9}  {'Transfer%':>10}  {'Spend%':>7}")
    print(header)
    print("  " + "-" * (len(header) - 2))
    for b in BRACKET_ORDER:
        grp = [h for h in households if h.bracket == b]
        if not grp:
            continue
        nb = len(grp)
        avg_inc  = sum(h.income for h in grp) / nb
        share    = sum(h.income for h in grp) / total_income * 100 if total_income else 0
        avg_lab  = sum(h.labor_share for h in grp) / nb * 100
        avg_cap  = sum(h.capital_share for h in grp) / nb * 100
        avg_tra  = sum(h.transfer_share for h in grp) / nb * 100
        avg_cons = sum(h.consumption_rate for h in grp) / nb * 100
        print(f"  {BRACKET_LABELS[b]:<10}{nb:>8,}  ${avg_inc:>11,.0f}  {share:>9.1f}%  "
              f"{avg_lab:>6.1f}%  {avg_cap:>8.1f}%  {avg_tra:>9.1f}%  {avg_cons:>6.1f}%")
    print("────────────────────────────────────────────────────────────────────────────────────\n")
