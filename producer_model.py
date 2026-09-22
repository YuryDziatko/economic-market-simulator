"""
producer_model.py  —  Firm types and market structures.

Firm taxonomy:
  ownership   : private | public
  size        : small | medium | large
  structure   : competitive | oligopoly | monopoly

Market share assignment per division:
  competitive  : many firms, roughly equal small shares (+ noise)
  oligopoly    : leader ~50%, 2-3 followers split rest
  monopoly     : single firm 100%

Total production per division matches that division's GDP share (P×Q).
"""
import random
from dataclasses import dataclass, field
from typing import List, Dict, Tuple
import pandas as pd

# Cost ratio (costs / revenue) — economies of scale
COST_RATIO = {
    ("small",  "private"): 0.86,
    ("medium", "private"): 0.78,
    ("large",  "private"): 0.70,
    ("small",  "public"):  0.90,   # public firms less efficient
    ("medium", "public"):  0.84,
    ("large",  "public"):  0.76,
}

# Base markup over cost — market power
MARKUP_BASE = {
    "competitive": 0.05,
    "oligopoly":   0.22,
    "monopoly":    0.45,
}

SIZE_MARKUP_ADJ = {"small": -0.02, "medium": 0.0, "large": 0.06}


@dataclass
class Firm:
    firm_id:          int
    division:         str
    ownership:        str    # 'private' | 'public'
    size:             str    # 'small' | 'medium' | 'large'
    market_structure: str    # 'competitive' | 'oligopoly' | 'monopoly'
    market_share:     float  # fraction of division GDP this firm produces
    div_gdp:          float  # division's total GDP contribution

    # Dynamic fields updated each tick
    revenue:          float = 0.0
    cost_ratio:       float = 0.80
    markup:           float = 0.15
    capacity_factor:  float = 1.0   # scales with profitability over time

    def __post_init__(self):
        self.cost_ratio = COST_RATIO.get((self.size, self.ownership), 0.80)
        self.markup     = (MARKUP_BASE.get(self.market_structure, 0.15)
                          + SIZE_MARKUP_ADJ.get(self.size, 0.0))
        self.revenue    = self.div_gdp * self.market_share

    @property
    def costs(self) -> float:
        return self.revenue * self.cost_ratio

    @property
    def profit(self) -> float:
        return self.revenue - self.costs

    @property
    def profit_margin(self) -> float:
        return self.profit / self.revenue if self.revenue > 0 else 0.0

    def price_adjustment(self, excess_demand: float) -> float:
        """How much this firm moves its effective price given excess demand."""
        sensitivity = {"competitive": 0.8, "oligopoly": 0.3, "monopoly": 0.1}
        return sensitivity.get(self.market_structure, 0.5) * excess_demand * 0.02

    def update_capacity(self):
        """Profitable firms expand; loss-making ones contract."""
        if self.profit_margin > 0.05:
            self.capacity_factor = min(2.0, self.capacity_factor * 1.005)
        elif self.profit_margin < 0:
            self.capacity_factor = max(0.5, self.capacity_factor * 0.998)


def _assign_shares_competitive(firms_in_div: list, rng: random.Random) -> list:
    """Roughly equal shares with small random variation."""
    n = len(firms_in_div)
    raw = [rng.uniform(0.7, 1.3) for _ in range(n)]
    # Larger firms get bigger shares
    size_weight = {"small": 0.8, "medium": 1.5, "large": 3.0}
    raw = [r * size_weight.get(f.size, 1.0) for r, f in zip(raw, firms_in_div)]
    total = sum(raw)
    return [r / total for r in raw]


def _assign_shares_oligopoly(firms_in_div: list, rng: random.Random) -> list:
    """Dominant leader gets ~50%, rest split remainder."""
    n = len(firms_in_div)
    if n == 0: return []
    if n == 1: return [1.0]
    # Sort: large first, then medium, then small
    order = {"large": 0, "medium": 1, "small": 2}
    firms_in_div.sort(key=lambda f: order.get(f.size, 1))
    leader_share = rng.uniform(0.45, 0.60)
    remaining = 1.0 - leader_share
    follower_shares = [rng.uniform(0.5, 1.5) for _ in range(n - 1)]
    total_f = sum(follower_shares)
    follower_shares = [s / total_f * remaining for s in follower_shares]
    return [leader_share] + follower_shares


