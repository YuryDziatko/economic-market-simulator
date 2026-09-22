"""
create_config.py  —  Generates simulation_config.xlsx
Run once to create the template, then edit the Excel file to tune the simulation.
"""
from pathlib import Path
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

OUT = Path("config/simulation_config.xlsx")

# ── Division defaults ───────────────────────────────────────────────────────
DIV_INFO = [
    ("01", "Food & Non-Alcoholic Beverages"),
    ("02", "Alcoholic Beverages & Tobacco"),
    ("03", "Clothing & Footwear"),
    ("04", "Housing & Utilities"),
    ("05", "Furnishings & Maintenance"),
    ("06", "Health"),
    ("07", "Transport"),
    ("08", "Communication"),
    ("09", "Recreation"),
    ("10", "Education"),
    ("11", "Restaurants & Hotels"),
    ("12", "Financial & Insurance"),
]

QUANTITY_DEFAULTS = {
    "01": 8000, "02": 3000, "03": 4000, "04": 1500,
    "05": 3500, "06": 2000, "07": 1500, "08": 5000,
    "09": 3000, "10": 800,  "11": 5000, "12": 1500,
}

# market_structure | priv_small | priv_med | priv_large | pub_small | pub_med | pub_large
PRODUCER_DEFAULTS = {
    "01": ("competitive", 15, 4, 1, 2, 0, 0),
    "02": ("oligopoly",    2, 1, 1, 0, 0, 1),
    "03": ("competitive", 12, 3, 1, 0, 0, 0),
    "04": ("oligopoly",    1, 2, 1, 0, 1, 1),
    "05": ("competitive", 10, 3, 1, 0, 0, 0),
    "06": ("oligopoly",    2, 2, 1, 1, 1, 1),
    "07": ("oligopoly",    1, 2, 1, 0, 1, 1),
    "08": ("monopoly",     0, 0, 1, 0, 0, 1),
    "09": ("competitive",  8, 3, 1, 0, 1, 0),
    "10": ("oligopoly",    2, 2, 0, 0, 2, 1),
    "11": ("competitive", 20, 5, 2, 0, 1, 0),
    "12": ("oligopoly",    1, 2, 1, 0, 0, 1),
}

# ── Styles ──────────────────────────────────────────────────────────────────
HDR_FILL  = PatternFill("solid", fgColor="2D6A9F")
HDR_FONT  = Font(bold=True, color="FFFFFF", size=10)
NOTE_FILL = PatternFill("solid", fgColor="FFF3CD")
NOTE_FONT = Font(italic=True, color="856404", size=9)
ALT_FILL  = PatternFill("solid", fgColor="EEF4FB")
THIN = Side(style="thin", color="CCCCCC")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
CENTER = Alignment(horizontal="center", vertical="center")

def hdr(ws, row, col, value, width=None):
    c = ws.cell(row=row, column=col, value=value)
    c.fill = HDR_FILL; c.font = HDR_FONT; c.alignment = CENTER; c.border = BORDER
    if width:
        ws.column_dimensions[c.column_letter].width = width

def note(ws, row, col, value):
    c = ws.cell(row=row, column=col, value=value)
    c.fill = NOTE_FILL; c.font = NOTE_FONT; c.alignment = Alignment(wrap_text=True)

def cell(ws, row, col, value, alt=False):
    c = ws.cell(row=row, column=col, value=value)
    if alt: c.fill = ALT_FILL
    c.border = BORDER
    c.alignment = CENTER
    return c

# ── Sheet 1: quantity_config ────────────────────────────────────────────────
def sheet_quantity(wb):
    ws = wb.create_sheet("quantity_config")
    ws.row_dimensions[1].height = 30
    note(ws, 1, 1,
         "Set max_quantity_per_good for each COICOP division. "
         "Each good in that division gets a random quantity from 1 to this value.")
    ws.merge_cells("A1:D1")

    headers = ["coicop_division", "division_name", "max_quantity_per_good", "notes"]
    widths  = [18, 34, 22, 40]
    for c, (h, w) in enumerate(zip(headers, widths), 1):
        hdr(ws, 2, c, h, w)

    for r, (div, name) in enumerate(DIV_INFO, 3):
        alt = (r % 2 == 0)
        cell(ws, r, 1, div, alt)
        cell(ws, r, 2, name, alt)
        cell(ws, r, 3, QUANTITY_DEFAULTS[div], alt)
        cell(ws, r, 4, "Edit the number in column C ↑", alt)
    ws.freeze_panes = "A3"

