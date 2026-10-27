from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

from .api import SimulationResult, run_simulation
from .config import SimulationConfig


# KPI metadata is intentionally centralized so the terminal, API, and future web UI
# can all use the same labels and interpretation.
KPI_REGISTRY: dict[str, dict[str, str]] = {
    "nominal_gdp": {"label": "Nominal GDP", "unit": "currency", "delta": "percent"},
    "real_gdp_growth": {"label": "Real GDP growth", "unit": "percent", "delta": "pp"},
    "inflation": {"label": "Inflation", "unit": "percent", "delta": "pp"},
    "unemployment_rate": {"label": "Unemployment rate", "unit": "percent", "delta": "pp"},
    "income_gini": {"label": "Income Gini", "unit": "decimal", "delta": "absolute"},
    "public_debt_to_gdp": {"label": "Debt / GDP", "unit": "percent", "delta": "pp"},
    "final_households": {"label": "Households", "unit": "count", "delta": "percent"},
    "final_companies": {"label": "Companies", "unit": "count", "delta": "percent"},
    "final_products": {"label": "Products", "unit": "count", "delta": "percent"},
    "average_wage_annual": {"label": "Average annual wage", "unit": "currency", "delta": "percent"},
    "government_budget_balance": {"label": "Government budget balance", "unit": "currency", "delta": "absolute"},
    "public_debt": {"label": "Public debt", "unit": "currency", "delta": "percent"},
}

DEFAULT_KPIS: tuple[str, ...] = (
    "nominal_gdp",
    "real_gdp_growth",
    "inflation",
    "unemployment_rate",
    "income_gini",
    "public_debt_to_gdp",
    "final_households",
    "final_companies",
    "final_products",
    "average_wage_annual",
    "government_budget_balance",
    "public_debt",
)


@dataclass(slots=True)
class ScenarioComparison:
    """Results from one baseline and one or more alternative scenarios."""

    baseline_name: str
    baseline: SimulationResult
    scenarios: dict[str, SimulationResult]
    kpis: tuple[str, ...] = DEFAULT_KPIS

    def summaries(self) -> dict[str, dict[str, Any]]:
        return {
            self.baseline_name: _extended_summary(self.baseline),
            **{name: _extended_summary(result) for name, result in self.scenarios.items()},
        }

    def kpi_long(self) -> pd.DataFrame:
        """Long table: one row per KPI and scenario, ideal for APIs and charts."""
        summaries = self.summaries()
        base = summaries[self.baseline_name]
        rows: list[dict[str, Any]] = []

        for scenario_name, summary in summaries.items():
            is_baseline = scenario_name == self.baseline_name
            for key in self.kpis:
                meta = KPI_REGISTRY.get(key, {"label": key, "unit": "number", "delta": "absolute"})
                baseline_value = _as_float(base.get(key))
                scenario_value = _as_float(summary.get(key))
                delta_abs = scenario_value - baseline_value
                delta_relative = _relative_change(baseline_value, scenario_value)
                delta_pp = delta_abs * 100.0

                rows.append({
                    "KPI": key,
                    "Label": meta["label"],
                    "Unit": meta["unit"],
                    "Delta_Type": meta["delta"],
                    "Scenario": scenario_name,
                    "Is_Baseline": is_baseline,
                    "Baseline_Value": baseline_value,
                    "Scenario_Value": scenario_value,
                    "Delta_Absolute": 0.0 if is_baseline else delta_abs,
                    "Delta_Relative": 0.0 if is_baseline else delta_relative,
                    "Delta_Percentage_Points": 0.0 if is_baseline else delta_pp,
                })
        return pd.DataFrame(rows)

    def kpi_table(self) -> pd.DataFrame:
        """Human-friendly wide table with a value and delta column per scenario."""
        summaries = self.summaries()
        base = summaries[self.baseline_name]
        rows: list[dict[str, Any]] = []

        for key in self.kpis:
            meta = KPI_REGISTRY.get(key, {"label": key, "unit": "number", "delta": "absolute"})
            base_value = _as_float(base.get(key))
            row: dict[str, Any] = {
                "KPI": key,
                "Metric": meta["label"],
                "Unit": meta["unit"],
                self.baseline_name: base_value,
            }
            for scenario_name, summary in self.scenarios.items():
                scenario_value = _as_float(_extended_summary(summary).get(key))
                row[scenario_name] = scenario_value
                row[f"{scenario_name} Δ"] = _display_delta(
                    base_value, scenario_value, meta["delta"]
                )
            rows.append(row)
        return pd.DataFrame(rows)

    def yearly_metric(self, column: str) -> pd.DataFrame:
        """Align a yearly-summary column across all scenarios for line/bar charts."""
        frames = {self.baseline_name: self.baseline.yearly_summary}
        frames.update({name: result.yearly_summary for name, result in self.scenarios.items()})

        merged: pd.DataFrame | None = None
        for name, frame in frames.items():
            if column not in frame.columns:
                raise KeyError(f"{column!r} is not present in yearly_summary")
            current = frame[["Year", column]].rename(columns={column: name})
            merged = current if merged is None else merged.merge(current, on="Year", how="outer")
        return merged.sort_values("Year").reset_index(drop=True) if merged is not None else pd.DataFrame()

    def yearly_dashboard(self) -> dict[str, list[dict[str, Any]]]:
        """JSON-friendly datasets for the six charts planned for the web MVP."""
        metrics = {
            "gdp": "Real_GDP_Base_Prices",
            "gdp_growth": "Real_GDP_Growth_YoY",
            "inflation": "Inflation_YoY",
            "unemployment": "Unemployment_Rate_End",
            "gini": "Income_Gini_End_Class_Average",
            "debt_to_gdp": "Debt_to_GDP_End",
        }
        return {
            name: self.yearly_metric(column).replace({np.nan: None}).to_dict(orient="records")
            for name, column in metrics.items()
        }

    def to_dict(self) -> dict[str, Any]:
        """JSON-friendly payload intended for the future FastAPI response."""
        long_table = self.kpi_long().replace({np.nan: None})
        return {
            "baseline": self.baseline_name,
            "scenario_names": list(self.scenarios),
            "summaries": self.summaries(),
            "kpis": long_table.to_dict(orient="records"),
            "yearly": self.yearly_dashboard(),
        }


