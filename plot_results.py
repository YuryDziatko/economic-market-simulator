"""
plot_results.py — Visualise economics simulation output
Reads results/history.csv and produces a 4-panel chart saved to results/charts.png

Usage:
    python plot_results.py
    python plot_results.py --results results/history.csv --out results/charts.png
    python plot_results.py --compare results/baseline.csv results/shock.csv --labels Baseline "Oil shock"
"""

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import matplotlib.gridspec as gridspec
import numpy as np
import pandas as pd

# ── Division labels ────────────────────────────────────────────────────────────
DIV_NAMES = {
    "01": "Food",
    "02": "Alcohol & Tobacco",
    "03": "Clothing",
    "04": "Housing",
    "05": "Furnishings",
    "06": "Health",
    "07": "Transport",
    "08": "Communication",
    "09": "Recreation",
    "10": "Education",
    "11": "Restaurants",
    "12": "Financial",
}

# Colour palette — one per division
DIV_COLORS = [
    "#E05C3A", "#3A7DC9", "#2DAA74", "#E6AA1E",
    "#9B59B6", "#1ABC9C", "#E74C3C", "#3498DB",
    "#F39C12", "#27AE60", "#8E44AD", "#16A085",
]

ACCENT   = "#E05C3A"
BLUE     = "#3A7DC9"
DARK_BG  = "#F7F6F3"
GRID_CLR = "#E0DED8"


def load(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str)
    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["year"] = df["tick"] / 12
    # Annual inflation (rolling 12-tick % change in CPI)
    if "inflation_yoy" not in df.columns:
        df["inflation_yoy"] = df["cpi"].pct_change(12) * 100
    return df


def price_cols(df: pd.DataFrame) -> list:
    return [c for c in df.columns if c.startswith("price_")]


# ── Plot 1: CPI over time ──────────────────────────────────────────────────────
def plot_cpi(ax, datasets: list, labels: list):
    for i, (df, label) in enumerate(zip(datasets, labels)):
        color = ACCENT if i == 0 else BLUE
        lw    = 2.2 if i == 0 else 1.6
        ls    = "-"  if i == 0 else "--"
        ax.plot(df["year"], df["cpi"], color=color, lw=lw, ls=ls, label=label)

    ax.axhline(1.0, color=GRID_CLR, lw=1, zorder=0)
    ax.set_title("Consumer Price Index", fontsize=12, fontweight="bold", pad=8)
    ax.set_xlabel("Year", fontsize=10)
    ax.set_ylabel("Index (base = 1.0)", fontsize=10)
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.2f"))
    ax.legend(fontsize=9)
    _style(ax)


# ── Plot 2: Annual inflation rate ─────────────────────────────────────────────
def plot_inflation(ax, datasets: list, labels: list):
    for i, (df, label) in enumerate(zip(datasets, labels)):
        color = ACCENT if i == 0 else BLUE
        lw    = 2.0  if i == 0 else 1.5
        ls    = "-"  if i == 0 else "--"
        ax.plot(df["year"], df["inflation_yoy"], color=color, lw=lw, ls=ls, label=label)

    ax.axhline(0, color=GRID_CLR, lw=1, zorder=0)
    ax.fill_between(datasets[0]["year"], datasets[0]["inflation_yoy"], 0,
                    where=datasets[0]["inflation_yoy"] > 0,
                    alpha=0.12, color=ACCENT, label="_")
    ax.set_title("Annual Inflation Rate (YoY)", fontsize=12, fontweight="bold", pad=8)
    ax.set_xlabel("Year", fontsize=10)
    ax.set_ylabel("Inflation (%)", fontsize=10)
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.1f%%"))
    if len(datasets) > 1:
        ax.legend(fontsize=9)
    _style(ax)


