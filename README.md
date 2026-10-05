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

## Phase 1.1 — Intelligent company entry / exit

At the beginning of each year after Year 1, the economy-wide number of potential entrants is still determined by prior-year **real GDP growth × company growth sensitivity**. Those entrants are now allocated to specific product markets using three prior-year signals:

- persistent shortage / unmet demand,
- product demand growth,
- operating-profit margin proxy.

If recession-driven exits are enabled, exits are allocated to markets with excess inventory, falling demand, and losses. A product is never allowed to fall below one producer.

Entry and exit now affect real production capacity. An entrant adds a configurable share of average incumbent capacity; an exit removes a configurable share. Product market structure is reclassified dynamically: 1 firm = Monopoly, 2–4 = Oligopoly, 5+ = Competitive.

Detailed annual allocation is written to `output/market_events.csv` and to the `market_events` sheet in the output workbook. `product_monthly` now also includes `Firm_Count`, the evolving market structure, and a product-level operating-profit proxy.


## Phase 1.2 — Monthly product innovation

The original `data/Product_List.xlsx` remains the seed database and is never modified.
At the start of each month, every eligible product has an editable probability (default 2%) of launching one new variant. Variant names always use the original root product name plus launch month/year/serial/generation, so recursive innovation does not create unreadably long names.

Example:

- Parent: `Beer | Corona Extra | 12pk Bottles | $18.99`
- Variant: `Beer | Corona Extra_M03_Y02_0127_G1 | 12pk Bottles | random launch price`

A variant inherits the parent's COICOP code, division, category, unit and approximately its elasticity. To keep the model closed, the launch initially transfers a configurable share of the parent's baseline demand and production rather than creating new spending or productive capacity from nothing. After launch, it behaves like any other product: its price, demand, production, inventory and firm count evolve normally.

New settings in `General_Settings` include:

- `product_innovation_chance` — default 2% per eligible product per month
- `innovation_demand_share` — default 10% of parent baseline spending
- `innovation_output_share` — default 10% of parent output/inventory
- launch price range — default 85% to 115% of the parent's current price
- elasticity variation — default 0.05 standard deviation
- initial firms — default 1
- optional monthly launch cap
- whether newly created variants can themselves innovate later

The run writes:

- `output/Product_List_Seed_Copy.xlsx` — untouched copy of the starting product workbook
- `output/Product_List_Simulation.xlsx` — final dynamic product database plus launch-event log
- `output/product_events.csv` — every product launch with parent, date, price and transferred shares
- `output/products_final.csv` — final product state

**Compounding note:** with a 2% monthly probability and `new_products_can_innovate = 1`, product variety compounds. Starting from 477 products, a 10-year run can reasonably reach several thousand products. Set `new_products_can_innovate = 0` or use `max_new_products_per_month` if you want slower growth.
