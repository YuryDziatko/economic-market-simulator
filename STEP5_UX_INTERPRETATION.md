# Step 5 — Dashboard UX and Interpretation

Step 5 improves the dashboard without changing the economics engine.

## Added

- Contextual `i` tooltips beside important parameters.
- Human-readable percentage inputs remain in place (`20` means `20%`).
- Live assumption warnings for extreme population growth, inflation, tax rates, product innovation, productivity, inequality, and long horizons.
- Final-year status badges for growth, inflation, unemployment, inequality and debt/GDP.
- Automatic plain-English interpretation of a single simulation.
- Automatic interpretation of baseline-vs-scenario differences.
- Explicit reminder that status labels and interpretation describe the simulated economy and are not real-world forecasts.

## Interpretation philosophy

The dashboard describes signals already present in the model output. It avoids claiming that a single variable definitely caused an outcome when the model contains multiple interacting feedback loops.

## Run locally

```powershell
pip install -r requirements.txt
uvicorn web_main:app --reload
```

Open `http://127.0.0.1:8000/`.
