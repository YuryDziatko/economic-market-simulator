const integerFields = new Set(["simulation_years", "num_households", "num_companies"]);
const percentFields = new Set([
  "tax_rate",
  "corporate_profit_tax_rate",
  "annual_inflation",
  "demographic_growth",
  "annual_labor_productivity_growth",
  "product_innovation_chance",
  "unemployment_transfer_rate",
  "government_consumption_share",
  "general_transfer_share",
  "debt_interest_rate",
]);
const baselineFields = [
  "simulation_years", "num_households", "num_companies", "target_gini",
  "tax_rate", "corporate_profit_tax_rate", "annual_inflation", "demographic_growth",
  "annual_labor_productivity_growth", "product_innovation_chance",
  "unemployment_transfer_rate", "government_consumption_share",
  "general_transfer_share", "debt_interest_rate",
];
const scenarioPercentFields = new Set([
  "tax_rate", "corporate_profit_tax_rate", "annual_inflation",
  "demographic_growth", "annual_labor_productivity_growth", "product_innovation_chance",
]);

let defaults = null;
let currentMode = "single";
const charts = {};

const moneyFormatter = new Intl.NumberFormat("en-US", {
  style: "currency", currency: "USD", maximumFractionDigits: 0,
});
const compactMoneyFormatter = new Intl.NumberFormat("en-US", {
  style: "currency", currency: "USD", notation: "compact", maximumFractionDigits: 2,
});
const integerFormatter = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });

function pct(value, digits = 2) {
  const n = Number(value);
  return Number.isFinite(n) ? `${(n * 100).toFixed(digits)}%` : "—";
}
function money(value) {
  const n = Number(value);
  return Number.isFinite(n) ? moneyFormatter.format(n) : "—";
}
function compactMoney(value) {
  const n = Number(value);
  return Number.isFinite(n) ? compactMoneyFormatter.format(n) : "—";
}
function integer(value) {
  const n = Number(value);
  return Number.isFinite(n) ? integerFormatter.format(n) : "—";
}
function decimal(value, digits = 3) {
  const n = Number(value);
  return Number.isFinite(n) ? n.toFixed(digits) : "—";
}
function signedPctPoint(value, digits = 2) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  return `${n >= 0 ? "+" : ""}${n.toFixed(digits)} pp`;
}
function signedRelative(value, digits = 2) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  return `${n >= 0 ? "+" : ""}${(n * 100).toFixed(digits)}%`;
}
function signedAbsolute(value, digits = 3) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  return `${n >= 0 ? "+" : ""}${n.toFixed(digits)}`;
}

function setStatus(message, isError = false) {
  const status = document.getElementById("status");
  status.textContent = message;
  status.classList.toggle("error", isError);
}

function setInputFromConfig(key, value) {
  const el = document.getElementById(key);
  if (!el || value === undefined || value === null) return;
  el.value = percentFields.has(key) ? Number(value) * 100 : value;
}

async function loadDefaults() {
  setStatus("Loading baseline settings…");
  try {
    const response = await fetch("/api/config");
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Could not load settings");
    defaults = data.defaults;
    baselineFields.forEach(key => setInputFromConfig(key, defaults[key]));
    setStatus("Ready. Percentage fields use normal percent values (for example, 1 = 1%).");
  } catch (error) {
    setStatus(error.message, true);
  }
}

function readBaselineOverrides() {
  const overrides = {};
  for (const key of baselineFields) {
    const el = document.getElementById(key);
    if (!el || el.value === "") continue;
    let value = integerFields.has(key) ? parseInt(el.value, 10) : parseFloat(el.value);
    if (percentFields.has(key)) value /= 100;
    overrides[key] = value;
  }

  // The fiscal allocation shares must reconcile to 100%. Reserve is the unallocated share.
  if ("government_consumption_share" in overrides && "general_transfer_share" in overrides) {
    const allocated = overrides.government_consumption_share + overrides.general_transfer_share;
    if (allocated > 1.0000001) {
      throw new Error("Government purchases + general transfers cannot exceed 100% of gross tax revenue.");
    }
    overrides.government_reserve_share = Math.max(0, 1 - allocated);
  }
  return overrides;
}

