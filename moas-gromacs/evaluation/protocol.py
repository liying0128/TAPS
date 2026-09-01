"""Unified evaluation protocol. first-hit is auxiliary; committed fold is the discovery criterion."""

from __future__ import annotations

import numpy as np

from moas_common import COMMIT_PS, FOLD_RMSD_NM


def longest_true_run(mask: np.ndarray) -> int:
    best = cur = 0
    for v in np.asarray(mask, dtype=bool):
        if v:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return int(best)


def first_true_index(mask: np.ndarray):
    idx = np.flatnonzero(np.asarray(mask, dtype=bool))
    return int(idx[0]) if len(idx) else None


def productive_stats(rmsd: np.ndarray, dt_ps: float, fold_rmsd: float = FOLD_RMSD_NM, commit_ps: float = COMMIT_PS) -> dict:
    """Match the existing CLN025 reports: hit vs commit>=40 ps, visits, revisits."""
    rmsd = np.asarray(rmsd, dtype=np.float64)
    folded = rmsd < fold_rmsd
    n = len(folded)
    hit_i = first_true_index(folded)
    commit_frames = max(1, int(round(commit_ps / max(dt_ps, 1e-9))))
    # visits: True runs
    visits = []
    i = 0
    while i < n:
        if not folded[i]:
            i += 1
            continue
        j = i
        while j < n and folded[j]:
            j += 1
        visits.append((i, j))
        i = j
    committed = [v for v in visits if (v[1] - v[0]) >= commit_frames]
    commit_i = committed[0][0] if committed else None
    return {
        "n_frames": n,
        "dt_ps": float(dt_ps),
        "fold_frac": float(folded.mean()) if n else 0.0,
        "first_hit_frame": hit_i,
        "commit_frame": commit_i,
        "n_visits": len(visits),
        "n_committed_visits": len(committed),
        "n_reexploit": max(0, len(committed) - 1) if committed else 0,
        "max_residence_frames": longest_true_run(folded),
        "transient_only": hit_i is not None and commit_i is None,
    }
