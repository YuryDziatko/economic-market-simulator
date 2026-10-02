from __future__ import annotations

import numpy as np
import pandas as pd


def simulate(products: pd.DataFrame, companies: pd.DataFrame, production: pd.DataFrame, years: int, annual_inflation: float, price_noise: float, tax_rate: float, n_households: int, n_companies: int, rng: np.random.Generator):
    months = years * 12
    base_prices = products.set_index("Product_ID")["Base_Price"].astype(float)
    quantities = products.set_index("Product_ID")["Quantity_P0"].astype(float)
    current_prices = base_prices.copy()
    base_gdp = float((base_prices * quantities).sum())
    if base_gdp <= 0:
        raise ValueError("Period-0 GDP is zero")

    fixed_p0 = companies.set_index("Company_ID")["Fixed_Cost_P0"].astype(float)
    var_ratio = companies.set_index("Company_ID")["Variable_Cost_Ratio"].to_dict()
    prod = production.copy()
    prod["Variable_Cost_Ratio"] = prod["Company_ID"].map(var_ratio)

    rows = []
    cpi_history = [100.0]
    prev_gdp = base_gdp

    def append_row(t, year, month, gdp, cpi, mom_infl, infl12, price_change_median, producer_profit):
        taxes = gdp * tax_rate
        consumption = gdp - taxes
        rows.append({
            "Period_Month": t,
            "Year": year,
            "Month_in_Year": month,
            "Nominal_GDP_Monthly": gdp,
            "Nominal_GDP_Annualized": gdp * 12,
            "Nominal_GDP_Growth_MoM": 0.0 if t == 0 else gdp / prev_gdp - 1,
            "Real_GDP_Monthly_Base_Prices": base_gdp,
            "Real_GDP_Growth_MoM": 0.0,
            "CPI_Index": cpi,
            "Inflation_MoM": mom_infl,
            "Inflation_12M": infl12,
            "Median_Product_Price_Change": price_change_median,
            "Household_Count": n_households,
            "Company_Count": n_companies,
            "Household_Gross_Income": gdp,
            "Household_Taxes": taxes,
            "Household_Consumption": consumption,
            "Fiscal_Demand_Gap": taxes,
            "Producer_Profit": producer_profit,
        })

    append_row(0, 0, 0, base_gdp, 100.0, 0.0, 0.0, 0.0, float(companies["Profit_P0"].sum()))
    target_monthly = annual_inflation / 12.0

    for t in range(1, months + 1):
        noise = rng.normal(0.0, price_noise, len(current_prices))
        noise -= np.median(noise)
        changes = np.clip(target_monthly + noise, -0.95, None)
        current_prices *= (1.0 + changes)

        gdp = float((current_prices * quantities).sum())
        cpi = gdp / base_gdp * 100.0
        mom_infl = cpi / cpi_history[-1] - 1.0
        infl12 = cpi / cpi_history[t - 12] - 1.0 if t >= 12 else (cpi / 100.0) ** (12.0 / t) - 1.0

        current_prod_prices = prod["Product_ID"].map(current_prices)
        revenue = current_prod_prices * prod["Quantity_P0"]
        variable = revenue * prod["Variable_Cost_Ratio"]
        rev_by_company = revenue.groupby(prod["Company_ID"]).sum().reindex(fixed_p0.index, fill_value=0.0)
        var_by_company = variable.groupby(prod["Company_ID"]).sum().reindex(fixed_p0.index, fill_value=0.0)
        fixed = fixed_p0 * (cpi / 100.0)
        profit = float((rev_by_company - var_by_company - fixed).sum())

        year = (t - 1) // 12 + 1
        month = (t - 1) % 12 + 1
        append_row(t, year, month, gdp, cpi, mom_infl, infl12, float(np.median(changes)), profit)
        cpi_history.append(cpi)
        prev_gdp = gdp

    monthly = pd.DataFrame(rows)
    yearly_rows = []
    for year in range(1, years + 1):
        end = monthly.loc[monthly["Period_Month"] == year * 12].iloc[0]
        start = monthly.loc[monthly["Period_Month"] == (year - 1) * 12].iloc[0]
        yearly_rows.append({
            "Year": year,
            "Nominal_GDP_Annualized": end["Nominal_GDP_Annualized"],
            "Nominal_GDP_Growth_YoY": end["Nominal_GDP_Monthly"] / start["Nominal_GDP_Monthly"] - 1,
            "Real_GDP_Annualized_Base_Prices": end["Real_GDP_Monthly_Base_Prices"] * 12,
            "Real_GDP_Growth_YoY": 0.0,
            "Inflation_YoY": end["CPI_Index"] / start["CPI_Index"] - 1,
            "CPI_Index": end["CPI_Index"],
            "Household_Count": int(end["Household_Count"]),
            "Company_Count": int(end["Company_Count"]),
            "Producer_Profit_Monthly": end["Producer_Profit"],
        })
    return monthly, pd.DataFrame(yearly_rows)
