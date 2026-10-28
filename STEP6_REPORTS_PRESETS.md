# Step 6 — Downloadable reports + saved scenario presets

## Goals

1. Let a user reuse common policy scenarios quickly.
2. Let a user save a custom scenario without adding accounts or a database.
3. Let a user download the results of the last run as Excel or CSV ZIP.
4. Keep the Render web service stateless.

## Scenario presets

Compare mode includes built-in presets:

- Higher income tax
- Lower income tax
- Inflation shock
- Population boom
- Productivity boom
- Innovation boom
- Demand-squeeze stress

Custom presets are stored in browser `localStorage` under `economic-market-simulator-presets-v1`.

A custom preset stores only scenario overrides, not baseline settings or simulation results. It is local to that browser/device and is not synchronized across computers.

## Report API

### Single simulation

`POST /api/reports/simulation.xlsx`

Uses the same request schema as `/api/simulate` and returns a multi-sheet Excel workbook.

`POST /api/reports/simulation.zip`

Returns a ZIP containing JSON metadata plus the core CSV output tables.

### Scenario comparison

`POST /api/reports/comparison.xlsx`

Uses the same request schema as `/api/compare` and returns KPI tables, scenario summaries, configs, and yearly chart datasets.

`POST /api/reports/comparison.zip`

Returns those comparison datasets as CSV/JSON files.

## Why reports re-run the simulation

The browser retains only the small request payload. When a download button is clicked, it submits the same request to a report endpoint. The server runs the model again and creates the file in memory.

This design:

- does not depend on temporary Render disk files;
- does not require session state;
- works across multiple Render workers;
- avoids sending huge detailed DataFrames to the browser just to download them again.

Using the same random seed keeps the downloaded report consistent with the dashboard run.

## Standard report contents

Excel and CSV ZIP reports include the core tables:

- summary/config
- yearly summary
- monthly macro
- household income by class/month
- government monthly flows
- company events
- market events
- product events
- final product database

`product_monthly` is omitted from standard web reports because it can become very large after many years of product innovation.

## Local run

```powershell
uvicorn web_main:app --reload
```

Open `http://127.0.0.1:8000/`, run a simulation, then use the download buttons below the KPI cards.
