#!/usr/bin/env python3
"""Shared helpers for the hybrid / FEU offline pipeline (Workflow §2–§3)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Tuple

import numpy as np

from taps_common import ANALYSIS, ROOT, TapsError, log, wrap_deg

# CLN025 (RMSD, Rg) bins — same box as stage13
RMSD_MAX = 1.60
RG_MIN, RG_MAX = 0.45, 1.70
FOLD_RMSD = 0.25
COMMIT_PS = 40.0  # ≥ this consecutive time in a new/target region

# Alanine dipeptide Ramachandran
ALA_NBINS = 36
C7AX = (70.0, -70.0)
C7AX_R = 25.0


@dataclass(frozen=True)
class SourceSpec:
    name: str
    kind: str  # "cln" | "ala2"
    trajs: Tuple[Path, ...]


def cln_bins(rmsd: np.ndarray, rg: np.ndarray, nbins: int) -> Tuple[np.ndarray, np.ndarray]:
    i = np.floor(np.clip(rmsd, 0.0, RMSD_MAX) / RMSD_MAX * nbins).astype(np.int64)
    i = np.clip(i, 0, nbins - 1)
    j = np.floor(np.clip(rg - RG_MIN, 0.0, RG_MAX - RG_MIN) / (RG_MAX - RG_MIN) * nbins).astype(np.int64)
    j = np.clip(j, 0, nbins - 1)
    return i, j


def ala_bins(phi: np.ndarray, psi: np.ndarray, nbins: int = ALA_NBINS) -> Tuple[np.ndarray, np.ndarray]:
    i = np.floor((wrap_deg(phi) + 180.0) / 360.0 * nbins).astype(np.int64) % nbins
    j = np.floor((wrap_deg(psi) + 180.0) / 360.0 * nbins).astype(np.int64) % nbins
    return i, j


def circ_diff(a, b):
    return wrap_deg(np.asarray(a, dtype=np.float64) - np.asarray(b, dtype=np.float64))


def in_c7ax(phi, psi) -> np.ndarray:
    d = np.hypot(circ_diff(phi, C7AX[0]), circ_diff(psi, C7AX[1]))
    return d <= C7AX_R


def resample_linear(t_ps, *cols, dt: float = 2.0):
    t_ps = np.asarray(t_ps, dtype=np.float64)
    if len(t_ps) < 2:
        return (t_ps,) + tuple(np.asarray(c) for c in cols)
    t0, t1 = float(t_ps[0]), float(t_ps[-1])
    t_new = np.arange(t0, t1 + 1e-9, dt)
    out = [t_new]
    for c in cols:
        out.append(np.interp(t_new, t_ps, np.asarray(c, dtype=np.float64)))
    return tuple(out)


def causal_hist(flat: np.ndarray, end: int, nbin: int) -> np.ndarray:
    hist = np.zeros(nbin, dtype=np.int64)
    if end >= 0:
        np.add.at(hist, flat[: end + 1], 1)
    return hist


def window_stats(x: np.ndarray, dt_ps: float) -> Dict[str, float]:
    """Temporal statistics on a 1-D history window (no future leak)."""
    x = np.asarray(x, dtype=np.float64)
    if len(x) < 2:
        return {
            "vel": 0.0,
            "acc": 0.0,
            "msd": 0.0,
            "var": 0.0,
            "persist": 0.0,
        }
    vel = np.diff(x) / dt_ps
    acc = np.diff(vel) / dt_ps if len(vel) > 1 else np.array([0.0])
    disp = x - x[0]
    # directional persistence: fraction of steps with same sign as net displacement
    net = x[-1] - x[0]
    if abs(net) < 1e-12:
        persist = 0.0
    else:
        persist = float((np.sign(vel) == np.sign(net)).mean())
    return {
        "vel": float(vel.mean()),
        "acc": float(acc.mean()),
        "msd": float(np.mean(disp**2)),
        "var": float(x.var()),
        "persist": persist,
    }


def longest_true_run(mask: np.ndarray) -> int:
    m = np.asarray(mask, dtype=np.int8)
    if m.size == 0 or not m.any():
        return 0
    d = np.diff(np.concatenate([[0], m, [0]]))
    starts = np.flatnonzero(d == 1)
    ends = np.flatnonzero(d == -1)
    return int((ends - starts).max())


def occupancy_entropy(counts: np.ndarray) -> float:
    p = np.asarray(counts, dtype=np.float64)
    p = p[p > 0]
    if p.size == 0:
        return 0.0
    p = p / p.sum()
    return float(-(p * np.log(p)).sum())


def feu_from_future(
    past_flat: np.ndarray,
    fut_flat: np.ndarray,
    fut_target: np.ndarray,
    now_target: bool,
    dt_ps: float,
    commit_ps: float = COMMIT_PS,
) -> Dict[str, float]:
    """Causal FEU. Novelty is no longer 'any unseen frame'.

    Old novelty = fraction of future frames in never-seen bins. That treats a
    one-frame flicker through an adjacent empty bin as high novelty.

    New novelty mixes three checks, all causal (past = frames ≤ seed):
      rare     inverse past-count of the bins the future actually visits
      info     entropy gain of the occupancy histogram after adding the future
      persist  longest consecutive stay in unseen bins, scaled by commit_ps
    """
    nbin = int(
        max(
            int(past_flat.max()) + 1 if len(past_flat) else 1,
            int(fut_flat.max()) + 1 if len(fut_flat) else 1,
        )
    )
    hist = np.bincount(past_flat, minlength=nbin)
    empty = {
        "novelty": 0.0,
        "novelty_unseen": 0.0,
        "novelty_rare": 0.0,
        "novelty_info": 0.0,
        "novelty_persist": 0.0,
        "diversity": 0.0,
        "discovery": 0.0,
        "discovery_commit": 0.0,
        "commitment": 0.0,
    }
    if fut_flat.size == 0:
        return empty
    idx = np.clip(fut_flat, 0, nbin - 1)
    unseen = hist[idx] == 0
    novelty_unseen = float(unseen.mean())
    novelty_rare = float((1.0 / (hist[idx].astype(np.float64) + 1.0)).mean())
    hist_after = hist.copy()
    np.add.at(hist_after, idx, 1)
    h0 = occupancy_entropy(hist)
    h1 = occupancy_entropy(hist_after)
    novelty_info = float(np.clip((h1 - h0) / np.log(max(2, int((hist_after > 0).sum()))), 0.0, 1.0))
    novelty_persist = float(min(1.0, (longest_true_run(unseen) * dt_ps) / commit_ps)) if unseen.any() else 0.0
    novelty = float(0.40 * novelty_rare + 0.30 * novelty_info + 0.30 * novelty_persist)
    new_bins = len(set(idx[unseen].tolist())) if unseen.any() else 0
    diversity = float(new_bins / max(1, len(set(idx.tolist()))))
    entered = bool(np.asarray(fut_target).any()) and not now_target
    longest = longest_true_run(fut_target)
    discovery = 1.0 if entered else 0.0
    discovery_commit = 1.0 if entered and (longest * dt_ps) >= commit_ps else 0.0
    commitment = float(min(1.0, (longest * dt_ps) / commit_ps)) if np.asarray(fut_target).any() else 0.0
    if now_target:
        discovery = 0.0
        discovery_commit = 0.0
    return {
        "novelty": novelty,
        "novelty_unseen": novelty_unseen,
        "novelty_rare": novelty_rare,
        "novelty_info": novelty_info,
        "novelty_persist": novelty_persist,
        "diversity": diversity,
        "discovery": discovery,
        "discovery_commit": discovery_commit,
        "commitment": commitment,
    }


FEU_WEIGHTS = {
    "default": (0.30, 0.20, 0.25, 0.25),
    "equal": (0.25, 0.25, 0.25, 0.25),
    "explore": (0.40, 0.30, 0.20, 0.10),
    "commit": (0.15, 0.15, 0.30, 0.40),
    "nocommit": (0.40, 0.30, 0.30, 0.00),
}


def feu_score(comp: Dict[str, float], weights: Tuple[float, float, float, float] = FEU_WEIGHTS["default"]) -> float:
    w1, w2, w3, w4 = weights
    return float(
        w1 * comp["novelty"]
        + w2 * comp["diversity"]
        + w3 * comp["discovery"]
        + w4 * comp["commitment"]
    )


def last_frontier_2d(xy_all: np.ndarray, xy_q: np.ndarray, nbins: int = 24) -> np.ndarray:
    z = np.asarray(xy_all, dtype=np.float64)
    zq = np.asarray(xy_q, dtype=np.float64)
    lo = z.min(axis=0)
    hi = z.max(axis=0)
    span = np.maximum(hi - lo, 1e-6)
    lo = lo - 0.05 * span
    hi = hi + 0.05 * span
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
    return 1.5 * frontier[iq, jq].astype(np.float64) + radius * (1.0 - 0.5 * lat_rho)


def density_score(flat_all: np.ndarray, flat_q: np.ndarray, nbin: int) -> np.ndarray:
    hist = np.bincount(flat_all, minlength=nbin).astype(np.float64)
    hist /= max(1.0, hist.sum())
    rho = hist[np.clip(flat_q, 0, nbin - 1)]
    inv = 1.0 / (rho + 1e-6)
    return inv / (inv.max() + 1e-12)


def hybrid_outdir() -> Path:
    p = ANALYSIS / "hybrid"
    p.mkdir(parents=True, exist_ok=True)
    return p
