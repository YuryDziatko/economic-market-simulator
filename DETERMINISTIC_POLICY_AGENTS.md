# Deterministic Policy Agents

This step adds five reproducible annual policy strategies on top of `PolicyState` and `PolicyAction`.

## Agents

- `technocratic` — balances inflation, employment, growth, and debt.
- `market_liberal` — emphasizes private investment, lower taxes, and restrained transfers.
- `social_democratic` — emphasizes employment, redistribution, and public demand.
- `state_directed` — emphasizes public demand and capital formation through stronger intervention.
- `hybrid` — uses moderate responses across growth, inflation, jobs, inequality, and debt.

These are stylized simulation strategies, not empirical descriptions of real governments or political systems.

## Decision timing

The economic engine still runs monthly. A deterministic agent observes the completed prior year and makes one bounded policy decision at the beginning of the next year. Therefore a 10-year run produces at most 9 agent decisions (Years 2–10).

Each observation contains real GDP growth, 12-month inflation, unemployment, Gini, debt/GDP, capacity utilization, household saving rate, investment/GDP, and the government budget balance/GDP.

All actions pass through the existing policy limits. The agent cannot modify structural parameters.

## Python

```python
from econ_sim import SimulationConfig, get_agent, run_simulation

config = SimulationConfig.from_excel("data/Simulation_Settings.xlsx")
result = run_simulation(config, policy_agent=get_agent("technocratic"))
print(result.policy_history)
```

## API

`GET /api/policy/agents` lists available agents and their priority weights.

`POST /api/policy/agents/simulate` example:

```json
{
  "agent": "hybrid",
  "overrides": {"simulation_years": 10},
  "include_monthly": false
}
```

The response includes the agent profile, final summary, yearly results, and a policy-decision history with the observed state that triggered each decision.
