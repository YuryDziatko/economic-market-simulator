import pytest

from econ_sim import SimulationConfig, compare_scenarios


def quick_config() -> SimulationConfig:
    return SimulationConfig.from_excel("data/Simulation_Settings.xlsx").with_overrides(
        simulation_years=1,
        product_innovation_chance=0.0,
        new_products_can_innovate=False,
    )


def test_compare_one_scenario_returns_kpi_and_yearly_data():
    baseline = quick_config()
    comparison = compare_scenarios(
        baseline,
        {"Higher tax": {"tax_rate": 0.30}},
    )

    assert comparison.baseline_name == "Baseline"
    assert list(comparison.scenarios) == ["Higher tax"]
    assert not comparison.kpi_long().empty
    assert "Higher tax Δ" in comparison.kpi_table().columns

    yearly = comparison.yearly_metric("Real_GDP_Growth_YoY")
    assert list(yearly.columns) == ["Year", "Baseline", "Higher tax"]
    assert len(yearly) == 1

    payload = comparison.to_dict()
    assert payload["baseline"] == "Baseline"
    assert payload["scenario_names"] == ["Higher tax"]
    assert "gdp" in payload["yearly"]


def test_override_scenario_keeps_same_seed():
    baseline = quick_config()
    comparison = compare_scenarios(
        baseline,
        {"Population": {"demographic_growth": 0.02}},
    )
    assert comparison.scenarios["Population"].config.random_seed == baseline.random_seed


def test_empty_scenarios_rejected():
    with pytest.raises(ValueError, match="At least one scenario"):
        compare_scenarios(quick_config(), {})
