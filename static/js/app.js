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


function numberFromInput(id) {
  const el = document.getElementById(id);
  if (!el || el.value === "") return null;
  const n = Number(el.value);
  return Number.isFinite(n) ? n : null;
}

function collectInputWarnings() {
  const warnings = [];
  const pop = numberFromInput("demographic_growth");
  const inflation = numberFromInput("annual_inflation");
  const incomeTax = numberFromInput("tax_rate");
  const corpTax = numberFromInput("corporate_profit_tax_rate");
  const innovation = numberFromInput("product_innovation_chance");
  const productivity = numberFromInput("annual_labor_productivity_growth");
  const gini = numberFromInput("target_gini");
  const years = numberFromInput("simulation_years");
  const gov = numberFromInput("government_consumption_share");
  const transfers = numberFromInput("general_transfer_share");

  if (pop !== null && Math.abs(pop) >= 5) warnings.push(`Population growth of ${pop}% per year compounds very quickly and can dominate labor-market results.`);
  if (pop !== null && Math.abs(pop) >= 20) warnings.push("Population growth above ±20% is an extreme stress-test assumption rather than a typical demographic scenario.");
  if (inflation !== null && inflation >= 10) warnings.push(`An inflation target of ${inflation}% is a high-inflation scenario.`);
  if (inflation !== null && inflation < 0) warnings.push("A negative inflation target represents a deliberate deflation scenario.");
  if (incomeTax !== null && incomeTax > 50) warnings.push(`Household income tax of ${incomeTax}% is a high-tax stress scenario.`);
  if (corpTax !== null && corpTax > 50) warnings.push(`Corporate tax of ${corpTax}% is a high-tax stress scenario.`);
  if (innovation !== null && innovation >= 5) warnings.push(`${innovation}% monthly product innovation compounds rapidly because many products can create variants.`);
  if (productivity !== null && productivity >= 5) warnings.push(`${productivity}% annual labor-productivity growth can materially reduce labor needed per unit of output.`);
  if (gini !== null && gini >= 0.60) warnings.push(`A starting Gini of ${gini.toFixed(2)} represents very high income inequality.`);
  if (years !== null && years >= 25) warnings.push(`A ${years}-year simulation magnifies compounding assumptions; interpret long-horizon results cautiously.`);
  if (gov !== null && transfers !== null && gov + transfers > 100) warnings.push("Government purchases plus general transfers exceed 100% of gross tax revenue and must be reduced.");
  return warnings;
}

function renderInputWarnings() {
  const box = document.getElementById("inputWarnings");
  const warnings = collectInputWarnings();
  if (!box) return;
  if (warnings.length === 0) {
    box.classList.add("hidden");
    box.innerHTML = "";
    return;
  }
  box.innerHTML = `<strong>Check these assumptions:</strong><ul>${warnings.map(w => `<li>${w}</li>`).join("")}</ul>`;
  box.classList.remove("hidden");
}

function badge(label, value, tone = "neutral") {
  return `<span class="status-badge ${tone}"><span class="status-dot"></span>${label}: ${value}</span>`;
}

function classifyGrowth(value) {
  if (!Number.isFinite(value)) return ["Growth", "—", "neutral"];
  if (value < 0) return ["Growth", `Recession ${pct(value)}`, "danger"];
  if (value < 0.01) return ["Growth", `Weak ${pct(value)}`, "warning"];
  if (value <= 0.035) return ["Growth", `Moderate ${pct(value)}`, "good"];
  return ["Growth", `Rapid ${pct(value)}`, "warning"];
}

function classifyInflation(value, target) {
  if (!Number.isFinite(value)) return ["Inflation", "—", "neutral"];
  if (value < 0) return ["Inflation", `Deflation ${pct(value)}`, "danger"];
  if (value >= 0.08) return ["Inflation", `Very high ${pct(value)}`, "danger"];
  if (value >= 0.05) return ["Inflation", `High ${pct(value)}`, "warning"];
  if (Number.isFinite(target) && Math.abs(value - target) <= 0.01) return ["Inflation", `Near target ${pct(value)}`, "good"];
  return ["Inflation", pct(value), "neutral"];
}

function classifyUnemployment(value) {
  if (!Number.isFinite(value)) return ["Unemployment", "—", "neutral"];
  if (value >= 0.15) return ["Unemployment", `Severe ${pct(value)}`, "danger"];
  if (value >= 0.10) return ["Unemployment", `High ${pct(value)}`, "danger"];
  if (value >= 0.06) return ["Unemployment", `Elevated ${pct(value)}`, "warning"];
  return ["Unemployment", `Low ${pct(value)}`, "good"];
}

function classifyDebt(value) {
  if (!Number.isFinite(value)) return ["Debt / GDP", "—", "neutral"];
  if (value >= 1.0) return ["Debt / GDP", `High ${pct(value)}`, "danger"];
  if (value >= 0.60) return ["Debt / GDP", `Elevated ${pct(value)}`, "warning"];
  return ["Debt / GDP", pct(value), "good"];
}

function classifyGini(value) {
  if (!Number.isFinite(value)) return ["Inequality", "—", "neutral"];
  if (value >= 0.50) return ["Inequality", `Very high ${decimal(value)}`, "danger"];
  if (value >= 0.40) return ["Inequality", `High ${decimal(value)}`, "warning"];
  return ["Inequality", decimal(value), "neutral"];
}

function renderStatusBadges(summary, targetInflation) {
  const items = [
    classifyGrowth(Number(summary.real_gdp_growth)),
    classifyInflation(Number(summary.inflation), Number(targetInflation)),
    classifyUnemployment(Number(summary.unemployment_rate)),
    classifyGini(Number(summary.income_gini)),
    classifyDebt(Number(summary.public_debt_to_gdp)),
  ];
  document.getElementById("statusBadges").innerHTML = items.map(x => badge(...x)).join("");
}

