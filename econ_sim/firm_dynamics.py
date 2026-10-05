from __future__ import annotations

import numpy as np
import pandas as pd


def classify_market(firm_counts: np.ndarray) -> np.ndarray:
    """Endogenous market structure from the active producer count."""
    counts = np.asarray(firm_counts, dtype=int)
    return np.where(
        counts <= 1,
        "Monopoly",
        np.where(counts <= 4, "Oligopoly", "Competitive"),
    ).astype(object)


def prior_year_market_metrics(
    product_history: list[dict],
    prior_year: int,
    product_ids: np.ndarray,
) -> pd.DataFrame:
    """Create product-level signals used for annual entry/exit decisions."""
    hist = pd.DataFrame(product_history)
    hist = hist[hist["Year"] == prior_year].copy()
    if hist.empty:
        return pd.DataFrame({
            "Product_ID": product_ids,
            "Shortage_Rate": 0.0,
            "Demand_Growth": 0.0,
            "Profit_Margin": 0.0,
            "Inventory_Months": 0.0,
        })

    rows = []
    for pid in product_ids:
        p = hist[hist["Product_ID"] == pid].sort_values("Month_in_Year")
        if p.empty:
            rows.append((pid, 0.0, 0.0, 0.0, 0.0))
            continue

        demand_total = float(p["Demand"].sum())
        unmet_total = float(p["Unmet_Demand"].sum())
        shortage_rate = unmet_total / max(demand_total, 1e-9)

        first_q = float(p.head(min(3, len(p)))["Demand"].mean())
        last_q = float(p.tail(min(3, len(p)))["Demand"].mean())
        demand_growth = last_q / max(first_q, 1e-9) - 1.0

        revenue = float(p["Sales_Value"].sum())
        profit = float(p["Operating_Profit_Proxy"].sum())
        profit_margin = profit / max(revenue, 1e-9)

        avg_monthly_demand = demand_total / max(len(p), 1)
        ending_inventory = float(p.iloc[-1]["Inventory_End"])
        inventory_months = ending_inventory / max(avg_monthly_demand, 1e-9)

        rows.append((pid, shortage_rate, demand_growth, profit_margin, inventory_months))

    return pd.DataFrame(rows, columns=[
        "Product_ID", "Shortage_Rate", "Demand_Growth", "Profit_Margin", "Inventory_Months"
    ])


def score_markets(
    metrics: pd.DataFrame,
    entry_shortage_weight: float,
    entry_demand_growth_weight: float,
    entry_margin_weight: float,
    exit_surplus_weight: float,
    exit_demand_decline_weight: float,
    exit_loss_weight: float,
) -> pd.DataFrame:
    """Normalize economic signals and calculate entry/exit attractiveness scores."""
    m = metrics.copy()
    shortage = np.clip(m["Shortage_Rate"].to_numpy(float), 0.0, 1.0)
    growth = np.clip(m["Demand_Growth"].to_numpy(float) / 0.25, 0.0, 1.0)
    margin = np.clip(m["Profit_Margin"].to_numpy(float) / 0.25, 0.0, 1.0)

    surplus = np.clip(m["Inventory_Months"].to_numpy(float), 0.0, 1.0)
    decline = np.clip(-m["Demand_Growth"].to_numpy(float) / 0.25, 0.0, 1.0)
    loss = np.clip(-m["Profit_Margin"].to_numpy(float) / 0.25, 0.0, 1.0)

    ew = max(entry_shortage_weight + entry_demand_growth_weight + entry_margin_weight, 1e-9)
    xw = max(exit_surplus_weight + exit_demand_decline_weight + exit_loss_weight, 1e-9)

    m["Entry_Score"] = (
        entry_shortage_weight * shortage
        + entry_demand_growth_weight * growth
        + entry_margin_weight * margin
    ) / ew
    m["Exit_Score"] = (
        exit_surplus_weight * surplus
        + exit_demand_decline_weight * decline
        + exit_loss_weight * loss
    ) / xw
    return m


def allocate_market_changes(
    total_change: int,
    scored: pd.DataFrame,
    firm_counts: np.ndarray,
    product_ids: np.ndarray,
    rng: np.random.Generator,
    max_entries_per_product: int,
    max_exits_per_product: int,
    min_entry_score: float,
    min_exit_score: float,
) -> np.ndarray:
    """
    Allocate a macro company-count change across product markets.

    Positive values are entrants; negative values are exits. Exits never reduce a
    product below one active producer.
    """
    delta = np.zeros(len(product_ids), dtype=int)
    if total_change == 0:
        return delta

    score_map = scored.set_index("Product_ID")
    if total_change > 0:
        scores = np.array([
            float(score_map.loc[pid, "Entry_Score"]) if pid in score_map.index else 0.0
            for pid in product_ids
        ])
        eligible = scores >= float(min_entry_score)
        # If the whole economy grows but all micro scores are very weak, use a tiny
        # baseline weight instead of silently discarding macro-required entrants.
        weights = np.where(eligible, np.maximum(scores, 1e-6), 0.0)
        if weights.sum() <= 0:
            weights = np.full(len(product_ids), 1.0 / len(product_ids))
        else:
            weights = weights / weights.sum()

        for _ in range(total_change):
            capacity = delta < int(max_entries_per_product)
            w = weights * capacity
            if w.sum() <= 0:
                break
            idx = int(rng.choice(len(product_ids), p=w / w.sum()))
            delta[idx] += 1
        return delta

    scores = np.array([
        float(score_map.loc[pid, "Exit_Score"]) if pid in score_map.index else 0.0
        for pid in product_ids
    ])
    exits_needed = abs(int(total_change))
    for _ in range(exits_needed):
        can_exit = (firm_counts + delta > 1) & (-delta < int(max_exits_per_product))
        eligible = can_exit & (scores >= float(min_exit_score))
        w = np.where(eligible, np.maximum(scores, 1e-6), 0.0)
        if w.sum() <= 0:
            # Never force an exit from a healthy market merely to hit the macro target.
            break
        idx = int(rng.choice(len(product_ids), p=w / w.sum()))
        delta[idx] -= 1
    return delta
