"""
market.py  —  Equilibrium market engine (updated for v2).

Period 0 = base period (equilibrium, inflation = 0%).
Each tick = 1 month.
"""
from dataclasses import dataclass, field
from typing import Dict, List
import pandas as pd
from household_model import Household, COICOP_WEIGHTS, ELASTICITY
from producer_model import Firm


@dataclass
class EconomicState:
    tick: int
    price_index:       Dict[str, float]   # division -> index (1.0 at base)
    cpi:               float
    inflation_yoy:     float              # % vs same tick 12 months ago
    gdp_nominal:       float
    gdp_real:          float              # deflated by CPI
    total_consumption: float
    total_investment:  float
    total_gov_spend:   float
    gini:              float
    unemployment_rate: float = 0.05


class Shock:
    def __init__(self, division: str, shock_type: str,
                 magnitude: float, start_tick: int, duration: int):
        self.division   = division
        self.shock_type = shock_type    # 'supply' | 'demand' | 'cost'
        self.magnitude  = magnitude     # e.g. -0.3 = −30%
        self.start_tick = start_tick
        self.duration   = duration
        self._applied   = 0

    def is_active(self, tick: int) -> bool:
        return self.start_tick <= tick < self.start_tick + self.duration

    def mark_applied(self):
        self._applied += 1