# ── Sheet 2: household_config ───────────────────────────────────────────────
def sheet_household(wb):
    ws = wb.create_sheet("household_config")
    ws.row_dimensions[1].height = 30
    note(ws, 1, 1,
         "Configure household distribution. Gini + total_households → "
         "class counts and avg incomes are derived automatically.")
    ws.merge_cells("A1:C1")

    headers = ["parameter", "value", "description"]
    widths  = [32, 16, 55]
    for c, (h, w) in enumerate(zip(headers, widths), 1):
        hdr(ws, 2, c, h, w)

    rows = [
        ("gini_coefficient",           0.35,    "Gini index 0–1 (0=perfect equality, 1=max inequality). US ≈ 0.39"),
        ("total_households",           1000,    "Total number of households simulated (period 0)"),
        ("consumption_share_of_gdp",   0.60,    "Fraction of GDP attributed to household consumption (C in C+I+G)"),
        ("savings_rate",               0.10,    "Overall calibration rate used only to size total household income from GDP"),
        ("tax_rate",                   0.22,    "Average income tax rate applied by government"),
        ("money_supply_growth",        0.002,   "Monthly money supply growth rate (~2.4% annual inflation at baseline)"),
        ("population_growth_rate",     0.01,    "Annual %% growth in number of households — new households added each year"),
    ]
    for r, (param, val, desc) in enumerate(rows, 3):
        alt = (r % 2 == 0)
        cell(ws, r, 1, param, alt)
        c = cell(ws, r, 2, val, alt)
        c.font = Font(bold=True, color="1A5276")
        cell(ws, r, 3, desc, alt).alignment = Alignment(wrap_text=True)
    ws.freeze_panes = "A3"

# ── Sheet 3: producer_config ─────────────────────────────────────────────────
def sheet_producer(wb):
    ws = wb.create_sheet("producer_config")
    ws.row_dimensions[1].height = 42
    note(ws, 1, 1,
         "Configure producer market structure per division.\n"
         "market_structure: competitive | oligopoly | monopoly\n"
         "Counts are number of firms of each type. "
         "Total production across all firms in a division matches that division's GDP share.")
    ws.merge_cells("A1:J1")

    headers = ["coicop_division","division_name","market_structure",
               "priv_small","priv_medium","priv_large",
               "pub_small","pub_medium","pub_large","notes"]
    widths  = [16, 30, 16, 11, 12, 11, 10, 11, 10, 38]
    for c, (h, w) in enumerate(zip(headers, widths), 1):
        hdr(ws, 2, c, h, w)

    for r, (div, name) in enumerate(DIV_INFO, 3):
        alt = (r % 2 == 0)
        ms, ps, pm, pl, gs, gm, gl = PRODUCER_DEFAULTS[div]
        vals = [div, name, ms, ps, pm, pl, gs, gm, gl,
                "competitive=many small  oligopoly=3-4  monopoly=1"]
        for c, v in enumerate(vals, 1):
            cc = cell(ws, r, c, v, alt)
            if c == 3:  # market_structure column — colour-code
                colors = {"competitive":"D4EFDF","oligopoly":"FCF3CF","monopoly":"FADBD8"}
                cc.fill = PatternFill("solid", fgColor=colors.get(v, "FFFFFF"))
                cc.font = Font(bold=True, size=9)
    ws.freeze_panes = "A3"

# ── Sheet 4: evolution_config ───────────────────────────────────────────────
def sheet_evolution(wb):
    ws = wb.create_sheet("evolution_config")
    ws.row_dimensions[1].height = 42
    note(ws, 1, 1,
         "Controls yearly product catalogue evolution.\n"
         "Each year, every product independently rolls a chance to change price "
         "(direction depends on that division's market_structure — monopolies more "
         "likely to raise prices, competitive markets more likely to cut them) and a "
         "separate, independent chance to spawn a new product line (a priced variant).")
    ws.merge_cells("A1:C1")

    headers = ["parameter", "value", "description"]
    widths  = [30, 14, 60]
    for c, (h, w) in enumerate(zip(headers, widths), 1):
        hdr(ws, 2, c, h, w)

    rows = [
        ("no_change_prob",        0.90, "Chance a product's price stays exactly the same this year"),
        ("price_change_min",      0.01, "Minimum % magnitude of a price change, when one happens"),
        ("price_change_max",      0.12, "Maximum % magnitude of a price change, when one happens"),
        ("new_product_prob",      0.02, "Chance any given product spawns a new priced variant this year"),
        ("new_product_price_min", 0.80, "New variant's price = parent price × Uniform(this, price_max)"),
        ("new_product_price_max", 1.25, "New variant's price = parent price × Uniform(price_min, this)"),
    ]
    for r, (param, val, desc) in enumerate(rows, 3):
        alt = (r % 2 == 0)
        cell(ws, r, 1, param, alt)
        c = cell(ws, r, 2, val, alt)
        c.font = Font(bold=True, color="1A5276")
        cell(ws, r, 3, desc, alt).alignment = Alignment(wrap_text=True)
    ws.freeze_panes = "A3"

    note2_row = len(rows) + 4
    note(ws, note2_row, 1,
         "Price-rise probability by market structure (fixed in code, not editable here):\n"
         "  competitive: 35% up / 65% down     oligopoly: 65% up / 35% down     monopoly: 80% up / 20% down")
    ws.merge_cells(f"A{note2_row}:C{note2_row}")


