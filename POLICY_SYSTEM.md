# Policy System — controlled interface for future AI government agents

## Purpose

The economic engine now separates **structural/calibration parameters** from **policy levers** that may change while a simulation is running.

A future rule-based or LLM policy agent must not edit `SimulationConfig` arbitrarily. Instead it observes the economy and proposes a bounded `PolicyAction`. The engine validates that action, converts it into a new `PolicyState`, logs the decision, and continues the same simulated economy.

## Allowed policy levers (v1)

| Lever | Absolute range | Maximum change per simulated year |
|---|---:|---:|
| Household income tax | 0% to 60% | ±5 percentage points |
| Corporate profit tax | 0% to 60% | ±5 percentage points |
| Policy interest rate | 0% to 20% | ±3 percentage points |
| Government purchase share | 0% to 100% | ±10 percentage points |
| General transfer share | 0% to 100% | ±10 percentage points |
| Unemployment benefit rate | 0% to 100% | ±10 percentage points |
| Profit-retention rate | 0% to 100% | ±15 percentage points |

Government purchases + general transfers may not exceed 100% of tax revenue. The reserve share is the balancing item.

## Structural parameters

Everything not in the policy list remains structural during a run. Examples include population growth mechanics, price/production adjustment speeds, product innovation behavior, labor productivity assumptions, capital efficiency, depreciation, and behavioral elasticities.

This separation is intentional: an AI can make policy decisions, but it cannot rewrite the laws/calibration of the simulated economy while the run is in progress.

## Python API

```python
from econ_sim import PolicyAction, SimulationConfig, run_simulation

config = SimulationConfig.from_excel("data/Simulation_Settings.xlsx").with_overrides(
    simulation_years=5,
)

schedule = {
    2: PolicyAction(
        interest_rate=0.01,
        reason="Raise rates by one percentage point.",
    ),
    3: PolicyAction(
        tax_rate=-0.02,
        reason="Cut household income tax by two percentage points.",
    ),
}

result = run_simulation(config, policy_schedule=schedule)
print(result.policy_history)
```

`PolicyAction` values are **deltas**, not target levels.

## Web API

### GET `/api/policy/limits`

Returns policy fields, structural fields and bounds. This endpoint will be useful for the future AI prompt/tool schema and for dashboard controls.

### POST `/api/policy/simulate`

Example:

```json
{
  "overrides": {
    "simulation_years": 5
  },
  "policy_schedule": {
    "2": {
      "interest_rate": 0.01,
      "reason": "Inflation is above target."
    },
    "3": {
      "tax_rate": -0.02,
      "reason": "Support household demand."
    }
  },
  "include_monthly": false
}
```

The response contains normal simulation results plus `policy_history`.

## Policy log

Every applied decision records:

- simulated year;
- free-text reason;
- policy values before the action;
- non-zero action deltas;
- policy values after the action.

The monthly macro table also records the active policy settings each month, and the annual summary includes end-of-year policy values.

## Next step

Build deterministic policy agents that observe the prior year's economy and generate one `PolicyAction` per year. Once their behavior is stable, an LLM/AI agent can implement the same interface without any change to the economic engine.
