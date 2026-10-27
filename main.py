from pathlib import Path

from econ_sim import SimulationConfig, run_simulation
from econ_sim.utils import gini

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
OUTPUT = ROOT / "output"


def money(value: float) -> str:
    return f"${value:,.0f}"


def main() -> None:
    # Excel remains the default UI for a local PyCharm run, but after this line
    # the simulation is controlled only by the typed SimulationConfig object.
    config = SimulationConfig.from_excel(DATA / "Simulation_Settings.xlsx")

    result = run_simulation(
        config,
        settings_path=DATA / "Simulation_Settings.xlsx",
        product_path=DATA / "Product_List.xlsx",
        output_dir=OUTPUT,
        save=True,
    )

    final = result.final_year
    generated_gini = gini(result.households["Gross_Monthly_Income"])

    print("\n" + "=" * 92)
    print("ECONOMIC MARKET SIMULATOR — CONFIG API")
    print("=" * 92)
    print(f"Simulation horizon          : {config.simulation_years} years")
    print(f"Random seed                 : {config.random_seed}")
    print(f"Starting households         : {config.num_households:,}")
    print(f"Starting companies          : {config.num_companies:,}")
    print(f"Starting products           : {len(result.products_seed):,}")
    print(f"Final products              : {len(result.products_final):,}")
    print(f"Period-0 annualized GDP     : {money(result.period0_gdp * 12)}")
    print(f"Target / generated Gini     : {config.target_gini:.3f} / {generated_gini:.3f}")
    print(f"Household income tax        : {config.tax_rate:.2%}")
    print(f"Corporate tax              : {config.corporate_profit_tax_rate:.2%}")

    if final:
        print("\nFINAL YEAR")
        print(f"Nominal GDP                 : {money(final['Nominal_GDP'])}")
        print(f"Real GDP growth             : {final['Real_GDP_Growth_YoY']:.2%}")
        print(f"Inflation                   : {final['Inflation_YoY']:.2%}")
        print(f"Unemployment                : {final['Unemployment_Rate_End']:.2%}")
        print(f"Income Gini                 : {final['Income_Gini_End_Class_Average']:.3f}")
        print(f"Households                  : {int(final['Household_Count_End']):,}")
        print(f"Companies                   : {int(final['Company_Count_End']):,}")
        print(f"Products                    : {int(final['Product_Count_End']):,}")
        print(f"Public debt / GDP           : {final['Debt_to_GDP_End']:.2%}")

    if result.output_workbook:
        print(f"\nDetailed output             : {result.output_workbook}")
    print("=" * 92)


if __name__ == "__main__":
    main()
