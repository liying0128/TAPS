#!/usr/bin/env python3
"""Production MOAS ranking used in the manuscript (eqs. for novelty, LAST, target, mix).

Bit-identical logic with:
  moas-adk/stage_adk_discover.py
  moas-mbp/stage_mbp_discover.py
  taps-gromacs/stage13_cln025_discover.py  (CLN025 target score uses RMSD, not Euclidean CV distance)

This module is the deposit for JCTC/JCIM Data and Software Availability.
It does not run MD. Feed candidate CV endpoints and the visited pool.

Manuscript mapping
------------------
novelty      1 / (rho + 1e-6), rho = 24×24 histogram density of the visited pool
boundary     LAST-style frontier score (occupied bin with an empty 4-neighbor)
target       1 / (distance-to-closed + offset); CLN025 uses max(RMSD − 0.25, 0) + 0.05
mix          equal mean of percentile ranks of the active objectives
diversity    greedy accept while CV distance to already chosen seeds ≥ δ
"""

from __future__ import annotations

import numpy as np

MOAS_OBJECTIVE_WEIGHTS = {
    "moas": (1.0, 1.0, 1.0),
    "nov": (1.0, 0.0, 0.0),
    "bnd": (0.0, 1.0, 0.0),
    "tgt": (0.0, 0.0, 1.0),
    "novbnd": (1.0, 1.0, 0.0),
    "novtgt": (1.0, 0.0, 1.0),
    "bndtgt": (0.0, 1.0, 1.0),
}


def percentile_rank(a: np.ndarray) -> np.ndarray:
    a = np.asarray(a, dtype=np.float64)
    order = np.argsort(a, kind="mergesort")
    ranks = np.empty(len(a), dtype=np.float64)
    ranks[order] = np.linspace(0.0, 1.0, len(a), dtype=np.float64)
    return ranks


def density_at(x_all, y_all, x_q, y_q, nbins, lo, hi):
    def to_bins(x, y):
        i = np.clip(((np.asarray(x) - lo[0]) / (hi[0] - lo[0]) * nbins).astype(np.int64), 0, nbins - 1)
        j = np.clip(((np.asarray(y) - lo[1]) / (hi[1] - lo[1]) * nbins).astype(np.int64), 0, nbins - 1)
        return i, j

    i, j = to_bins(x_all, y_all)
    hist = np.zeros((nbins, nbins), dtype=np.float64)
    np.add.at(hist, (i, j), 1)
    hist /= max(1.0, hist.sum())
    iq, jq = to_bins(x_q, y_q)
    return hist[iq, jq]


def novelty_scores(x_all, y_all, x_q, y_q, nbins=24, pad=2.0):
    lo = np.array([np.min(x_all) - pad, np.min(y_all) - pad], dtype=float)
    hi = np.array([np.max(x_all) + pad, np.max(y_all) + pad], dtype=float)
    rho = density_at(x_all, y_all, x_q, y_q, nbins, lo, hi)
    inv = 1.0 / (rho + 1e-6)
    return inv / (inv.max() + 1e-12)


def last_frontier_scores(x_all, y_all, x_q, y_q, nbins: int = 24) -> np.ndarray:
    z = np.stack([x_all, y_all], axis=1)
    zq = np.stack([x_q, y_q], axis=1)
    lo = z.min(axis=0) - 2.0
    hi = z.max(axis=0) + 2.0
    hist, xedges, yedges = np.histogram2d(z[:, 0], z[:, 1], bins=nbins, range=[[lo[0], hi[0]], [lo[1], hi[1]]])
    occ = hist > 0
    pad = np.pad(occ, 1, constant_values=False)
    empty_n = (~pad[:-2, 1:-1]) | (~pad[2:, 1:-1]) | (~pad[1:-1, :-2]) | (~pad[1:-1, 2:])
    frontier = occ & empty_n
    iq = np.clip(np.digitize(zq[:, 0], xedges) - 1, 0, nbins - 1)
    jq = np.clip(np.digitize(zq[:, 1], yedges) - 1, 0, nbins - 1)
    radius = np.linalg.norm(zq - z.mean(axis=0), axis=1)
    radius = radius / (float(radius.max()) + 1e-12)
    lat_rho = hist[iq, jq]
    lat_rho = lat_rho / (float(lat_rho.max()) + 1e-12)
    on_rim = frontier[iq, jq].astype(np.float64)
    return 1.5 * on_rim + radius * (1.0 - 0.5 * lat_rho)


def target_scores_adk(lid_q, nmp_q, refs: dict) -> np.ndarray:
    d_closed = np.hypot(lid_q - refs["closed_lid"], nmp_q - refs["closed_nmp"])
    return 1.0 / (d_closed + 5.0)


def target_scores_mbp(dist_q, theta_q, refs: dict) -> np.ndarray:
    d_closed = np.hypot((dist_q - refs["closed_dist"]) / 0.05, (theta_q - refs["closed_theta"]) / 4.0)
    return 1.0 / (d_closed + 5.0)


def target_scores_cln(rmsd_q, fold_rmsd: float = 0.25) -> np.ndarray:
    return 1.0 / (np.maximum(rmsd_q - fold_rmsd, 0.0) + 0.05)


def moas_mix(novelty, boundary, target, method: str = "moas") -> np.ndarray:
    wn, wb, wt = MOAS_OBJECTIVE_WEIGHTS[method]
    parts = []
    if wn:
        parts.append(percentile_rank(novelty))
    if wb:
        parts.append(percentile_rank(boundary))
    if wt:
        parts.append(percentile_rank(target))
    if not parts:
        raise ValueError(f"no MOAS objectives enabled for {method}")
    return sum(parts) / float(len(parts))


def greedy_diverse(x, y, score, n_seeds: int, min_sep: float) -> list[int]:
    order = np.argsort(-np.asarray(score))
    picked: list[int] = []
    for idx in order:
        i = int(idx)
        if all(float(np.hypot(x[i] - x[j], y[i] - y[j])) >= min_sep for j in picked):
            picked.append(i)
        if len(picked) >= n_seeds:
            break
    return picked
