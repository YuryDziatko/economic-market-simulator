from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Iterable, Mapping

from .config import SimulationConfig


@dataclass(frozen=True, slots=True)
class PolicyLimits:
    """Absolute bounds plus maximum annual movement for one policy lever."""

    minimum: float
    maximum: float
    max_annual_change: float


POLICY_LIMITS: dict[str, PolicyLimits] = {
    "tax_rate": PolicyLimits(0.00, 0.60, 0.05),
    "corporate_profit_tax_rate": PolicyLimits(0.00, 0.60, 0.05),
    "interest_rate": PolicyLimits(0.00, 0.20, 0.03),
    "government_consumption_share": PolicyLimits(0.00, 1.00, 0.10),
    "general_transfer_share": PolicyLimits(0.00, 1.00, 0.10),
    "unemployment_transfer_rate": PolicyLimits(0.00, 1.00, 0.10),
    "profit_retention_rate": PolicyLimits(0.00, 1.00, 0.15),
}

POLICY_FIELDS = frozenset(POLICY_LIMITS)
STRUCTURAL_FIELDS = frozenset(
    name for name in SimulationConfig.__dataclass_fields__ if name not in POLICY_FIELDS
)


@dataclass(frozen=True, slots=True)
class PolicyState:
    """Policy settings that may change while one simulated economy is running.

    Structural/calibration settings remain in ``SimulationConfig``.  A future AI
    agent receives this smaller state and can only propose bounded actions against
    it, rather than editing arbitrary engine parameters.
    """

    tax_rate: float
    corporate_profit_tax_rate: float
    interest_rate: float
    government_consumption_share: float
    general_transfer_share: float
    government_reserve_share: float
    unemployment_transfer_rate: float
    profit_retention_rate: float

    @classmethod
    def from_config(cls, config: SimulationConfig) -> "PolicyState":
        return cls(
            tax_rate=config.tax_rate,
            corporate_profit_tax_rate=config.corporate_profit_tax_rate,
            interest_rate=config.interest_rate,
            government_consumption_share=config.government_consumption_share,
            general_transfer_share=config.general_transfer_share,
            government_reserve_share=config.government_reserve_share,
            unemployment_transfer_rate=config.unemployment_transfer_rate,
            profit_retention_rate=config.profit_retention_rate,
        )

    def to_dict(self) -> dict[str, float]:
        return asdict(self)

    def apply_to_config(self, config: SimulationConfig) -> SimulationConfig:
        return config.with_overrides(**self.to_dict())

    def validate(self) -> None:
        for field_name, limits in POLICY_LIMITS.items():
            value = float(getattr(self, field_name))
            if not limits.minimum <= value <= limits.maximum:
                raise ValueError(
                    f"{field_name} must be between {limits.minimum:.3f} and {limits.maximum:.3f}"
                )
        fiscal_total = (
            self.government_consumption_share
            + self.general_transfer_share
            + self.government_reserve_share
        )
        if abs(fiscal_total - 1.0) > 1e-9:
            raise ValueError(
                "government_consumption_share + general_transfer_share + "
                "government_reserve_share must equal 1.0"
            )
        if self.government_reserve_share < 0:
            raise ValueError("government_reserve_share cannot be negative")


@dataclass(frozen=True, slots=True)
class PolicyAction:
    """Annual changes proposed by a policy rule or future AI agent.

    Values are *changes*, not target levels.  For example ``interest_rate=0.01``
    means raise the annual policy rate by one percentage point.
    """

    tax_rate: float = 0.0
    corporate_profit_tax_rate: float = 0.0
    interest_rate: float = 0.0
    government_consumption_share: float = 0.0
    general_transfer_share: float = 0.0
    unemployment_transfer_rate: float = 0.0
    profit_retention_rate: float = 0.0
    reason: str = ""

    def changes(self) -> dict[str, float]:
        return {
            key: float(value)
            for key, value in asdict(self).items()
            if key != "reason" and abs(float(value)) > 1e-15
        }

    def validate(self) -> None:
        for field_name, delta in self.changes().items():
            limits = POLICY_LIMITS[field_name]
            if abs(delta) > limits.max_annual_change + 1e-12:
                raise ValueError(
                    f"{field_name} annual change {delta:+.4f} exceeds allowed "
                    f"±{limits.max_annual_change:.4f}"
                )


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    year: int
    before: PolicyState
    action: PolicyAction
    after: PolicyState

    def to_record(self) -> dict[str, object]:
        record: dict[str, object] = {
            "Year": self.year,
            "Reason": self.action.reason,
        }
        for key, value in self.before.to_dict().items():
            record[f"Before_{key}"] = value
        for key, value in self.action.changes().items():
            record[f"Delta_{key}"] = value
        for key, value in self.after.to_dict().items():
            record[f"After_{key}"] = value
        return record


def apply_policy_action(
    state: PolicyState,
    action: PolicyAction,
    *,
    clamp: bool = False,
) -> PolicyState:
    """Apply a bounded annual policy action.

    ``clamp=False`` is the default for simulation/API use: invalid AI or user
    actions are rejected loudly. ``clamp=True`` is available for exploratory
    agents that deliberately want hard safety rails.
    """

    state.validate()
    action.validate()
    values = state.to_dict()

    for field_name, delta in action.changes().items():
        limits = POLICY_LIMITS[field_name]
        candidate = float(values[field_name]) + delta
        if clamp:
            candidate = max(limits.minimum, min(limits.maximum, candidate))
        elif not limits.minimum <= candidate <= limits.maximum:
            raise ValueError(
                f"{field_name} would become {candidate:.4f}, outside allowed "
                f"[{limits.minimum:.4f}, {limits.maximum:.4f}]"
            )
        values[field_name] = candidate

    # Fiscal spending/transfer shares are changed directly; the reserve is the
    # balancing item so the fiscal allocation always remains exactly 100%.
    reserve = 1.0 - (
        float(values["government_consumption_share"])
        + float(values["general_transfer_share"])
    )
    if reserve < -1e-12:
        raise ValueError(
            "Policy action makes government purchases + general transfers exceed 100% of tax revenue"
        )
    values["government_reserve_share"] = max(reserve, 0.0)

    new_state = replace(state, **values)
    new_state.validate()
    return new_state


def normalize_policy_schedule(
    schedule: Mapping[int, PolicyAction] | Iterable[tuple[int, PolicyAction]] | None,
    *,
    simulation_years: int,
) -> dict[int, PolicyAction]:
    if schedule is None:
        return {}
    items = schedule.items() if isinstance(schedule, Mapping) else schedule
    normalized: dict[int, PolicyAction] = {}
    for raw_year, action in items:
        year = int(raw_year)
        if year < 1 or year > simulation_years:
            raise ValueError(f"Policy action year {year} must be between 1 and {simulation_years}")
        if not isinstance(action, PolicyAction):
            raise TypeError(f"Policy schedule year {year} must contain PolicyAction objects")
        action.validate()
        normalized[year] = action
    return dict(sorted(normalized.items()))
