import numpy as np
from fastapi.testclient import TestClient

from app.main import app
from econ_sim import PolicyState, SimulationConfig, get_agent, run_simulation


def _fast_config(**overrides):
    base = SimulationConfig.from_excel("data/Simulation_Settings.xlsx")
    return base.with_overrides(
        simulation_years=2,
        product_innovation_chance=0.0,
        new_products_can_innovate=False,
        **overrides,
    )


def test_agent_catalog_api():
    client = TestClient(app)
    response = client.get("/api/policy/agents")
    assert response.status_code == 200
    keys = {item["key"] for item in response.json()["agents"]}
    assert {"technocratic", "market_liberal", "social_democratic", "state_directed", "hybrid"} <= keys


def test_deterministic_agent_starts_after_observing_year_one():
    config = _fast_config(interest_rate=0.03)
    result = run_simulation(config, save=False, policy_agent=get_agent("technocratic"))
    assert len(result.policy_history) == 1
    event = result.policy_history.iloc[0]
    assert int(event["Year"]) == 2
    assert event["Decision_Source"] == "deterministic_agent"
    assert event["Agent_Key"] == "technocratic"
    assert int(event["Observed_year"]) == 1
    assert isinstance(event["Reason"], str) and event["Reason"]


def test_agents_are_reproducible_with_same_seed():
    config = _fast_config(random_seed=123)
    a = run_simulation(config, save=False, policy_agent=get_agent("hybrid"))
    b = run_simulation(config, save=False, policy_agent=get_agent("hybrid"))
    assert a.policy_history.to_dict(orient="records") == b.policy_history.to_dict(orient="records")
    assert np.isclose(a.summary()["nominal_gdp"], b.summary()["nominal_gdp"])


def test_agent_simulation_api():
    client = TestClient(app)
    response = client.post(
        "/api/policy/agents/simulate",
        json={
            "agent": "hybrid",
            "overrides": {
                "simulation_years": 2,
                "product_innovation_chance": 0.0,
                "new_products_can_innovate": False,
            },
            "include_monthly": False,
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["agent"]["key"] == "hybrid"
    assert len(payload["policy_history"]) == 1
