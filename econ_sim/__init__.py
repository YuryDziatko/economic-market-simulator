"""Economic market simulation package."""

from .api import SimulationResult, run_simulation
from .comparison import ScenarioComparison, compare_scenarios
from .config import SimulationConfig
from .policy import (
    POLICY_FIELDS, POLICY_LIMITS, STRUCTURAL_FIELDS,
    PolicyAction, PolicyDecision, PolicyLimits, PolicyState,
    apply_policy_action, normalize_policy_schedule,
)

__all__ = [
    "SimulationConfig",
    "SimulationResult",
    "ScenarioComparison",
    "PolicyLimits",
    "PolicyState",
    "PolicyAction",
    "PolicyDecision",
    "POLICY_FIELDS",
    "STRUCTURAL_FIELDS",
    "POLICY_LIMITS",
    "apply_policy_action",
    "normalize_policy_schedule",
    "run_simulation",
    "compare_scenarios",
]
