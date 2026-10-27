# Step 1 — SimulationConfig + Clean Engine API

## What changed

- Added `econ_sim/config.py` with immutable, validated `SimulationConfig`.
- Added `econ_sim/api.py` with public `run_simulation(config)` and `SimulationResult`.
- Refactored `econ_sim/engine.py` so scalar settings arrive through `SimulationConfig` instead of ~50 arguments.
- Refactored `main.py` into a thin CLI adapter.
- Kept Excel as the default local input source via `SimulationConfig.from_excel(...)`.
- Added `with_overrides(...)` for baseline/scenario runs and future web-form input.
- Added `SimulationResult.summary()` for JSON-friendly KPI output.
- Added tests and a scenario example.

## Regression check

A one-year Phase-3 run using the new API reproduced the previous behavior:

- final products: 611
- new products: 134
- real GDP growth: ~0.82%
- inflation: ~-4.57%
- unemployment: ~4.47%
- government revenue: ~$56.99M
- government spending: ~$57.55M
- public debt/GDP: ~0.42%

`pytest -q` passes all 3 tests.
