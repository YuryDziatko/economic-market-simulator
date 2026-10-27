# Step 2 — Baseline vs Scenario Comparison

The project now has a reusable comparison layer on top of `run_simulation(config)`.

## Basic use

```python
from econ_sim import SimulationConfig, compare_scenarios

baseline = SimulationConfig.from_excel("data/Simulation_Settings.xlsx")

comparison = compare_scenarios(
    baseline,
    {
        "30% income tax": {"tax_rate": 0.30},
        "2% population growth": {"demographic_growth": 0.02},
    },
)
```

The dictionary values may be either:

- config override dictionaries, or
- complete `SimulationConfig` objects.

Override dictionaries inherit all unchanged baseline settings, including the random seed. This is useful because a policy scenario should ideally be compared with the same random economy.

## KPI table

```python
comparison.kpi_table()
```

Returns a wide pandas DataFrame containing the baseline value, each scenario value, and a delta column.

Percentage variables such as inflation and unemployment use percentage-point deltas. Level variables such as GDP and product count use relative percentage changes when that is meaningful.

## API-friendly table

```python
comparison.kpi_long()
```

Returns one row per KPI/scenario with:

- baseline value
- scenario value
- absolute change
- relative change
- percentage-point change

This format maps cleanly into JSON and web tables.

## Chart datasets

```python
comparison.yearly_metric("Real_GDP_Base_Prices")
```

returns:

```text
Year | Baseline | Scenario A | Scenario B
```

`comparison.yearly_dashboard()` already builds datasets for the six planned MVP charts:

- real GDP
- real GDP growth
- inflation
- unemployment
- Gini
- debt/GDP

## Future FastAPI endpoint

The web service can eventually do approximately:

```python
comparison = compare_scenarios(baseline, scenarios)
return comparison.to_dict()
```

No Excel parsing or pandas transformation will need to exist inside the route itself.
