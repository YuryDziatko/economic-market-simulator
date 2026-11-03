import numpy as np

from econ_sim import SimulationConfig, run_simulation


def phase4_config(**overrides):
    base = SimulationConfig.from_excel("data/Simulation_Settings.xlsx")
    return base.with_overrides(
        simulation_years=1,
        product_innovation_chance=0.0,
        new_products_can_innovate=False,
        **overrides,
    )


def test_phase4a_savings_fund_investment_and_build_capital():
    result = run_simulation(phase4_config(), save=False)
    monthly = result.monthly_macro[result.monthly_macro["Period_Month"] > 0].reset_index(drop=True)

    assert (monthly["Household_Savings"] > 0).all()
    assert (monthly["Retained_Business_Income"] >= 0).all()
    assert (monthly["Realized_Investment"] >= 0).all()
    assert (monthly["Capital_Depreciation"] > 0).all()
    assert (monthly["Capacity_Utilization"] >= 0).all()
    assert (monthly["Capacity_Utilization"] <= 1.000001).all()

    # Funding pool carries forward exactly: prior pool + new funds - realized investment.
    prior_pool = 0.0
    for row in monthly.to_dict("records"):
        expected = prior_pool + row["New_Investment_Funds"] - row["Realized_Investment"]
        assert np.isclose(row["Investment_Funding_Pool_End"], expected, atol=0.01)
        prior_pool = row["Investment_Funding_Pool_End"]

    # With no product innovation or annual firm event in Year 1, capital follows
    # K_t = K_(t-1) + I_t - depreciation_t.
    prior_capital = float(result.monthly_macro.iloc[0]["Capital_Stock_End"])
    for row in monthly.to_dict("records"):
        expected = prior_capital + row["Realized_Investment"] - row["Capital_Depreciation"]
        assert np.isclose(row["Capital_Stock_End"], expected, atol=0.05)
        prior_capital = row["Capital_Stock_End"]


def test_higher_interest_rate_raises_household_saving_rate_and_reduces_desired_investment():
    low = run_simulation(phase4_config(interest_rate=0.01), save=False)
    high = run_simulation(phase4_config(interest_rate=0.08), save=False)

    low_y = low.yearly_summary.iloc[-1]
    high_y = high.yearly_summary.iloc[-1]
    assert high_y["Household_Savings_Rate_End"] > low_y["Household_Savings_Rate_End"]
    assert high_y["Desired_Investment"] < low_y["Desired_Investment"]
