# Agent-Based Economic Simulation

Python simulation of households, firms, COICOP consumption divisions, prices, GDP, inequality, economic shocks, product evolution, and market structure.

## V3 market mechanics

The V3 engine no longer sets supply equal to demand. Each month:

1. Household spending is converted to desired real quantity using the current division price index.
2. Firms produce from lagged expected demand, subject to production capacity.
3. Firms carry inventory between months.
4. Household orders are allocated to firms by configured market share.
5. Sales are limited by available inventory; unfilled orders become shortages.
6. Firms calculate revenue, production cost, profit, investment, and capacity expansion.
7. Prices react to shortages, excess inventory, money growth, subsidies, and cost shocks.
8. CPI, consumption, investment, government spending, GDP, Gini, and shortage rates are recorded.

This creates genuine supply-demand imbalance instead of mechanically forcing equilibrium.

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

## Main files

- `household_model.py` — household income brackets, consumption behavior, Gini and population evolution
- `producer_model.py` — firms, market structures, production capacity, inventory, profit and investment
- `market.py` — monthly supply-demand matching, price formation, CPI and GDP accounting
- `product_evolution.py` — annual catalogue evolution
- `build_goods_db.py` — builds the product database from `Product_List.xlsx`
- `simulation_config.xlsx` — simulation parameters
- `plot_results.py` — dashboards and scenario comparison

## Notes

- The product catalogue `P × Q` value is an annual reference value and is not identical to simulated GDP (`C + I + G`).
- Division quantities are calibrated to normalized COICOP expenditure weights so random product quantities do not make expensive sectors dominate the starting economy.
- In V3.0, firm market shares determine order allocation. A natural V3.1 extension is endogenous consumer choice based on price and quality.
