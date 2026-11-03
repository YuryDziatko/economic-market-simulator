from __future__ import annotations

from dataclasses import fields
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from econ_sim import SimulationConfig


CONFIG_FIELDS = {field.name for field in fields(SimulationConfig)}


class SimulationRequest(BaseModel):
    """Run one simulation by overriding the Excel/default baseline config."""

    model_config = ConfigDict(extra="forbid")

    overrides: dict[str, Any] = Field(default_factory=dict)
    include_monthly: bool = False

    @field_validator("overrides")
    @classmethod
    def validate_override_names(cls, value: dict[str, Any]) -> dict[str, Any]:
        unknown = sorted(set(value) - CONFIG_FIELDS)
        if unknown:
            raise ValueError(f"Unknown SimulationConfig field(s): {', '.join(unknown)}")
        return value


class CompareRequest(BaseModel):
    """Compare a baseline with one or more named scenarios."""

    model_config = ConfigDict(extra="forbid")

    baseline_overrides: dict[str, Any] = Field(default_factory=dict)
    scenarios: dict[str, dict[str, Any]]
    baseline_name: str = "Baseline"

    @field_validator("baseline_overrides")
    @classmethod
    def validate_baseline_overrides(cls, value: dict[str, Any]) -> dict[str, Any]:
        unknown = sorted(set(value) - CONFIG_FIELDS)
        if unknown:
            raise ValueError(f"Unknown SimulationConfig field(s): {', '.join(unknown)}")
        return value

    @field_validator("scenarios")
    @classmethod
    def validate_scenarios(cls, value: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        if not value:
            raise ValueError("At least one scenario is required")
        for name, overrides in value.items():
            if not name.strip():
                raise ValueError("Scenario names cannot be blank")
            unknown = sorted(set(overrides) - CONFIG_FIELDS)
            if unknown:
                raise ValueError(
                    f"Scenario {name!r} has unknown SimulationConfig field(s): {', '.join(unknown)}"
                )
        return value

class PolicyActionInput(BaseModel):
    """One bounded annual policy change. Values are deltas, not target levels."""

    model_config = ConfigDict(extra="forbid")

    tax_rate: float = 0.0
    corporate_profit_tax_rate: float = 0.0
    interest_rate: float = 0.0
    government_consumption_share: float = 0.0
    general_transfer_share: float = 0.0
    unemployment_transfer_rate: float = 0.0
    profit_retention_rate: float = 0.0
    reason: str = ""


class PolicySimulationRequest(BaseModel):
    """Run one economy with annual controlled policy actions."""

    model_config = ConfigDict(extra="forbid")

    overrides: dict[str, Any] = Field(default_factory=dict)
    policy_schedule: dict[int, PolicyActionInput] = Field(default_factory=dict)
    include_monthly: bool = False

    @field_validator("overrides")
    @classmethod
    def validate_policy_baseline_override_names(cls, value: dict[str, Any]) -> dict[str, Any]:
        unknown = sorted(set(value) - CONFIG_FIELDS)
        if unknown:
            raise ValueError(f"Unknown SimulationConfig field(s): {', '.join(unknown)}")
        return value
