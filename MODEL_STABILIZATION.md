# Model Stabilization Phase

This phase stabilizes long-horizon simulations without editing the original `data/Product_List.xlsx`.

## 1. Product lifecycle

- Seed products loaded from `Product_List.xlsx` are permanent.
- Simulation-created variants can be launched and retired in memory.
- Default launches are capped at 3 per month.
- New variants cannot create child variants by default.
- A variant can retire only after reaching the minimum age and staying below the configured sales-market-share threshold for the configured number of consecutive months.
- Retirement never writes back to `Product_List.xlsx`.

## 2. Labor recalibration

Labor demand is now anchored to the current labor force at the baseline unemployment rate. Real output is compared with potential output, where potential grows with population and labor productivity. This removes the previous mechanical tendency for unemployment to drift upward simply because productivity and population grew.

## 3. GDP validation

The model computes production GDP and independently verifies it using the expenditure identity available in this closed economy:

`GDP = household consumption + government purchases + private investment + inventory investment`

Monthly nominal and real accounting gaps are reported. They should remain near floating-point zero.

## 4. Inflation validation

The model now reports both:

- CPI inflation: household-consumption price index.
- GDP-deflator inflation: economy-wide production-price index.

The CPI-minus-deflator inflation gap is reported as a diagnostic measure.

## 5. Price stabilization defaults

- `price_adjustment_speed`: 0.04 (previously 0.12)
- `max_monthly_price_change`: 3% (previously 10%)

These changes damp temporary supply-demand imbalances while preserving endogenous inflation/deflation.

## Important

These changes improve numerical/economic stability but do not force GDP growth, inflation, or unemployment to predetermined targets. Long-run outcomes still depend on demand, investment, productivity, fiscal policy, demographics, and the policy agent.