function readScenarioOverrides() {
  const keys = [
    "tax_rate", "corporate_profit_tax_rate", "annual_inflation",
    "demographic_growth", "annual_labor_productivity_growth", "product_innovation_chance",
  ];
  const overrides = {};
  for (const key of keys) {
    const el = document.getElementById(`scenario_${key}`);
    if (!el || el.value.trim() === "") continue;
    let value = parseFloat(el.value);
    if (scenarioPercentFields.has(key)) value /= 100;
    overrides[key] = value;
  }
  if (Object.keys(overrides).length === 0) {
    throw new Error("Enter at least one scenario value to compare.");
  }
  return overrides;
}

function setMode(mode) {
  currentMode = mode;
  document.querySelectorAll(".mode-button").forEach(button => {
    button.classList.toggle("active", button.dataset.mode === mode);
  });
  document.getElementById("scenarioPanel").classList.toggle("hidden", mode !== "compare");
  document.getElementById("runButton").textContent = mode === "compare" ? "Compare scenario" : "Run simulation";
  document.getElementById("comparisonTablePanel").classList.add("hidden");
}

function destroyCharts() {
  for (const chart of Object.values(charts)) chart.destroy();
  for (const key of Object.keys(charts)) delete charts[key];
}

function chartBaseOptions({ percent = false, gini = false, currency = false } = {}) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: "index", intersect: false },
    plugins: {
      legend: { position: "bottom", labels: { usePointStyle: true, boxWidth: 8 } },
      tooltip: {
        callbacks: {
          label(context) {
            const label = context.dataset.label ? `${context.dataset.label}: ` : "";
            const v = context.parsed.y;
            if (currency) return label + compactMoney(v);
            if (percent) return label + pct(v);
            if (gini) return label + Number(v).toFixed(3);
            return label + integer(v);
          },
        },
      },
    },
    scales: {
      x: { grid: { display: false }, title: { display: true, text: "Year" } },
      y: {
        beginAtZero: false,
        grid: { color: "rgba(148,163,184,.16)" },
        ticks: {
          callback(value) {
            if (currency) return compactMoney(value);
            if (percent) return `${(Number(value) * 100).toFixed(0)}%`;
            if (gini) return Number(value).toFixed(2);
            return integer(value);
          },
        },
      },
    },
  };
}

function makeChart(id, config) {
  const canvas = document.getElementById(id);
  if (!canvas || typeof Chart === "undefined") return;
  if (charts[id]) charts[id].destroy();
  charts[id] = new Chart(canvas, config);
}

function singleSeriesChart(id, rows, key, label, options = {}) {
  makeChart(id, {
    type: "line",
    data: {
      labels: rows.map(r => `Year ${r.Year}`),
      datasets: [{
        label,
        data: rows.map(r => r[key]),
        tension: .25,
        pointRadius: 3,
        pointHoverRadius: 5,
        borderWidth: 2.5,
      }],
    },
    options: chartBaseOptions(options),
  });
}

function renderSingleCharts(rows) {
  singleSeriesChart("gdpChart", rows, "Real_GDP_Base_Prices", "Real GDP", { currency: true });
  singleSeriesChart("gdpGrowthChart", rows, "Real_GDP_Growth_YoY", "Real GDP growth", { percent: true });
  singleSeriesChart("inflationChart", rows, "Inflation_YoY", "Inflation", { percent: true });
  singleSeriesChart("unemploymentChart", rows, "Unemployment_Rate_End", "Unemployment", { percent: true });
  singleSeriesChart("giniChart", rows, "Income_Gini_End_Class_Average", "Income Gini", { gini: true });
  singleSeriesChart("debtChart", rows, "Debt_to_GDP_End", "Debt / GDP", { percent: true });

  makeChart("scaleChart", {
    type: "line",
    data: {
      labels: rows.map(r => `Year ${r.Year}`),
      datasets: [
        { label: "Households", data: rows.map(r => r.Household_Count_End), tension: .25, borderWidth: 2.2 },
        { label: "Companies", data: rows.map(r => r.Company_Count_End), tension: .25, borderWidth: 2.2 },
        { label: "Products", data: rows.map(r => r.Product_Count_End), tension: .25, borderWidth: 2.2 },
      ],
    },
    options: chartBaseOptions(),
  });
}

function comparisonMetricChart(id, rows, options = {}) {
  if (!rows || rows.length === 0) return;
  const valueKeys = Object.keys(rows[0]).filter(k => k !== "Year");
  makeChart(id, {
    type: "line",
    data: {
      labels: rows.map(r => `Year ${r.Year}`),
      datasets: valueKeys.map(key => ({
        label: key,
        data: rows.map(r => r[key]),
        tension: .25,
        pointRadius: 3,
        pointHoverRadius: 5,
        borderWidth: 2.5,
      })),
    },
    options: chartBaseOptions(options),
  });
}

