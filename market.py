"""
market.py — V3 supply-demand market engine.

Each COICOP division is a market in real-output units. Households form nominal
spending budgets, which are converted into desired quantities by dividing by
the current division price index. Firms produce from lagged expectations,
carry inventory, face capacity constraints, fulfill orders, and can create
shortages. Prices respond to shortages, excess inventories, monetary growth,
and cost shocks.
"""
from dataclasses import dataclass
from typing import Dict, List
import pandas as pd
from household_model import Household, COICOP_WEIGHTS
from producer_model import Firm


@dataclass
class EconomicState:
    tick: int
    price_index: Dict[str, float]
    cpi: float
    inflation_yoy: float
    gdp_nominal: float
    gdp_real: float
    total_consumption: float
    total_investment: float
    total_gov_spend: float
    gini: float
    total_shortage_rate: float = 0.0


class Shock:
    def __init__(self, division: str, shock_type: str,
                 magnitude: float, start_tick: int, duration: int):
        self.division = division
        self.shock_type = shock_type
        self.magnitude = magnitude
        self.start_tick = start_tick
        self.duration = duration

    def is_active(self, tick: int) -> bool:
        return self.start_tick <= tick < self.start_tick + self.duration


class MarketEngine:
    def __init__(self, households: List[Household], firms: List[Firm],
                 goods_db: pd.DataFrame, tax_rate: float = 0.22,
                 money_growth: float = 0.002,
                 inflation_target_annual: float = 0.02,
                 productivity_growth_annual: float = 0.015,
                 capital_productivity_multiplier: float = 1.50,
                 subsidy_divs: Dict[str, float] = None,
                 price_caps: Dict[str, float] = None):
        self.households = households
        self.firms = firms
        self.goods_db = goods_db
        self.tax_rate = tax_rate
        self.money_growth = money_growth
        self.inflation_target_annual = inflation_target_annual
        self.productivity_growth_annual = productivity_growth_annual
        self.capital_productivity_multiplier = capital_productivity_multiplier
        self.inflation_target_monthly = (1.0 + inflation_target_annual) ** (1.0 / 12.0) - 1.0
        self.productivity_growth_monthly = (1.0 + productivity_growth_annual) ** (1.0 / 12.0) - 1.0
        self.subsidy_divs = subsidy_divs or {"01": 0.05, "06": 0.10}
        self.price_caps = price_caps or {}
        self.shocks: List[Shock] = []

        self.divisions = sorted(goods_db["coicop_division"].unique())
        self.base_div_gdp = goods_db.groupby("coicop_division")["gdp_contribution"].sum().to_dict()
        self.base_gdp_annual = sum(self.base_div_gdp.values())
        self.price_index = {d: 1.0 for d in self.divisions}
        self._cpi_history = [1.0]

        # Base household demand is monthly nominal spending at P=1.0; because
        # price=1 in the base period, it is also the real-output quantity.
        self._base_demand = {
            d: sum(hh.demand_for(d, 1.0, 1.0) for hh in self.households)
            for d in self.divisions
        }

        # Initialize every firm to a balanced base market. Supply is not forced
        # to equal demand after this point; it emerges from capacity/inventory.
        for div in self.divisions:
            div_firms = [f for f in self.firms if f.division == div]
            for f in div_firms:
                f.initialize_market_state(self._base_demand.get(div, 0.0))

    def add_shock(self, shock: Shock):
        self.shocks.append(shock)

    def _active_shocks(self, tick: int) -> List[Shock]:
        return [s for s in self.shocks if s.is_active(tick)]

    def _shock_multiplier(self, division: str, shock_type: str, tick: int) -> float:
        m = 1.0
        for s in self._active_shocks(tick):
            if s.division == division and s.shock_type == shock_type:
                m *= max(0.0, 1.0 + s.magnitude)
        return m

    def rebase_division(self, division: str, new_div_gdp: float, price_shift: float):
        """Update catalogue reference values without mechanically creating supply."""
        self.base_div_gdp[division] = new_div_gdp
        if division in self.price_index:
            shift = max(-0.20, min(0.20, price_shift))
            self.price_index[division] = max(0.3, self.price_index[division] * (1 + shift))
        for f in self.firms:
            if f.division == division:
                f.div_gdp = new_div_gdp

    # ── Demand ──────────────────────────────────────────────────────────────
    def _quantity_demand(self, division: str, tick: int) -> float:
        # Household.demand_for returns desired real quantity. Price elasticity
        # is already applied there, so do not divide by price a second time.
        quantity = sum(hh.demand_for(division, self.price_index[division], 1.0)
                       for hh in self.households)
        return quantity * self._shock_multiplier(division, "demand", tick)

    # ── Firms / market clearing ─────────────────────────────────────────────
    def _operate_firms(self, tick: int) -> Dict[str, dict]:
        market_stats = {}
        for div in self.divisions:
            div_firms = [f for f in self.firms if f.division == div]
            if not div_firms:
                continue

            supply_factor = self._shock_multiplier(div, "supply", tick)
            cost_factor = self._shock_multiplier(div, "cost", tick)

            # Productivity improves effective capacity and lowers unit costs over time.
            # Firms still produce before observing current-period household demand.
            for f in div_firms:
                f.advance_productivity(self.productivity_growth_monthly)
                f.plan_and_produce(supply_factor=supply_factor)

            total_demand = self._quantity_demand(div, tick)

            # V3.0 keeps configured market shares as order-allocation weights.
            # V3.1 can replace this with endogenous price/quality choice.
            share_sum = sum(max(0.0, f.market_share) for f in div_firms) or 1.0
            for f in div_firms:
                firm_orders = total_demand * max(0.0, f.market_share) / share_sum
                f.fulfill_orders(firm_orders)
                f.close_period(self.price_index[div], cost_factor=cost_factor)

            demanded = sum(f.units_demanded for f in div_firms)
            sold = sum(f.units_sold for f in div_firms)
            unmet = sum(f.unmet_demand for f in div_firms)
            inventory = sum(f.inventory for f in div_firms)
            target_inventory = sum(f.target_inventory for f in div_firms)
            production = sum(f.production for f in div_firms)
            capacity = sum(f.production_capacity for f in div_firms)
            revenue = sum(f.revenue for f in div_firms)
            investment = sum(f.investment for f in div_firms)

            market_stats[div] = {
                "demand": demanded,
                "sold": sold,
                "unmet": unmet,
                "inventory": inventory,
                "target_inventory": target_inventory,
                "production": production,
                "capacity": capacity,
                "revenue": revenue,
                "investment": investment,
            }
        return market_stats

    # ── Price formation ────────────────────────────────────────────────────
    def _update_prices_from_market(self, tick: int, stats: Dict[str, dict]):
        for div, s in stats.items():
            div_firms = [f for f in self.firms if f.division == div]
            structure = div_firms[0].market_structure if div_firms else "competitive"

            shortage_rate = s["unmet"] / max(s["demand"], 1e-9)
            inventory_gap = ((s["inventory"] - s["target_inventory"])
                             / max(s["target_inventory"], 1e-9))
            inventory_gap = max(-2.0, min(3.0, inventory_gap))

            # Competitive markets react relatively quickly to imbalances;
            # concentrated markets are somewhat stickier in this V3 version.
            shortage_sensitivity = {
                "competitive": 0.08, "oligopoly": 0.06,
                "duopoly": 0.055, "monopoly": 0.04,
            }.get(structure, 0.06)
            inventory_sensitivity = 0.025

            # Cost shocks pass through gradually to consumer prices.
            cost_factor = self._shock_multiplier(div, "cost", tick)
            cost_inflation = cost_factor - 1.0
            cost_pass = 0.30 * cost_inflation

            subsidy = self.subsidy_divs.get(div, 0.0)
            delta = (shortage_sensitivity * shortage_rate
                     - inventory_sensitivity * max(0.0, inventory_gap)
                     + self.inflation_target_monthly
                     + cost_pass
                     - subsidy * 0.002)
            delta = max(-0.05, min(0.05, delta))

            new_idx = self.price_index[div] * (1.0 + delta)
            cap = self.price_caps.get(div)
            if cap is not None:
                new_idx = min(new_idx, cap)
            self.price_index[div] = max(0.3, new_idx)

    def _compute_cpi(self) -> float:
        w_total = sum(COICOP_WEIGHTS.get(d, 0.0) for d in self.divisions)
        return sum(self.price_index[d] * COICOP_WEIGHTS.get(d, 0.0)
                   for d in self.divisions) / max(w_total, 1e-9)

    def _compute_gini(self) -> float:
        incomes = sorted(max(0.0, hh.income) for hh in self.households)
        n = len(incomes)
        total = sum(incomes)
        if n == 0 or total <= 0:
            return 0.0
        weighted = sum((2 * (i + 1) - n - 1) * y for i, y in enumerate(incomes))
        return weighted / (n * total)

    def _update_household_incomes(self) -> None:
        """Grow income by source, linking real wage growth to productivity.

        Labor income: inflation target + productivity growth.
        Transfers: indexed to inflation target.
        Capital income: inflation target + a larger productivity-linked return.
        The household's fixed source shares determine its blended growth rate.
        """
        labor_annual = self.inflation_target_annual + self.productivity_growth_annual
        transfer_annual = self.inflation_target_annual
        capital_annual = (self.inflation_target_annual
                          + self.productivity_growth_annual * self.capital_productivity_multiplier)

        labor_m = (1.0 + labor_annual) ** (1.0 / 12.0) - 1.0
        transfer_m = (1.0 + transfer_annual) ** (1.0 / 12.0) - 1.0
        capital_m = (1.0 + capital_annual) ** (1.0 / 12.0) - 1.0

        for hh in self.households:
            growth = (hh.labor_share * labor_m
                      + hh.capital_share * capital_m
                      + hh.transfer_share * transfer_m)
            hh.income *= (1.0 + growth)

    def tick(self, t: int) -> EconomicState:
        # Income growth occurs before households form current demand.
        self._update_household_incomes()

        stats = self._operate_firms(t)

        # GDP uses actual transactions, not desired demand.
        C = sum(s["revenue"] for s in stats.values())
        I = sum(s["investment"] for s in stats.values())
        G = sum(hh.income for hh in self.households) * self.tax_rate
        gdp_nominal = C + I + G

        # Prices adjust after observing this month's shortages/inventories.
        self._update_prices_from_market(t, stats)
        cpi = self._compute_cpi()
        gdp_real = gdp_nominal / max(cpi, 1e-9)

        self._cpi_history.append(cpi)
        if len(self._cpi_history) >= 13:
            inf_yoy = (cpi / self._cpi_history[-13] - 1) * 100
        else:
            inf_yoy = 0.0

        total_demand = sum(s["demand"] for s in stats.values())
        total_unmet = sum(s["unmet"] for s in stats.values())
        shortage_rate = total_unmet / max(total_demand, 1e-9)

        return EconomicState(
            tick=t, price_index=dict(self.price_index), cpi=cpi,
            inflation_yoy=inf_yoy, gdp_nominal=gdp_nominal,
            gdp_real=gdp_real, total_consumption=C,
            total_investment=I, total_gov_spend=G,
            gini=self._compute_gini(), total_shortage_rate=shortage_rate,
        )

    def _state_row(self, state: EconomicState) -> dict:
        row = {
            "tick": state.tick,
            "year": round(state.tick / 12, 3),
            "cpi": round(state.cpi, 5),
            "inflation_yoy": round(state.inflation_yoy, 3),
            "gdp_nominal": round(state.gdp_nominal, 2),
            "gdp_real": round(state.gdp_real, 2),
            "gdp_nominal_annualized": round(state.gdp_nominal * 12, 2),
            "gdp_real_annualized": round(state.gdp_real * 12, 2),
            "consumption": round(state.total_consumption, 2),
            "investment": round(state.total_investment, 2),
            "gov_spend": round(state.total_gov_spend, 2),
            "gini": round(state.gini, 5),
            "shortage_rate": round(state.total_shortage_rate, 5),
        }
        for d in self.divisions:
            row[f"price_{d}"] = round(state.price_index[d], 5)
            fs = [f for f in self.firms if f.division == d]
            demand = sum(f.units_demanded for f in fs)
            sold = sum(f.units_sold for f in fs)
            inventory = sum(f.inventory for f in fs)
            capacity = sum(f.effective_capacity for f in fs)
            production = sum(f.production for f in fs)
            row[f"demand_{d}"] = round(demand, 2)
            row[f"sales_{d}"] = round(sold, 2)
            row[f"inventory_{d}"] = round(inventory, 2)
            row[f"capacity_{d}"] = round(capacity, 2)
            row[f"production_{d}"] = round(production, 2)
        return row

    def run(self, ticks: int) -> pd.DataFrame:
        rows = []
        for t in range(1, ticks + 1):
            state = self.tick(t)
            rows.append(self._state_row(state))
            if t % 12 == 0:
                print(f"  Year {t//12:>2}  CPI={state.cpi:.4f}  "
                      f"Inf={state.inflation_yoy:+.1f}%  "
                      f"GDP_ann=${state.gdp_nominal*12:>11,.0f}  "
                      f"Shortage={state.total_shortage_rate:.2%}  "
                      f"Gini={state.gini:.3f}")
        return pd.DataFrame(rows)

    def run_with_evolution(self, total_ticks: int, evolve_fn, ticks_per_year: int = 12) -> pd.DataFrame:
        """Run an exact number of ticks and apply annual updates after each full year."""
        rows = []
        prev_year_gdp_real = None
        for t in range(1, total_ticks + 1):
            state = self.tick(t)
            row = self._state_row(state)
            row["households"] = len(self.households)
            rows.append(row)

            if t % ticks_per_year == 0:
                year = t // ticks_per_year
                annual_real = state.gdp_real * 12
                gdp_growth_rate = 0.0
                if prev_year_gdp_real:
                    gdp_growth_rate = annual_real / prev_year_gdp_real - 1
                prev_year_gdp_real = annual_real

                avg_income = sum(h.income for h in self.households) / max(len(self.households), 1)
                avg_prod = sum(f.productivity_index for f in self.firms) / max(len(self.firms), 1)
                print(f"  Year {year:>2}  CPI={state.cpi:.4f}  "
                      f"Inf={state.inflation_yoy:+.1f}%  "
                      f"GDP_ann=${state.gdp_nominal*12:>11,.0f}  "
                      f"GDP_growth={gdp_growth_rate:+.2%}  "
                      f"Prod={avg_prod:.3f}  "
                      f"AvgInc=${avg_income:,.0f}  "
                      f"Shortage={state.total_shortage_rate:.2%}  "
                      f"Gini={state.gini:.3f}  HH={len(self.households):,}")

                if t < total_ticks and evolve_fn is not None:
                    evolve_fn(year, self, gdp_growth_rate)
        return pd.DataFrame(rows)

