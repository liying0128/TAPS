"""Causal kinetic proxy from short-window MSD / velocity (no future leak)."""

from __future__ import annotations

import numpy as np


def kinetic_score(msd=None, vel=None, var=None, **kwargs) -> np.ndarray:
    msd = np.asarray(msd, dtype=np.float64)
    vel = np.abs(np.asarray(vel, dtype=np.float64)) if vel is not None else 0.0
    var = np.asarray(var, dtype=np.float64) if var is not None else 0.0
    return msd + 0.25 * vel + 0.25 * var
