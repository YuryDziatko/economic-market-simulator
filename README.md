# EconomicSimulation — Phase 0

A PyCharm-ready starting point for an agent-based economic simulation using the supplied product list.

## Starting accounting identity

At Period 0 the project enforces:

**GDP = total product value = total producer revenue = total household gross income**

With the default **tax = transfer = savings = 0**, household **consumption = income = GDP**.

## Included databases

- `products`: 477 products/services from `Product_List.xlsx`, plus quantity, price, elasticity and market structure.
- `households`: Low, Middle, High, Top 1%, Top 0.1%; income distribution calibrated to the chosen Gini.
- `companies`: Private/Public and Small/Middle/Big producers with revenue, fixed costs, variable costs, profit, margin, investment.
- `production`: many-to-many link between companies and products.
- `monthly_macro`: GDP, GDP growth, CPI/inflation, household/company counts, household consumption, producer profit.
- `yearly_summary`: one row per simulated year.

## Run in PyCharm

1. Open this folder as a PyCharm project.
2. Select Python 3.11+.
3. In the terminal run:

```bash
pip install -r requirements.txt
```

4. Edit `data/Simulation_Settings.xlsx`.
5. Run `main.py`.
6. Review `output/Simulation_Output.xlsx` and the CSV files.

## Editable settings workbook

### General_Settings
Defaults requested for the starting model:

- Gini = 30%
- Taxes = 0%
- Interest rate = 0%
- Inflation = 2%
- Households = 1,000
- Companies = 1,000
- Simulation = 10 years

### Household_Classes
Default percentile groups:

- Low = bottom 40%
- Middle = 40–80%
- High = 80–99%
- Top 1% = 99–99.9%
- Top 0.1% = top 0.1%

The class counts come from these shares. The chosen Gini changes the average income and income share of each group.

### Company_Settings
Defaults:

- Size mix: 70% Small, 25% Middle, 5% Big
- Ownership: 90% Private, 10% Public
- Markets: 70% Competitive, 25% Oligopoly, 5% Monopoly
- Competitive: 8–20 firms per product
- Oligopoly: 3–4 firms
- Monopoly: 1 firm

### Quantity_Limits
Each product category has an editable minimum and maximum monthly quantity. The Period-0 quantity of each product is random inside that interval.

## Phase 0 dynamics

- Quantities are fixed after Period 0.
- Each month product prices change around `annual inflation / 12`.
- The cross-product median price change is targeted to `inflation / 12`.
- Random dispersion allows individual prices to rise faster/slower and occasionally fall.
- Product absolute demand elasticity is random from 0 to 1, but is not yet used.
- Real GDP growth is 0% because quantities are fixed; nominal GDP changes with prices.

## Good Phase 1 additions

1. Household consumption baskets by income class.
2. Elasticity-driven demand when relative prices change.
3. Inventories, shortages and unsold goods.
4. Company hiring/wages and unemployment.
5. Company investment and entry/exit.
6. Government taxes, transfers and spending.
7. Interest rate effects on saving, credit and investment.
8. Endogenous GDP growth and inflation instead of exogenous price drift.
