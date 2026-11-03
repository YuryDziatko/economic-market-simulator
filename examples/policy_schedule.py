"""Example of a controlled multi-year policy path.

A future deterministic or AI policy agent will generate the same PolicyAction
objects after observing each year's economy.
"""

from econ_sim import PolicyAction, SimulationConfig, run_simulation

config = SimulationConfig.from_excel("data/Simulation_Settings.xlsx").with_overrides(
    simulation_years=5,
)

policy_schedule = {
    2: PolicyAction(
        interest_rate=0.01,
        reason="Inflation-control example: raise the policy rate by 1 percentage point.",
    ),
    3: PolicyAction(
        tax_rate=-0.02,
        corporate_profit_tax_rate=-0.01,
        reason="Growth example: reduce household and corporate tax rates.",
    ),
    4: PolicyAction(
        government_consumption_share=0.03,
        general_transfer_share=-0.03,
        reason="Reallocate three percentage points of tax revenue toward government purchases.",
    ),
}

result = run_simulation(config, policy_schedule=policy_schedule)
print(result.policy_history.to_string(index=False))
print(result.yearly_summary[[
    "Year", "Real_GDP_Growth_YoY", "Inflation_YoY", "Unemployment_Rate_End",
    "Income_Tax_Rate_End", "Corporate_Tax_Rate_End", "Interest_Rate_End",
]].to_string(index=False))
