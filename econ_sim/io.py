from __future__ import annotations

from pathlib import Path
import pandas as pd


def _check_share(df: pd.DataFrame, col: str, name: str):
    value = float(pd.to_numeric(df[col], errors="raise").sum())
    if abs(value - 1.0) > 1e-6:
        raise ValueError(f"{name} shares must total 100%; currently {value:.4%}")


def load_settings(path: Path) -> dict:
    general_df = pd.read_excel(path, sheet_name="General_Settings", header=2)
    general_df = general_df.dropna(subset=["Key"])
    general = dict(zip(general_df["Key"].astype(str), general_df["Value"]))

    classes = pd.read_excel(path, sheet_name="Household_Classes", header=2)
    classes = classes[pd.to_numeric(classes["Order"], errors="coerce").notna()].copy()
    classes["Order"] = classes["Order"].astype(int)
    classes["Population Share"] = pd.to_numeric(classes["Population Share"], errors="raise")
    classes = classes.sort_values("Order")
    _check_share(classes, "Population Share", "Household class")

    sizes = pd.read_excel(path, sheet_name="Company_Settings", skiprows=3, nrows=3)
    sizes = sizes[["Size", "Share", "Fixed Cost / Revenue", "Variable Cost / Revenue", "Investment P0"]].copy()
    for col in ["Share", "Fixed Cost / Revenue", "Variable Cost / Revenue", "Investment P0"]:
        sizes[col] = pd.to_numeric(sizes[col], errors="raise")
    _check_share(sizes, "Share", "Company size")

    ownership = pd.read_excel(path, sheet_name="Company_Settings", skiprows=10, nrows=2)
    ownership = ownership[["Ownership", "Share"]].copy()
    ownership["Share"] = pd.to_numeric(ownership["Share"], errors="raise")
    _check_share(ownership, "Share", "Ownership")

    markets = pd.read_excel(path, sheet_name="Company_Settings", skiprows=16, nrows=3)
    markets = markets[["Market", "Product Share", "Min Firms", "Max Firms"]].copy()
    markets["Product Share"] = pd.to_numeric(markets["Product Share"], errors="raise")
    markets["Min Firms"] = pd.to_numeric(markets["Min Firms"], errors="raise").astype(int)
    markets["Max Firms"] = pd.to_numeric(markets["Max Firms"], errors="raise").astype(int)
    _check_share(markets, "Product Share", "Market")

    quantity = pd.read_excel(path, sheet_name="Quantity_Limits", header=2)
    quantity = quantity.dropna(subset=["Division", "Category"]).copy()
    quantity["Division"] = quantity["Division"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(2)
    quantity["Min Qty / Product"] = pd.to_numeric(quantity["Min Qty / Product"], errors="raise").astype(int)
    quantity["Max Qty / Product"] = pd.to_numeric(quantity["Max Qty / Product"], errors="raise").astype(int)
    if (quantity["Max Qty / Product"] < quantity["Min Qty / Product"]).any():
        raise ValueError("Quantity max cannot be less than quantity min")

    return {"general": general, "classes": classes, "sizes": sizes, "ownership": ownership, "markets": markets, "quantity": quantity}


def load_products(path: Path) -> pd.DataFrame:
    frames = []
    xls = pd.ExcelFile(path)
    for sheet in xls.sheet_names:
        df = pd.read_excel(path, sheet_name=sheet)
        if df.shape[1] < 5:
            continue
        df = df.iloc[:, :5].copy()
        df.columns = ["COICOP", "Category", "Product", "Unit", "Base_Price"]
        df = df.dropna(subset=["COICOP", "Product", "Base_Price"])
        df["Source_Sheet"] = sheet
        frames.append(df)
    products = pd.concat(frames, ignore_index=True)
    products["COICOP"] = products["COICOP"].astype(str).str.strip()
    products["Division"] = products["COICOP"].str.split(".").str[0].str.zfill(2)
    products["Category"] = products["Category"].astype(str).str.strip()
    products["Product"] = products["Product"].astype(str).str.strip()
    products["Unit"] = products["Unit"].astype(str).str.strip()
    products["Base_Price"] = pd.to_numeric(products["Base_Price"], errors="raise").astype(float)
    products = products.sort_values(["Division", "COICOP", "Category", "Product"]).reset_index(drop=True)
    products.insert(0, "Product_ID", [f"P{i:04d}" for i in range(1, len(products) + 1)])
    return products


def save_outputs(output_dir: Path, **frames):
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, df in frames.items():
        df.to_csv(output_dir / f"{name}.csv", index=False)
    excel_path = output_dir / "Simulation_Output.xlsx"
    with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
        preferred = ["yearly_summary", "monthly_macro", "households", "companies", "products", "production"]
        for name in preferred:
            if name in frames:
                frames[name].to_excel(writer, sheet_name=name[:31], index=False)
    return excel_path