# ── Plot 3: Price index per COICOP division ───────────────────────────────────
def plot_prices(ax, df: pd.DataFrame, title_suffix: str = ""):
    cols = price_cols(df)
    for i, col in enumerate(cols):
        div = col.split("_")[1]
        name = DIV_NAMES.get(div, div)
        color = DIV_COLORS[i % len(DIV_COLORS)]
        ax.plot(df["year"], df[col], color=color, lw=1.4, label=name)

    ax.axhline(1.0, color=GRID_CLR, lw=1, zorder=0)
    ax.set_title(f"Price Index by COICOP Division{title_suffix}",
                 fontsize=12, fontweight="bold", pad=8)
    ax.set_xlabel("Year", fontsize=10)
    ax.set_ylabel("Index (base = 1.0)", fontsize=10)
    ax.legend(fontsize=7.5, ncol=2, loc="upper left",
              framealpha=0.85, edgecolor=GRID_CLR)
    _style(ax)


# ── Plot 4: Lorenz curve + Gini ───────────────────────────────────────────────
def plot_lorenz(ax, datasets: list, labels: list):
    """
    Approximate Lorenz curve from the Gini coefficient.
    True Lorenz needs household income array; we reconstruct a
    log-normal distribution consistent with the final Gini.
    """
    n = 1000
    for i, (df, label) in enumerate(zip(datasets, labels)):
        gini_final = df["gini"].iloc[-1]
        color = ACCENT if i == 0 else BLUE
        ls    = "-"  if i == 0 else "--"

        # Reconstruct income distribution from Gini via log-normal sigma
        # For log-normal: Gini = 2*Phi(sigma/sqrt(2)) - 1
        # Solve for sigma numerically
        from scipy.special import ndtr  # standard normal CDF
        sigma = np.sqrt(2) * ndtr(np.linspace(0.01, 3, 500))
        ginis = 2 * ndtr(np.linspace(0.01, 3, 500) / np.sqrt(2)) - 1

        # Interpolate to find sigma matching gini_final
        sigma_val = float(np.interp(gini_final, ginis,
                                    np.linspace(0.01, 3, 500)))
        incomes = np.sort(np.random.lognormal(0, sigma_val, n))
        cum_pop    = np.linspace(0, 1, n)
        cum_income = np.cumsum(incomes) / incomes.sum()

        ax.plot(cum_pop, cum_income, color=color, lw=2, ls=ls,
                label=f"{label}  (Gini={gini_final:.3f})")

    # Equality line
    ax.plot([0, 1], [0, 1], color=GRID_CLR, lw=1.2, ls="--", label="Perfect equality")
    ax.fill_between([0, 1], [0, 1], [0, 0], alpha=0.04, color=GRID_CLR)

    ax.set_title("Lorenz Curve — Income Inequality", fontsize=12, fontweight="bold", pad=8)
    ax.set_xlabel("Cumulative population share", fontsize=10)
    ax.set_ylabel("Cumulative income share", fontsize=10)
    ax.legend(fontsize=9)
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.xaxis.set_major_formatter(mticker.PercentFormatter(1.0))
    ax.yaxis.set_major_formatter(mticker.PercentFormatter(1.0))
    _style(ax)


# ── Plot 5: GDP over time ─────────────────────────────────────────────────────
def plot_gdp(ax, datasets: list, labels: list):
    for i, (df, label) in enumerate(zip(datasets, labels)):
        color = ACCENT if i == 0 else BLUE
        lw    = 2.0  if i == 0 else 1.5
        ls    = "-"  if i == 0 else "--"
        if "gdp_real_annualized" in df.columns:
            gdp_col = "gdp_real_annualized"
        elif "gdp_real" in df.columns:
            gdp_col = "gdp_real"
        elif "gdp_nominal" in df.columns:
            gdp_col = "gdp_nominal"
        else:
            gdp_col = "gdp"
        ax.plot(df["year"], df[gdp_col] / 1e6, color=color, lw=lw, ls=ls, label=label)

    ax.set_title("GDP (real, CPI-deflated, annualized)", fontsize=12, fontweight="bold", pad=8)
    ax.set_xlabel("Year", fontsize=10)
    ax.set_ylabel("Real GDP (millions USD)", fontsize=10)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:.1f}M"))
    if len(datasets) > 1:
        ax.legend(fontsize=9)
    _style(ax)


