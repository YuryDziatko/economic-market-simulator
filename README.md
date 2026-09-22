# Agent-Based Economic Simulation

Python simulation of households, firms, COICOP consumption divisions, prices, GDP, inequality, economic shocks, productivity, demographics, product evolution, and market structure.

## V3.1 market mechanics

The engine does not set supply equal to demand. Each month:

1. Household income grows by source: labor income follows inflation plus productivity, transfers are indexed to inflation, and capital income receives a larger productivity-linked return.
2. Household budgets generate desired **real quantities**. Price elasticity is applied directly to quantity, avoiding a double price adjustment.
3. Firm productivity rises over time, increasing effective production capacity and lowering unit production cost.
4. Firms produce from lagged expected demand, subject to effective production capacity.
5. Firms carry inventory between months.
6. Household orders are allocated to firms by configured market share.
7. Sales are limited by available inventory; unfilled orders become shortages.
8. Firms calculate revenue, cost, profit, investment, and capacity expansion.
9. Prices react to shortages, excess inventory, the baseline inflation target, subsidies, and cost shocks.
10. CPI, consumption, investment, government spending, GDP, Gini, productivity, and shortage rates are recorded.
11. Population grows annually even when product-catalogue evolution is disabled.

This creates genuine supply-demand imbalance and lets long-run real growth emerge from productivity, household income growth, and demographics.

## Baseline growth parameters

These are editable in `simulation_config.xlsx` on the `household_config` sheet:

- `inflation_target_annual` — default `0.02` (2.0%)
- `productivity_growth_rate` — default `0.015` (1.5%)
- `population_growth_rate` — default `0.01` (1.0%)
- `capital_productivity_multiplier` — default `1.50`

With the default seed and a 36-month run without catalogue evolution, the model produces approximately 2% annual inflation and positive baseline real-GDP growth. Exact results depend on configuration and random seed.

## Setup

```bash
pip install -r requirements.txt
python build_goods_db.py
python simulate.py --ticks 120
python plot_results.py --results results/history.csv --out results/charts.png
```

Or run the convenience launcher:

```bash
python main.py --ticks 120
```

## Shock example

A 30% Transport supply shock beginning in month 13 for six months:

```bash
python simulate.py --ticks 36 --compare-shock "07,supply,-0.30,13,6" --no-evolution
python plot_results.py --compare results/baseline.csv results/shock.csv --labels Baseline Shock --out results/charts_compare.png
```

In the default validation run, the transport shock creates a temporary real shortage, raises CPI relative to baseline, and lowers real GDP relative to baseline.

## Main files

- `household_model.py` — income brackets, source-specific income shares, consumption behavior, Gini and population evolution
- `producer_model.py` — firms, market structures, productivity, production capacity, inventory, profit and investment
- `market.py` — monthly supply-demand matching, income dynamics, price formation, CPI and GDP accounting
- `product_evolution.py` — annual catalogue evolution
- `build_goods_db.py` — builds the product database from `Product_List.xlsx`
- `simulation_config.xlsx` — simulation parameters
- `plot_results.py` — dashboards and scenario comparison

## Notes

- The product catalogue `P × Q` value is an annual reference value and is not identical to simulated GDP (`C + I + G`).
- Division quantities are calibrated to normalized COICOP expenditure weights so random product quantities do not make expensive sectors dominate the starting economy.
- `--no-evolution` disables product-catalogue mutation only; demographic growth and productivity continue.
- Firm market shares currently determine order allocation. A natural next extension is endogenous consumer choice based on firm price and quality.
