import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import app
from econ_sim import (
    POLICY_FIELDS,
    STRUCTURAL_FIELDS,
    PolicyAction,
    PolicyState,
    SimulationConfig,
    apply_policy_action,
    run_simulation,
)


def _fast_config(**overrides):
    base = SimulationConfig.from_excel("data/Simulation_Settings.xlsx")
    return base.with_overrides(
        simulation_years=2,
        product_innovation_chance=0.0,
        new_products_can_innovate=False,
        **overrides,
    )


def test_policy_fields_are_separate_from_structural_fields():
    assert "interest_rate" in POLICY_FIELDS
    assert "tax_rate" in POLICY_FIELDS
    assert "annual_labor_productivity_growth" in STRUCTURAL_FIELDS
    assert "demographic_growth" in STRUCTURAL_FIELDS
    assert POLICY_FIELDS.isdisjoint(STRUCTURAL_FIELDS)


def test_policy_action_is_bounded_and_fiscal_reserve_balances():
    state = PolicyState.from_config(_fast_config())
    next_state = apply_policy_action(
        state,
        PolicyAction(
            tax_rate=0.02,
            government_consumption_share=-0.05,
            general_transfer_share=0.03,
            reason="Test reallocation",
        ),
    )
    assert np.isclose(next_state.tax_rate, state.tax_rate + 0.02)
    assert np.isclose(
        next_state.government_consumption_share
        + next_state.general_transfer_share
        + next_state.government_reserve_share,
        1.0,
    )

    with pytest.raises(ValueError):
        apply_policy_action(state, PolicyAction(interest_rate=0.10))


def test_yearly_policy_schedule_changes_policy_inside_same_economy():
    config = _fast_config(interest_rate=0.03)
    result = run_simulation(
        config,
        save=False,
        policy_schedule={
            2: PolicyAction(
                interest_rate=0.02,
                tax_rate=-0.01,
                reason="Tighten rates while cutting income tax",
            )
        },
    )

    assert len(result.policy_history) == 1
    event = result.policy_history.iloc[0]
    assert int(event["Year"]) == 2
    assert np.isclose(event["After_interest_rate"], 0.05)
    assert np.isclose(event["After_tax_rate"], config.tax_rate - 0.01)

    year1 = result.monthly_macro[result.monthly_macro["Year"] == 1]
    year2 = result.monthly_macro[result.monthly_macro["Year"] == 2]
    assert np.isclose(year1["Policy_Interest_Rate"].iloc[-1], 0.03)
    assert np.isclose(year2["Policy_Interest_Rate"].iloc[0], 0.05)
    assert np.isclose(year2["Policy_Income_Tax_Rate"].iloc[0], config.tax_rate - 0.01)


def test_policy_api_exposes_limits_and_runs_schedule():
    client = TestClient(app)
    limits = client.get("/api/policy/limits")
    assert limits.status_code == 200
    assert "interest_rate" in limits.json()["policy_fields"]

    response = client.post(
        "/api/policy/simulate",
        json={
            "overrides": {
                "simulation_years": 1,
                "product_innovation_chance": 0.0,
                "new_products_can_innovate": False,
            },
            "policy_schedule": {
                "1": {
                    "interest_rate": 0.01,
                    "reason": "Small rate increase"
                }
            },
            "include_monthly": False,
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert len(payload["policy_history"]) == 1
    assert payload["policy_history"][0]["Year"] == 1
