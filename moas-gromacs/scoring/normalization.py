"""Robust percentile / z-score normalization before fusion."""

from __future__ import annotations

import numpy as np


def percentile_rank(a: np.ndarray) -> np.ndarray:
    a = np.asarray(a, dtype=np.float64)
    n = len(a)
    if n == 0:
        return a
    order = np.argsort(a, kind="mergesort")
    ranks = np.empty(n, dtype=np.float64)
    ranks[order] = np.linspace(0.0, 1.0, n, dtype=np.float64)
    return ranks


def robust_z(a: np.ndarray) -> np.ndarray:
    a = np.asarray(a, dtype=np.float64)
    med = np.nanmedian(a)
    mad = np.nanmedian(np.abs(a - med))
    scale = 1.4826 * mad if mad > 1e-12 else (np.nanstd(a) + 1e-12)
    return np.clip((a - med) / scale, -8.0, 8.0)


def normalize_objectives(table: dict, method: str = "percentile") -> dict:
    fn = percentile_rank if method == "percentile" else robust_z
    return {k: fn(v) for k, v in table.items()}