function trendDirection(first, last, tolerance = 1e-9) {
  if (!Number.isFinite(first) || !Number.isFinite(last)) return "unknown";
  if (last > first + tolerance) return "rose";
  if (last < first - tolerance) return "fell";
  return "was broadly unchanged";
}

function renderSingleInterpretation(summary, yearly, config) {
  const final = yearly[yearly.length - 1] || {};
  const first = yearly[0] || {};
  const growth = Number(summary.real_gdp_growth);
  const inflation = Number(summary.inflation);
  const unemployment = Number(summary.unemployment_rate);
  const gini = Number(summary.income_gini);
  const debt = Number(summary.public_debt_to_gdp);
  const bullets = [];

  if (Number.isFinite(growth)) {
    bullets.push(growth < 0
      ? `The economy ended in <strong>recession</strong>, with real GDP ${pct(growth)} year over year.`
      : `Real output ended ${pct(growth)} above the prior year. This measures quantity/output growth after removing price changes.`);
  }
  if (Number.isFinite(inflation)) {
    const target = Number(config?.annual_inflation);
    const targetText = Number.isFinite(target) ? ` versus the ${pct(target)} background target` : "";
    bullets.push(inflation < 0
      ? `The final year had <strong>deflation</strong> of ${pct(inflation)}${targetText}, meaning simulated prices fell overall.`
      : `Inflation finished at ${pct(inflation)}${targetText}. Inflation and real GDP growth do not need to be similar because one measures prices and the other measures real output.`);
  }
  if (Number.isFinite(unemployment)) {
    if (unemployment >= 0.10) bullets.push(`<strong>Unemployment is high at ${pct(unemployment)}</strong>. In this model that means labor supply substantially exceeds employment demand generated by production; population and productivity assumptions can amplify this gap.`);
    else bullets.push(`Unemployment ended at ${pct(unemployment)}, indicating ${unemployment < .06 ? "a relatively tight" : "some slack in the"} simulated labor market.`);
  }
  if (Number.isFinite(gini)) bullets.push(`Income inequality ended at a Gini of ${decimal(gini)}; the class-average Gini ${trendDirection(Number(first.Income_Gini_End_Class_Average), Number(final.Income_Gini_End_Class_Average))} over the displayed period.`);
  if (Number.isFinite(debt)) bullets.push(`Public debt finished at ${pct(debt)} of nominal GDP. The debt ratio reflects accumulated fiscal deficits/surpluses plus debt interest.`);

  const startProducts = Number(summary.starting_products);
  const finalProducts = Number(summary.final_products);
  if (Number.isFinite(startProducts) && Number.isFinite(finalProducts) && finalProducts !== startProducts) {
    bullets.push(`Product variety changed from ${integer(startProducts)} to ${integer(finalProducts)} products as the monthly innovation mechanism created new variants.`);
  }

  document.getElementById("interpretation").innerHTML = `<p><strong>Model reading:</strong> these outcomes describe the internal simulation under your assumptions.</p><ul>${bullets.map(b => `<li>${b}</li>`).join("")}</ul>`;
}

function renderComparisonInterpretation(data, scenarioName) {
  const base = data.summaries.Baseline;
  const scenario = data.summaries[scenarioName];
  const rows = data.kpis.filter(row => row.Scenario === scenarioName);
  const byKey = Object.fromEntries(rows.map(row => [row.KPI, row]));
  const bullets = [];

  const gdp = byKey.real_gdp_growth;
  if (gdp) bullets.push(`Real GDP growth is ${signedPctPoint(gdp.Delta_Percentage_Points)} relative to baseline.`);
  const inf = byKey.inflation;
  if (inf) bullets.push(`Inflation is ${signedPctPoint(inf.Delta_Percentage_Points)} relative to baseline.`);
  const un = byKey.unemployment_rate;
  if (un) bullets.push(`Unemployment is ${signedPctPoint(un.Delta_Percentage_Points)} relative to baseline.`);
  const gi = byKey.income_gini;
  if (gi) bullets.push(`Income Gini changes by ${signedAbsolute(gi.Delta_Absolute)}; a negative value means the scenario is more equal than baseline.`);
  const dg = byKey.public_debt_to_gdp;
  if (dg) bullets.push(`Debt/GDP is ${signedPctPoint(dg.Delta_Percentage_Points)} relative to baseline.`);

  const direction = Number(scenario.nominal_gdp) >= Number(base.nominal_gdp) ? "larger" : "smaller";
  document.getElementById("interpretation").innerHTML = `<p><strong>${scenarioName}</strong> ends with a ${direction} nominal economy than the baseline. The bullets below isolate the main final-year differences while both runs use the same random seed.</p><ul>${bullets.map(b => `<li>${b}</li>`).join("")}</ul>`;
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
    renderInputWarnings();
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
  renderStatusBadges(data.summary, data.config?.annual_inflation);
  renderSingleInterpretation(data.summary, data.yearly, data.config);
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
  renderStatusBadges(data.summaries[scenarioName], scenarioOverrides?.annual_inflation ?? baselineOverrides?.annual_inflation ?? defaults?.annual_inflation);
  renderComparisonInterpretation(data, scenarioName);
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
  renderInputWarnings();
}

document.querySelectorAll(".mode-button").forEach(button => {
  button.addEventListener("click", () => setMode(button.dataset.mode));
});
document.getElementById("runButton").addEventListener("click", runDashboard);
document.getElementById("resetButton").addEventListener("click", resetDefaults);
document.querySelectorAll(".controls-panel input").forEach(el => {
  el.addEventListener("input", renderInputWarnings);
  el.addEventListener("change", renderInputWarnings);
});

loadDefaults();
