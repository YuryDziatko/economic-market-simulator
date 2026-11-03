# Phase 4A — Household Savings, Company Investment and Capital Stock

## What changed

Phase 4A adds a real intertemporal link between income today and productive capacity tomorrow.

```text
Disposable household income
        ├── Consumption
        └── Savings ─────────────┐
                                 ├── Investment funding pool
Retained business income ────────┘
                                 ↓
                        Realized investment
                                 ↓
                     Productive capital stock
                                 ↓
                       Production capacity
                                 ↓
                           Future output
```

## Household savings

Each income class has a base, minimum and maximum saving rate in `Savings_Settings`.

The actual saving rate is:

```text
base saving rate + savings sensitivity × (policy interest rate - neutral interest rate)
```

and is clipped to the class minimum/maximum.

Household disposable income now satisfies:

```text
Disposable income = Consumption budget + Savings
```

## Retained business income

After the corporate-tax proxy, part of business/capital income is retained by firms. Only the remainder is distributed to household owners as capital income. This avoids simultaneously treating the same business income as household income and internal investment finance.

## Investment funding pool

The carried-forward pool satisfies:

```text
Pool end = Pool begin + Household savings + Retained business income - Realized investment
```

Unused funding remains available in future months.

## Desired investment

Monthly desired investment includes:

- replacement investment for depreciation;
- expansion investment driven by capacity utilization;
- prior product shortages;
- prior operating-margin proxy;
- an interest-rate adjustment.

Higher policy rates relative to the neutral rate reduce expansion investment. Lower rates increase it.

## Investment demand vs recipient capital

The model deliberately separates two concepts:

1. **Investment-goods demand** — which products businesses purchase as capital goods/services. It uses the editable `Investment_Demand` COICOP weights.
2. **Recipient-market allocation** — which product markets receive the resulting productive capital. It uses utilization, shortage and margin signals.

This avoids treating the seller of an investment good as automatically being the industry receiving the new productive capacity.

## Capital and capacity

The core capital identity is:

```text
Capital(t) = Capital(t-1) + Investment(t) - Depreciation(t)
```

Capacity then responds to the capital-stock ratio using `capital_efficiency`, subject to `max_monthly_capacity_growth`.

Production planning remains demand-responsive, but next-month production cannot exceed available capacity.

## Innovation and firm dynamics

- Product innovation transfers a share of the parent's capital and capacity to the child product; it does not create productive assets from nothing.
- Firm entry/exit scales productive capacity and capital together with the market's production base.

## New scalar settings

- `neutral_interest_rate`
- `savings_rate_sensitivity`
- `annual_depreciation_rate`
- `capital_output_ratio`
- `initial_capacity_utilization`
- `profit_retention_rate`
- `investment_interest_sensitivity`
- `capital_efficiency`
- `max_monthly_capacity_growth`
- `max_investment_share_of_funds`

## New structural sheets

- `Savings_Settings`
- `Investment_Demand`
- `Phase4A_Model`

## New outputs

Monthly/yearly output now includes:

- Household_Savings
- Household_Savings_Rate
- Accumulated_Household_Savings
- Retained_Business_Income
- New_Investment_Funds
- Investment_Funding_Pool_End
- Desired_Investment
- Planned_Investment
- Realized_Investment
- Unmet_Investment_Demand_Value
- Capital_Stock_End
- Capital_Depreciation
- Capacity_Utilization

Product-level output also contains capacity, utilization, capital stock and allocated investment.

## Validation

Phase 4A tests verify:

- household savings are positive under the default calibration;
- the investment funding pool reconciles month to month;
- capital follows `K(t)=K(t-1)+I(t)-Depreciation(t)` in a no-innovation Year-1 test;
- productive utilization remains bounded;
- higher interest rates raise household saving rates;
- higher interest rates reduce desired investment.
