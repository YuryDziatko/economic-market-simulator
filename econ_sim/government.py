from __future__ import annotations

import numpy as np
import pandas as pd

from .labor import exact_class_counts


def distribute_general_transfers(
    total_transfer_budget: float,
    current_households: int,
    classes: pd.DataFrame,
    government_transfers: pd.DataFrame,
) -> np.ndarray:
    """Distribute a nominal transfer pool across classes using household count × class weight."""
    class_order = classes["Class"].astype(str).tolist()
    settings = government_transfers.set_index("Class").reindex(class_order)
    if settings["Transfer Weight"].isna().any():
        raise ValueError("Government_Transfers must contain every household class")

    counts = exact_class_counts(current_households, classes).astype(float)
    weights = counts * settings["Transfer Weight"].to_numpy(float)
    budget = max(float(total_transfer_budget), 0.0)
    if budget <= 0 or weights.sum() <= 0:
        return np.zeros(len(class_order), dtype=float)
    return budget * weights / weights.sum()


def government_product_demand(
    purchase_budget: float,
    product_meta: pd.DataFrame,
    current_prices: np.ndarray,
    current_production: np.ndarray,
    government_demand: pd.DataFrame,
) -> tuple[np.ndarray, np.ndarray]:
    """Convert the public-purchase budget into product quantities.

    Each product receives a score equal to current nominal production value times
    its division's editable government-priority weight. This keeps government
    demand proportional to the scale of the economy while still tilting purchases
    toward health, education, transport, housing, or other selected divisions.
    """
    n = len(product_meta)
    budget = max(float(purchase_budget), 0.0)
    if budget <= 0 or n == 0:
        return np.zeros(n, dtype=float), np.zeros(n, dtype=float)

    weight_map = government_demand.set_index("Division")["Government Weight"].to_dict()
    divisions = product_meta["Division"].astype(str).to_numpy()
    priority = np.array([max(float(weight_map.get(d, 0.0)), 0.0) for d in divisions])
    production_value = np.maximum(current_production, 0.0) * np.maximum(current_prices, 0.01)
    scores = priority * production_value

    if scores.sum() <= 0:
        scores = production_value.copy()
    if scores.sum() <= 0:
        scores = np.maximum(priority, 0.0)
    if scores.sum() <= 0:
        return np.zeros(n, dtype=float), np.zeros(n, dtype=float)

    spending = budget * scores / scores.sum()
    quantities = np.divide(
        spending,
        np.maximum(current_prices, 0.01),
        out=np.zeros_like(spending),
        where=current_prices > 0,
    )
    return quantities, spending


def fiscal_update(
    *,
    household_tax_revenue: float,
    corporate_tax_revenue: float,
    unemployment_benefits: float,
    general_transfers: float,
    realized_government_purchases: float,
    public_debt_begin: float,
    annual_debt_interest_rate: float,
) -> dict:
    """Close the government budget and carry the public debt stock forward."""
    debt_begin = max(float(public_debt_begin), 0.0)
    interest = debt_begin * max(float(annual_debt_interest_rate), 0.0) / 12.0
    household_tax = max(float(household_tax_revenue), 0.0)
    corporate_tax = max(float(corporate_tax_revenue), 0.0)
    revenue = household_tax + corporate_tax
    spending = (
        max(float(unemployment_benefits), 0.0)
        + max(float(general_transfers), 0.0)
        + max(float(realized_government_purchases), 0.0)
        + interest
    )
    balance = revenue - spending
    debt_end = max(0.0, debt_begin - balance)

    return {
        "Household_Tax_Revenue": household_tax,
        "Corporate_Tax_Revenue": corporate_tax,
        "Government_Revenue": revenue,
        "Unemployment_Benefits": max(float(unemployment_benefits), 0.0),
        "General_Transfers": max(float(general_transfers), 0.0),
        "Government_Purchases": max(float(realized_government_purchases), 0.0),
        "Debt_Interest": interest,
        "Government_Spending": spending,
        "Government_Budget_Balance": balance,
        "Public_Debt_Begin": debt_begin,
        "Public_Debt_End": debt_end,
    }


def next_government_budgets(
    *,
    gross_tax_revenue: float,
    current_purchase_budget: float,
    government_consumption_share: float,
    general_transfer_share: float,
    max_government_demand_growth: float,
) -> tuple[float, float]:
    """Set next month's purchase and general-transfer budgets from current tax revenue."""
    revenue = max(float(gross_tax_revenue), 0.0)
    purchase_target = revenue * max(float(government_consumption_share), 0.0)
    transfer_target = revenue * max(float(general_transfer_share), 0.0)

    current = max(float(current_purchase_budget), 0.0)
    if current > 0:
        cap = abs(float(max_government_demand_growth))
        low = current * (1.0 - cap)
        high = current * (1.0 + cap)
        purchase_target = float(np.clip(purchase_target, max(0.0, low), high))

    return purchase_target, transfer_target
