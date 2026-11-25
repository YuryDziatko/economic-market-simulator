# Model Calibration — Sticky Prices and Neutral Baseline

This calibration follows the stabilization phase and keeps `data/Product_List.xlsx` unchanged.

## Main changes

- Price increases and price decreases are asymmetric. Shortages move prices faster than comparable surpluses.
- Individual monthly price cuts are capped more tightly than price increases.
- Firms form inflation expectations from the configured inflation target plus recent inflation instead of abandoning the target immediately.
- Old inventories have only partial influence on price setting.
- Service-like output is not carried as inventory; physical goods experience inventory clearance/obsolescence between months.
- Production cuts react more slowly than production expansions.
- Wages receive full inflation and productivity pass-through in the neutral calibration.
- Employment sensitivity to temporary output gaps is lower, reducing mechanical long-run unemployment drift.
- Persistently unused productive capital is scrapped faster than normally utilized capital.

## Important modeling rule

Deflation is **not prohibited**. A sufficiently deep and persistent demand shortfall can still produce negative CPI inflation. The calibration only prevents mild inventory imbalances from creating years of economy-wide deflation in an otherwise neutral run.

## Seed goods

The original `Product_List.xlsx` is a read-only seed database. None of these calibration rules edit its rows, names, units, prices, sheets, or categories.

## 20-year neutral validation

Using 1,000 households, 1,000 companies, 0.5% annual population growth, 2% inflation target, 20% household tax, 20% corporate tax, and the fixed random seed, the calibrated run ended approximately at:

- CPI inflation: **2.78%**
- Unemployment: **5.81%**
- Capacity utilization: **70.02%**
- Debt/GDP: **11.13%**
- Real GDP growth in year 20: **-0.42%**

The remaining slight long-run real-output drift is a separate demand/growth calibration issue; the price/labor instability that previously produced chronic deflation and extreme unemployment is removed.

A deliberately severe contraction (zero inflation target, 20% policy rate, 100% fiscal reserve, falling population) still produces roughly -0.5% to -0.8% annual deflation, confirming that negative inflation remains possible rather than hard-clamped.
