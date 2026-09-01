"""MOAS-Weighted: Utility = sum_i w_i(t) * objective_i."""

from __future__ import annotations

import numpy as np


def weighted_utility(objectives: dict, weights: dict) -> np.ndarray:
    acc = None
    wsum = 0.0
    for name, arr in objectives.items():
        w = float(weights.get(name, 0.0))
        if w == 0.0:
            continue
        x = w * np.asarray(arr, dtype=np.float64)
        acc = x if acc is None else acc + x
        wsum += w
    if acc is None:
        raise ValueError("all weights are zero")
    return acc / max(wsum, 1e-12)
