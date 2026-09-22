"""
producer_model.py — Firms and market structures for the V3 market engine.

The V3 model treats each COICOP division as a market measured in real-output
units. One base-period real-output unit has a price index of 1.0. Firms carry
physical/economic state (capacity, inventory, production, sales and unmet
orders) instead of having supply mechanically set equal to demand.
"""
import random
from dataclasses import dataclass
from typing import List, Dict, Tuple
import pandas as pd

COST_RATIO = {
    ("small",  "private"): 0.86,
    ("medium", "private"): 0.78,
    ("large",  "private"): 0.70,
    ("small",  "public"):  0.90,
    ("medium", "public"):  0.84,
    ("large",  "public"):  0.76,
}

MARKUP_BASE = {
    "competitive": 0.05,
    "oligopoly":   0.22,
    "duopoly":     0.30,
    "monopoly":    0.45,
}
SIZE_MARKUP_ADJ = {"small": -0.02, "medium": 0.0, "large": 0.06}


@dataclass
class Firm:
    firm_id:          int
    division:         str
    ownership:        str
    size:             str
    market_structure: str
    market_share:     float
    div_gdp:          float

    # Structural parameters
    cost_ratio:       float = 0.80
    markup:           float = 0.15

    # V3 operating state (monthly, real-output units unless noted)
    production_capacity: float = 0.0
    inventory:            float = 0.0
    target_inventory:     float = 0.0
    expected_demand:      float = 0.0
    production:           float = 0.0
    units_demanded:       float = 0.0
    units_sold:           float = 0.0
    unmet_demand:         float = 0.0

    # Financial state (nominal dollars per month)
    revenue:          float = 0.0
    total_cost:       float = 0.0
    profit:           float = 0.0
    investment:       float = 0.0
    utilization:      float = 0.0

    def __post_init__(self):
        self.cost_ratio = COST_RATIO.get((self.size, self.ownership), 0.80)
        self.markup = max(0.0, MARKUP_BASE.get(self.market_structure, 0.15)
                          + SIZE_MARKUP_ADJ.get(self.size, 0.0))

    @property
    def profit_margin(self) -> float:
        return self.profit / self.revenue if self.revenue > 0 else 0.0

    def initialize_market_state(self, monthly_division_demand: float,
                                inventory_months: float = 0.10,
                                capacity_buffer: float = 0.05) -> None:
        """Calibrate firm capacity/inventory to the base-period household market."""
        base_orders = max(0.0, monthly_division_demand * self.market_share)
        self.expected_demand = base_orders
        self.target_inventory = base_orders * inventory_months
        self.inventory = self.target_inventory
        self.production_capacity = max(1e-9, base_orders * (1.0 + capacity_buffer))
        self.production = 0.0
        self.units_demanded = base_orders
        self.units_sold = base_orders
        self.unmet_demand = 0.0
        self.revenue = base_orders
        self.total_cost = self.revenue * self.cost_ratio
        self.profit = self.revenue - self.total_cost

    def plan_and_produce(self, supply_factor: float = 1.0) -> None:
        """Produce from lagged expected demand; current-period demand is not known yet."""
        desired = max(0.0, self.expected_demand + self.target_inventory - self.inventory)
        effective_capacity = max(0.0, self.production_capacity * max(0.0, supply_factor))
        self.production = min(desired, effective_capacity)
        self.utilization = self.production / max(self.production_capacity, 1e-9)
        self.inventory += self.production

    def fulfill_orders(self, units_demanded: float) -> None:
        self.units_demanded = max(0.0, units_demanded)
        self.units_sold = min(self.units_demanded, self.inventory)
        self.unmet_demand = max(0.0, self.units_demanded - self.units_sold)
        self.inventory = max(0.0, self.inventory - self.units_sold)

    def close_period(self, division_price_index: float, cost_factor: float = 1.0) -> None:
        """Calculate financial results, update forecast, and make a modest capacity decision."""
        price = max(0.01, division_price_index)
        self.revenue = self.units_sold * price
        unit_cost = max(0.01, self.cost_ratio * max(0.05, cost_factor))
        variable_cost = self.production * unit_cost
        # Small fixed operating cost keeps idle capacity from being free.
        fixed_cost = self.production_capacity * self.cost_ratio * 0.01
        self.total_cost = variable_cost + fixed_cost
        self.profit = self.revenue - self.total_cost

        # Adaptive expectations: orders matter even if stockouts prevented sales.
        self.expected_demand = 0.70 * self.units_demanded + 0.30 * self.expected_demand

        self.investment = 0.0
        if self.profit > 0:
            if self.utilization >= 0.90 or self.unmet_demand > 0:
                invest_rate = 0.30
            elif self.utilization >= 0.75:
                invest_rate = 0.12
            else:
                invest_rate = 0.03
            self.investment = self.profit * invest_rate

            # Capacity is expensive: roughly 24 months of base unit-cost per added
            # monthly unit of capacity. This prevents explosive capacity growth.
            capacity_cost_per_unit = max(1.0, 24.0 * self.cost_ratio)
            self.production_capacity += self.investment / capacity_cost_per_unit
        elif self.profit < 0 and self.utilization < 0.55:
            # Persistent slack/losses slowly retire capacity.
            self.production_capacity *= 0.997

        # Inventory target follows expected demand gradually.
        desired_target = 0.10 * self.expected_demand
        self.target_inventory = 0.85 * self.target_inventory + 0.15 * desired_target


