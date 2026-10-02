from __future__ import annotations

import numpy as np
import pandas as pd


def calibrate_baseline_spending(
    products: pd.DataFrame,
    households: pd.DataFrame,
    basket_preferences: pd.DataFrame,
    class_order: list[str],
    tolerance: float = 1e-9,
    max_iter: int = 10000,
) -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
    """
    Build a class x product Period-0 spending matrix using iterative proportional fitting (RAS).

    Row targets = actual Period-0 class consumption budgets.
    Column targets = actual Period-0 product revenue.
    Seed weights = class budget x division preference multiplier.

    Therefore Period 0 reconciles exactly on both sides:
      total planned spending by class == class budget
      total planned spending on each product == product P0 revenue
    """
    class_budget = (
        households.groupby("Class", observed=True)["Consumption"].sum()
        .reindex(class_order)
        .fillna(0.0)
        .to_numpy(float)
    )
    product_revenue = products["Revenue_P0"].to_numpy(float)

    if not np.isclose(class_budget.sum(), product_revenue.sum(), atol=0.01):
        raise ValueError("Household consumption and product P0 revenue must reconcile before basket calibration")

    pref = basket_preferences.set_index("Division")
    product_divisions = products["Division"].astype(str).tolist()

    seed = np.empty((len(class_order), len(products)), dtype=float)
    for c_idx, class_name in enumerate(class_order):
        multipliers = np.array([float(pref.loc[d, class_name]) for d in product_divisions], dtype=float)
        seed[c_idx, :] = np.maximum(product_revenue, 1e-12) * multipliers

    # If any product has zero Period-0 revenue, it must have zero spending target.
    zero_cols = product_revenue <= 0
    seed[:, zero_cols] = 0.0
    positive_cols = ~zero_cols
    seed[:, positive_cols] = np.maximum(seed[:, positive_cols], 1e-15)

    x = seed.copy()
    total = product_revenue.sum()
    if total <= 0:
        raise ValueError("Period-0 GDP is zero")
    x *= total / x.sum()

    for _ in range(max_iter):
        row_sums = x.sum(axis=1)
        row_factors = np.divide(class_budget, row_sums, out=np.ones_like(class_budget), where=row_sums > 0)
        x *= row_factors[:, None]

        col_sums = x.sum(axis=0)
        col_factors = np.divide(product_revenue, col_sums, out=np.ones_like(product_revenue), where=col_sums > 0)
        x *= col_factors[None, :]

        max_row_err = np.max(np.abs(x.sum(axis=1) - class_budget))
        max_col_err = np.max(np.abs(x.sum(axis=0) - product_revenue))
        if max(max_row_err, max_col_err) <= max(0.01, tolerance * total):
            break
    else:
        raise RuntimeError("Basket calibration did not converge")

    base_prices = products["Base_Price"].to_numpy(float)
    baseline_qty = np.divide(x, base_prices[None, :], out=np.zeros_like(x), where=base_prices[None, :] > 0)

    rows = []
    for c_idx, class_name in enumerate(class_order):
        for p_idx, product_id in enumerate(products["Product_ID"]):
            rows.append({
                "Class": class_name,
                "Product_ID": product_id,
                "Division": products.iloc[p_idx]["Division"],
                "P0_Spending": x[c_idx, p_idx],
                "P0_Quantity": baseline_qty[c_idx, p_idx],
            })

    return pd.DataFrame(rows), x, baseline_qty


def monthly_class_product_demand(
    baseline_qty: np.ndarray,
    current_prices: np.ndarray,
    base_prices: np.ndarray,
    elasticities: np.ndarray,
    class_budgets: np.ndarray,
    household_factor: float,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Own-price response followed by a class-level budget constraint.
    This preserves the user's idea of 0..1 product elasticity while preventing
    a household class from spending more than its monthly consumption budget.
    """
    relative_price = np.divide(current_prices, base_prices, out=np.ones_like(current_prices), where=base_prices > 0)
    price_response = np.power(np.maximum(relative_price, 1e-12), -elasticities)

    preliminary_qty = baseline_qty * household_factor * price_response[None, :]
    preliminary_spend = preliminary_qty * current_prices[None, :]

    row_spend = preliminary_spend.sum(axis=1)
    scale = np.divide(class_budgets, row_spend, out=np.ones_like(class_budgets), where=row_spend > 0)
    demand_qty = preliminary_qty * scale[:, None]
    planned_spending = demand_qty * current_prices[None, :]
    return demand_qty, planned_spending
