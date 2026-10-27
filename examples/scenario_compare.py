from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

"""Step 2 example: compare multiple policy scenarios against one baseline."""

from econ_sim import SimulationConfig, compare_scenarios


baseline = SimulationConfig.from_excel("data/Simulation_Settings.xlsx").with_overrides(
    simulation_years=3,
    product_innovation_chance=0.005,
)

comparison = compare_scenarios(
    baseline,
    {
        "Higher income tax": {"tax_rate": 0.30},
        "Higher population growth": {"demographic_growth": 0.02},
        "Lower innovation": {"product_innovation_chance": 0.001},
    },
)

print(comparison.kpi_table().to_string(index=False))
print("\nGDP chart data:")
print(comparison.yearly_metric("Real_GDP_Base_Prices").to_string(index=False))
