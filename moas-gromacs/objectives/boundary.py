"""Causal boundary / LAST-frontier score."""

from __future__ import annotations

import numpy as np


def boundary_score(last_score=None, **kwargs) -> np.ndarray:
    return np.asarray(last_score, dtype=np.float64)
