#!/usr/bin/env python3
"""Shared ranking / productive-exploration / stage helpers (Workflow §6, §10)."""

from __future__ import annotations

from typing import Dict, Iterable, Optional, Sequence

import numpy as np

from hybrid_common import (
    ALA_NBINS,
    COMMIT_PS,
    FOLD_RMSD,
    ala_bins,
    cln_bins,
    in_c7ax,
    longest_true_run,
    occupancy_entropy,
)
from taps_common import spearman


def pearson(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    if a.size < 3 or a.std() < 1e-12 or b.std() < 1e-12:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def ranking_metrics(pred: np.ndarray, y: np.ndarray, top_frac: float = 0.10, ks=(20, 50, 100)) -> dict:
    pred = np.asarray(pred, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    n = len(y)
    out = {
        "n": int(n),
        "mse": float(np.mean((pred - y) ** 2)),
        "mae": float(np.mean(np.abs(pred - y))),
        "spearman": spearman(pred, y),
        "pearson": pearson(pred, y),
    }
    n_top = max(1, int(round(n * top_frac)))
    pred_top = np.argsort(-pred)[:n_top]
    true_top = set(np.argsort(-y)[:n_top].tolist())
    out["top10_precision"] = float(np.mean([i in true_top for i in pred_top]))
    out["top10_enrich"] = float(y[pred_top].mean() / (y.mean() + 1e-12))
    out["top10_mean_feu"] = float(y[pred_top].mean())
    for k in ks:
        if n < k:
            continue
        pidx = np.argsort(-pred)[:k]
        tset = set(np.argsort(-y)[:k].tolist())
        out[f"top{k}_precision"] = float(np.mean([i in tset for i in pidx]))
        out[f"top{k}_mean_feu"] = float(y[pidx].mean())
    return out


def fmt_metrics(name: str, m: dict) -> str:
    return (
        f"{name:22s}  n={m['n']}  mse={m['mse']:.5f}  mae={m['mae']:.5f}  "
        f"Sp={m['spearman']:+.3f}  Pe={m['pearson']:+.3f}  "
        f"top10% P={m['top10_precision']:.3f}  enrich={m['top10_enrich']:.2f}  "
        f"top10% FEU={m['top10_mean_feu']:.4f}"
    )


def topk_sets(score: np.ndarray, k: int) -> set:
    return set(np.argsort(-np.asarray(score))[:k].tolist())


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    return float(len(a & b) / max(1, len(a | b)))


def overlap_frac(a: set, b: set) -> float:
    return float(len(a & b) / max(1, min(len(a), len(b))))


def time_split_by_source(source: np.ndarray, t_ps: np.ndarray, val_frac: float = 0.3):
    tr, va = [], []
    for src in np.unique(source):
        idx = np.flatnonzero(source == src)
        order = idx[np.argsort(t_ps[idx])]
        n_val = max(1, int(round(len(order) * val_frac)))
        n_tr = len(order) - n_val
        if n_tr < 8:
            tr.extend(order.tolist())
            continue
        tr.extend(order[:n_tr].tolist())
        va.extend(order[n_tr:].tolist())
    return np.asarray(tr, dtype=np.int64), np.asarray(va, dtype=np.int64)


def zscore_fit(X: np.ndarray, idx: np.ndarray):
    mu = X[idx].mean(axis=0)
    sd = X[idx].std(axis=0)
    sd = np.where(sd < 1e-8, 1.0, sd)
    return mu, sd


def apply_z(X, mu, sd):
    return (X - mu) / sd


def ridge_fit(Xz: np.ndarray, y: np.ndarray, idx: np.ndarray, l2: float = 1.0):
    A = np.column_stack([np.ones(len(idx)), Xz[idx]])
    xtx = A.T @ A
    xty = A.T @ y[idx]
    xtx[1:, 1:] += l2 * np.eye(xtx.shape[0] - 1)
    return np.linalg.solve(xtx, xty)


def ridge_pred(Xz: np.ndarray, w: np.ndarray) -> np.ndarray:
    return w[0] + Xz @ w[1:]


def encode_xy(kind: str, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    if kind == "ala2":
        xr = np.deg2rad(x)
        yr = np.deg2rad(y)
        return np.stack([np.sin(xr), np.cos(xr), np.sin(yr), np.cos(yr)], axis=1)
    return np.stack([x, y], axis=1)


def feat_matrix(kind: str, arr: dict, names: Sequence[str]) -> np.ndarray:
    cols = []
    if "x" in names or "y" in names:
        cols.append(encode_xy(kind, arr["x"], arr["y"]))
    extra = [n for n in names if n not in ("x", "y")]
    if extra:
        cols.append(np.stack([np.asarray(arr[n], dtype=np.float64) for n in extra], axis=1))
    return np.concatenate(cols, axis=1).astype(np.float64)


STATIC_COLS = ("x", "y", "rho", "last_score")
TEMPORAL_COLS = (
    "vel_x_50",
    "acc_x_50",
    "msd_x_50",
    "var_x_50",
    "persist_x_50",
    "vel_y_50",
    "msd_x_100",
    "msd_x_200",
    "persist_x_200",
)


def coverage_and_target(kind: str, x: np.ndarray, y: np.ndarray):
    if kind == "cln":
        bi, bj = cln_bins(x, y, 24)
        nside = 24
        target = np.asarray(x) < FOLD_RMSD
    else:
        bi, bj = ala_bins(x, y)
        nside = ALA_NBINS
        target = in_c7ax(x, y)
    flat = bi * nside + bj
    return flat, target, nside * nside


def first_time(mask: np.ndarray, t_ps: np.ndarray) -> Optional[float]:
    hit = np.flatnonzero(mask)
    if hit.size == 0:
        return None
    return float(t_ps[int(hit[0])])


def first_commit_time(mask: np.ndarray, t_ps: np.ndarray, dt_ps: float, commit_ps: float = COMMIT_PS):
    need = max(1, int(round(commit_ps / max(dt_ps, 1e-9))))
    m = np.asarray(mask, dtype=np.int8)
    if m.size < need or not m.any():
        return None
    c = np.convolve(m, np.ones(need, dtype=np.int32), mode="valid")
    hit = np.flatnonzero(c >= need)
    if hit.size == 0:
        return None
    return float(t_ps[int(hit[0]) + need - 1])


def sojourn_ps(mask: np.ndarray, dt_ps: float) -> np.ndarray:
    m = np.asarray(mask, dtype=np.int8)
    if m.size == 0 or not m.any():
        return np.asarray([], dtype=np.float64)
    d = np.diff(np.concatenate([[0], m, [0]]))
    starts = np.flatnonzero(d == 1)
    ends = np.flatnonzero(d == -1)
    return (ends - starts).astype(np.float64) * dt_ps


def productive_metrics(
    kind: str,
    t_ps: np.ndarray,
    x: np.ndarray,
    y: np.ndarray,
    seg: Optional[np.ndarray] = None,
    commit_ps: float = COMMIT_PS,
) -> dict:
    """Workflow §10: replace first-hit with productive exploration."""
    t_ps = np.asarray(t_ps, dtype=np.float64)
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    dt = float(t_ps[1] - t_ps[0]) if len(t_ps) > 1 else 2.0
    flat, target, nbin = coverage_and_target(kind, x, y)
    seen = set()
    novel_t = []
    for i, b in enumerate(flat.tolist()):
        if b not in seen:
            seen.add(b)
            novel_t.append(float(t_ps[i]))
    hist = np.bincount(flat, minlength=nbin)
    stays = sojourn_ps(target, dt)
    first_hit = first_time(target, t_ps)
    first_commit = first_commit_time(target, t_ps, dt, commit_ps)
    reexploit = 0
    if seg is not None and first_commit is not None:
        names = np.asarray(seg)
        after = False
        seen_seg = set()
        for i in range(len(names)):
            if t_ps[i] >= first_commit:
                after = True
            if after and target[i]:
                seen_seg.add(str(names[i]))
        reexploit = max(0, len(seen_seg) - 1)
    sim_ns = float((t_ps[-1] - t_ps[0]) + dt) / 1000.0 if len(t_ps) else 0.0
    return {
        "n_frames": int(len(t_ps)),
        "sim_ns": sim_ns,
        "coverage": float(len(seen) / max(1, nbin)),
        "n_novel_bins": int(len(seen)),
        "novel_per_ns": float(len(seen) / max(sim_ns, 1e-9)),
        "entropy": occupancy_entropy(hist),
        "first_hit_ns": None if first_hit is None else first_hit / 1000.0,
        "first_commit_ns": None if first_commit is None else first_commit / 1000.0,
        "n_target_frames": int(target.sum()),
        "frac_target": float(target.mean()),
        "n_sojourns": int(len(stays)),
        "mean_residence_ps": float(stays.mean()) if len(stays) else 0.0,
        "max_residence_ps": float(stays.max()) if len(stays) else 0.0,
        "committed_visits": int((stays >= commit_ps).sum()),
        "reexploit_segments": int(reexploit),
        "transient_only": bool(first_hit is not None and first_commit is None),
    }


def fmt_productive(name: str, m: dict) -> str:
    def ns(v):
        return "none" if v is None else f"{v:.3f}"

    return (
        f"{name:16s}  ns={m['sim_ns']:7.2f}  cov={m['coverage']:.4f}  "
        f"novel/ns={m['novel_per_ns']:.1f}  H={m['entropy']:.3f}  "
        f"hit={ns(m['first_hit_ns']):>8s}  commit={ns(m['first_commit_ns']):>8s}  "
        f"frac={m['frac_target']:.4f}  res_mean={m['mean_residence_ps']:.1f}ps  "
        f"commit_vis={m['committed_visits']}  reexploit={m['reexploit_segments']}"
        + ("  TRANSIENT_ONLY" if m["transient_only"] else "")
    )


def stage_by_round(n_rounds: int) -> Dict[int, str]:
    """Equal thirds of adaptive rounds (round 0 = init, not staged)."""
    out = {}
    for r in range(1, n_rounds + 1):
        q = (r - 1) / max(1, n_rounds)
        out[r] = "early" if q < 1.0 / 3.0 else ("middle" if q < 2.0 / 3.0 else "late")
    return out


def stage_by_coverage_gain(history: Iterable[dict], window: int = 2) -> Dict[int, str]:
    """Early = high recent coverage gain; late = saturation. Workflow §6.1 / §8."""
    rows = [h for h in history if int(h.get("round", -1)) > 0]
    rows = sorted(rows, key=lambda h: int(h["round"]))
    if not rows:
        return {}
    gains = []
    prev = None
    for h in rows:
        cov = float(h.get("coverage", 0.0))
        if prev is None:
            g = cov
        else:
            g = cov - prev
        gains.append(g)
        prev = cov
    # smooth
    sm = []
    for i in range(len(gains)):
        lo = max(0, i - window + 1)
        sm.append(float(np.mean(gains[lo : i + 1])))
    thr_hi = float(np.quantile(sm, 0.66)) if len(sm) > 2 else max(sm)
    thr_lo = float(np.quantile(sm, 0.33)) if len(sm) > 2 else min(sm)
    out = {}
    for h, g in zip(rows, sm):
        if g >= thr_hi:
            out[int(h["round"])] = "early"
        elif g <= thr_lo:
            out[int(h["round"])] = "late"
        else:
            out[int(h["round"])] = "middle"
    return out
