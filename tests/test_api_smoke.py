from econ_sim import SimulationConfig, run_simulation


def test_clean_api_one_year_smoke():
    config = SimulationConfig.from_excel("data/Simulation_Settings.xlsx").with_overrides(
        simulation_years=1,
        product_innovation_chance=0.0,
        new_products_can_innovate=False,
    )
    result = run_simulation(config, save=False)

    assert len(result.monthly_macro) == 13  # Period 0 + 12 months
    assert len(result.yearly_summary) == 1
    assert len(result.products_seed) == 477
    assert len(result.products_final) == 477
    assert result.period0_gdp > 0
    assert result.summary()["final_year"] == 1
