"""Pareto front over a small set of objectives."""

from __future__ import annotations

import numpy as np


def pareto_mask(cols: np.ndarray) -> np.ndarray:
    """cols: (n, d), higher is better. Returns boolean mask of non-dominated rows."""
    x = np.asarray(cols, dtype=np.float64)
    n = len(x)
    keep = np.ones(n, dtype=bool)
    for i in range(n):
        if not keep[i]:
            continue
        ge = np.all(x >= x[i], axis=1)
        gt = np.any(x > x[i], axis=1)
        dominated_i = ge & gt
        dominated_i[i] = False
        if dominated_i.any():
            keep[i] = False
        keep[dominated_i] = False
    return keep


def pareto_front(objectives: dict) -> np.ndarray:
    cols = np.column_stack([np.asarray(v, dtype=np.float64) for v in objectives.values()])
    return np.flatnonzero(pareto_mask(cols))