class MarketEngine:
    def __init__(
        self,
        households:   List[Household],
        firms:        List[Firm],
        goods_db:     pd.DataFrame,
        tax_rate:     float = 0.22,
        money_growth: float = 0.002,
        subsidy_divs: Dict[str, float] = None,
        price_caps:   Dict[str, float] = None,
    ):
        self.households    = households
        self.firms         = firms
        self.goods_db      = goods_db
        self.tax_rate      = tax_rate
        self.money_growth  = money_growth
        self.subsidy_divs  = subsidy_divs or {"01": 0.05, "06": 0.10}
        self.price_caps    = price_caps   or {}
        self.shocks:        List[Shock] = []

        self.divisions = sorted(goods_db["coicop_division"].unique())

        # Period-0 base GDP per division
        self.base_div_gdp: Dict[str, float] = (
            goods_db.groupby("coicop_division")["gdp_contribution"]
            .sum().to_dict()
        )
        self.base_gdp = sum(self.base_div_gdp.values())

        # Price index starts at 1.0 (base period = equilibrium)
        self.price_index: Dict[str, float] = {d: 1.0 for d in self.divisions}

        # CPI history for YoY calc
        self._cpi_history: List[float] = [1.0]   # index 0 = base period

        # Base period demand (for normalising excess demand)
        self._base_demand: Dict[str, float] = {
            d: sum(hh.demand_for(d, 1.0, 1.0) for hh in self.households)
            for d in self.divisions
        }

    def add_shock(self, shock: Shock):
        self.shocks.append(shock)

    # ── Catalogue evolution hook ────────────────────────────────────────────────
    def rebase_division(self, division: str, new_div_gdp: float, price_shift: float):
        """
        Called once per simulated year after the product catalogue evolves.
        new_div_gdp  : this division's fresh Σ(price × quantity) from the evolved catalogue.
        price_shift  : fractional change in that division's average catalogue price
                       (e.g. +0.03 = catalogue prices rose 3% on average this year).
        The price_shift is applied directly to the tâtonnement price_index as an
        autonomous producer-price movement, on top of demand/supply pressure.
        The GDP rebase changes the revenue base firms in this division are scaled against,
        capturing new products / discontinued lines changing division output.
        """
        old_gdp = self.base_div_gdp.get(division, new_div_gdp)
        self.base_div_gdp[division] = new_div_gdp

        # Rescale each firm's revenue base (market shares stay fixed; total pie changes)
        for f in self.firms:
            if f.division == division:
                f.div_gdp = new_div_gdp

        # Autonomous price index shift from catalogue-level price changes
        if division in self.price_index:
            shift = max(-0.20, min(0.20, price_shift))  # clamp extreme swings
            self.price_index[division] = max(0.3, self.price_index[division] * (1 + shift))

    def _active_shocks(self, tick: int) -> List[Shock]:
        return [s for s in self.shocks if s.is_active(tick)]

    # ── Demand ────────────────────────────────────────────────────────────────
    def _demand(self, division: str, tick: int) -> float:
        d = sum(hh.demand_for(division, self.price_index[division], 1.0)
                for hh in self.households)
        for s in self._active_shocks(tick):
            if s.division == division and s.shock_type == "demand":
                d *= (1 + s.magnitude)
        return d

    # ── Supply (as fraction of base demand) ───────────────────────────────────
    def _supply_fraction(self, division: str, tick: int) -> float:
        """
        Anchored at 1.0 (equilibrium) by default.
        Only shocks move aggregate supply away from equilibrium.
        Firm capacity dynamics affect firm-level revenues but not aggregate prices.
        """
        sf = 1.0
        for s in self._active_shocks(tick):
            if s.division == division and s.shock_type == "supply":
                sf *= (1 + s.magnitude)
        return max(0.1, sf)

    # ── Price update ──────────────────────────────────────────────────────────
    def _update_prices(self, tick: int):
        for div in self.divisions:
            demand  = self._demand(div, tick)
            supply  = demand * self._supply_fraction(div, tick)
            excess  = (demand - supply) / max(supply, 1.0)
            excess  = max(-0.5, min(0.5, excess))

            # Competitive markets adjust faster; monopolies are stickier
            div_firms = [f for f in self.firms if f.division == div]
            ms = div_firms[0].market_structure if div_firms else "competitive"
            price_sensitivity = {"competitive": 0.04, "oligopoly": 0.025, "monopoly": 0.01}
            resp = price_sensitivity.get(ms, 0.03) * excess

            # Cost shock pass-through
            cost_pass = 0.0
            for s in self._active_shocks(tick):
                if s.division == div and s.shock_type == "cost":
                    cost_pass += s.magnitude * 0.5

            # Subsidy dampens price rises
            subsidy = self.subsidy_divs.get(div, 0.0)

            delta = resp + self.money_growth + cost_pass - subsidy * 0.002
            delta = max(-0.05, min(0.05, delta))

            new_idx = self.price_index[div] * (1 + delta)

            # Price cap enforcement
            cap = self.price_caps.get(div)
            if cap:
                new_idx = min(new_idx, cap)

            self.price_index[div] = max(0.3, new_idx)

    # ── CPI  ──────────────────────────────────────────────────────────────────
    def _compute_cpi(self) -> float:
        w_total = sum(COICOP_WEIGHTS.get(d, 0) for d in self.divisions)
        return sum(self.price_index[d] * COICOP_WEIGHTS.get(d, 0)
                   for d in self.divisions) / max(w_total, 1e-9)

    # ── GDP  ──────────────────────────────────────────────────────────────────
    def _compute_gdp(self, tick: int):
        C = sum(
            sum(hh.demand_for(d, self.price_index[d], 1.0) for d in self.divisions)
            for hh in self.households
        )
        I = sum(f.revenue * 0.08 * f.capacity_factor for f in self.firms)
        G = sum(hh.income for hh in self.households) * self.tax_rate
        return C, I, G

    # ── Gini from actual household incomes ────────────────────────────────────
    def _compute_gini(self) -> float:
        incomes = sorted(hh.income for hh in self.households)
        n = len(incomes)
        if n == 0: return 0.0
        cum, gsum = 0, 0
        for i, y in enumerate(incomes):
            cum  += y
            gsum += (2*(i+1) - n - 1) * y
        return gsum / (n * cum) if cum > 0 else 0.0

    # ── Single tick ────────────────────────────────────────────────────────────
    def tick(self, t: int) -> EconomicState:
        self._update_prices(t)

        # Wage growth (half money growth rate)
        for hh in self.households:
            hh.income *= (1 + self.money_growth * 0.5)

        # Update firm revenues and capacities
        for f in self.firms:
            demand_share = self._demand(f.division, t) / max(self._base_demand.get(f.division, 1), 1)
            f.revenue = f.div_gdp * f.market_share * demand_share * self.price_index[f.division]
            f.update_capacity()

        cpi = self._compute_cpi()
        C, I, G = self._compute_gdp(t)
        gdp_nominal = C + I + G
        gdp_real    = gdp_nominal / cpi

        # YoY inflation
        self._cpi_history.append(cpi)
        if len(self._cpi_history) > 13:
            inf_yoy = (cpi / self._cpi_history[-13] - 1) * 100
        else:
            inf_yoy = 0.0

        return EconomicState(
            tick=t, price_index=dict(self.price_index),
            cpi=cpi, inflation_yoy=inf_yoy,
            gdp_nominal=gdp_nominal, gdp_real=gdp_real,
            total_consumption=C, total_investment=I, total_gov_spend=G,
            gini=self._compute_gini(),
        )

    # ── Full run ───────────────────────────────────────────────────────────────
    def run(self, ticks: int) -> pd.DataFrame:
        rows = []
        for t in range(1, ticks + 1):
            state = self.tick(t)
            row = {
                "tick":        t,
                "year":        round(t / 12, 3),
                "cpi":         round(state.cpi, 5),
                "inflation_yoy": round(state.inflation_yoy, 3),
                "gdp_nominal": round(state.gdp_nominal, 2),
                "gdp_real":    round(state.gdp_real, 2),
                "consumption": round(state.total_consumption, 2),
                "investment":  round(state.total_investment, 2),
                "gov_spend":   round(state.total_gov_spend, 2),
                "gini":        round(state.gini, 5),
            }
            for d in self.divisions:
                row[f"price_{d}"] = round(state.price_index[d], 5)
            rows.append(row)

            if t % 12 == 0:
                print(f"  Year {t//12:>2}  "
                      f"CPI={state.cpi:.4f}  "
                      f"Inf={state.inflation_yoy:+.1f}%  "
                      f"GDP_nom=${state.gdp_nominal:>11,.0f}  "
                      f"GDP_real=${state.gdp_real:>10,.0f}  "
                      f"Gini={state.gini:.3f}")

        return pd.DataFrame(rows)

    # ── Full run with annual catalogue evolution ────────────────────────────────
    def run_with_evolution(self, years: int, evolve_fn, ticks_per_year: int = 12) -> pd.DataFrame:
        """
        Run the simulation year by year, evolving the product catalogue AND
        household population between years.

        evolve_fn(year, engine, gdp_growth_rate) -> called after each completed
        year (years 1..years-1, NOT after the final year). gdp_growth_rate is
        this year's real-GDP growth vs the prior year (0.0 for year 1).
        """
        rows = []
        prev_year_gdp_real = None
        state = None
        for year in range(1, years + 1):
            for t_in_year in range(1, ticks_per_year + 1):
                t = (year - 1) * ticks_per_year + t_in_year
                state = self.tick(t)
                row = {
                    "tick": t, "year": round(t / ticks_per_year, 3),
                    "cpi": round(state.cpi, 5),
                    "inflation_yoy": round(state.inflation_yoy, 3),
                    "gdp_nominal": round(state.gdp_nominal, 2),
                    "gdp_real": round(state.gdp_real, 2),
                    "consumption": round(state.total_consumption, 2),
                    "investment": round(state.total_investment, 2),
                    "gov_spend": round(state.total_gov_spend, 2),
                    "gini": round(state.gini, 5),
                    "households": len(self.households),
                }
                for d in self.divisions:
                    row[f"price_{d}"] = round(state.price_index[d], 5)
                rows.append(row)

            gdp_growth_rate = 0.0
            if prev_year_gdp_real:
                gdp_growth_rate = (state.gdp_real / prev_year_gdp_real - 1)
            prev_year_gdp_real = state.gdp_real

            print(f"  Year {year:>2}  "
                  f"CPI={state.cpi:.4f}  "
                  f"Inf={state.inflation_yoy:+.1f}%  "
                  f"GDP_nom=${state.gdp_nominal:>11,.0f}  "
                  f"GDP_real=${state.gdp_real:>10,.0f}  "
                  f"GDP_growth={gdp_growth_rate:+.2%}  "
                  f"Gini={state.gini:.3f}  "
                  f"HH={len(self.households):,}")

            if year < years and evolve_fn is not None:
                evolve_fn(year, self, gdp_growth_rate)

        return pd.DataFrame(rows)
