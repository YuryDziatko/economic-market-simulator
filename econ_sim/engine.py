from __future__ import annotations

import numpy as np
import pandas as pd

from .demand import calibrate_baseline_spending, monthly_class_product_demand
from .product_dynamics import launch_product_variants
from .labor import prepare_labor_market, labor_and_income_state, next_average_wage
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
    employment_settings: pd.DataFrame,
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
    product_innovation_chance: float,
    innovation_demand_share: float,
    innovation_output_share: float,
    innovation_price_min_multiplier: float,
    innovation_price_max_multiplier: float,
    innovation_elasticity_noise: float,
    innovation_initial_firms: int,
    max_new_products_per_month: int,
    new_products_can_innovate: bool,
    labor_force_participation: float,
    initial_unemployment_rate: float,
    labor_income_share_p0: float,
    labor_output_elasticity: float,
    labor_wage_demand_elasticity: float,
    annual_labor_productivity_growth: float,
    wage_adjustment_speed: float,
    wage_inflation_pass_through: float,
    max_monthly_wage_change: float,
    unemployment_transfer_rate: float,
    rng: np.random.Generator,
):
    months = int(years) * 12
    if months <= 0:
        raise ValueError("Simulation years must be positive")

    class_order = classes["Class"].astype(str).tolist()
    basket_calibration, baseline_spending, baseline_qty = calibrate_baseline_spending(
        products, households, basket_preferences, class_order
    )

    product_meta = products.copy().reset_index(drop=True)
    product_meta["Root_Product"] = product_meta["Product"].astype(str)
    product_meta["Parent_Product_ID"] = ""
    product_meta["Created_Period_Month"] = 0
    product_meta["Created_Year"] = 0
    product_meta["Created_Month"] = 0
    product_meta["Is_Innovation"] = False
    product_meta["Generation"] = 0
    product_meta["Launch_Price"] = product_meta["Base_Price"].astype(float)

    product_ids = product_meta["Product_ID"].astype(str).to_numpy()
    base_prices = products["Base_Price"].to_numpy(float)
    base_output = products["Quantity_P0"].to_numpy(float)
    elasticities = products["Elasticity_Abs"].to_numpy(float)

    current_prices = base_prices.copy()
    demand_ref_prices = base_prices.copy()
    real_base_prices = base_prices.copy()
    cpi_ref_prices = base_prices.copy()
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
    cpi_weights = (base_prices * base_output) / base_gdp_monthly
    next_variant_number = 1

    base_class_budget = (
        households.groupby("Class", observed=True)["Consumption"].sum()
        .reindex(class_order)
        .fillna(0.0)
        .to_numpy(float)
    )

    labor_calibration = prepare_labor_market(
        households=households,
        classes=classes,
        employment_settings=employment_settings,
        labor_force_participation=labor_force_participation,
        initial_unemployment_rate=initial_unemployment_rate,
        labor_income_share_p0=labor_income_share_p0,
        base_gdp_monthly=base_gdp_monthly,
    )
    current_average_wage = float(labor_calibration["base_average_wage"])
    period0_labor, period0_class_income, _ = labor_and_income_state(
        year=0,
        period_month=0,
        month_in_year=0,
        current_households=current_households,
        classes=classes,
        labor_calibration=labor_calibration,
        labor_force_participation=labor_force_participation,
        annual_labor_productivity_growth=annual_labor_productivity_growth,
        labor_output_elasticity=labor_output_elasticity,
        labor_wage_demand_elasticity=labor_wage_demand_elasticity,
        price_level=1.0,
        base_real_output=base_gdp_monthly,
        planned_real_output=base_gdp_monthly,
        nominal_output=base_gdp_monthly,
        average_wage=current_average_wage,
        tax_rate=tax_rate,
        unemployment_transfer_rate=unemployment_transfer_rate,
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
    product_event_rows: list[dict] = []
    household_income_rows: list[dict] = period0_class_income.to_dict("records")
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
        "Planned_Consumption": float(period0_labor["Household_Consumption_Budget"]),
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
        "Product_Count": len(product_meta),
        "New_Products_This_Month": 0,
        "Labor_Force": period0_labor["Labor_Force"],
        "Employment": period0_labor["Employment"],
        "Unemployment": period0_labor["Unemployment"],
        "Employment_Rate": period0_labor["Employment_Rate"],
        "Unemployment_Rate": period0_labor["Unemployment_Rate"],
        "Average_Wage": period0_labor["Average_Wage"],
        "Wage_Growth_MoM": 0.0,
        "Labor_Income": period0_labor["Labor_Income"],
        "Capital_Income": period0_labor["Capital_Income"],
        "Household_Gross_Income": period0_labor["Household_Gross_Income"],
        "Household_Taxes": period0_labor["Household_Taxes"],
        "Household_Disposable_Income": period0_labor["Household_Disposable_Income"],
        "Income_Gini_Class_Average": period0_labor["Income_Gini_Class_Average"],
        "Labor_Productivity_Index": period0_labor["Labor_Productivity_Index"],
        "Real_Wage_Index": period0_labor["Real_Wage_Index"],
        "Labor_Wage_Demand_Factor": period0_labor["Labor_Wage_Demand_Factor"],
        "Labor_Constraint_Production_Factor": 1.0,
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

            product_ids = product_meta["Product_ID"].astype(str).to_numpy()
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

        # Monthly product innovation. New variants inherit their parent's category/unit,
        # but receive a new name and launch price. Demand, production, inventory and CPI
        # weight are split from the parent so product creation itself does not manufacture
        # demand, output, or inflation from nothing.
        (
            product_meta, baseline_qty, current_prices, demand_ref_prices,
            real_base_prices, cpi_ref_prices, cpi_weights, current_production,
            inventory, elasticities, firm_counts, market_structure,
            innovation_events, next_variant_number,
        ) = launch_product_variants(
            product_meta=product_meta,
            baseline_qty=baseline_qty,
            current_prices=current_prices,
            demand_ref_prices=demand_ref_prices,
            real_base_prices=real_base_prices,
            cpi_ref_prices=cpi_ref_prices,
            cpi_weights=cpi_weights,
            current_production=current_production,
            inventory=inventory,
            elasticities=elasticities,
            firm_counts=firm_counts,
            market_structure=market_structure,
            innovation_chance=product_innovation_chance,
            innovation_demand_share=innovation_demand_share,
            innovation_output_share=innovation_output_share,
            innovation_price_min_multiplier=innovation_price_min_multiplier,
            innovation_price_max_multiplier=innovation_price_max_multiplier,
            innovation_elasticity_noise=innovation_elasticity_noise,
            innovation_initial_firms=innovation_initial_firms,
            max_new_products_per_month=max_new_products_per_month,
            new_products_can_innovate=new_products_can_innovate,
            year=year,
            month_in_year=month_in_year,
            period_month=t,
            rng=rng,
            next_variant_number=next_variant_number,
        )
        if not innovation_events.empty:
            product_event_rows.extend(innovation_events.to_dict("records"))
        new_products_this_month = len(innovation_events)
        product_ids = product_meta["Product_ID"].astype(str).to_numpy()

        household_factor = current_households / initial_households

        # ---- Phase 2 labor market ----
        # First test whether the production plan can be staffed. If labor demand
        # exceeds the labor force, physical output is scaled before household
        # income and product demand are calculated.
        planned_real_pre_labor = float(np.sum(current_production * real_base_prices))
        planned_nominal_pre_labor = float(np.sum(current_production * current_prices))
        labor_probe, _, labor_factor = labor_and_income_state(
            year=year,
            period_month=t,
            month_in_year=month_in_year,
            current_households=current_households,
            classes=classes,
            labor_calibration=labor_calibration,
            labor_force_participation=labor_force_participation,
            annual_labor_productivity_growth=annual_labor_productivity_growth,
            labor_output_elasticity=labor_output_elasticity,
            labor_wage_demand_elasticity=labor_wage_demand_elasticity,
            price_level=cpi_history[-1] / 100.0,
            base_real_output=base_gdp_monthly,
            planned_real_output=planned_real_pre_labor,
            nominal_output=planned_nominal_pre_labor,
            average_wage=current_average_wage,
            tax_rate=tax_rate,
            unemployment_transfer_rate=unemployment_transfer_rate,
        )
        desired_employment_signal = labor_probe["Desired_Employment_Pre_Constraint"]
        if labor_factor < 1.0:
            current_production = current_production * labor_factor

        planned_real_after_labor = float(np.sum(current_production * real_base_prices))
        planned_nominal_after_labor = float(np.sum(current_production * current_prices))
        labor_macro, class_income_df, _ = labor_and_income_state(
            year=year,
            period_month=t,
            month_in_year=month_in_year,
            current_households=current_households,
            classes=classes,
            labor_calibration=labor_calibration,
            labor_force_participation=labor_force_participation,
            annual_labor_productivity_growth=annual_labor_productivity_growth,
            labor_output_elasticity=labor_output_elasticity,
            labor_wage_demand_elasticity=labor_wage_demand_elasticity,
            price_level=cpi_history[-1] / 100.0,
            base_real_output=base_gdp_monthly,
            planned_real_output=planned_real_after_labor,
            nominal_output=planned_nominal_after_labor,
            average_wage=current_average_wage,
            tax_rate=tax_rate,
            unemployment_transfer_rate=unemployment_transfer_rate,
        )
        labor_macro["Desired_Employment_Pre_Constraint"] = desired_employment_signal
        labor_macro["Labor_Constraint_Production_Factor"] = labor_factor
        household_income_rows.extend(class_income_df.to_dict("records"))
        class_budgets = (
            class_income_df.set_index("Class")["Consumption_Budget"]
            .reindex(class_order).fillna(0.0).to_numpy(float)
        )

        demand_by_class, planned_spending = monthly_class_product_demand(
            baseline_qty=baseline_qty,
            current_prices=current_prices,
            base_prices=demand_ref_prices,
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
        real_gdp = float(np.sum(current_production * real_base_prices))
        price_relatives = np.divide(
            current_prices, cpi_ref_prices, out=np.ones_like(current_prices), where=cpi_ref_prices > 0
        )
        cpi = float(100.0 * np.sum(cpi_weights * price_relatives))
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
            "Product_Count": len(product_meta),
            "New_Products_This_Month": int(new_products_this_month),
            "Labor_Force": labor_macro["Labor_Force"],
            "Employment": labor_macro["Employment"],
            "Unemployment": labor_macro["Unemployment"],
            "Employment_Rate": labor_macro["Employment_Rate"],
            "Unemployment_Rate": labor_macro["Unemployment_Rate"],
            "Average_Wage": labor_macro["Average_Wage"],
            "Wage_Growth_MoM": 0.0,
            "Labor_Income": labor_macro["Labor_Income"],
            "Capital_Income": labor_macro["Capital_Income"],
            "Household_Gross_Income": labor_macro["Household_Gross_Income"],
            "Household_Taxes": labor_macro["Household_Taxes"],
            "Household_Disposable_Income": labor_macro["Household_Disposable_Income"],
            "Income_Gini_Class_Average": labor_macro["Income_Gini_Class_Average"],
            "Labor_Productivity_Index": labor_macro["Labor_Productivity_Index"],
            "Real_Wage_Index": labor_macro["Real_Wage_Index"],
            "Labor_Wage_Demand_Factor": labor_macro["Labor_Wage_Demand_Factor"],
            "Labor_Constraint_Production_Factor": labor_macro["Labor_Constraint_Production_Factor"],
        })

        meta_product = product_meta["Product"].to_numpy(object)
        meta_category = product_meta["Category"].to_numpy(object)
        meta_division = product_meta["Division"].to_numpy(object)
        meta_parent = product_meta["Parent_Product_ID"].to_numpy(object)
        meta_generation = product_meta["Generation"].to_numpy(int)
        meta_created_period = product_meta["Created_Period_Month"].to_numpy(int)

        for i, pid in enumerate(product_ids):
            product_rows.append({
                "Period_Month": t,
                "Year": year,
                "Month_in_Year": month_in_year,
                "Product_ID": pid,
                "Product": meta_product[i],
                "Category": meta_category[i],
                "Division": meta_division[i],
                "Parent_Product_ID": meta_parent[i],
                "Generation": int(meta_generation[i]),
                "Created_Period_Month": int(meta_created_period[i]),
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

        next_wage, wage_change = next_average_wage(
            current_paid_wage=max(labor_macro["Average_Wage"], 0.01),
            labor_force=labor_macro["Labor_Force"],
            desired_employment_pre_constraint=labor_macro["Desired_Employment_Pre_Constraint"],
            target_unemployment_rate=labor_calibration["target_unemployment_rate"],
            inflation_mom=inflation_mom,
            wage_adjustment_speed=wage_adjustment_speed,
            wage_inflation_pass_through=wage_inflation_pass_through,
            max_monthly_wage_change=max_monthly_wage_change,
        )
        monthly_rows[-1]["Wage_Growth_MoM"] = wage_change

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
        current_average_wage = next_wage
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
    product_events_df = pd.DataFrame(product_event_rows)
    household_income_monthly = pd.DataFrame(household_income_rows)

    products_final = product_meta.copy()
    products_final["Current_Price"] = current_prices
    products_final["Demand_Reference_Price"] = demand_ref_prices
    products_final["Real_Base_Price"] = real_base_prices
    products_final["Current_Production"] = current_production
    products_final["Inventory_End"] = inventory
    products_final["Elasticity_Abs"] = elasticities
    products_final["Number_of_Firms"] = firm_counts
    products_final["Market_Structure"] = market_structure
    products_final["CPI_Weight"] = cpi_weights

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
            "Product_Count_End": int(end["Product_Count"]),
            "New_Products_Created": int(y["New_Products_This_Month"].sum()),
            "Labor_Force_End": float(end["Labor_Force"]),
            "Employment_End": float(end["Employment"]),
            "Unemployment_Rate_End": float(end["Unemployment_Rate"]),
            "Average_Unemployment_Rate": float(y["Unemployment_Rate"].mean()),
            "Average_Wage_End": float(end["Average_Wage"]),
            "Average_Wage_Annual": float(end["Average_Wage"] * 12.0),
            "Labor_Income": float(y["Labor_Income"].sum()),
            "Capital_Income": float(y["Capital_Income"].sum()),
            "Household_Gross_Income": float(y["Household_Gross_Income"].sum()),
            "Household_Disposable_Income": float(y["Household_Disposable_Income"].sum()),
            "Income_Gini_End_Class_Average": float(end["Income_Gini_Class_Average"]),
            "Labor_Productivity_Index_End": float(end["Labor_Productivity_Index"]),
            "Labor_Constraint_Months": int((y["Labor_Constraint_Production_Factor"] < 0.999999).sum()),
        })

    return (
        monthly,
        pd.DataFrame(yearly_rows),
        basket_calibration,
        company_events_df,
        market_events_df,
        product_monthly,
        products_final,
        product_events_df,
        household_income_monthly,
    )
