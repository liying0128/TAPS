"""Causal CLN025 novelty: inverse local density."""

from __future__ import annotations

import numpy as np


def novelty_score(rho=None, inv_rho=None, **kwargs) -> np.ndarray:
    if inv_rho is not None:
        return np.asarray(inv_rho, dtype=np.float64)
    rho = np.asarray(rho, dtype=np.float64)
    return 1.0 / (rho + 1e-6)
