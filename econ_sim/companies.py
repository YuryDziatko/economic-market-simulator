from __future__ import annotations

import numpy as np
import pandas as pd

from .utils import exact_labels, split_integer


def prepare_products(products: pd.DataFrame, quantity: pd.DataFrame, markets: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    p = products.copy()
    limits = quantity[["Division", "Category", "Min Qty / Product", "Max Qty / Product"]].copy()
    p = p.merge(limits, on=["Division", "Category"], how="left")
    if p["Max Qty / Product"].isna().any():
        missing = p.loc[p["Max Qty / Product"].isna(), ["Division", "Category"]].drop_duplicates()
        raise ValueError("Missing quantity settings:\n" + missing.to_string(index=False))

    p["Min_Qty"] = p["Min Qty / Product"].astype(int)
    p["Max_Qty"] = p["Max Qty / Product"].astype(int)
    p["Quantity_P0"] = [int(rng.integers(lo, hi + 1)) for lo, hi in zip(p["Min_Qty"], p["Max_Qty"])]
    p["Elasticity_Abs"] = rng.uniform(0.0, 1.0, len(p))
    p["Market_Structure"] = exact_labels(len(p), markets["Market"].astype(str).tolist(), markets["Product Share"], rng)

    bounds = markets.set_index("Market")[["Min Firms", "Max Firms"]].to_dict("index")
    p["Number_of_Firms"] = [int(rng.integers(bounds[m]["Min Firms"], bounds[m]["Max Firms"] + 1)) for m in p["Market_Structure"]]
    p["Revenue_P0"] = p["Base_Price"] * p["Quantity_P0"]
    return p.drop(columns=["Min Qty / Product", "Max Qty / Product"])


def generate_companies(products: pd.DataFrame, n_companies: int, sizes: pd.DataFrame, ownership: pd.DataFrame, rng: np.random.Generator):
    ids = np.array([f"C{i:05d}" for i in range(1, n_companies + 1)], dtype=object)
    companies = pd.DataFrame({
        "Company_ID": ids,
        "Ownership": exact_labels(n_companies, ownership["Ownership"].astype(str).tolist(), ownership["Share"], rng),
        "Size": exact_labels(n_companies, sizes["Size"].astype(str).tolist(), sizes["Share"], rng),
    })
    param = sizes.set_index("Size")[["Fixed Cost / Revenue", "Variable Cost / Revenue", "Investment P0"]]
    companies = companies.join(param, on="Size")
    companies = companies.rename(columns={
        "Fixed Cost / Revenue": "Fixed_Cost_Ratio",
        "Variable Cost / Revenue": "Variable_Cost_Ratio",
        "Investment P0": "Investment",
    })

    # Producer slots: each product has the number of firms implied by its market structure.
    slots = []
    for row in products.itertuples(index=False):
        slots += [row.Product_ID] * int(row.Number_of_Firms)
    rng.shuffle(slots)
    product_to_firms = {pid: [] for pid in products["Product_ID"]}

    # Give as many companies as possible one initial product slot.
    company_order = ids.copy()
    rng.shuffle(company_order)
    first = min(len(slots), n_companies)
    for i in range(first):
        product_to_firms[slots[i]].append(str(company_order[i]))

    # Fill the remaining slots while keeping producers within a product unique.
    for pid in slots[first:]:
        used = set(product_to_firms[pid])
        candidates = ids[~np.isin(ids, list(used))]
        if len(candidates) == 0:
            raise ValueError("Not enough companies for requested firms-per-product settings")
        product_to_firms[pid].append(str(rng.choice(candidates)))

    size_of = companies.set_index("Company_ID")["Size"].to_dict()
    var_ratio = sizes.set_index("Size")["Variable Cost / Revenue"].to_dict()
    product_lookup = products.set_index("Product_ID")

    production_rows = []
    for pid, firm_ids in product_to_firms.items():
        row = product_lookup.loc[pid]
        concentration = {"Competitive": 5.0, "Oligopoly": 2.0, "Monopoly": 1.0}.get(row["Market_Structure"], 2.0)
        q = split_integer(int(row["Quantity_P0"]), len(firm_ids), concentration, rng)
        for cid, qty in zip(firm_ids, q):
            revenue = float(row["Base_Price"]) * int(qty)
            vr = float(var_ratio[size_of[cid]])
            production_rows.append({
                "Product_ID": pid,
                "Company_ID": cid,
                "Market_Structure": row["Market_Structure"],
                "Quantity_P0": int(qty),
                "Base_Price": float(row["Base_Price"]),
                "Revenue_P0": revenue,
                "Variable_Cost_Ratio": vr,
                "Variable_Cost_P0": revenue * vr,
            })

    production = pd.DataFrame(production_rows)
    agg = production.groupby("Company_ID").agg(
        Quantity_P0=("Quantity_P0", "sum"),
        Revenue_P0=("Revenue_P0", "sum"),
        Variable_Cost_P0=("Variable_Cost_P0", "sum"),
        Product_Count=("Product_ID", "nunique"),
    )
    companies = companies.join(agg, on="Company_ID")
    for c in ["Quantity_P0", "Revenue_P0", "Variable_Cost_P0", "Product_Count"]:
        companies[c] = companies[c].fillna(0)
    companies["Fixed_Cost_P0"] = companies["Revenue_P0"] * companies["Fixed_Cost_Ratio"]
    companies["Total_Cost_P0"] = companies["Fixed_Cost_P0"] + companies["Variable_Cost_P0"]
    companies["Profit_P0"] = companies["Revenue_P0"] - companies["Total_Cost_P0"]
    companies["Margin_P0"] = np.where(companies["Revenue_P0"] > 0, companies["Profit_P0"] / companies["Revenue_P0"], 0)
    companies["Status"] = np.where(companies["Product_Count"] > 0, "Active", "Inactive")

    primary = production.sort_values(["Company_ID", "Revenue_P0"], ascending=[True, False]).drop_duplicates("Company_ID").set_index("Company_ID")["Market_Structure"]
    companies["Primary_Market_Structure"] = companies["Company_ID"].map(primary).fillna("None")
    return companies, production
