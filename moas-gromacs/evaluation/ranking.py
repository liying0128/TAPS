"""Ranking helpers for Phase 1 offline comparison."""

from __future__ import annotations

import numpy as np


def spearman(a, b) -> float:
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    if a.size < 3 or np.std(a) < 1e-12 or np.std(b) < 1e-12:
        return float("nan")
    ra = np.argsort(np.argsort(a))
    rb = np.argsort(np.argsort(b))
    return float(np.corrcoef(ra, rb)[0, 1])


def ranking_metrics(pred, y, top_frac=0.10, ks=(50, 100, 200)) -> dict:
    pred = np.asarray(pred, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    n = len(y)
    n_top = max(1, int(round(n * top_frac)))
    pred_top = np.argsort(-pred)[:n_top]
    true_top = set(np.argsort(-y)[:n_top].tolist())
    out = {
        "n": int(n),
        "spearman": spearman(pred, y),
        "top10_precision": float(np.mean([i in true_top for i in pred_top])),
        "top10_enrich": float(y[pred_top].mean() / (y.mean() + 1e-12)),
        "top10_mean": float(y[pred_top].mean()),
        "y_mean": float(y.mean()),
    }
    for k in ks:
        if n < k:
            continue
        pidx = np.argsort(-pred)[:k]
        out[f"top{k}_enrich"] = float(y[pidx].mean() / (y.mean() + 1e-12))
        out[f"top{k}_mean"] = float(y[pidx].mean())
        out[f"top{k}_hitrate"] = float((y[pidx] > 0).mean()) if np.any(y > 0) else float("nan")
    return out


def fmt_rank(name: str, m: dict) -> str:
    extra = ""
    if "top100_enrich" in m:
        extra = f"  top100 enrich={m['top100_enrich']:.2f}  hitrate={m.get('top100_hitrate', float('nan')):.3f}"
    return (
        f"{name:28s}  n={m['n']:5d}  Sp={m['spearman']:+.3f}  "
        f"top10% P={m['top10_precision']:.3f}  enrich={m['top10_enrich']:.2f}  "
        f"top10% y={m['top10_mean']:.4f}{extra}"
    )


def topk_set(score, k) -> set:
    return set(np.argsort(-np.asarray(score))[:k].tolist())


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    return float(len(a & b) / max(1, len(a | b)))
