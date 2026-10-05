from __future__ import annotations

import numpy as np
import pandas as pd

from .firm_dynamics import classify_market


def launch_product_variants(
    product_meta: pd.DataFrame,
    baseline_qty: np.ndarray,
    current_prices: np.ndarray,
    demand_ref_prices: np.ndarray,
    real_base_prices: np.ndarray,
    cpi_ref_prices: np.ndarray,
    cpi_weights: np.ndarray,
    current_production: np.ndarray,
    inventory: np.ndarray,
    elasticities: np.ndarray,
    firm_counts: np.ndarray,
    market_structure: np.ndarray,
    innovation_chance: float,
    innovation_demand_share: float,
    innovation_output_share: float,
    innovation_price_min_multiplier: float,
    innovation_price_max_multiplier: float,
    innovation_elasticity_noise: float,
    innovation_initial_firms: int,
    max_new_products_per_month: int,
    new_products_can_innovate: bool,
    year: int,
    month_in_year: int,
    period_month: int,
    rng: np.random.Generator,
    next_variant_number: int,
):
    """
    Launch new product variants from products that exist at the start of the month.

    A launch does not create demand or productive capacity from nothing:
      * a share of the parent's baseline demand is transferred to the variant;
      * a share of the parent's current production/inventory is transferred;
      * CPI weight is split between parent and child without creating an index jump.

    The new product can still grow later through ordinary demand/production dynamics.
    """
    chance = float(np.clip(innovation_chance, 0.0, 1.0))
    demand_share = float(np.clip(innovation_demand_share, 0.0, 0.95))
    output_share = float(np.clip(innovation_output_share, 0.0, 0.95))
    price_min = max(float(innovation_price_min_multiplier), 0.01)
    price_max = max(float(innovation_price_max_multiplier), price_min)
    elasticity_noise = max(float(innovation_elasticity_noise), 0.0)
    initial_firms = max(int(innovation_initial_firms), 1)
    cap = int(max_new_products_per_month)

    n_start = len(product_meta)
    if n_start == 0 or chance <= 0:
        return (
            product_meta, baseline_qty, current_prices, demand_ref_prices,
            real_base_prices, cpi_ref_prices, cpi_weights, current_production,
            inventory, elasticities, firm_counts, market_structure,
            pd.DataFrame(), next_variant_number,
        )

    eligible = np.ones(n_start, dtype=bool)
    if not new_products_can_innovate and "Is_Innovation" in product_meta.columns:
        eligible &= ~product_meta["Is_Innovation"].to_numpy(bool)

    # Do not create a variant from a completely inactive zero-demand/zero-output row.
    eligible &= (baseline_qty[:, :n_start].sum(axis=0) > 1e-12) | (current_production[:n_start] > 1e-12)

    candidate_idx = np.flatnonzero(eligible & (rng.random(n_start) < chance))
    if cap > 0 and len(candidate_idx) > cap:
        candidate_idx = np.sort(rng.choice(candidate_idx, size=cap, replace=False))

    if len(candidate_idx) == 0:
        return (
            product_meta, baseline_qty, current_prices, demand_ref_prices,
            real_base_prices, cpi_ref_prices, cpi_weights, current_production,
            inventory, elasticities, firm_counts, market_structure,
            pd.DataFrame(), next_variant_number,
        )

    new_meta_rows: list[dict] = []
    event_rows: list[dict] = []
    new_baseline_cols = []
    new_prices = []
    new_demand_refs = []
    new_real_bases = []
    new_cpi_refs = []
    new_cpi_weights = []
    new_production = []
    new_inventory = []
    new_elasticities = []
    new_firm_counts = []

    for parent_idx in candidate_idx:
        parent = product_meta.iloc[parent_idx]
        serial = next_variant_number
        next_variant_number += 1
        new_id = f"N{serial:06d}"
        root_name = str(parent.get("Root_Product", parent["Product"]))
        generation = int(parent.get("Generation", 0)) + 1
        new_name = f"{root_name}_M{month_in_year:02d}_Y{year:02d}_{serial:04d}_G{generation}"

        parent_price = float(current_prices[parent_idx])
        launch_multiplier = float(rng.uniform(price_min, price_max))
        launch_price = max(0.01, parent_price * launch_multiplier)

        # Transfer baseline spending share rather than simply copying demand.
        parent_demand_ref = max(float(demand_ref_prices[parent_idx]), 0.01)
        child_baseline = (
            baseline_qty[:, parent_idx].copy()
            * demand_share
            * parent_demand_ref
            / launch_price
        )
        baseline_qty[:, parent_idx] *= (1.0 - demand_share)
        new_baseline_cols.append(child_baseline)

        parent_prod_before = float(current_production[parent_idx])
        child_production = parent_prod_before * output_share
        current_production[parent_idx] *= (1.0 - output_share)
        new_production.append(child_production)

        parent_inventory_before = float(inventory[parent_idx])
        child_inventory = parent_inventory_before * output_share
        inventory[parent_idx] *= (1.0 - output_share)
        new_inventory.append(child_inventory)

        child_elasticity = float(np.clip(
            elasticities[parent_idx] + rng.normal(0.0, elasticity_noise),
            0.0,
            1.0,
        ))
        new_elasticities.append(child_elasticity)

        # Split CPI expenditure weight while preserving the parent's current price ratio,
        # which prevents an artificial CPI jump on the launch date.
        parent_weight = float(cpi_weights[parent_idx])
        child_weight = parent_weight * demand_share
        cpi_weights[parent_idx] *= (1.0 - demand_share)
        parent_cpi_ref = max(float(cpi_ref_prices[parent_idx]), 0.01)
        parent_price_ratio = parent_price / parent_cpi_ref
        child_cpi_ref = launch_price / max(parent_price_ratio, 1e-12)

        new_prices.append(launch_price)
        new_demand_refs.append(launch_price)
        # Same physical unit/category as parent: use parent's real base price so merely
        # splitting production between parent and variant does not create real GDP.
        new_real_bases.append(float(real_base_prices[parent_idx]))
        new_cpi_refs.append(child_cpi_ref)
        new_cpi_weights.append(child_weight)
        new_firm_counts.append(initial_firms)

        new_meta_rows.append({
            "Product_ID": new_id,
            "COICOP": parent["COICOP"],
            "Category": parent["Category"],
            "Product": new_name,
            "Root_Product": root_name,
            "Unit": parent["Unit"],
            "Base_Price": launch_price,
            "Source_Sheet": "Simulation Innovation",
            "Division": parent["Division"],
            "Min_Qty": parent.get("Min_Qty", 0),
            "Max_Qty": parent.get("Max_Qty", 0),
            "Quantity_P0": 0.0,
            "Elasticity_Abs": child_elasticity,
            "Market_Structure": str(classify_market(np.array([initial_firms]))[0]),
            "Number_of_Firms": initial_firms,
            "Revenue_P0": 0.0,
            "Parent_Product_ID": parent["Product_ID"],
            "Created_Period_Month": period_month,
            "Created_Year": year,
            "Created_Month": month_in_year,
            "Is_Innovation": True,
            "Generation": generation,
            "Launch_Price": launch_price,
        })

        event_rows.append({
            "Period_Month": period_month,
            "Year": year,
            "Month_in_Year": month_in_year,
            "Event": "Product Launch",
            "Parent_Product_ID": parent["Product_ID"],
            "Parent_Product": parent["Product"],
            "New_Product_ID": new_id,
            "New_Product": new_name,
            "Division": parent["Division"],
            "Category": parent["Category"],
            "Unit": parent["Unit"],
            "Parent_Price": parent_price,
            "Launch_Price": launch_price,
            "Price_Multiplier": launch_multiplier,
            "Demand_Share_Transferred": demand_share,
            "Output_Share_Transferred": output_share,
            "Launch_Production": child_production,
            "Elasticity_Abs": child_elasticity,
            "Initial_Firms": initial_firms,
            "Generation": generation,
        })

    product_meta = pd.concat([product_meta, pd.DataFrame(new_meta_rows)], ignore_index=True)
    baseline_qty = np.column_stack([baseline_qty] + new_baseline_cols)
    current_prices = np.concatenate([current_prices, np.asarray(new_prices, dtype=float)])
    demand_ref_prices = np.concatenate([demand_ref_prices, np.asarray(new_demand_refs, dtype=float)])
    real_base_prices = np.concatenate([real_base_prices, np.asarray(new_real_bases, dtype=float)])
    cpi_ref_prices = np.concatenate([cpi_ref_prices, np.asarray(new_cpi_refs, dtype=float)])
    cpi_weights = np.concatenate([cpi_weights, np.asarray(new_cpi_weights, dtype=float)])
    current_production = np.concatenate([current_production, np.asarray(new_production, dtype=float)])
    inventory = np.concatenate([inventory, np.asarray(new_inventory, dtype=float)])
    elasticities = np.concatenate([elasticities, np.asarray(new_elasticities, dtype=float)])
    firm_counts = np.concatenate([firm_counts, np.asarray(new_firm_counts, dtype=int)])
    market_structure = classify_market(firm_counts)

    # Floating point drift from many splits should not change total CPI weight.
    total_weight = cpi_weights.sum()
    if total_weight > 0:
        cpi_weights = cpi_weights / total_weight

    return (
        product_meta, baseline_qty, current_prices, demand_ref_prices,
        real_base_prices, cpi_ref_prices, cpi_weights, current_production,
        inventory, elasticities, firm_counts, market_structure,
        pd.DataFrame(event_rows), next_variant_number,
    )
