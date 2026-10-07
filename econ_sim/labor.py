from __future__ import annotations

import numpy as np
import pandas as pd

from .utils import gini


def exact_class_counts(total_households: int, classes: pd.DataFrame) -> np.ndarray:
    """Return integer household counts by class that sum exactly to total_households."""
    shares = classes["Population Share"].to_numpy(float)
    raw = shares * int(total_households)
    counts = np.floor(raw).astype(int)
    remainder = int(total_households) - int(counts.sum())
    if remainder > 0:
        counts[np.argsort(-(raw - counts))[:remainder]] += 1
    return counts


def prepare_labor_market(
    households: pd.DataFrame,
    classes: pd.DataFrame,
    employment_settings: pd.DataFrame,
    labor_force_participation: float,
    initial_unemployment_rate: float,
    labor_income_share_p0: float,
    base_gdp_monthly: float,
) -> dict:
    class_order = classes["Class"].astype(str).tolist()
    settings = employment_settings.set_index("Class").reindex(class_order)
    if settings.isna().any().any():
        raise ValueError("Employment_Settings must contain every household class")

    initial_counts = (
        households.groupby("Class", observed=True)["Household_ID"]
        .count().reindex(class_order).fillna(0).to_numpy(int)
    )
    lf_multiplier = settings["Labor-Force Participation Multiplier"].to_numpy(float)
    class_participation = np.clip(float(labor_force_participation) * lf_multiplier, 0.0, 1.0)
    labor_force_by_class = initial_counts * class_participation
    labor_force = float(labor_force_by_class.sum())
    if labor_force <= 0:
        raise ValueError("Initial labor force is zero; increase labor-force participation")

    target_unemployment = float(np.clip(initial_unemployment_rate, 0.0, 0.95))
    base_employment = labor_force * (1.0 - target_unemployment)
    if base_employment <= 0:
        raise ValueError("Initial employment is zero")

    labor_share = float(np.clip(labor_income_share_p0, 0.01, 0.99))
    base_labor_income = float(base_gdp_monthly) * labor_share
    base_average_wage = base_labor_income / base_employment

    return {
        "class_order": class_order,
        "wage_multipliers": settings["Wage Multiplier"].to_numpy(float),
        "capital_weights": settings["Capital Income Weight"].to_numpy(float),
        "participation_multipliers": lf_multiplier,
        "base_labor_force": labor_force,
        "base_employment": base_employment,
        "base_average_wage": base_average_wage,
        "target_unemployment_rate": target_unemployment,
        "labor_income_share_p0": labor_share,
    }


