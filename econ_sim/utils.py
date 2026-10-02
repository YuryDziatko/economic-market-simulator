from __future__ import annotations

import numpy as np


def gini(values) -> float:
    x = np.asarray(values, dtype=float)
    if x.size == 0 or x.sum() <= 0:
        return 0.0
    if np.any(x < 0):
        raise ValueError("Gini requires non-negative values")
    x = np.sort(x)
    n = x.size
    i = np.arange(1, n + 1, dtype=float)
    return float(2 * np.sum(i * x) / (n * np.sum(x)) - (n + 1) / n)


def exact_labels(n: int, labels: list[str], shares, rng: np.random.Generator) -> np.ndarray:
    shares = np.asarray(shares, dtype=float)
    shares = shares / shares.sum()
    raw = shares * n
    counts = np.floor(raw).astype(int)
    remainder = n - counts.sum()
    if remainder:
        counts[np.argsort(-(raw - counts))[:remainder]] += 1
    result = np.concatenate([np.repeat(label, count) for label, count in zip(labels, counts)])
    rng.shuffle(result)
    return result


def split_integer(total: int, n: int, concentration: float, rng: np.random.Generator) -> np.ndarray:
    if n <= 0:
        return np.array([], dtype=int)
    if n == 1:
        return np.array([int(total)], dtype=int)
    if total <= 0:
        return np.zeros(n, dtype=int)
    weights = rng.dirichlet(np.full(n, concentration, dtype=float))
    raw = weights * int(total)
    values = np.floor(raw).astype(int)
    remainder = int(total) - values.sum()
    if remainder:
        values[np.argsort(-(raw - values))[:remainder]] += 1
    return values
