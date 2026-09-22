"""
agents.py — Economic agents: Household, Firm, Government
"""
import random
from dataclasses import dataclass, field
from typing import Dict


# COICOP division weights for CPI basket (approximate US weights)
COICOP_WEIGHTS: Dict[str, float] = {
    "01": 0.136,  # Food
    "02": 0.014,  # Alcohol & tobacco
    "03": 0.030,  # Clothing
    "04": 0.175,  # Housing & utilities
    "05": 0.055,  # Furnishings
    "06": 0.073,  # Health
    "07": 0.151,  # Transport
    "08": 0.035,  # Communication
    "09": 0.055,  # Recreation
    "10": 0.030,  # Education
    "11": 0.065,  # Restaurants & hotels
    "12": 0.035,  # Financial & insurance
}

# Price elasticity of demand per division (negative = normal good)
ELASTICITY: Dict[str, float] = {
    "01": -0.3,   # Food: inelastic
    "02": -0.5,
    "03": -0.8,
    "04": -0.2,   # Housing: very inelastic
    "05": -1.1,
    "06": -0.2,   # Health: inelastic
    "07": -0.6,
    "08": -0.7,
    "09": -1.3,   # Recreation: elastic
    "10": -0.4,
    "11": -0.9,
    "12": -0.5,
}


@dataclass
class Household:
    hh_id: int
    income: float          # monthly income USD
    savings: float = 0.0
    savings_rate: float = 0.10

    # spending budget per COICOP division (fraction of disposable income)
    basket: Dict[str, float] = field(default_factory=dict)

    def __post_init__(self):
        if not self.basket:
            self.basket = dict(COICOP_WEIGHTS)  # copy default weights

    @property
    def disposable_income(self) -> float:
        return self.income * (1 - self.savings_rate)

    def demand_for(self, division: str, price_index: float, base_price_index: float) -> float:
        """Quantity demanded adjusted for price change via elasticity."""
        base_spend = self.disposable_income * self.basket.get(division, 0.0)
        if base_price_index <= 0:
            return base_spend
        price_ratio = price_index / base_price_index
        elasticity = ELASTICITY.get(division, -0.5)
        qty_adjustment = 1 + elasticity * (price_ratio - 1)
        qty_adjustment = max(0.1, qty_adjustment)   # demand never goes to 0
        return base_spend * qty_adjustment

    def update_savings(self, total_spent: float):
        self.savings += self.income - total_spent


@dataclass
class Firm:
    firm_id: int
    division: str
    base_cost: float        # average production cost per unit
    markup: float = 0.25    # price = cost * (1 + markup)
    inventory: float = 100.0
    capacity: float = 120.0 # max units producible per tick

    @property
    def supply_price(self) -> float:
        return self.base_cost * (1 + self.markup)

    def produce(self, demand: float) -> float:
        """Produce up to capacity; return actual units supplied."""
        produced = min(demand, self.capacity)
        self.inventory = max(0, self.inventory + produced - demand)
        return produced

    def adjust_price(self, excess_demand: float):
        """Raise markup if demand exceeds supply, lower if surplus."""
        adjustment = 0.02 * (excess_demand / max(self.capacity, 1))
        self.markup = max(0.05, min(1.0, self.markup + adjustment))

    def adjust_capacity(self, profit_signal: float):
        """Expand capacity if profitable."""
        if profit_signal > 0:
            self.capacity *= 1.01
        else:
            self.capacity = max(10, self.capacity * 0.99)


@dataclass
class Government:
    tax_rate: float = 0.20
    subsidy_divisions: Dict[str, float] = field(default_factory=dict)  # div -> subsidy fraction
    price_caps: Dict[str, float] = field(default_factory=dict)          # div -> max price index
    money_supply_growth: float = 0.002  # per tick ~2.4% annual

    def apply_tax(self, income: float) -> float:
        return income * (1 - self.tax_rate)

    def apply_subsidy(self, division: str, cost: float) -> float:
        subsidy = self.subsidy_divisions.get(division, 0.0)
        return cost * (1 - subsidy)

    def enforce_price_cap(self, division: str, price: float) -> float:
        cap = self.price_caps.get(division)
        if cap is not None:
            return min(price, cap)
        return price


def build_households(n: int, income_mean: float = 5000, income_std: float = 2000) -> list:
    households = []
    for i in range(n):
        income = max(1000, random.gauss(income_mean, income_std))
        savings_rate = random.uniform(0.05, 0.20)
        hh = Household(hh_id=i, income=income, savings_rate=savings_rate)
        households.append(hh)
    return households


def build_firms(divisions: list) -> list:
    firms = []
    fid = 0
    for div in divisions:
        n_firms = random.randint(2, 5)
        for _ in range(n_firms):
            base_cost = random.uniform(10, 500)
            markup = random.uniform(0.10, 0.40)
            firm = Firm(firm_id=fid, division=div, base_cost=base_cost, markup=markup)
            firms.append(firm)
            fid += 1
    return firms