def _assign_shares_competitive(firms_in_div: list, rng: random.Random) -> list:
    n = len(firms_in_div)
    raw = [rng.uniform(0.7, 1.3) for _ in range(n)]
    size_weight = {"small": 0.8, "medium": 1.5, "large": 3.0}
    raw = [r * size_weight.get(f.size, 1.0) for r, f in zip(raw, firms_in_div)]
    total = sum(raw)
    return [r / total for r in raw]


def _assign_shares_oligopoly(firms_in_div: list, rng: random.Random) -> list:
    n = len(firms_in_div)
    if n == 0:
        return []
    if n == 1:
        return [1.0]
    order = {"large": 0, "medium": 1, "small": 2}
    firms_in_div.sort(key=lambda f: order.get(f.size, 1))
    leader_share = rng.uniform(0.45, 0.60)
    remaining = 1.0 - leader_share
    follower_shares = [rng.uniform(0.5, 1.5) for _ in range(n - 1)]
    total_f = sum(follower_shares)
    return [leader_share] + [s / total_f * remaining for s in follower_shares]


def build_firms_for_division(
    division: str,
    div_gdp: float,
    market_structure: str,
    counts: Dict[Tuple[str, str], int],
    rng: random.Random,
    start_id: int = 0,
) -> List[Firm]:
    firms = []
    fid = start_id
    for (size, ownership), n in counts.items():
        for _ in range(n):
            firms.append(Firm(
                firm_id=fid, division=division, ownership=ownership,
                size=size, market_structure=market_structure,
                market_share=0.0, div_gdp=div_gdp,
            ))
            fid += 1

    if not firms:
        return []

    if market_structure == "monopoly":
        if len(firms) != 1:
            # A market with two firms is a duopoly, not a monopoly. Preserve the
            # configured firms but label it correctly and allocate sensible shares.
            market_structure = "duopoly" if len(firms) == 2 else "oligopoly"
            for f in firms:
                f.market_structure = market_structure
            shares = _assign_shares_oligopoly(firms, rng)
        else:
            shares = [1.0]
    elif market_structure in ("oligopoly", "duopoly"):
        shares = _assign_shares_oligopoly(firms, rng)
    else:
        shares = _assign_shares_competitive(firms, rng)

    for f, s in zip(firms, shares):
        f.market_share = s
    return firms


def build_all_firms(goods_db: pd.DataFrame, producer_config: pd.DataFrame,
                    rng_seed: int = 42) -> List[Firm]:
    rng = random.Random(rng_seed)
    all_firms = []
    fid = 0
    div_gdp = goods_db.groupby("coicop_division")["gdp_contribution"].sum().to_dict()

    for _, row in producer_config.iterrows():
        div = str(row["coicop_division"]).strip().zfill(2)
        ms = str(row["market_structure"]).strip().lower()
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
    print(f"  {'Div':<4} {'Name':<16} {'Structure':<13} {'Firms':>5} {'Priv':>5} {'Pub':>4} {'Div GDP':>14}")
    print(f"  {'-'*72}")
    for div in sorted(set(f.division for f in firms)):
        div_firms = [f for f in firms if f.division == div]
        ms = div_firms[0].market_structure if div_firms else "?"
        n_priv = sum(1 for f in div_firms if f.ownership == "private")
        n_pub = sum(1 for f in div_firms if f.ownership == "public")
        gdp = div_gdp.get(div, 0)
        print(f"  {div:<4} {div_names.get(div,div):<16} {ms:<13} {len(div_firms):>5} "
              f"{n_priv:>5} {n_pub:>4} ${gdp:>12,.0f}")
    print(f"\n  Total firms: {len(firms)} (private: {sum(f.ownership=='private' for f in firms)}, "
          f"public: {sum(f.ownership=='public' for f in firms)})")
    print("────────────────────────────────────────────────────────────────────────────\n")