def build_firms_for_division(
    division: str,
    div_gdp: float,
    market_structure: str,
    counts: Dict[Tuple[str,str], int],   # (size, ownership) -> count
    rng: random.Random,
    start_id: int = 0,
) -> List[Firm]:
    """Create all firms for one COICOP division."""
    firms = []
    fid = start_id
    for (size, ownership), n in counts.items():
        for _ in range(n):
            f = Firm(
                firm_id=fid, division=division, ownership=ownership,
                size=size, market_structure=market_structure,
                market_share=0.0, div_gdp=div_gdp,
            )
            firms.append(f)
            fid += 1

    if not firms:
        return []

    # Assign market shares
    if market_structure == "monopoly":
        shares = [1.0 / len(firms)] * len(firms)
    elif market_structure == "oligopoly":
        shares = _assign_shares_oligopoly(firms, rng)
    else:
        shares = _assign_shares_competitive(firms, rng)

    for f, s in zip(firms, shares):
        f.market_share = s
        f.revenue = div_gdp * s

    return firms


def build_all_firms(
    goods_db: pd.DataFrame,
    producer_config: pd.DataFrame,
    rng_seed: int = 42,
) -> List[Firm]:
    """Build the complete firm population from config and goods DB."""
    rng = random.Random(rng_seed)
    all_firms = []
    fid = 0

    # Division GDP contributions
    div_gdp = (goods_db.groupby("coicop_division")["gdp_contribution"].sum().to_dict())

    for _, row in producer_config.iterrows():
        div = str(row["coicop_division"]).strip().zfill(2)
        ms  = str(row["market_structure"]).strip().lower()
        gdp = div_gdp.get(div, 0.0)

        counts = {
            ("small",  "private"): int(row.get("priv_small",  0) or 0),
            ("medium", "private"): int(row.get("priv_medium", 0) or 0),
            ("large",  "private"): int(row.get("priv_large",  0) or 0),
            ("small",  "public"):  int(row.get("pub_small",   0) or 0),
            ("medium", "public"):  int(row.get("pub_medium",  0) or 0),
            ("large",  "public"):  int(row.get("pub_large",   0) or 0),
        }
        counts = {k: v for k, v in counts.items() if v > 0}

        firms = build_firms_for_division(div, gdp, ms, counts, rng, start_id=fid)
        all_firms.extend(firms)
        fid += len(firms)

    return all_firms


def print_producer_report(firms: List[Firm], goods_db: pd.DataFrame):
    div_gdp = goods_db.groupby("coicop_division")["gdp_contribution"].sum().to_dict()
    div_names = {"01":"Food","02":"Alcohol/Tobacco","03":"Clothing","04":"Housing",
                 "05":"Furnishings","06":"Health","07":"Transport","08":"Communication",
                 "09":"Recreation","10":"Education","11":"Restaurants","12":"Financial"}

    print("\n── Producer Market Structure ───────────────────────────────────────────────")
    print(f"  {'Div':<4} {'Name':<16} {'Structure':<13} {'Firms':>5} "
          f"{'Priv':>5} {'Pub':>4} {'Div GDP':>14} {'Avg Margin':>11}")
    print(f"  {'-'*80}")

    for div in sorted(set(f.division for f in firms)):
        div_firms = [f for f in firms if f.division == div]
        ms = div_firms[0].market_structure if div_firms else "?"
        n_priv = sum(1 for f in div_firms if f.ownership == "private")
        n_pub  = sum(1 for f in div_firms if f.ownership == "public")
        avg_margin = sum(f.profit_margin for f in div_firms) / len(div_firms) if div_firms else 0
        gdp = div_gdp.get(div, 0)
        name = div_names.get(div, div)
        print(f"  {div:<4} {name:<16} {ms:<13} {len(div_firms):>5} "
              f"{n_priv:>5} {n_pub:>4} ${gdp:>12,.0f} {avg_margin:>10.1%}")

    print(f"\n  Total firms: {len(firms)} "
          f"(private: {sum(1 for f in firms if f.ownership=='private')}, "
          f"public: {sum(1 for f in firms if f.ownership=='public')})")
    print("────────────────────────────────────────────────────────────────────────────\n")