def labor_and_income_state(
    *,
    year: int,
    period_month: int,
    month_in_year: int,
    current_households: int,
    classes: pd.DataFrame,
    labor_calibration: dict,
    labor_force_participation: float,
    annual_labor_productivity_growth: float,
    labor_output_elasticity: float,
    labor_wage_demand_elasticity: float,
    price_level: float,
    base_real_output: float,
    planned_real_output: float,
    nominal_output: float,
    average_wage: float,
    tax_rate: float,
    unemployment_transfer_rate: float,
) -> tuple[dict, pd.DataFrame, float]:
    """
    Compute labor demand, employment, class income and a production labor-capacity factor.

    Desired employment is anchored to Period-0 employment and responds to real output,
    while labor productivity reduces workers required for the same real output.
    """
    class_order = labor_calibration["class_order"]
    counts = exact_class_counts(current_households, classes)
    participation = np.clip(
        float(labor_force_participation) * labor_calibration["participation_multipliers"],
        0.0,
        1.0,
    )
    labor_force_class = counts * participation
    labor_force = float(labor_force_class.sum())

    productivity_index = (1.0 + float(annual_labor_productivity_growth)) ** (period_month / 12.0)
    output_ratio = max(float(planned_real_output) / max(float(base_real_output), 1e-9), 0.0)
    elasticity = max(float(labor_output_elasticity), 0.01)
    current_real_wage = max(float(average_wage) / max(float(price_level), 1e-9), 1e-9)
    base_real_wage = max(float(labor_calibration["base_average_wage"]), 1e-9)
    wage_elasticity = max(float(labor_wage_demand_elasticity), 0.0)
    wage_demand_factor = (base_real_wage / current_real_wage) ** wage_elasticity
    wage_demand_factor = float(np.clip(wage_demand_factor, 0.50, 2.00))

    desired_employment_pre_constraint = (
        float(labor_calibration["base_employment"])
        * (output_ratio ** elasticity)
        * wage_demand_factor
        / max(productivity_index, 1e-9)
    )

    if desired_employment_pre_constraint > labor_force and desired_employment_pre_constraint > 0:
        # If labor is binding, scale physical production so labor required no longer
        # exceeds the available labor force. Invert the employment/output elasticity.
        production_factor = (labor_force / desired_employment_pre_constraint) ** (1.0 / elasticity)
        production_factor = float(np.clip(production_factor, 0.0, 1.0))
    else:
        production_factor = 1.0

    adjusted_output_ratio = output_ratio * production_factor
    desired_employment = (
        float(labor_calibration["base_employment"])
        * (max(adjusted_output_ratio, 0.0) ** elasticity)
        * wage_demand_factor
        / max(productivity_index, 1e-9)
    )
    employment = min(desired_employment, labor_force)
    unemployment = max(labor_force - employment, 0.0)
    unemployment_rate = unemployment / labor_force if labor_force > 0 else 0.0
    employment_rate = employment / labor_force if labor_force > 0 else 0.0

    # Employment is allocated proportionally to each class's labor force.
    employed_class = (
        labor_force_class * employment_rate
        if labor_force > 0 else np.zeros_like(labor_force_class)
    )
    unemployed_class = np.maximum(labor_force_class - employed_class, 0.0)

    # Wage index is an economy-wide average offer. In a severe downturn, actual
    # labor compensation cannot exceed total nominal production income.
    wage_offer = max(float(average_wage), 0.0)
    potential_labor_income = employment * wage_offer
    labor_income_total = min(potential_labor_income, max(float(nominal_output), 0.0))
    paid_average_wage = labor_income_total / employment if employment > 0 else 0.0

    wage_mult = labor_calibration["wage_multipliers"]
    raw_labor = employed_class * wage_mult
    if raw_labor.sum() > 0:
        labor_income_class = labor_income_total * raw_labor / raw_labor.sum()
    else:
        labor_income_class = np.zeros_like(raw_labor)

    # The remainder of national production income is capital/business income.
    # This closes the household income side until investment/government are modeled.
    capital_income_total = max(float(nominal_output) - labor_income_total, 0.0)
    capital_weight = counts * labor_calibration["capital_weights"]
    if capital_weight.sum() > 0:
        capital_income_class = capital_income_total * capital_weight / capital_weight.sum()
    else:
        capital_income_class = np.zeros_like(capital_weight, dtype=float)

    transfers_class = unemployed_class * paid_average_wage * float(unemployment_transfer_rate)
    gross_income_class = labor_income_class + capital_income_class + transfers_class
    taxes_class = gross_income_class * float(tax_rate)
    disposable_class = gross_income_class - taxes_class
    savings_class = np.zeros_like(disposable_class)
    consumption_class = disposable_class - savings_class

    avg_income = np.divide(
        gross_income_class,
        counts,
        out=np.zeros_like(gross_income_class, dtype=float),
        where=counts > 0,
    )
    avg_labor_income = np.divide(
        labor_income_class,
        counts,
        out=np.zeros_like(labor_income_class, dtype=float),
        where=counts > 0,
    )
    avg_capital_income = np.divide(
        capital_income_class,
        counts,
        out=np.zeros_like(capital_income_class, dtype=float),
        where=counts > 0,
    )

    # Approximate monthly Gini from class-average household income. This is a
    # transparent Phase-2 measure; individual household income dynamics come later.
    expanded = np.repeat(avg_income, counts.astype(int)) if counts.sum() > 0 else np.array([])
    income_gini = float(gini(expanded)) if len(expanded) else 0.0

    rows = []
    for i, class_name in enumerate(class_order):
        rows.append({
            "Period_Month": period_month,
            "Year": year,
            "Month_in_Year": month_in_year,
            "Class": class_name,
            "Households": int(counts[i]),
            "Labor_Force": float(labor_force_class[i]),
            "Employed": float(employed_class[i]),
            "Unemployed": float(unemployed_class[i]),
            "Employment_Rate": employment_rate,
            "Average_Wage_Employed": (
                labor_income_class[i] / employed_class[i] if employed_class[i] > 0 else 0.0
            ),
            "Labor_Income": float(labor_income_class[i]),
            "Capital_Income": float(capital_income_class[i]),
            "Transfers": float(transfers_class[i]),
            "Gross_Income": float(gross_income_class[i]),
            "Taxes": float(taxes_class[i]),
            "Disposable_Income": float(disposable_class[i]),
            "Savings": float(savings_class[i]),
            "Consumption_Budget": float(consumption_class[i]),
            "Average_Gross_Income_Per_Household": float(avg_income[i]),
            "Average_Labor_Income_Per_Household": float(avg_labor_income[i]),
            "Average_Capital_Income_Per_Household": float(avg_capital_income[i]),
            "Income_Share": (
                float(gross_income_class[i] / gross_income_class.sum())
                if gross_income_class.sum() > 0 else 0.0
            ),
        })

    macro = {
        "Labor_Force": labor_force,
        "Employment": employment,
        "Unemployment": unemployment,
        "Employment_Rate": employment_rate,
        "Unemployment_Rate": unemployment_rate,
        "Desired_Employment_Pre_Constraint": desired_employment_pre_constraint,
        "Labor_Constraint_Production_Factor": production_factor,
        "Average_Wage": paid_average_wage,
        "Labor_Income": labor_income_total,
        "Capital_Income": capital_income_total,
        "Transfers": float(transfers_class.sum()),
        "Household_Gross_Income": float(gross_income_class.sum()),
        "Household_Taxes": float(taxes_class.sum()),
        "Household_Disposable_Income": float(disposable_class.sum()),
        "Household_Consumption_Budget": float(consumption_class.sum()),
        "Income_Gini_Class_Average": income_gini,
        "Labor_Productivity_Index": productivity_index,
        "Real_Wage_Index": current_real_wage / base_real_wage,
        "Labor_Wage_Demand_Factor": wage_demand_factor,
    }
    return macro, pd.DataFrame(rows), production_factor


def next_average_wage(
    current_paid_wage: float,
    labor_force: float,
    desired_employment_pre_constraint: float,
    target_unemployment_rate: float,
    inflation_mom: float,
    wage_adjustment_speed: float,
    wage_inflation_pass_through: float,
    max_monthly_wage_change: float,
) -> tuple[float, float]:
    target_employment = max(labor_force * (1.0 - target_unemployment_rate), 1e-9)
    labor_gap = desired_employment_pre_constraint / target_employment - 1.0
    wage_change = (
        float(wage_inflation_pass_through) * float(inflation_mom)
        + float(wage_adjustment_speed) * labor_gap
    )
    cap = abs(float(max_monthly_wage_change))
    wage_change = float(np.clip(wage_change, -cap, cap))
    next_wage = max(0.01, float(current_paid_wage) * (1.0 + wage_change))
    return next_wage, wage_change
