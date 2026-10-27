# Step 3 — FastAPI Web Layer

This step exposes the simulation engine as a web/API service without moving economics logic into the web code.

## Run locally

```powershell
pip install -r requirements.txt
uvicorn web_main:app --reload
```

Open:

- `http://127.0.0.1:8000/` — minimal browser UI
- `http://127.0.0.1:8000/docs` — Swagger/OpenAPI UI
- `http://127.0.0.1:8000/api/health` — health check

## Endpoints

### GET `/api/config`
Returns the baseline `SimulationConfig` loaded from `data/Simulation_Settings.xlsx`.

### POST `/api/simulate`

```json
{
  "overrides": {
    "simulation_years": 5,
    "tax_rate": 0.30,
    "demographic_growth": 0.02
  },
  "include_monthly": false
}
```

The response includes the effective config, summary KPIs, and yearly results.

### POST `/api/compare`

```json
{
  "baseline_overrides": {
    "simulation_years": 5
  },
  "scenarios": {
    "Higher tax": {"tax_rate": 0.30},
    "Faster population": {"demographic_growth": 0.02}
  },
  "baseline_name": "Baseline"
}
```

The response is the Step-2 comparison payload, already shaped for dashboard charts.

## Architecture

```text
Browser / API client
        |
        v
FastAPI app
        |
        +--> SimulationRequest / CompareRequest validation
        |
        v
SimulationConfig
        |
        +--> run_simulation()
        |       |
        |       v
        |   SimulationResult
        |
        +--> compare_scenarios()
                |
                v
          ScenarioComparison
```

The web layer never reads or mutates economics internals directly. It only creates validated configs and calls the public engine API.

## Render

A starter `render.yaml` is included. The service runs with:

```bash
uvicorn web_main:app --host 0.0.0.0 --port $PORT
```

For the first public MVP, runs are synchronous and results stay in memory. Saved user scenarios/background jobs can be added later if simulation runtime becomes too long for a normal HTTP request.
