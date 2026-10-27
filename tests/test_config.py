from econ_sim.config import SimulationConfig


def test_config_override_is_immutable():
    base = SimulationConfig()
    scenario = base.with_overrides(tax_rate=0.30, simulation_years=5)

    assert base.tax_rate == 0.20
    assert base.simulation_years == 10
    assert scenario.tax_rate == 0.30
    assert scenario.simulation_years == 5


def test_fiscal_shares_must_balance():
    try:
        SimulationConfig().with_overrides(government_consumption_share=0.70)
    except ValueError as exc:
        assert "must equal 1.0" in str(exc)
    else:
        raise AssertionError("Expected fiscal-share validation error")
