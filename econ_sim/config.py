from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, get_type_hints

import pandas as pd


@dataclass(frozen=True, slots=True)
class SimulationConfig:
    """Typed scalar settings for one simulation run.

    The engine receives this object instead of reading Excel or accepting dozens
    of independent keyword arguments. Excel, a web form, tests, or a future API
    can all create the same configuration object.
    """

    # Core economy
    target_gini: float = 0.30
    tax_rate: float = 0.20
    interest_rate: float = 0.00
    annual_inflation: float = 0.02
    num_households: int = 1000
    num_companies: int = 1000
    simulation_years: int = 10
    random_seed: int = 42
    monthly_price_noise_std: float = 0.0025

    # Demography / firms / equilibrium
    demographic_growth: float = 0.01
    company_growth_sensitivity: float = 1.0
    allow_company_exits: bool = False
    price_adjustment_speed: float = 0.12
    production_adjustment_speed: float = 0.25
    max_monthly_price_change: float = 0.10
    max_monthly_production_change: float = 0.15
    initial_inventory_months: float = 0.0

    # Intelligent entry / exit
    entry_shortage_weight: float = 0.45
    entry_demand_growth_weight: float = 0.30
    entry_margin_weight: float = 0.25
    exit_surplus_weight: float = 0.40
    exit_demand_decline_weight: float = 0.30
    exit_loss_weight: float = 0.30
    max_entries_per_product: int = 5
    max_exits_per_product: int = 3
    entry_capacity_share: float = 0.15
    exit_capacity_share: float = 1.00
    min_entry_score: float = 0.05
    min_exit_score: float = 0.15

    # Product innovation
    product_innovation_chance: float = 0.02
    innovation_demand_share: float = 0.10
    innovation_output_share: float = 0.10
    innovation_price_min_multiplier: float = 0.85
    innovation_price_max_multiplier: float = 1.15
    innovation_elasticity_noise: float = 0.05
    innovation_initial_firms: int = 1
    max_new_products_per_month: int = 0
    new_products_can_innovate: bool = True

    # Labor market
    labor_force_participation: float = 0.65
    initial_unemployment_rate: float = 0.04
    labor_income_share_p0: float = 0.65
    labor_output_elasticity: float = 0.90
    annual_labor_productivity_growth: float = 0.015
    wage_adjustment_speed: float = 0.08
    wage_inflation_pass_through: float = 0.50
    max_monthly_wage_change: float = 0.05
    unemployment_transfer_rate: float = 0.30
    labor_wage_demand_elasticity: float = 0.35

    # Government
    corporate_profit_tax_rate: float = 0.20
    government_consumption_share: float = 0.80
    general_transfer_share: float = 0.20
    government_reserve_share: float = 0.00
    initial_public_debt: float = 0.0
    debt_interest_rate: float = 0.03
    max_government_demand_growth: float = 0.10

    @classmethod
    def from_mapping(cls, values: dict[str, Any]) -> "SimulationConfig":
        """Create a config from a dict such as General_Settings key/value pairs."""
        hints = get_type_hints(cls)
        kwargs: dict[str, Any] = {}
        for name, expected_type in hints.items():
            if name not in values or pd.isna(values[name]):
                continue
            value = values[name]
            if expected_type is bool:
                if isinstance(value, str):
                    kwargs[name] = value.strip().lower() in {"1", "true", "yes", "y", "on"}
                else:
                    kwargs[name] = bool(int(value))
            elif expected_type is int:
                kwargs[name] = int(value)
            elif expected_type is float:
                kwargs[name] = float(value)
            else:
                kwargs[name] = value
        config = cls(**kwargs)
        config.validate()
        return config

    @classmethod
    def from_excel(cls, path: str | Path) -> "SimulationConfig":
        """Load only scalar settings from the Excel control workbook."""
        df = pd.read_excel(Path(path), sheet_name="General_Settings", header=2)
        df = df.dropna(subset=["Key"])
        values = dict(zip(df["Key"].astype(str), df["Value"]))
        return cls.from_mapping(values)

    def with_overrides(self, **changes: Any) -> "SimulationConfig":
        """Return a validated copy, useful for scenarios and web-form inputs."""
        config = replace(self, **changes)
        config.validate()
        return config

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def validate(self) -> None:
        if not 0 <= self.target_gini < 1:
            raise ValueError("target_gini must be between 0 and 1")
        if self.num_households <= 0:
            raise ValueError("num_households must be positive")
        if self.num_companies <= 0:
            raise ValueError("num_companies must be positive")
        if self.simulation_years <= 0:
            raise ValueError("simulation_years must be positive")
        if self.innovation_price_min_multiplier <= 0:
            raise ValueError("innovation_price_min_multiplier must be positive")
        if self.innovation_price_max_multiplier < self.innovation_price_min_multiplier:
            raise ValueError("innovation launch price max must be >= min")

        probability_fields = {
            "tax_rate": self.tax_rate,
            "product_innovation_chance": self.product_innovation_chance,
            "innovation_demand_share": self.innovation_demand_share,
            "innovation_output_share": self.innovation_output_share,
            "labor_force_participation": self.labor_force_participation,
            "initial_unemployment_rate": self.initial_unemployment_rate,
            "labor_income_share_p0": self.labor_income_share_p0,
            "unemployment_transfer_rate": self.unemployment_transfer_rate,
            "corporate_profit_tax_rate": self.corporate_profit_tax_rate,
        }
        for name, value in probability_fields.items():
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")

        fiscal_total = (
            self.government_consumption_share
            + self.general_transfer_share
            + self.government_reserve_share
        )
        if abs(fiscal_total - 1.0) > 1e-6:
            raise ValueError(
                "government_consumption_share + general_transfer_share + "
                f"government_reserve_share must equal 1.0; got {fiscal_total:.6f}"
            )
