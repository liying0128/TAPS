"""kNN-AS scores (Rovers et al., J. Chem. Theory Comput. 2025, 10.1021/acs.jctc.5c00462).

Paper: fit a k-NN graph on subsampled visited CV points; score = ||sum_j (z_j - q)||
over the k nearest neighbors. Interior points cancel; boundary points have a long
resultant. No target state. Matches LAST more closely than MOAS-static.

Their AdK used k=5 and subsample fraction P=0.5. sklearn's kneighbors includes self,
and their loop skips it (indices[:,1:]), so a point in the pool is scored with k-1
others. Queries that are not in the pool use all k neighbors.
"""

from __future__ import annotations

import numpy as np

KNN_K = 5
KNN_SUBSAMPLE = 0.5
KNN_MAX_POOL = 20000


def knn_as_scores(
    xy_pool,
    xy_query,
    k: int = KNN_K,
    subsample: float = KNN_SUBSAMPLE,
    rng_seed: int = 0,
    scale=None,
    max_pool: int = KNN_MAX_POOL,
) -> np.ndarray:
    z = np.asarray(xy_pool, dtype=np.float64)
    q = np.asarray(xy_query, dtype=np.float64)
    if z.ndim != 2 or q.ndim != 2 or z.shape[1] != q.shape[1]:
        raise ValueError(f"knn-as expected (N,d) and (M,d), got {z.shape} {q.shape}")
    if len(z) == 0 or len(q) == 0:
        return np.zeros(len(q), dtype=np.float64)
    if scale is None:
        std = np.maximum(z.std(axis=0), 1e-8)
        z = z / std
        q = q / std
    else:
        sc = np.asarray(scale, dtype=np.float64)
        z = z / sc
        q = q / sc
    n = len(z)
    n_keep = min(int(max_pool), max(int(k) + 1, int(round(n * float(subsample)))))
    n_keep = min(n, max(n_keep, min(n, int(k) + 1)))
    if n_keep < n:
        rng = np.random.default_rng(int(rng_seed))
        z = z[rng.choice(n, size=n_keep, replace=False)]
    k_use = min(int(k), len(z))
    scores = np.empty(len(q), dtype=np.float64)
    chunk = 256
    for i0 in range(0, len(q), chunk):
        qi = q[i0 : i0 + chunk]
        d2 = ((qi[:, None, :] - z[None, :, :]) ** 2).sum(axis=2)
        nn = np.argpartition(d2, kth=k_use - 1, axis=1)[:, :k_use]
        for t in range(len(qi)):
            delta = z[nn[t]] - qi[t]
            mag = np.sqrt((delta * delta).sum(axis=1))
            keep = mag > 1e-10
            if not np.any(keep):
                scores[i0 + t] = 0.0
            else:
                scores[i0 + t] = float(np.linalg.norm(delta[keep].sum(axis=0)))
    return scores
