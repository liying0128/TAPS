"""Post-hoc commitment labels (future residence). Causal proxy: closer-to-fold RMSD."""

from __future__ import annotations

import numpy as np


def commitment_labels(comm=None, disc_commit=None, **kwargs) -> np.ndarray:
    if comm is not None:
        return np.asarray(comm, dtype=np.float64)
    return np.asarray(disc_commit, dtype=np.float64)


def commitment_proxy_rmsd(rmsd, fold_rmsd=0.25) -> np.ndarray:
    """Causal stand-in until a commit predictor exists: nearer the fold basin."""
    rmsd = np.asarray(rmsd, dtype=np.float64)
    return 1.0 / (np.maximum(rmsd - fold_rmsd, 0.0) + 0.05)
