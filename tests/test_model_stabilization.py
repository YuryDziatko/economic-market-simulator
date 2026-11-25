import numpy as np

from econ_sim import SimulationConfig, run_simulation


def stabilized_config(**overrides):
    base = SimulationConfig.from_excel("data/Simulation_Settings.xlsx")
    params = {"simulation_years": 3, "demographic_growth": 0.005}
    params.update(overrides)
    return base.with_overrides(**params)


def test_seed_products_are_never_removed_and_product_growth_is_bounded():
    result = run_simulation(stabilized_config(), save=False)
    seed_ids = set(result.products_seed["Product_ID"].astype(str))
    final_ids = set(result.products_final["Product_ID"].astype(str))
    assert seed_ids <= final_ids

    # 3 launches/month maximum means at most 108 launches over 36 months.
    assert int(result.yearly_summary["New_Products_Created"].sum()) <= 108
    assert len(result.products_final) <= len(result.products_seed) + 108

    retired = result.product_events[result.product_events["Event"] == "Product Retirement"]
    if not retired.empty:
        assert not set(retired["Product_ID"].astype(str)) & seed_ids


def test_gdp_accounting_reconciles_and_inflation_metrics_are_finite():
    result = run_simulation(stabilized_config(), save=False)
    m = result.monthly_macro[result.monthly_macro["Period_Month"] > 0]
    assert float(m["Nominal_GDP_Accounting_Gap"].abs().max()) < 0.01
    assert float(m["Real_GDP_Accounting_Gap"].abs().max()) < 0.01
    assert np.isfinite(m["GDP_Deflator_Index"]).all()
    assert np.isfinite(m["GDP_Deflator_Inflation_12M"]).all()


def test_neutral_baseline_no_longer_explodes_in_three_year_smoke_run():
    result = run_simulation(stabilized_config(), save=False)
    y = result.yearly_summary.iloc[-1]
    assert abs(float(y["Inflation_YoY"])) < 0.10
    assert float(y["Unemployment_Rate_End"]) < 0.15
    assert int(y["Product_Count_End"]) < 1000


def test_calibrated_baseline_has_sticky_downward_prices():
    result = run_simulation(stabilized_config(simulation_years=5), save=False)
    y = result.yearly_summary
    # Neutral baseline should not generate chronic deflation merely from inventory carryover.
    assert int((y["Inflation_YoY"] < 0).sum()) <= 1
    assert float(y["Inflation_YoY"].min()) > -0.01


def test_calibrated_price_cuts_are_asymmetric():
    cfg = stabilized_config()
    assert cfg.price_adjustment_speed_down < cfg.price_adjustment_speed_up
    assert cfg.max_monthly_price_decrease < cfg.max_monthly_price_increase
    assert cfg.inflation_expectation_anchor_weight > 0.5