function renderComparisonCharts(yearly, summaries, scenarioName) {
  comparisonMetricChart("gdpChart", yearly.gdp, { currency: true });
  comparisonMetricChart("gdpGrowthChart", yearly.gdp_growth, { percent: true });
  comparisonMetricChart("inflationChart", yearly.inflation, { percent: true });
  comparisonMetricChart("unemploymentChart", yearly.unemployment, { percent: true });
  comparisonMetricChart("giniChart", yearly.gini, { gini: true });
  comparisonMetricChart("debtChart", yearly.debt_to_gdp, { percent: true });

  const baseline = summaries.Baseline;
  const scenario = summaries[scenarioName];
  makeChart("scaleChart", {
    type: "bar",
    data: {
      labels: ["Households", "Companies", "Products"],
      datasets: [
        { label: "Baseline", data: [baseline.final_households, baseline.final_companies, baseline.final_products] },
        { label: scenarioName, data: [scenario.final_households, scenario.final_companies, scenario.final_products] },
      ],
    },
    options: {
      ...chartBaseOptions(),
      scales: {
        x: { grid: { display: false } },
        y: { beginAtZero: true, grid: { color: "rgba(148,163,184,.16)" } },
      },
    },
  });
}

function card(label, value, delta = "") {
  return `<div class="card"><div class="label">${label}</div><div class="value">${value}</div>${delta ? `<div class="delta">${delta}</div>` : ""}</div>`;
}

function renderSingleCards(summary, yearly) {
  const final = yearly[yearly.length - 1] || {};
  const cards = [
    card("Nominal GDP", compactMoney(summary.nominal_gdp)),
    card("Real GDP growth", pct(summary.real_gdp_growth)),
    card("Inflation", pct(summary.inflation)),
    card("Unemployment", pct(summary.unemployment_rate)),
    card("Income Gini", decimal(summary.income_gini)),
    card("Debt / GDP", pct(summary.public_debt_to_gdp)),
    card("Households", integer(final.Household_Count_End ?? summary.starting_households)),
    card("Companies", integer(final.Company_Count_End ?? summary.starting_companies)),
    card("Products", integer(summary.final_products)),
    card("Average annual wage", compactMoney(final.Average_Wage_Annual)),
    card("Government balance", compactMoney(final.Government_Budget_Balance)),
    card("Public debt", compactMoney(final.Public_Debt_End)),
  ];
  document.getElementById("cards").innerHTML = cards.join("");
}

function renderComparisonCards(data) {
  const scenarioName = data.scenario_names[0];
  const summary = data.summaries[scenarioName];
  const rows = data.kpis.filter(row => row.Scenario === scenarioName);
  const byKey = Object.fromEntries(rows.map(row => [row.KPI, row]));

  function deltaFor(key) {
    const row = byKey[key];
    if (!row) return "";
    if (row.Delta_Type === "pp") return `${signedPctPoint(row.Delta_Percentage_Points)} vs baseline`;
    if (row.Delta_Type === "percent") return `${signedRelative(row.Delta_Relative)} vs baseline`;
    return `${signedAbsolute(row.Delta_Absolute)} vs baseline`;
  }

  const cards = [
    card("Nominal GDP", compactMoney(summary.nominal_gdp), deltaFor("nominal_gdp")),
    card("Real GDP growth", pct(summary.real_gdp_growth), deltaFor("real_gdp_growth")),
    card("Inflation", pct(summary.inflation), deltaFor("inflation")),
    card("Unemployment", pct(summary.unemployment_rate), deltaFor("unemployment_rate")),
    card("Income Gini", decimal(summary.income_gini), deltaFor("income_gini")),
    card("Debt / GDP", pct(summary.public_debt_to_gdp), deltaFor("public_debt_to_gdp")),
    card("Households", integer(summary.final_households), deltaFor("final_households")),
    card("Companies", integer(summary.final_companies), deltaFor("final_companies")),
    card("Products", integer(summary.final_products), deltaFor("final_products")),
    card("Average annual wage", compactMoney(summary.average_wage_annual), deltaFor("average_wage_annual")),
    card("Government balance", compactMoney(summary.government_budget_balance), deltaFor("government_budget_balance")),
    card("Public debt", compactMoney(summary.public_debt), deltaFor("public_debt")),
  ];
  document.getElementById("cards").innerHTML = cards.join("");
}