# ── Shared axis styling ───────────────────────────────────────────────────────
def _style(ax):
    ax.set_facecolor(DARK_BG)
    ax.grid(True, color=GRID_CLR, linewidth=0.6, linestyle="-")
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color(GRID_CLR)
    ax.tick_params(labelsize=9, colors="#555")
    ax.xaxis.label.set_color("#444")
    ax.yaxis.label.set_color("#444")
    ax.title.set_color("#222")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Plot economics simulation results")
    parser.add_argument("--results", type=str, default="results/history.csv",
                        help="Path to history CSV (single run)")
    parser.add_argument("--compare", nargs="+", type=str, default=None,
                        help="Two CSV files to compare side by side")
    parser.add_argument("--labels", nargs="+", type=str, default=None,
                        help="Labels for each dataset when using --compare")
    parser.add_argument("--out", type=str, default="results/charts.png",
                        help="Output image path")
    args = parser.parse_args()

    # Load datasets
    if args.compare:
        paths = args.compare
        labels = args.labels if args.labels else [Path(p).stem for p in paths]
    else:
        paths = [args.results]
        labels = ["Simulation"]

    datasets = [load(p) for p in paths]

    # ── Layout: 2×3 grid (5 plots + 1 summary card) ──────────────────
    fig = plt.figure(figsize=(16, 11), facecolor="white")
    fig.suptitle("Economics Simulation Dashboard", fontsize=16,
                 fontweight="bold", color="#222", y=0.98)

    gs = gridspec.GridSpec(2, 3, figure=fig, hspace=0.42, wspace=0.32,
                           left=0.07, right=0.97, top=0.93, bottom=0.07)

    ax_cpi   = fig.add_subplot(gs[0, 0])
    ax_inf   = fig.add_subplot(gs[0, 1])
    ax_gdp   = fig.add_subplot(gs[0, 2])
    ax_price = fig.add_subplot(gs[1, 0:2])
    ax_lorenz = fig.add_subplot(gs[1, 2])

    plot_cpi(ax_cpi, datasets, labels)
    plot_inflation(ax_inf, datasets, labels)
    plot_gdp(ax_gdp, datasets, labels)
    plot_prices(ax_price, datasets[0])
    plot_lorenz(ax_lorenz, datasets, labels)

    # ── Summary stats box (top-right corner of price chart) ──────────
    df0 = datasets[0]
    total_inf = (df0["cpi"].iloc[-1] / df0["cpi"].iloc[0] - 1) * 100
    avg_inf   = df0["inflation_yoy"].dropna().mean()
    gdp_col = "gdp_real" if "gdp_real" in df0.columns else "gdp_nominal" if "gdp_nominal" in df0.columns else "gdp"
    final_gdp = df0[gdp_col].iloc[-1]
    final_gini = df0["gini"].iloc[-1]
    ticks = len(df0)

    stats_text = (
        f"Run: {ticks} ticks  ({ticks//12}y {ticks%12}m)\n"
        f"Total inflation : {total_inf:+.1f}%\n"
        f"Avg annual inf  : {avg_inf:.1f}%\n"
        f"Final GDP       : ${final_gdp:,.0f}\n"
        f"Final Gini      : {final_gini:.3f}"
    )
    ax_price.text(
        0.99, 0.97, stats_text,
        transform=ax_price.transAxes,
        fontsize=8.5, va="top", ha="right",
        fontfamily="monospace",
        bbox=dict(boxstyle="round,pad=0.5", facecolor="white",
                  edgecolor=GRID_CLR, alpha=0.92),
    )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight", facecolor="white")
    print(f"Chart saved → {out_path}")


if __name__ == "__main__":
    main()
