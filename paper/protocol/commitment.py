#!/usr/bin/env python3
"""Committed visit, occupancy, and residence times used in the manuscript.

CLN025 (main text): contiguous sojourn duration t_end − t_start + dt ≥ τ, τ = 40 ps.
AdK / MBP (production): consecutive True frames ≥ round(τ / Δt), τ = 200 ps, Δt = 2 ps.

Occupancy is mean(mask) over the pooled campaign and does not depend on τ.
A committed visit is equivalent to longest_sojourn ≥ τ.
"""

from __future__ import annotations

import numpy as np


def occupancy(mask: np.ndarray) -> float:
    m = np.asarray(mask, dtype=bool)
    return float(m.mean()) if m.size else 0.0


def first_commit_from_mask(mask: np.ndarray, t_ps: np.ndarray, commit_ps: float):
    """CLN025 main-text definition. Returns first commit time in ns, or None."""
    t = np.asarray(t_ps, dtype=np.float64)
    m = np.asarray(mask, dtype=bool)
    n = len(m)
    i = 0
    while i < n:
        if not m[i]:
            i += 1
            continue
        j = i + 1
        while j < n and m[j]:
            j += 1
        dt_end = float(t[1] - t[0]) if n > 1 else 2.0
        if j < n:
            dt_end = float(t[j] - t[j - 1])
        elif n > 1:
            dt_end = float(np.median(np.diff(t)))
        dur = float(t[j - 1] - t[i]) + dt_end
        if dur >= commit_ps:
            return float(t[i]) / 1000.0
        i = j
    return None


def first_commit_nframes(mask: np.ndarray, t_ps: np.ndarray, commit_ps: float):
    """AdK/MBP production definition. Returns first commit time in ns, or None."""
    t = np.asarray(t_ps, dtype=np.float64)
    m = np.asarray(mask, dtype=bool)
    n = len(m)
    if n == 0:
        return None
    dt = float(t[1] - t[0]) if n > 1 else 2.0
    need = max(1, int(round(commit_ps / max(dt, 1e-9))))
    padded = np.concatenate([[False], m, [False]])
    d = np.diff(padded.astype(np.int8))
    i0 = np.flatnonzero(d == 1)
    i1 = np.flatnonzero(d == -1)
    ok = np.flatnonzero((i1 - i0) >= need)
    if len(ok) == 0:
        return None
    return float(t[i0[ok[0]]]) / 1000.0


def sojourns_ps(kind: str, mask: np.ndarray, t_ps: np.ndarray) -> np.ndarray:
    """Contiguous residence times (ps) using the production sojourn definition."""
    t = np.asarray(t_ps, dtype=np.float64)
    m = np.asarray(mask, dtype=bool)
    n = len(m)
    if n == 0:
        return np.asarray([], dtype=float)
    padded = np.concatenate([[False], m, [False]])
    d = np.diff(padded.astype(np.int8))
    i0 = np.flatnonzero(d == 1)
    i1 = np.flatnonzero(d == -1)
    if kind == "cln":
        med_dt = float(np.median(np.diff(t))) if n > 1 else 2.0
        durs = []
        for a, b in zip(i0, i1):
            dt_end = float(t[b] - t[b - 1]) if b < n else med_dt
            durs.append(float(t[b - 1] - t[a]) + dt_end)
        return np.asarray(durs, dtype=float)
    dt = float(t[1] - t[0]) if n > 1 else 2.0
    return np.asarray([(b - a) * dt for a, b in zip(i0, i1)], dtype=float)