# ── Sheet 5: bracket_config ──────────────────────────────────────────────────
BRACKET_ROWS = [
    # bracket, pct_lower, pct_upper, labor_min, labor_max, capital_min, capital_max,
    # transfer_min, transfer_max, consumption_min, consumption_max, notes
    ("Low",    0,    40,   0.25, 0.35, 0.00, 0.02, 0.60, 0.70, 1.00, 1.15,
     "Bottom 40%. Dissaving: essential expenses ≥ cash flow; relies on transfers/debt."),
    ("Middle", 40,   80,   0.75, 0.85, 0.02, 0.05, 0.10, 0.20, 0.92, 0.97,
     "40th–80th pct. Fixed wages/salaries; savings via home equity & retirement accounts."),
    ("High",   80,   99,   0.80, 0.90, 0.05, 0.15, 0.00, 0.05, 0.75, 0.85,
     "80th–99th pct (Top 20%). High professional salaries & bonuses; deliberate saving."),
    ("Top1",   99,   99.9, 0.35, 0.45, 0.50, 0.60, 0.00, 0.01, 0.50, 0.65,
     "Top 1%. Capital gains, business equity & dividends; capital expansion."),
    ("Top01",  99.9, 100,  0.15, 0.25, 0.75, 0.85, 0.00, 0.01, 0.15, 0.35,
     "Top 0.1%. Asset appreciation & financial capital; income = investment engine."),
]

def sheet_bracket(wb):
    ws = wb.create_sheet("bracket_config")
    ws.row_dimensions[1].height = 60
    note(ws, 1, 1,
         "Household income brackets. pct_lower/pct_upper = income percentile range this bracket covers.\n"
         "labor/capital/transfer = share of GROSS income from each source (sampled uniformly in range, "
         "then normalised to sum to 100%% per household).\n"
         "consumption_min/max = share of gross income SPENT (Low can exceed 100%% = dissaving/debt). "
         "Savings rate = 1 − consumption.")
    ws.merge_cells("A1:L1")

    headers = ["bracket", "pct_lower", "pct_upper",
               "labor_min", "labor_max", "capital_min", "capital_max",
               "transfer_min", "transfer_max", "consumption_min", "consumption_max", "notes"]
    widths  = [10, 10, 10, 10, 10, 11, 11, 12, 12, 14, 14, 46]
    for c, (h, w) in enumerate(zip(headers, widths), 1):
        hdr(ws, 2, c, h, w)

    for r, row_data in enumerate(BRACKET_ROWS, 3):
        alt = (r % 2 == 0)
        for c, v in enumerate(row_data, 1):
            cell(ws, r, c, v, alt)
    ws.freeze_panes = "A3"


# ── Upgrade helper: append new parameters to an existing household_config ────
NEW_HOUSEHOLD_PARAMS = [
    ("population_growth_rate", 0.01,
     "Annual %% growth in number of households — new households added each year"),
]

def upgrade_household_config(ws):
    existing = set()
    r = 3
    while ws.cell(row=r, column=1).value:
        existing.add(str(ws.cell(row=r, column=1).value).strip())
        r += 1
    added = []
    for param, val, desc in NEW_HOUSEHOLD_PARAMS:
        if param not in existing:
            alt = (r % 2 == 0)
            cell(ws, r, 1, param, alt)
            c = cell(ws, r, 2, val, alt)
            c.font = Font(bold=True, color="1A5276")
            cell(ws, r, 3, desc, alt).alignment = Alignment(wrap_text=True)
            added.append(param)
            r += 1
    return added


def main():
    import sys
    OUT.parent.mkdir(parents=True, exist_ok=True)

    if OUT.exists() and "--fresh" not in sys.argv:
        # Preserve the user's existing edits — only add sheets/rows that are missing.
        wb = openpyxl.load_workbook(OUT)
        added = []
        if "quantity_config" not in wb.sheetnames:
            sheet_quantity(wb); added.append("quantity_config")
        if "household_config" not in wb.sheetnames:
            sheet_household(wb); added.append("household_config")
        else:
            patched = upgrade_household_config(wb["household_config"])
            if patched:
                added.append(f"household_config (+{','.join(patched)})")
        if "producer_config" not in wb.sheetnames:
            sheet_producer(wb); added.append("producer_config")
        if "evolution_config" not in wb.sheetnames:
            sheet_evolution(wb); added.append("evolution_config")
        if "bracket_config" not in wb.sheetnames:
            sheet_bracket(wb); added.append("bracket_config")
        wb.save(OUT)
        if added:
            print(f"Existing config found → {OUT}")
            print(f"  Added missing sheet(s)/param(s): {', '.join(added)}")
        else:
            print(f"Existing config found → {OUT}  (already up to date, nothing changed)")
    else:
        wb = openpyxl.Workbook()
        wb.remove(wb.active)   # remove default sheet
        sheet_quantity(wb)
        sheet_household(wb)
        sheet_producer(wb)
        sheet_evolution(wb)
        sheet_bracket(wb)
        wb.save(OUT)
        print(f"Fresh config created → {OUT}")

    print("Edit it, then run:  python build_goods_db.py")

if __name__ == "__main__":
    main()
