"""Uncalibrated uncertainty proxy. High sigma is not automatically high value."""

from __future__ import annotations

import numpy as np


def uncertainty_score(msd=None, inv_rho=None, **kwargs) -> np.ndarray:
    msd = np.asarray(msd, dtype=np.float64)
    inv = np.asarray(inv_rho, dtype=np.float64) if inv_rho is not None else 1.0
    return msd * inv
