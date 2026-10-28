# Economic Market Simulator

A Python agent-style economic simulation with households, companies, products, labor, government, market structure, product innovation, supply/demand adjustment, and monthly/annual macroeconomic reporting.

The current model includes:

- household income classes and target Gini;
- consumption baskets and price elasticity;
- product supply, demand, inventory, shortages and price adjustment;
- competitive, oligopoly and monopoly markets;
- intelligent firm entry/exit;
- monthly product innovation;
- demographic growth;
- employment, unemployment, wages and productivity;
- labor and capital household income;
- household and business taxes;
- transfers, government purchases, budget balance and public debt.

## Clean simulation API

The engine no longer reads scalar settings directly from Excel and no longer requires dozens of independent arguments.

All scalar settings live in one typed object:

```python
from econ_sim import SimulationConfig, run_simulation

config = SimulationConfig(
    simulation_years=10,
    num_households=1000,
    num_companies=1000,
    target_gini=0.30,
    tax_rate=0.20,
    annual_inflation=0.02,
)

result = run_simulation(config)
print(result.summary())
```

For normal PyCharm use, load the existing Excel control workbook:

```python
config = SimulationConfig.from_excel("data/Simulation_Settings.xlsx")
result = run_simulation(config)
```

For a scenario or future web form, override only the requested values:

```python
baseline = SimulationConfig.from_excel("data/Simulation_Settings.xlsx")

scenario = baseline.with_overrides(
    tax_rate=0.30,
    annual_inflation=0.04,
    demographic_growth=0.015,
)

result = run_simulation(scenario)
```

`SimulationConfig` is immutable: changing a scenario does not modify the baseline configuration.

## Why this architecture matters

There are now three separate layers:

```text
Excel / future web form / tests
            ↓
     SimulationConfig
            ↓
      run_simulation()
            ↓
       economic engine
            ↓
     SimulationResult
```

Excel remains useful for detailed structural tables such as household classes, consumption preferences, company-size mixes, quantity limits, employment-class settings and government demand weights. Scalar run settings come from `SimulationConfig`.

This makes a future FastAPI endpoint straightforward: deserialize user inputs, create/override `SimulationConfig`, call `run_simulation(config)`, and return `result.summary()` plus chart-series data.

## Main package structure

```text
econ_sim/
    __init__.py
    api.py               # public run_simulation() API + SimulationResult
    config.py            # typed SimulationConfig
    engine.py            # monthly simulation loop
    demand.py
    companies.py
    households.py
    labor.py
    government.py
    firm_dynamics.py
    product_dynamics.py
    io.py                # Excel/table loaders and optional file outputs
    utils.py
```

## Running locally

Use Python 3.11+.

```bash
pip install -r requirements.txt
python main.py
```

`main.py` now contains very little orchestration: it loads `SimulationConfig`, calls `run_simulation()`, and prints the main KPIs.

## Results in memory

`run_simulation()` returns a `SimulationResult` object containing DataFrames such as:

- `monthly_macro`
- `yearly_summary`
- `household_income_monthly`
- `government_monthly`
- `product_monthly`
- `product_events`
- `company_events`
- `market_events`
- `products_final`

For web use, no files need to be written.

```python
result = run_simulation(config, save=False)
chart_data = result.yearly_summary
kpis = result.summary()
```

For local Excel/CSV output:

```python
result = run_simulation(config, save=True, output_dir="output")
```

## Tests

```bash
pytest -q
```

The smoke test calls the same clean API that a future FastAPI endpoint will call.

## Next architecture step

The next recommended step is a **scenario comparison service** so the application can run a baseline and one or more changed parameter sets and return KPI differences and chart-ready series. After that, the same API can be placed behind FastAPI and Chart.js for deployment on Render.

## Step 2: baseline vs scenario comparison

The public API now includes `compare_scenarios()`:

```python
from econ_sim import SimulationConfig, compare_scenarios

baseline = SimulationConfig.from_excel("data/Simulation_Settings.xlsx")
comparison = compare_scenarios(
    baseline,
    {
        "High tax": {"tax_rate": 0.30},
        "Fast population growth": {"demographic_growth": 0.02},
    },
)

print(comparison.kpi_table())
```

The comparison object also provides API-ready JSON via `comparison.to_dict()` and aligned yearly chart data via `comparison.yearly_metric(...)` / `comparison.yearly_dashboard()`.

See `STEP2_SCENARIO_COMPARISON.md` for details.

---

# Step 3 — FastAPI Web Layer

The simulation can now be run through HTTP without putting economic logic inside the web application.

## Start the web server

```powershell
pip install -r requirements.txt
uvicorn web_main:app --reload
```

Then open:

- `http://127.0.0.1:8000/` — minimal browser interface
- `http://127.0.0.1:8000/docs` — interactive Swagger API documentation
- `http://127.0.0.1:8000/api/health` — health endpoint

## Public API

- `GET /api/config` — baseline settings
- `POST /api/simulate` — run one simulation with config overrides
- `POST /api/compare` — baseline vs one or more scenarios

The API returns JSON-ready KPI and yearly data. Detailed product/company tables remain internal for now so normal API responses do not become unnecessarily large.

See `STEP3_FASTAPI.md` for request examples and Render deployment notes.


## Step 4: Chart.js dashboard

The browser UI at `/` is now a real simulation dashboard. It includes:

- human-readable percentage inputs (`20` means 20%, not `0.20`),
- settings loaded from `/api/config`,
- single-run and baseline-vs-scenario modes,
- final-year KPI cards,
- Chart.js charts for real GDP, real GDP growth, inflation, unemployment, Gini, debt/GDP, and economic scale,
- a baseline/scenario comparison table,
- raw API output for debugging.

Run locally:

```bash
pip install -r requirements.txt
uvicorn web_main:app --reload
```

Then open `http://127.0.0.1:8000/`.

## Step 5 — UX and automatic interpretation

The dashboard now includes contextual parameter help, live warnings for extreme assumptions, economic-status badges, and a plain-English interpretation panel for both single runs and scenario comparisons. The interpretation describes model outputs; it is not a real-world economic forecast.
