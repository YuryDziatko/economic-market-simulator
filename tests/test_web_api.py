from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def quick_overrides():
    return {
        "simulation_years": 1,
        "product_innovation_chance": 0.0,
        "new_products_can_innovate": False,
    }


def test_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_config_endpoint_has_defaults():
    response = client.get("/api/config")
    assert response.status_code == 200
    data = response.json()
    assert data["defaults"]["tax_rate"] == 0.20
    assert "simulation_years" in data["defaults"]


def test_simulate_endpoint_smoke():
    response = client.post("/api/simulate", json={"overrides": quick_overrides()})
    assert response.status_code == 200
    data = response.json()
    assert data["summary"]["final_year"] == 1
    assert len(data["yearly"]) == 1
    assert data["summary"]["starting_products"] == 477


def test_compare_endpoint_smoke():
    response = client.post(
        "/api/compare",
        json={
            "baseline_overrides": quick_overrides(),
            "scenarios": {"Higher tax": {"tax_rate": 0.30}},
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["baseline"] == "Baseline"
    assert data["scenario_names"] == ["Higher tax"]
    assert "gdp" in data["yearly"]


def test_unknown_config_field_rejected():
    response = client.post("/api/simulate", json={"overrides": {"not_a_real_setting": 10}})
    assert response.status_code == 422
