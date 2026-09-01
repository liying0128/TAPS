"""Information-gain: post-hoc uses nov_info; causal proxy is inverse density."""

from __future__ import annotations

import numpy as np


def information_gain_score(nov_info=None, inv_rho=None, **kwargs) -> np.ndarray:
    if nov_info is not None:
        return np.asarray(nov_info, dtype=np.float64)
    return np.asarray(inv_rho, dtype=np.float64)
