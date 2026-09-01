"""Do not take raw top-K utility; enforce latent-space diversity."""

from __future__ import annotations

import numpy as np


def greedy_maxmin(points: np.ndarray, scores: np.ndarray, k: int) -> np.ndarray:
    """Start at the best score, then repeatedly add the point farthest from the set."""
    pts = np.asarray(points, dtype=np.float64)
    sc = np.asarray(scores, dtype=np.float64)
    n = len(sc)
    k = min(k, n)
    if k <= 0:
        return np.asarray([], dtype=np.int64)
    chosen = [int(np.argmax(sc))]
    dmin = np.full(n, np.inf)
    dmin -= 0.0
    for _ in range(1, k):
        last = pts[chosen[-1]]
        dmin = np.minimum(dmin, np.linalg.norm(pts - last, axis=1))
        dmin[np.asarray(chosen, dtype=np.int64)] = -np.inf
        chosen.append(int(np.argmax(dmin)))
    return np.asarray(chosen, dtype=np.int64)


def select_diverse(candidates, scores, k, min_distance=None):
    return greedy_maxmin(candidates, scores, k)
