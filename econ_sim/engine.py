from __future__ import annotations

import numpy as np
import pandas as pd

from .demand import calibrate_baseline_spending, monthly_class_product_demand
from .firm_dynamics import (
    allocate_market_changes,
    classify_market,
    prior_year_market_metrics,
    score_markets,
)


def simulate(
    products: pd.DataFrame,
    households: pd.DataFrame,
    companies: pd.DataFrame,
    production: pd.DataFrame,
    classes: pd.DataFrame,
    basket_preferences: pd.DataFrame,
    years: int,
    annual_inflation: float,
    price_noise: float,
    tax_rate: float,
    demographic_growth: float,
    company_growth_sensitivity: float,
    allow_company_exits: bool,
    price_adjustment_speed: float,
    production_adjustment_speed: float,
    max_monthly_price_change: float,
    max_monthly_production_change: float,
    initial_inventory_months: float,
    entry_shortage_weight: float,
    entry_demand_growth_weight: float,
    entry_margin_weight: float,
    exit_surplus_weight: float,
    exit_demand_decline_weight: float,
    exit_loss_weight: float,
    max_entries_per_product: int,
    max_exits_per_product: int,
    entry_capacity_share: float,
    exit_capacity_share: float,
    min_entry_score: float,
    min_exit_score: float,
    rng: np.random.Generator,
):
    months = int(years) * 12
    if months <= 0:
        raise ValueError("Simulation years must be positive")

    class_order = classes["Class"].astype(str).tolist()
    basket_calibration, baseline_spending, baseline_qty = calibrate_baseline_spending(
        products, households, basket_preferences, class_order
    )

    product_ids = products["Product_ID"].astype(str).to_numpy()
    base_prices = products["Base_Price"].to_numpy(float)
    base_output = products["Quantity_P0"].to_numpy(float)
    elasticities = products["Elasticity_Abs"].to_numpy(float)

    current_prices = base_prices.copy()
    current_production = base_output.copy()
    inventory = base_output * float(initial_inventory_months)

    # Firm counts are now endogenous. Market structure is reclassified from the
    # active number of producers after every annual entry/exit event.
    firm_counts = products["Number_of_Firms"].to_numpy(int).copy()
    market_structure = classify_market(firm_counts)

    initial_households = len(households)
    current_households = initial_households
    initial_companies = len(companies)
    current_companies = initial_companies

    base_gdp_monthly = float(np.sum(base_prices * base_output))
    if base_gdp_monthly <= 0:
        raise ValueError("Period-0 GDP is zero")

    base_class_budget = (
        households.groupby("Class", observed=True)["Consumption"].sum()
        .reindex(class_order)
        .fillna(0.0)
        .to_numpy(float)
    )

    fixed_cost_p0_total = float(companies["Fixed_Cost_P0"].sum())
    avg_fixed_cost_p0_per_company = fixed_cost_p0_total / max(initial_companies, 1)
    avg_variable_cost_ratio = (
        float(companies["Variable_Cost_P0"].sum()) / base_gdp_monthly
        if base_gdp_monthly > 0 else 0.0
    )

    monthly_rows: list[dict] = []
    product_rows: list[dict] = []
    market_event_rows: list[dict] = []
    company_events = [{
        "Year": 0,
        "Event": "Initial",
        "Companies_Before": initial_companies,
        "Requested_Change": 0,
        "Actual_Change": 0,
        "Companies_After": initial_companies,
        "Prior_Year_Real_GDP_Growth": 0.0,
    }]

    monthly_rows.append({
        "Period_Month": 0,
        "Year": 0,
        "Month_in_Year": 0,
        "Household_Count": current_households,
        "Company_Count": current_companies,
        "Nominal_GDP_Monthly": base_gdp_monthly,
        "Nominal_GDP_Annualized": base_gdp_monthly * 12.0,
        "Nominal_GDP_Growth_MoM": 0.0,
        "Real_GDP_Monthly_Base_Prices": base_gdp_monthly,
        "Real_GDP_Growth_MoM": 0.0,
        "CPI_Index": 100.0,
        "Inflation_MoM": 0.0,
        "Inflation_12M": 0.0,
        "Planned_Consumption": float(base_class_budget.sum()),
        "Realized_Consumption_Sales": base_gdp_monthly,
        "Unmet_Demand_Value": 0.0,
        "Inventory_Value": float(np.sum(inventory * base_prices)),
        "Shortage_Product_Share": 0.0,
        "Average_Imbalance": 0.0,
        "Producer_Profit": float(companies["Profit_P0"].sum()),
        "Median_Product_Price_Change": 0.0,
        "Monopoly_Products": int(np.sum(market_structure == "Monopoly")),
        "Oligopoly_Products": int(np.sum(market_structure == "Oligopoly")),
        "Competitive_Products": int(np.sum(market_structure == "Competitive")),
    })

    cpi_history = [100.0]
    prev_nominal_gdp = base_gdp_monthly
    prev_real_gdp = base_gdp_monthly
    prior_year_real_growth = 0.0
    annual_real_flows: dict[int, float] = {}

    for t in range(1, months + 1):
        year = (t - 1) // 12 + 1
        month_in_year = (t - 1) % 12 + 1

        # Annual demographic update and intelligent firm entry/exit at the start
        # of each year after Year 1. Total entry is still tied to real GDP growth;
        # product allocation is based on the prior year's microeconomic signals.
        if month_in_year == 1 and year > 1:
            current_households = int(round(
                initial_households * ((1.0 + demographic_growth) ** (year - 1))
            ))

            before = current_companies
            growth_signal = prior_year_real_growth * company_growth_sensitivity
            if growth_signal >= 0:
                requested_change = int(round(current_companies * growth_signal))
            elif allow_company_exits:
                requested_change = -min(
                    current_companies - 1,
                    int(round(current_companies * abs(growth_signal))),
                )
            else:
                requested_change = 0

            metrics = prior_year_market_metrics(
                product_rows, year - 1, product_ids
            )
            scored = score_markets(
                metrics,
                entry_shortage_weight,
                entry_demand_growth_weight,
                entry_margin_weight,
                exit_surplus_weight,
                exit_demand_decline_weight,
                exit_loss_weight,
            )
            market_delta = allocate_market_changes(
                requested_change,
                scored,
                firm_counts,
                product_ids,
                rng,
                max_entries_per_product=max_entries_per_product,
                max_exits_per_product=max_exits_per_product,
                min_entry_score=min_entry_score,
                min_exit_score=min_exit_score,
            )
            actual_change = int(market_delta.sum())

            # Entry/exit changes productive capacity. One entrant receives a share
            # of average incumbent capacity; one exit removes a share of it.
            for i, delta in enumerate(market_delta):
                if delta == 0:
                    continue
                old_firms = max(int(firm_counts[i]), 1)
                old_structure = str(market_structure[i])
                old_production = float(current_production[i])

                if delta > 0:
                    capacity_factor = 1.0 + entry_capacity_share * (delta / old_firms)
                else:
                    capacity_factor = max(
                        0.05,
                        1.0 - exit_capacity_share * (abs(delta) / old_firms),
                    )
                current_production[i] *= capacity_factor
                firm_counts[i] = max(1, firm_counts[i] + delta)

                new_structure = str(classify_market(np.array([firm_counts[i]]))[0])
                market_structure[i] = new_structure
                score_row = scored.loc[scored["Product_ID"] == product_ids[i]].iloc[0]
                market_event_rows.append({
                    "Year": year,
                    "Product_ID": product_ids[i],
                    "Event": "Entry" if delta > 0 else "Exit",
                    "Firm_Change": int(delta),
                    "Firms_Before": old_firms,
                    "Firms_After": int(firm_counts[i]),
                    "Market_Before": old_structure,
                    "Market_After": new_structure,
                    "Production_Before": old_production,
                    "Production_After": float(current_production[i]),
                    "Entry_Score": float(score_row["Entry_Score"]),
                    "Exit_Score": float(score_row["Exit_Score"]),
                    "Prior_Shortage_Rate": float(score_row["Shortage_Rate"]),
                    "Prior_Demand_Growth": float(score_row["Demand_Growth"]),
                    "Prior_Profit_Margin": float(score_row["Profit_Margin"]),
                    "Prior_Inventory_Months": float(score_row["Inventory_Months"]),
                })

            current_companies += actual_change
            company_events.append({
                "Year": year,
                "Event": "Entry" if actual_change > 0 else "Exit" if actual_change < 0 else "No change",
                "Companies_Before": before,
                "Requested_Change": requested_change,
                "Actual_Change": actual_change,
                "Companies_After": current_companies,
                "Prior_Year_Real_GDP_Growth": prior_year_real_growth,
            })

        household_factor = current_households / initial_households
        prior_cpi_factor = cpi_history[-1] / 100.0
        class_budgets = base_class_budget * household_factor * prior_cpi_factor

        demand_by_class, planned_spending = monthly_class_product_demand(
            baseline_qty=baseline_qty,
            current_prices=current_prices,
            base_prices=base_prices,
            elasticities=elasticities,
            class_budgets=class_budgets,
            household_factor=household_factor,
        )
        demand = demand_by_class.sum(axis=0)

        inventory_start = inventory.copy()
        available = current_production + inventory_start
        sales = np.minimum(demand, available)
        inventory_end = np.maximum(available - sales, 0.0)
        unmet_qty = np.maximum(demand - available, 0.0)

        denom = np.maximum(demand + available, 1e-9)
        imbalance = (demand - available) / denom

        sales_value = sales * current_prices
        production_value = current_production * current_prices
        nominal_gdp = float(np.sum(production_value))
        real_gdp = float(np.sum(current_production * base_prices))
        cpi = float(np.sum(current_prices * base_output) / base_gdp_monthly * 100.0)
        inflation_mom = cpi / cpi_history[-1] - 1.0
        inflation_12m = (
            cpi / cpi_history[t - 12] - 1.0
            if t >= 12
            else (cpi / 100.0) ** (12.0 / t) - 1.0
        )

        # Product-level cost/profit proxy is used for next year's firm decisions.
        product_variable_cost = production_value * avg_variable_cost_ratio
        # Companies can produce more than one product, so product-level firm counts
        # cannot be multiplied by average company fixed cost directly. Allocate the
        # economy-wide fixed-cost pool across products by active producer presence.
        total_fixed_cost = (
            fixed_cost_p0_total
            * (cpi / 100.0)
            * (current_companies / initial_companies)
        )
        product_fixed_cost = total_fixed_cost * (
            firm_counts.astype(float) / max(float(firm_counts.sum()), 1.0)
        )
        product_profit_proxy = sales_value - product_variable_cost - product_fixed_cost
        product_margin_proxy = np.divide(
            product_profit_proxy,
            np.maximum(sales_value, 1e-9),
        )

        variable_cost = float(product_variable_cost.sum())
        fixed_cost = float(total_fixed_cost)
        producer_profit = float(sales_value.sum() - variable_cost - fixed_cost)

        planned_total = float(planned_spending.sum())
        realized_consumption = float(sales_value.sum())
        unmet_value = float(np.sum(unmet_qty * current_prices))
        inventory_value = float(np.sum(inventory_end * current_prices))

        monthly_rows.append({
            "Period_Month": t,
            "Year": year,
            "Month_in_Year": month_in_year,
            "Household_Count": current_households,
            "Company_Count": current_companies,
            "Nominal_GDP_Monthly": nominal_gdp,
            "Nominal_GDP_Annualized": nominal_gdp * 12.0,
            "Nominal_GDP_Growth_MoM": nominal_gdp / prev_nominal_gdp - 1.0,
            "Real_GDP_Monthly_Base_Prices": real_gdp,
            "Real_GDP_Growth_MoM": real_gdp / prev_real_gdp - 1.0,
            "CPI_Index": cpi,
            "Inflation_MoM": inflation_mom,
            "Inflation_12M": inflation_12m,
            "Planned_Consumption": planned_total,
            "Realized_Consumption_Sales": realized_consumption,
            "Unmet_Demand_Value": unmet_value,
            "Inventory_Value": inventory_value,
            "Shortage_Product_Share": float(np.mean(unmet_qty > np.maximum(0.01 * demand, 1e-9))),
            "Average_Imbalance": float(np.mean(imbalance)),
            "Producer_Profit": producer_profit,
            "Median_Product_Price_Change": 0.0,
            "Monopoly_Products": int(np.sum(market_structure == "Monopoly")),
            "Oligopoly_Products": int(np.sum(market_structure == "Oligopoly")),
            "Competitive_Products": int(np.sum(market_structure == "Competitive")),
        })

        for i, pid in enumerate(product_ids):
            product_rows.append({
                "Period_Month": t,
                "Year": year,
                "Month_in_Year": month_in_year,
                "Product_ID": pid,
                "Price": current_prices[i],
                "Demand": demand[i],
                "Production": current_production[i],
                "Inventory_Start": inventory_start[i],
                "Available_Supply": available[i],
                "Sales": sales[i],
                "Sales_Value": sales_value[i],
                "Inventory_End": inventory_end[i],
                "Unmet_Demand": unmet_qty[i],
                "Imbalance": imbalance[i],
                "Elasticity_Abs": elasticities[i],
                "Firm_Count": int(firm_counts[i]),
                "Market_Structure": market_structure[i],
                "Operating_Profit_Proxy": product_profit_proxy[i],
                "Profit_Margin_Proxy": product_margin_proxy[i],
            })

        background = annual_inflation / 12.0
        noise = rng.normal(0.0, price_noise, len(current_prices))
        noise -= np.median(noise)
        price_change = background + price_adjustment_speed * imbalance + noise
        price_change = np.clip(
            price_change,
            -max_monthly_price_change,
            max_monthly_price_change,
        )
        monthly_rows[-1]["Median_Product_Price_Change"] = float(np.median(price_change))
        next_prices = np.maximum(0.01, current_prices * (1.0 + price_change))

        # Recalculate response speed from the current endogenous market structure.
        market_speed = np.array([
            1.00 if m == "Competitive" else 0.75 if m == "Oligopoly" else 0.50
            for m in market_structure
        ])
        desired_ratio = np.divide(demand, np.maximum(current_production, 1e-9)) - 1.0
        prod_change = production_adjustment_speed * market_speed * desired_ratio
        prod_change = np.clip(
            prod_change,
            -max_monthly_production_change,
            max_monthly_production_change,
        )
        next_production = np.maximum(0.0, current_production * (1.0 + prod_change))

        inventory = inventory_end
        current_prices = next_prices
        current_production = next_production
        cpi_history.append(cpi)
        prev_nominal_gdp = nominal_gdp
        prev_real_gdp = real_gdp

        if month_in_year == 12:
            this_year_flow = float(sum(
                r["Real_GDP_Monthly_Base_Prices"]
                for r in monthly_rows
                if r["Year"] == year
            ))
            annual_real_flows[year] = this_year_flow
            prior_flow = (
                base_gdp_monthly * 12.0
                if year == 1
                else annual_real_flows[year - 1]
            )
            prior_year_real_growth = this_year_flow / prior_flow - 1.0

    monthly = pd.DataFrame(monthly_rows)
    product_monthly = pd.DataFrame(product_rows)
    company_events_df = pd.DataFrame(company_events)
    market_events_df = pd.DataFrame(market_event_rows)

    yearly_rows = []
    for year in range(1, years + 1):
        y = monthly[monthly["Year"] == year]
        nominal_flow = float(y["Nominal_GDP_Monthly"].sum())
        real_flow = float(y["Real_GDP_Monthly_Base_Prices"].sum())
        prev_nominal_flow = (
            base_gdp_monthly * 12.0
            if year == 1
            else float(monthly[monthly["Year"] == year - 1]["Nominal_GDP_Monthly"].sum())
        )
        prev_real_flow = (
            base_gdp_monthly * 12.0
            if year == 1
            else float(monthly[monthly["Year"] == year - 1]["Real_GDP_Monthly_Base_Prices"].sum())
        )
        end = y.iloc[-1]
        start_cpi = (
            100.0
            if year == 1
            else float(monthly[(monthly["Year"] == year - 1) & (monthly["Month_in_Year"] == 12)].iloc[-1]["CPI_Index"])
        )
        yearly_rows.append({
            "Year": year,
            "Nominal_GDP": nominal_flow,
            "Nominal_GDP_Growth_YoY": nominal_flow / prev_nominal_flow - 1.0,
            "Real_GDP_Base_Prices": real_flow,
            "Real_GDP_Growth_YoY": real_flow / prev_real_flow - 1.0,
            "Inflation_YoY": float(end["CPI_Index"] / start_cpi - 1.0),
            "CPI_Index_End": float(end["CPI_Index"]),
            "Household_Count_End": int(end["Household_Count"]),
            "Company_Count_End": int(end["Company_Count"]),
            "Planned_Consumption": float(y["Planned_Consumption"].sum()),
            "Realized_Consumption_Sales": float(y["Realized_Consumption_Sales"].sum()),
            "Unmet_Demand_Value": float(y["Unmet_Demand_Value"].sum()),
            "Average_Shortage_Product_Share": float(y["Shortage_Product_Share"].mean()),
            "Producer_Profit": float(y["Producer_Profit"].sum()),
            "Monopoly_Products_End": int(end["Monopoly_Products"]),
            "Oligopoly_Products_End": int(end["Oligopoly_Products"]),
            "Competitive_Products_End": int(end["Competitive_Products"]),
        })

    return (
        monthly,
        pd.DataFrame(yearly_rows),
        basket_calibration,
        company_events_df,
        market_events_df,
        product_monthly,
    )
