from pathlib import Path
import numpy as np

from econ_sim.io import load_settings, load_products, save_outputs
from econ_sim.companies import prepare_products, generate_companies
from econ_sim.households import generate_households
from econ_sim.engine import simulate
from econ_sim.utils import gini

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
OUTPUT = ROOT / "output"


def money(x):
    return f"${x:,.0f}"


def main():
    cfg = load_settings(DATA / "Simulation_Settings.xlsx")
    g = cfg["general"]
    target_gini = float(g["target_gini"])
    tax_rate = float(g["tax_rate"])
    interest_rate = float(g["interest_rate"])
    annual_inflation = float(g["annual_inflation"])
    n_households = int(g["num_households"])
    n_companies = int(g["num_companies"])
    years = int(g["simulation_years"])
    seed = int(g["random_seed"])
    price_noise = float(g["monthly_price_noise_std"])
    rng = np.random.default_rng(seed)

    products = load_products(DATA / "Product_List.xlsx")
    products = prepare_products(products, cfg["quantity"], cfg["markets"], rng)
    period0_gdp = float(products["Revenue_P0"].sum())

    households = generate_households(n_households, period0_gdp, target_gini, tax_rate, cfg["classes"], rng)
    companies, production = generate_companies(products, n_companies, cfg["sizes"], cfg["ownership"], rng)

    # Accounting reconciliation at the starting equilibrium.
    company_revenue = float(companies["Revenue_P0"].sum())
    household_income = float(households["Gross_Monthly_Income"].sum())
    if not np.isclose(company_revenue, period0_gdp, atol=0.01):
        raise RuntimeError("Company revenue does not reconcile to GDP")
    if not np.isclose(household_income, period0_gdp, atol=0.01):
        raise RuntimeError("Household income does not reconcile to GDP")

    monthly, yearly = simulate(products, companies, production, years, annual_inflation, price_noise, tax_rate, n_households, n_companies, rng)

    out = save_outputs(
        OUTPUT,
        yearly_summary=yearly,
        monthly_macro=monthly,
        households=households,
        companies=companies,
        products=products,
        production=production,
    )

    class_order = cfg["classes"]["Class"].astype(str).tolist()
    summary = households.groupby("Class", observed=True).agg(
        Households=("Household_ID", "count"),
        Avg_Monthly_Income=("Gross_Monthly_Income", "mean"),
        Income_Share=("Gross_Monthly_Income", "sum"),
        Consumption=("Consumption", "sum"),
    ).reindex(class_order)
    summary["Income_Share"] /= period0_gdp

    print("\n" + "=" * 88)
    print("ECONOMIC SIMULATION — PHASE 0")
    print("=" * 88)
    print(f"Products/services            : {len(products):,}")
    print(f"Households                   : {len(households):,}")
    print(f"Companies                    : {len(companies):,}")
    print(f"Active companies             : {(companies['Status'] == 'Active').sum():,}")
    print(f"Period-0 monthly GDP         : {money(period0_gdp)}")
    print(f"Period-0 annualized GDP      : {money(period0_gdp * 12)}")
    print(f"Target Gini                  : {target_gini:.3f}")
    print(f"Generated Gini               : {gini(households['Gross_Monthly_Income']):.3f}")
    print(f"Tax rate                     : {tax_rate:.2%}")
    print(f"Interest rate (stored)       : {interest_rate:.2%}")
    print(f"Inflation target             : {annual_inflation:.2%}")
    print(f"Simulation                   : {years} years / {years*12} months")

    print("\nHOUSEHOLD CLASS SUMMARY")
    print(summary.to_string(formatters={
        "Avg_Monthly_Income": lambda x: f"${x:,.0f}",
        "Income_Share": lambda x: f"{x:.1%}",
        "Consumption": lambda x: f"${x:,.0f}",
    }))

    print("\nYEARLY MACRO SUMMARY")
    print(yearly[["Year", "Nominal_GDP_Annualized", "Nominal_GDP_Growth_YoY", "Inflation_YoY", "Household_Count", "Company_Count"]].to_string(index=False, formatters={
        "Nominal_GDP_Annualized": lambda x: f"${x:,.0f}",
        "Nominal_GDP_Growth_YoY": lambda x: f"{x:.2%}",
        "Inflation_YoY": lambda x: f"{x:.2%}",
    }))
    print(f"\nDetailed output: {out}")
    print("=" * 88)


if __name__ == "__main__":
    main()
