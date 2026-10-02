from __future__ import annotations

from statistics import NormalDist
import numpy as np
import pandas as pd

from .utils import gini


def _weights(n: int, sigma: float) -> np.ndarray:
    normal = NormalDist()
    q = (np.arange(n) + 0.5) / n
    z = np.array([normal.inv_cdf(float(p)) for p in q])
    return np.exp(np.clip(sigma * z, -50, 50))


def _sigma_for_gini(n: int, target: float) -> float:
    target = float(np.clip(target, 0, 0.95))
    if target == 0:
        return 0.0
    lo, hi = 0.0, 1.0
    while gini(_weights(n, hi)) < target and hi < 8:
        hi *= 2
    for _ in range(70):
        mid = (lo + hi) / 2
        if gini(_weights(n, mid)) < target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def generate_households(n: int, total_income: float, target_gini: float, tax_rate: float, classes: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    sigma = _sigma_for_gini(n, target_gini)
    incomes_sorted = _weights(n, sigma)
    incomes_sorted = incomes_sorted / incomes_sorted.sum() * total_income

    raw = classes["Population Share"].to_numpy(float) * n
    counts = np.floor(raw).astype(int)
    remainder = n - counts.sum()
    if remainder:
        counts[np.argsort(-(raw - counts))[:remainder]] += 1

    labels_sorted = np.concatenate([
        np.repeat(str(label), count)
        for label, count in zip(classes["Class"], counts)
    ])

    perm = rng.permutation(n)
    income = np.empty(n, dtype=float)
    label = np.empty(n, dtype=object)
    income[perm] = incomes_sorted
    label[perm] = labels_sorted

    taxes = income * tax_rate
    transfers = np.zeros(n)
    savings = np.zeros(n)
    disposable = income - taxes + transfers
    consumption = disposable - savings

    df = pd.DataFrame({
        "Household_ID": [f"H{i:05d}" for i in range(1, n + 1)],
        "Class": label,
        "Gross_Monthly_Income": income,
        "Taxes": taxes,
        "Transfers": transfers,
        "Savings": savings,
        "Disposable_Income": disposable,
        "Consumption": consumption,
    })
    df["Gross_Annual_Income"] = df["Gross_Monthly_Income"] * 12
    return df
