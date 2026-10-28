# Step 4 — Chart.js Dashboard

This step turns the FastAPI MVP into an interactive economic dashboard.

## Features

- **Single run** mode calls `POST /api/simulate`.
- **Compare scenario** mode calls `POST /api/compare`.
- Baseline defaults are loaded from `GET /api/config`.
- Percentage inputs are displayed in human form: `20` = 20%, `2` = 2%, `1` = 1%. JavaScript converts them to decimals before calling the API.
- The same random seed is retained for baseline/scenario comparisons.

## Charts

1. Real GDP
2. Real GDP growth
3. Inflation
4. Unemployment
5. Income Gini
6. Public debt / GDP
7. Economic scale (households, companies, products)

## Important fiscal validation

Government purchases and general transfers are entered as percentages of gross tax revenue. The browser automatically sets the reserve to the remaining share. The combined user inputs may not exceed 100%.

## Local run

```powershell
pip install -r requirements.txt
uvicorn web_main:app --reload
```

Open:

- Dashboard: http://127.0.0.1:8000/
- API docs: http://127.0.0.1:8000/docs

## Git

```powershell
git status
git add -A
git commit -m "Add Chart.js economic dashboard"
git push
```
