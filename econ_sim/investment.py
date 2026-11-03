from __future__ import annotations

import numpy as np
import pandas as pd


def savings_rates_by_class(
    savings_settings: pd.DataFrame,
    class_order: list[str],
    *,
    interest_rate: float,
    neutral_interest_rate: float,
    sensitivity: float,
) -> np.ndarray:
    """Return current household saving rates by class.

    Rates start from class-specific baselines and move linearly with the gap
    between the policy rate and the neutral rate, then respect class-specific
    minimum/maximum bounds.
    """
    settings = savings_settings.set_index("Class").reindex(class_order)
    if settings.isna().any().any():
        missing = [name for name in class_order if name not in savings_settings["Class"].astype(str).tolist()]
        raise ValueError(f"Savings_Settings missing class(es): {', '.join(missing)}")

    base = settings["Base Savings Rate"].to_numpy(float)
    minimum = settings["Minimum Rate"].to_numpy(float)
    maximum = settings["Maximum Rate"].to_numpy(float)
    rate_gap = float(interest_rate) - float(neutral_interest_rate)
    actual = base + float(sensitivity) * rate_gap
    return np.clip(actual, minimum, maximum)


def initialize_capital_state(
    base_prices: np.ndarray,
    base_output: np.ndarray,
    *,
    capital_output_ratio: float,
    initial_capacity_utilization: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Create product-market productive capital and physical capacity.

    Capital is calibrated from annualized period-0 production value, while
    capacity is calibrated from period-0 physical output and the desired initial
    utilization rate.
    """
    annual_output_value = np.maximum(base_prices * base_output * 12.0, 0.0)
    capital_stock = annual_output_value * max(float(capital_output_ratio), 1e-9)
    utilization = float(np.clip(initial_capacity_utilization, 1e-6, 1.0))
    capacity = np.maximum(base_output / utilization, base_output)
    return capital_stock, capacity


def investment_market_scores(
    current_production: np.ndarray,
    capacity: np.ndarray,
    prior_imbalance: np.ndarray,
    prior_margin: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Score recipient markets for capital allocation.

    High utilization, prior shortages and positive operating margins make an
    industry more attractive for new productive capital.
    """
    utilization = np.divide(
        current_production,
        np.maximum(capacity, 1e-9),
        out=np.zeros_like(current_production, dtype=float),
        where=capacity > 0,
    )
    util_signal = np.clip((utilization - 0.70) / 0.30, 0.0, 1.0)
    shortage_signal = np.clip(prior_imbalance, 0.0, 1.0)
    margin_signal = np.clip(prior_margin / 0.20, 0.0, 1.0)
    score = 0.50 * util_signal + 0.30 * shortage_signal + 0.20 * margin_signal
    return np.clip(score, 0.0, 1.0), utilization


def desired_investment_budget(
    capital_stock: np.ndarray,
    scores: np.ndarray,
    *,
    annual_depreciation_rate: float,
    interest_rate: float,
    neutral_interest_rate: float,
    interest_sensitivity: float,
) -> float:
    """Maintenance plus expansion investment desired by firms this month."""
    monthly_depreciation = max(float(annual_depreciation_rate), 0.0) / 12.0
    maintenance = float(np.sum(capital_stock) * monthly_depreciation)

    # Attractiveness can fund expansion of up to ~0.5% of capital per month at
    # score 1.0 before the interest-rate adjustment.
    expansion = float(np.sum(capital_stock * scores) * 0.005)
    rate_gap = float(interest_rate) - float(neutral_interest_rate)
    rate_factor = float(np.exp(-max(float(interest_sensitivity), 0.0) * rate_gap))
    rate_factor = float(np.clip(rate_factor, 0.25, 2.0))
    return max(0.0, maintenance + expansion * rate_factor)


def allocate_investment_goods_demand(
    investment_budget: float,
    product_meta: pd.DataFrame,
    current_prices: np.ndarray,
    current_production: np.ndarray,
    investment_demand: pd.DataFrame,
) -> tuple[np.ndarray, np.ndarray]:
    """Allocate investment expenditure across existing products.

    These weights identify goods/services purchased for investment. They are
    distinct from the recipient-industry scores used to allocate resulting
    productive capital.
    """
    budget = max(float(investment_budget), 0.0)
    if budget <= 0 or len(product_meta) == 0:
        zeros = np.zeros(len(product_meta), dtype=float)
        return zeros, zeros

    weights_by_division = (
        investment_demand.set_index("Division")["Investment Weight"].astype(float).to_dict()
    )
    division_weight = product_meta["Division"].astype(str).map(weights_by_division).fillna(0.0).to_numpy(float)
    production_value = np.maximum(current_production * current_prices, 0.0)
    raw = production_value * np.maximum(division_weight, 0.0)
    if raw.sum() <= 0:
        raw = np.maximum(division_weight, 0.0)
    if raw.sum() <= 0:
        zeros = np.zeros(len(product_meta), dtype=float)
        return zeros, zeros

    planned_spending = budget * raw / raw.sum()
    qty = np.divide(
        planned_spending,
        np.maximum(current_prices, 1e-9),
        out=np.zeros_like(planned_spending),
        where=current_prices > 0,
    )
    return qty, planned_spending


def update_capital_and_capacity(
    capital_stock: np.ndarray,
    capacity: np.ndarray,
    realized_investment: float,
    recipient_scores: np.ndarray,
    *,
    annual_depreciation_rate: float,
    capital_efficiency: float,
    max_monthly_capacity_growth: float,
) -> tuple[np.ndarray, np.ndarray, float, np.ndarray]:
    """Apply depreciation and realized investment, then update capacity.

    Realized investment is allocated to recipient product markets using the
    attractiveness scores. If all scores are zero, capital shares are used.
    """
    old_capital = np.maximum(capital_stock.astype(float), 0.0)
    old_capacity = np.maximum(capacity.astype(float), 0.0)
    monthly_dep_rate = max(float(annual_depreciation_rate), 0.0) / 12.0
    depreciation_by_product = old_capital * monthly_dep_rate
    depreciation_total = float(depreciation_by_product.sum())

    weights = np.maximum(np.asarray(recipient_scores, dtype=float), 0.0)
    if weights.sum() <= 0:
        weights = old_capital.copy()
    if weights.sum() <= 0:
        weights = np.ones_like(old_capital)
    investment_by_product = max(float(realized_investment), 0.0) * weights / weights.sum()

    new_capital = np.maximum(old_capital - depreciation_by_product + investment_by_product, 0.0)
    capital_ratio = np.divide(
        new_capital,
        np.maximum(old_capital, 1e-9),
        out=np.ones_like(new_capital),
        where=old_capital > 0,
    )
    raw_capacity_factor = np.power(np.maximum(capital_ratio, 1e-9), max(float(capital_efficiency), 0.0))
    max_growth = max(float(max_monthly_capacity_growth), 0.0)
    capacity_factor = np.clip(raw_capacity_factor, max(0.0, 1.0 - max_growth), 1.0 + max_growth)
    new_capacity = np.maximum(old_capacity * capacity_factor, 0.0)
    return new_capital, new_capacity, depreciation_total, investment_by_product
