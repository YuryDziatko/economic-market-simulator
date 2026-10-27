from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil

import numpy as np
import pandas as pd

from .companies import generate_companies, prepare_products
from .config import SimulationConfig
from .engine import simulate
from .households import generate_households
from .io import load_products, load_settings, save_outputs


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"


@dataclass(slots=True)
class SimulationResult:
    """All important outputs from one run, independent of UI or file format."""

    config: SimulationConfig
    period0_gdp: float
    monthly_macro: pd.DataFrame
    yearly_summary: pd.DataFrame
    households: pd.DataFrame
    companies: pd.DataFrame
    production: pd.DataFrame
    products_seed: pd.DataFrame
    products_final: pd.DataFrame
    basket_calibration: pd.DataFrame
    company_events: pd.DataFrame
    market_events: pd.DataFrame
    product_monthly: pd.DataFrame
    product_events: pd.DataFrame
    household_income_monthly: pd.DataFrame
    government_monthly: pd.DataFrame
    output_workbook: Path | None = None

    @property
    def final_year(self) -> dict:
        if self.yearly_summary.empty:
            return {}
        return self.yearly_summary.iloc[-1].to_dict()

    def summary(self) -> dict:
        """Small JSON-friendly KPI payload for a web/API response."""
        final = self.final_year
        return {
            "period0_monthly_gdp": float(self.period0_gdp),
            "period0_annualized_gdp": float(self.period0_gdp * 12.0),
            "starting_households": int(self.config.num_households),
            "starting_companies": int(self.config.num_companies),
            "starting_products": int(len(self.products_seed)),
            "final_products": int(len(self.products_final)),
            "final_year": int(final.get("Year", 0)) if final else 0,
            "nominal_gdp": float(final.get("Nominal_GDP", 0.0)) if final else 0.0,
            "real_gdp_growth": float(final.get("Real_GDP_Growth_YoY", 0.0)) if final else 0.0,
            "inflation": float(final.get("Inflation_YoY", 0.0)) if final else 0.0,
            "unemployment_rate": float(final.get("Unemployment_Rate_End", 0.0)) if final else 0.0,
            "income_gini": float(final.get("Income_Gini_End_Class_Average", 0.0)) if final else 0.0,
            "public_debt_to_gdp": float(final.get("Debt_to_GDP_End", 0.0)) if final else 0.0,
        }

    def frames(self) -> dict[str, pd.DataFrame]:
        return {
            "yearly_summary": self.yearly_summary,
            "monthly_macro": self.monthly_macro,
            "households": self.households,
            "companies": self.companies,
            "products_seed": self.products_seed,
            "products_final": self.products_final,
            "product_events": self.product_events,
            "production": self.production,
            "basket_calibration": self.basket_calibration,
            "company_events": self.company_events,
            "market_events": self.market_events,
            "product_monthly": self.product_monthly,
            "household_income_monthly": self.household_income_monthly,
            "government_monthly": self.government_monthly,
        }


def run_simulation(
    config: SimulationConfig,
    *,
    settings_path: str | Path | None = None,
    product_path: str | Path | None = None,
    output_dir: str | Path | None = None,
    save: bool = False,
) -> SimulationResult:
    """Run the complete economy from a typed config.

    This is the public engine API intended for PyCharm, tests, FastAPI, notebooks,
    and scenario comparison. Excel supplies structural tables by default, while
    scalar settings come exclusively from ``config``.
    """
    config.validate()

    settings_path = Path(settings_path or (DEFAULT_DATA_DIR / "Simulation_Settings.xlsx"))
    product_path = Path(product_path or (DEFAULT_DATA_DIR / "Product_List.xlsx"))
    tables = load_settings(settings_path, validate_general=False)
    rng = np.random.default_rng(config.random_seed)

    products = load_products(product_path)
    products = prepare_products(products, tables["quantity"], tables["markets"], rng)
    period0_gdp = float(products["Revenue_P0"].sum())

    households = generate_households(
        config.num_households,
        period0_gdp,
        config.target_gini,
        config.tax_rate,
        tables["classes"],
        rng,
    )
    companies, production = generate_companies(
        products,
        config.num_companies,
        tables["sizes"],
        tables["ownership"],
        rng,
    )

    company_revenue = float(companies["Revenue_P0"].sum())
    household_income = float(households["Gross_Monthly_Income"].sum())
    if not np.isclose(company_revenue, period0_gdp, atol=0.01):
        raise RuntimeError("Company revenue does not reconcile to GDP")
    if not np.isclose(household_income, period0_gdp, atol=0.01):
        raise RuntimeError("Household income does not reconcile to GDP")

    (
        monthly,
        yearly,
        basket_calibration,
        company_events,
        market_events,
        product_monthly,
        products_final,
        product_events,
        household_income_monthly,
        government_monthly,
    ) = simulate(
        products=products,
        households=households,
        companies=companies,
        production=production,
        classes=tables["classes"],
        basket_preferences=tables["baskets"],
        employment_settings=tables["employment"],
        government_transfers=tables["government_transfers"],
        government_demand=tables["government_demand"],
        config=config,
        rng=rng,
    )

    result = SimulationResult(
        config=config,
        period0_gdp=period0_gdp,
        monthly_macro=monthly,
        yearly_summary=yearly,
        households=households,
        companies=companies,
        production=production,
        products_seed=products,
        products_final=products_final,
        basket_calibration=basket_calibration,
        company_events=company_events,
        market_events=market_events,
        product_monthly=product_monthly,
        product_events=product_events,
        household_income_monthly=household_income_monthly,
        government_monthly=government_monthly,
    )

    if save:
        target = Path(output_dir or (PROJECT_ROOT / "output"))
        target.mkdir(parents=True, exist_ok=True)
        shutil.copy2(product_path, target / "Product_List_Seed_Copy.xlsx")
        result.output_workbook = save_outputs(target, **result.frames())

    return result