function formatKpiValue(unit, value) {
  if (unit === "currency") return compactMoney(value);
  if (unit === "percent") return pct(value);
  if (unit === "count") return integer(value);
  if (unit === "decimal") return decimal(value);
  return Number(value).toLocaleString("en-US", { maximumFractionDigits: 3 });
}

function renderComparisonTable(data) {
  const scenarioName = data.scenario_names[0];
  const scenarioRows = data.kpis.filter(row => row.Scenario === scenarioName);
  const header = `<thead><tr><th>Metric</th><th>Baseline</th><th>${scenarioName}</th><th>Change</th></tr></thead>`;
  const body = scenarioRows.map(row => {
    let delta;
    if (row.Delta_Type === "pp") delta = signedPctPoint(row.Delta_Percentage_Points);
    else if (row.Delta_Type === "percent") delta = signedRelative(row.Delta_Relative);
    else delta = signedAbsolute(row.Delta_Absolute);
    return `<tr><td>${row.Label}</td><td>${formatKpiValue(row.Unit, row.Baseline_Value)}</td><td>${formatKpiValue(row.Unit, row.Scenario_Value)}</td><td>${delta}</td></tr>`;
  }).join("");
  document.getElementById("comparisonTable").innerHTML = header + `<tbody>${body}</tbody>`;
  document.getElementById("comparisonTablePanel").classList.remove("hidden");
}

async function runSingle(overrides) {
  const response = await fetch("/api/simulate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ overrides, include_monthly: false }),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || "Simulation failed");

  renderSingleCards(data.summary, data.yearly);
  renderSingleCharts(data.yearly);
  document.getElementById("resultTitle").textContent = "Final-year snapshot";
  document.getElementById("resultSubtitle").textContent = `Year ${data.summary.final_year} outcome from a ${overrides.simulation_years}-year simulation.`;
  document.getElementById("comparisonTablePanel").classList.add("hidden");
  return data;
}

async function runComparison(baselineOverrides) {
  const scenarioName = document.getElementById("scenario_name").value.trim() || "Alternative policy";
  const scenarioOverrides = readScenarioOverrides();
  const response = await fetch("/api/compare", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      baseline_name: "Baseline",
      baseline_overrides: baselineOverrides,
      scenarios: { [scenarioName]: scenarioOverrides },
    }),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || "Scenario comparison failed");

  renderComparisonCards(data);
  renderComparisonCharts(data.yearly, data.summaries, scenarioName);
  renderComparisonTable(data);
  document.getElementById("resultTitle").textContent = `${scenarioName} vs baseline`;
  document.getElementById("resultSubtitle").textContent = "Both simulations use the same random seed, so the differences primarily reflect the settings you changed.";
  return data;
}

async function runDashboard() {
  const button = document.getElementById("runButton");
  const reset = document.getElementById("resetButton");
  const output = document.getElementById("output");
  button.disabled = true;
  reset.disabled = true;
  setStatus(currentMode === "compare" ? "Running baseline and scenario…" : "Running simulation…");

  try {
    if (typeof Chart === "undefined") {
      throw new Error("Chart.js did not load. Check your internet connection and reload the page.");
    }
    const overrides = readBaselineOverrides();
    const data = currentMode === "compare" ? await runComparison(overrides) : await runSingle(overrides);
    output.textContent = JSON.stringify(data, null, 2);
    document.getElementById("results").classList.remove("hidden");
    setStatus("Simulation complete.");
    document.getElementById("results").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    setStatus(error.message || String(error), true);
    output.textContent = error.stack || String(error);
  } finally {
    button.disabled = false;
    reset.disabled = false;
  }
}

function resetDefaults() {
  if (!defaults) return;
  baselineFields.forEach(key => setInputFromConfig(key, defaults[key]));
  document.querySelectorAll("#scenarioPanel input[type='number']").forEach(el => { el.value = ""; });
  document.getElementById("scenario_name").value = "Alternative policy";
  setStatus("Baseline settings restored.");
}

document.querySelectorAll(".mode-button").forEach(button => {
  button.addEventListener("click", () => setMode(button.dataset.mode));
});
document.getElementById("runButton").addEventListener("click", runDashboard);
document.getElementById("resetButton").addEventListener("click", resetDefaults);

loadDefaults();
