"""Minimal example of the API the future web app will use."""

from econ_sim import SimulationConfig, run_simulation


base = SimulationConfig.from_excel("data/Simulation_Settings.xlsx").with_overrides(
    simulation_years=3,
    product_innovation_chance=0.005,  # keep this example quick
)
high_tax = base.with_overrides(
    tax_rate=0.30,
    government_consumption_share=0.75,
    general_transfer_share=0.25,
    government_reserve_share=0.00,
)

baseline_result = run_simulation(base)
scenario_result = run_simulation(high_tax)

print("BASELINE", baseline_result.summary())
print("HIGH TAX", scenario_result.summary())
