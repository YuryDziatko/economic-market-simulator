const fields = [
  "simulation_years", "num_households", "num_companies", "target_gini",
  "tax_rate", "corporate_profit_tax_rate", "annual_inflation", "demographic_growth"
];

function readOverrides() {
  const ints = new Set(["simulation_years", "num_households", "num_companies"]);
  const overrides = {};
  for (const key of fields) {
    const value = document.getElementById(key).value;
    overrides[key] = ints.has(key) ? parseInt(value, 10) : parseFloat(value);
  }
  return overrides;
}

function pct(v) { return `${(100 * v).toFixed(2)}%`; }
function money(v) { return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(v); }
function number(v) { return new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(v); }

function showCards(summary) {
  const metrics = [
    ["Nominal GDP", money(summary.nominal_gdp)],
    ["Real GDP growth", pct(summary.real_gdp_growth)],
    ["Inflation", pct(summary.inflation)],
    ["Unemployment", pct(summary.unemployment_rate)],
    ["Income Gini", Number(summary.income_gini).toFixed(3)],
    ["Debt / GDP", pct(summary.public_debt_to_gdp)],
    ["Final products", number(summary.final_products)],
  ];
  document.getElementById("cards").innerHTML = metrics.map(([label, value]) =>
    `<div class="card"><div class="label">${label}</div><div class="value">${value}</div></div>`
  ).join("");
}

async function runSimulation() {
  const button = document.getElementById("runButton");
  const status = document.getElementById("status");
  const output = document.getElementById("output");
  button.disabled = true;
  status.textContent = "Running simulation…";
  try {
    const response = await fetch("/api/simulate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ overrides: readOverrides(), include_monthly: false })
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Simulation failed");
    showCards(data.summary);
    output.textContent = JSON.stringify(data, null, 2);
    status.textContent = "Simulation complete.";
  } catch (error) {
    status.textContent = error.message;
    output.textContent = error.stack || String(error);
  } finally {
    button.disabled = false;
  }
}

document.getElementById("runButton").addEventListener("click", runSimulation);
