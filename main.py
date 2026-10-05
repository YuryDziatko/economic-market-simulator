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

    demographic_growth = float(g["demographic_growth"])
    company_growth_sensitivity = float(g["company_growth_sensitivity"])
    allow_company_exits = bool(int(g["allow_company_exits"]))
    price_adjustment_speed = float(g["price_adjustment_speed"])
    production_adjustment_speed = float(g["production_adjustment_speed"])
    max_monthly_price_change = float(g["max_monthly_price_change"])
    max_monthly_production_change = float(g["max_monthly_production_change"])
    initial_inventory_months = float(g["initial_inventory_months"])

    entry_shortage_weight = float(g["entry_shortage_weight"])
    entry_demand_growth_weight = float(g["entry_demand_growth_weight"])
    entry_margin_weight = float(g["entry_margin_weight"])
    exit_surplus_weight = float(g["exit_surplus_weight"])
    exit_demand_decline_weight = float(g["exit_demand_decline_weight"])
    exit_loss_weight = float(g["exit_loss_weight"])
    max_entries_per_product = int(g["max_entries_per_product"])
    max_exits_per_product = int(g["max_exits_per_product"])
    entry_capacity_share = float(g["entry_capacity_share"])
    exit_capacity_share = float(g["exit_capacity_share"])
    min_entry_score = float(g["min_entry_score"])
    min_exit_score = float(g["min_exit_score"])

    rng = np.random.default_rng(seed)

    products = load_products(DATA / "Product_List.xlsx")
    products = prepare_products(products, cfg["quantity"], cfg["markets"], rng)
    period0_gdp = float(products["Revenue_P0"].sum())

    households = generate_households(
        n_households, period0_gdp, target_gini, tax_rate, cfg["classes"], rng
    )
    companies, production = generate_companies(
        products, n_companies, cfg["sizes"], cfg["ownership"], rng
    )

    company_revenue = float(companies["Revenue_P0"].sum())
    household_income = float(households["Gross_Monthly_Income"].sum())
    if not np.isclose(company_revenue, period0_gdp, atol=0.01):
        raise RuntimeError("Company revenue does not reconcile to GDP")
    if not np.isclose(household_income, period0_gdp, atol=0.01):
        raise RuntimeError("Household income does not reconcile to GDP")

    monthly, yearly, basket_calibration, company_events, market_events, product_monthly = simulate(
        products=products,
        households=households,
        companies=companies,
        production=production,
        classes=cfg["classes"],
        basket_preferences=cfg["baskets"],
        years=years,
        annual_inflation=annual_inflation,
        price_noise=price_noise,
        tax_rate=tax_rate,
        demographic_growth=demographic_growth,
        company_growth_sensitivity=company_growth_sensitivity,
        allow_company_exits=allow_company_exits,
        price_adjustment_speed=price_adjustment_speed,
        production_adjustment_speed=production_adjustment_speed,
        max_monthly_price_change=max_monthly_price_change,
        max_monthly_production_change=max_monthly_production_change,
        initial_inventory_months=initial_inventory_months,
        entry_shortage_weight=entry_shortage_weight,
        entry_demand_growth_weight=entry_demand_growth_weight,
        entry_margin_weight=entry_margin_weight,
        exit_surplus_weight=exit_surplus_weight,
        exit_demand_decline_weight=exit_demand_decline_weight,
        exit_loss_weight=exit_loss_weight,
        max_entries_per_product=max_entries_per_product,
        max_exits_per_product=max_exits_per_product,
        entry_capacity_share=entry_capacity_share,
        exit_capacity_share=exit_capacity_share,
        min_entry_score=min_entry_score,
        min_exit_score=min_exit_score,
        rng=rng,
    )

    out = save_outputs(
        OUTPUT,
        yearly_summary=yearly,
        monthly_macro=monthly,
        households=households,
        companies=companies,
        products=products,
        production=production,
        basket_calibration=basket_calibration,
        company_events=company_events,
        market_events=market_events,
        product_monthly=product_monthly,
    )

    class_order = cfg["classes"]["Class"].astype(str).tolist()
    summary = households.groupby("Class", observed=True).agg(
        Households=("Household_ID", "count"),
        Avg_Monthly_Income=("Gross_Monthly_Income", "mean"),
        Income_Share=("Gross_Monthly_Income", "sum"),
        Consumption=("Consumption", "sum"),
    ).reindex(class_order)
    summary["Income_Share"] /= period0_gdp

    print("\n" + "=" * 100)
    print("ECONOMIC SIMULATION — PHASE 1: HOUSEHOLD DEMAND + SUPPLY/DEMAND EQUILIBRIUM")
    print("=" * 100)
    print(f"Products/services               : {len(products):,}")
    print(f"Starting households             : {len(households):,}")
    print(f"Starting companies              : {len(companies):,}")
    print(f"Period-0 monthly GDP            : {money(period0_gdp)}")
    print(f"Period-0 annualized GDP         : {money(period0_gdp * 12)}")
    print(f"Target / generated Gini         : {target_gini:.3f} / {gini(households['Gross_Monthly_Income']):.3f}")
    print(f"Annual household growth         : {demographic_growth:.2%}")
    print(f"Company growth sensitivity      : {company_growth_sensitivity:.2f}x real GDP growth")
    print(f"Background inflation            : {annual_inflation:.2%}")
    print(f"Interest rate (stored)          : {interest_rate:.2%}")
    print(f"Simulation                      : {years} years / {years * 12} months")

    print("\nHOUSEHOLD CLASS SUMMARY — PERIOD 0")
    print(summary.to_string(formatters={
        "Avg_Monthly_Income": lambda x: f"${x:,.0f}",
        "Income_Share": lambda x: f"{x:.1%}",
        "Consumption": lambda x: f"${x:,.0f}",
    }))

    print("\nYEARLY MACRO SUMMARY")
    print(yearly[[
        "Year", "Nominal_GDP", "Nominal_GDP_Growth_YoY", "Real_GDP_Growth_YoY",
        "Inflation_YoY", "Household_Count_End", "Company_Count_End",
        "Average_Shortage_Product_Share", "Monopoly_Products_End",
        "Oligopoly_Products_End", "Competitive_Products_End"
    ]].to_string(index=False, formatters={
        "Nominal_GDP": lambda x: f"${x:,.0f}",
        "Nominal_GDP_Growth_YoY": lambda x: f"{x:.2%}",
        "Real_GDP_Growth_YoY": lambda x: f"{x:.2%}",
        "Inflation_YoY": lambda x: f"{x:.2%}",
        "Average_Shortage_Product_Share": lambda x: f"{x:.1%}",
    }))

    print("\nCOMPANY ENTRY / EXIT EVENTS")
    print(company_events.to_string(index=False, formatters={
        "Prior_Year_Real_GDP_Growth": lambda x: f"{x:.2%}",
    }))

    if not market_events.empty:
        print("\nTOP MARKET ENTRY / EXIT EVENTS")
        display_events = market_events.sort_values(["Year", "Firm_Change"], ascending=[True, False]).head(30)
        print(display_events[[
            "Year", "Product_ID", "Event", "Firm_Change", "Firms_Before", "Firms_After",
            "Market_Before", "Market_After", "Prior_Shortage_Rate",
            "Prior_Demand_Growth", "Prior_Profit_Margin"
        ]].to_string(index=False, formatters={
            "Prior_Shortage_Rate": lambda x: f"{x:.1%}",
            "Prior_Demand_Growth": lambda x: f"{x:.1%}",
            "Prior_Profit_Margin": lambda x: f"{x:.1%}",
        }))

    print(f"\nDetailed output: {out}")
    print("=" * 100)


if __name__ == "__main__":
    main()