def compare_scenarios(
    baseline: SimulationConfig,
    scenarios: Mapping[str, SimulationConfig | Mapping[str, Any]],
    *,
    baseline_name: str = "Baseline",
    settings_path: str | Path | None = None,
    product_path: str | Path | None = None,
    kpis: tuple[str, ...] = DEFAULT_KPIS,
) -> ScenarioComparison:
    """Run a baseline and alternatives using the same public simulation API.

    Scenario values may be complete ``SimulationConfig`` objects or dictionaries
    of overrides. Override dictionaries are applied to the baseline, which keeps
    the same random seed by default and makes policy comparisons less noisy.
    """
    if not scenarios:
        raise ValueError("At least one scenario is required")

    baseline_result = run_simulation(
        baseline,
        settings_path=settings_path,
        product_path=product_path,
        save=False,
    )

    results: dict[str, SimulationResult] = {}
    for name, scenario in scenarios.items():
        if not str(name).strip():
            raise ValueError("Scenario names cannot be blank")
        if name == baseline_name:
            raise ValueError(f"Scenario name {name!r} conflicts with baseline_name")

        if isinstance(scenario, SimulationConfig):
            scenario_config = scenario
        else:
            scenario_config = baseline.with_overrides(**dict(scenario))

        results[str(name)] = run_simulation(
            scenario_config,
            settings_path=settings_path,
            product_path=product_path,
            save=False,
        )

    return ScenarioComparison(
        baseline_name=baseline_name,
        baseline=baseline_result,
        scenarios=results,
        kpis=tuple(kpis),
    )


def _extended_summary(result: SimulationResult) -> dict[str, Any]:
    summary = dict(result.summary())
    final = result.final_year
    summary.update({
        "final_households": int(final.get("Household_Count_End", result.config.num_households)) if final else result.config.num_households,
        "final_companies": int(final.get("Company_Count_End", result.config.num_companies)) if final else result.config.num_companies,
        "average_wage_annual": float(final.get("Average_Wage_Annual", 0.0)) if final else 0.0,
        "government_budget_balance": float(final.get("Government_Budget_Balance", 0.0)) if final else 0.0,
        "public_debt": float(final.get("Public_Debt_End", 0.0)) if final else 0.0,
    })
    return summary


def _as_float(value: Any) -> float:
    if value is None:
        return 0.0
    return float(value)


def _relative_change(baseline: float, scenario: float) -> float | None:
    if abs(baseline) < 1e-12:
        return None
    return (scenario / baseline) - 1.0


def _display_delta(baseline: float, scenario: float, delta_type: str) -> float | None:
    if delta_type == "pp":
        return (scenario - baseline) * 100.0
    if delta_type == "percent":
        return _relative_change(baseline, scenario)
    return scenario - baseline
