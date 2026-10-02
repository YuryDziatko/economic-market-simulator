# EconomicSimulation — Phase 1

Phase 1 turns the Phase-0 baseline into a monthly supply/demand simulation.

## New in Phase 1

- Household consumption baskets by income class.
- Period-0 basket calibration so class budgets and product sales reconcile exactly.
- Product demand reacts to price using each product's 0–1 elasticity.
- Household class budgets constrain total planned spending.
- Product inventory, realized sales, unmet demand, shortages, and surpluses.
- Endogenous price response to supply/demand imbalance plus background inflation.
- Company/product production responds gradually to demand.
- Competitive markets react faster than oligopoly; oligopoly faster than monopoly.
- Real GDP changes because product quantities now change.
- Household count grows once per year using `demographic_growth` (1% default).
- Company count grows once per year from the previous year's real GDP growth.

## Annual growth rules

### Households

At the start of simulation Year 2 and later:

`Households(year) = round(initial_households × (1 + demographic_growth)^(year - 1))`

With 1,000 initial households and 1% demographics:

- Year 1: 1,000
- Year 2: 1,010
- Year 3: about 1,020

### Companies

At the start of Year 2 and later:

`company_entry_rate = max(previous_real_GDP_growth, 0) × company_growth_sensitivity`

`new_companies = round(current_companies × company_entry_rate)`

Default sensitivity = 1.0.

Example: if real GDP grew 3%, about 3% more companies enter.

Company exits during recessions are disabled by default. Set `allow_company_exits = 1` to enable them.

## Monthly Phase-1 loop

1. Determine current household count and class consumption budgets.
2. Calculate product demand by household class.
3. Apply product price elasticity.
4. Re-scale each class to its consumption budget.
5. Compare demand with production + inventory.
6. Realized sales are limited by available supply.
7. Unsold output becomes inventory; excess demand becomes unmet demand.
8. Price changes from background inflation plus supply/demand pressure.
9. Next month's production adjusts toward demand.
10. Recalculate nominal GDP, real GDP, inflation, profit, shortages and inventory.

## Important Phase-1 simplifications

- Household income distribution/Gini is fixed in real terms after Period 0.
- New households preserve the same class distribution.
- New companies affect the company population count; detailed entrant balance sheets and product assignments are a later refinement.
- The interest rate is still stored but not behavioral yet.
- Government spending is not yet modeled.
- Product demand uses own-price elasticity only; explicit substitute/complement cross-elasticities are a future phase.

## Run in PyCharm

Use Python 3.11+.

```bash
pip install -r requirements.txt
python main.py
```

Edit assumptions in:

`data/Simulation_Settings.xlsx`

Main outputs are written to `output/`, including:

- `monthly_macro.csv`
- `yearly_summary.csv`
- `product_monthly.csv`
- `company_events.csv`
- `basket_calibration.csv`
- `Simulation_Output_Phase1.xlsx`
