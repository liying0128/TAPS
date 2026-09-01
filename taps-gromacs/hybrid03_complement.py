#!/usr/bin/env python3
"""
HYBRID 03  |  Workflow §6  LAST vs TAPS 互补性（不跑 MD）

两块证据：
  1) 候选表上 LAST 分数 vs 时序残差分数的排名分歧（按 early/middle/late）
  2) 已跑 campaign 每轮真实选出的 seed：位置重叠、类型是否不同

  python3 hybrid03_complement.py --system cln025
  python3 hybrid03_complement.py --system ala2
  python3 hybrid03_complement.py --system both

输出: analysis/hybrid/<kind>_complement_report.txt
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hybrid_common import cln_bins, hybrid_outdir  # noqa: E402
from hybrid_metrics import (  # noqa: E402
    STATIC_COLS,
    TEMPORAL_COLS,
    apply_z,
    feat_matrix,
    jaccard,
    overlap_frac,
    ridge_fit,
    ridge_pred,
    stage_by_coverage_gain,
    stage_by_round,
    time_split_by_source,
    topk_sets,
    zscore_fit,
)
from taps_common import ANALYSIS, TapsError, log, spearman  # noqa: E402


def load_table(kind: str, horizon: int):
    path = hybrid_outdir() / f"{kind}_candidates.npz"
    if not path.exists():
        raise TapsError(f"missing {path}; run hybrid01 first")
    arr = dict(np.load(path, allow_pickle=True))
    ykey = f"feu_{horizon}"
    if ykey not in arr:
        raise TapsError(f"no {ykey} in {path}")
    ok = np.isfinite(arr[ykey])
    for k, v in list(arr.items()):
        arr[k] = v[ok]
    return arr, arr[ykey]


def temporal_residual_score(kind: str, arr: dict, y: np.ndarray):
    """TAPS-like score = residual of FEU after static/LAST, predicted from window stats.

    This is the increment the outline asks for, not the old S_p (which tracked RMSD).
    """
    tr, va = time_split_by_source(arr["source"], arr["t_ps"])
    Xs = feat_matrix(kind, arr, STATIC_COLS)
    Xt = feat_matrix(kind, arr, TEMPORAL_COLS)
    mu_s, sd_s = zscore_fit(Xs, tr)
    mu_t, sd_t = zscore_fit(Xt, tr)
    Zs, Zt = apply_z(Xs, mu_s, sd_s), apply_z(Xt, mu_t, sd_t)
    w_s = ridge_fit(Zs, y, tr)
    resid = y - ridge_pred(Zs, w_s)
    w_t = ridge_fit(Zt, resid, tr)
    taps = ridge_pred(Zt, w_t)
    return taps, tr, va, resid


def campaign_dir(kind: str, tag: str) -> Path:
    root = ANALYSIS / ("cln025_unfolded" if kind == "cln" else "ala2_vacuum")
    return root / "campaigns" / tag


def load_history(kind: str, tag: str):
    path = campaign_dir(kind, tag) / "history.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def load_round_seeds(kind: str, tag: str) -> dict:
    out = {}
    for path in sorted(campaign_dir(kind, tag).glob("seeds_round*.json")):
        rec = json.loads(path.read_text(encoding="utf-8"))
        out[int(rec["round"])] = rec.get("seeds", [])
    return out


def seed_xy(seeds: list, kind: str):
    if kind == "cln":
        x = np.array([s["rmsd"] for s in seeds], dtype=np.float64)
        y = np.array([s["rg"] for s in seeds], dtype=np.float64)
    else:
        x = np.array([s.get("phi", s.get("x", np.nan)) for s in seeds], dtype=np.float64)
        y = np.array([s.get("psi", s.get("y", np.nan)) for s in seeds], dtype=np.float64)
    return x, y


def seed_bins(seeds: list, kind: str):
    x, y = seed_xy(seeds, kind)
    if not np.isfinite(x).all():
        return set()
    if kind == "cln":
        i, j = cln_bins(x, y, 24)
        return set(zip(i.tolist(), j.tolist()))
    from hybrid_common import ala_bins

    i, j = ala_bins(x, y)
    return set(zip(i.tolist(), j.tolist()))


def table_block(kind: str, arr: dict, y: np.ndarray, taps: np.ndarray, va: np.ndarray, ks=(20, 50, 100)):
    last = arr["last_score"]
    lines = ["=== candidate-table ranking disagreement (validation slice) ==="]
    lines.append(f"Spearman(LAST, TAPS_residual) = {spearman(last[va], taps[va]):+.3f}")
    lines.append(f"Spearman(LAST, FEU)           = {spearman(last[va], y[va]):+.3f}")
    lines.append(f"Spearman(TAPS_residual, FEU)  = {spearman(taps[va], y[va]):+.3f}")
    n = len(va)
    for k in ks:
        if n < k:
            continue
        a, b = topk_sets(last[va], k), topk_sets(taps[va], k)
        true = topk_sets(y[va], k)
        last_only = a - b
        taps_only = b - a
        lines.append(
            f"  top-{k:3d}  overlap={overlap_frac(a, b):.3f}  Jaccard={jaccard(a, b):.3f}  "
            f"LAST∩true={overlap_frac(a, true):.3f}  TAPS∩true={overlap_frac(b, true):.3f}  "
            f"LAST-only∩true={overlap_frac(last_only, true):.3f}  "
            f"TAPS-only∩true={overlap_frac(taps_only, true):.3f}  "
            f"meanFEU LAST={y[va][list(a)].mean():.4f}  TAPS={y[va][list(b)].mean():.4f}"
        )
    # unique high-FEU recovery
    n_top = max(1, int(round(0.10 * n)))
    true = topk_sets(y[va], n_top)
    last_top = topk_sets(last[va], n_top)
    taps_top = topk_sets(taps[va], n_top)
    both = last_top & taps_top & true
    l_only = (last_top - taps_top) & true
    t_only = (taps_top - last_top) & true
    none = true - last_top - taps_top
    lines.append(
        f"  true top10% split: both={len(both)}  LAST-only={len(l_only)}  "
        f"TAPS-only={len(t_only)}  missed={len(none)}  (n_true={len(true)})"
    )
    return lines, {
        "rank_spearman": float(spearman(last[va], taps[va])),
        "taps_only_true": int(len(t_only)),
        "last_only_true": int(len(l_only)),
        "n_true_top": int(len(true)),
    }


def stage_table(kind: str, arr: dict, y: np.ndarray, taps: np.ndarray):
    lines = ["=== stage-split on each source (time tertiles) ==="]
    last = arr["last_score"]
    summary = {}
    for src in np.unique(arr["source"]):
        idx = np.flatnonzero(arr["source"] == src)
        idx = idx[np.argsort(arr["t_ps"][idx])]
        n = len(idx)
        cuts = [0, n // 3, 2 * n // 3, n]
        names = ("early", "middle", "late")
        lines.append(f"  source={src}")
        for name, a, b in zip(names, cuts, cuts[1:]):
            sl = idx[a:b]
            if len(sl) < 30:
                continue
            k = max(10, int(0.10 * len(sl)))
            la, ta = topk_sets(last[sl], k), topk_sets(taps[sl], k)
            true = topk_sets(y[sl], k)
            rec = {
                "spearman_lt": float(spearman(last[sl], taps[sl])),
                "jaccard": jaccard(la, ta),
                "last_true": overlap_frac(la, true),
                "taps_true": overlap_frac(ta, true),
                "last_feu": float(y[sl][list(la)].mean()),
                "taps_feu": float(y[sl][list(ta)].mean()),
            }
            summary[f"{src}_{name}"] = rec
            lines.append(
                f"    {name:6s}  n={len(sl):5d}  Sp(L,T)={rec['spearman_lt']:+.3f}  "
                f"Jacc={rec['jaccard']:.3f}  LAST∩true={rec['last_true']:.3f}  "
                f"TAPS∩true={rec['taps_true']:.3f}  FEU L={rec['last_feu']:.4f} T={rec['taps_feu']:.4f}"
            )
    return lines, summary


def campaign_block(kind: str):
    lines = ["=== real campaign seeds (TAPS vs LAST, same budget rounds) ==="]
    taps_s = load_round_seeds(kind, "discover_taps")
    last_s = load_round_seeds(kind, "discover_last")
    hist = load_history(kind, "discover_last") or load_history(kind, "discover_taps")
    if not taps_s or not last_s:
        lines.append("  missing seeds_round*.json")
        return lines, {}
    n_rounds = max(max(taps_s), max(last_s))
    by_round = stage_by_round(n_rounds)
    by_gain = stage_by_coverage_gain(hist) if hist else {}
    stage_acc = {s: {"jacc": [], "rmsd_gap": [], "n": 0} for s in ("early", "middle", "late")}
    for rid in range(1, n_rounds + 1):
        if rid not in taps_s or rid not in last_s:
            continue
        tb, lb = seed_bins(taps_s[rid], kind), seed_bins(last_s[rid], kind)
        jac = jaccard(tb, lb)
        tx, _ = seed_xy(taps_s[rid], kind)
        lx, _ = seed_xy(last_s[rid], kind)
        gap = float(np.nanmean(tx) - np.nanmean(lx)) if kind == "cln" else float("nan")
        st = by_gain.get(rid, by_round.get(rid, "?"))
        lines.append(
            f"  r{rid:02d}  stage={st:6s}  seed-bin Jaccard={jac:.3f}  "
            f"nT={len(taps_s[rid])} nL={len(last_s[rid])}"
            + (f"  meanRMSD T-L={gap:+.3f}" if kind == "cln" else "")
        )
        if st in stage_acc:
            stage_acc[st]["jacc"].append(jac)
            if np.isfinite(gap):
                stage_acc[st]["rmsd_gap"].append(gap)
            stage_acc[st]["n"] += 1
    lines.append("  stage averages (coverage-gain stages if available):")
    summary = {}
    for st, rec in stage_acc.items():
        if not rec["jacc"]:
            continue
        mj = float(np.mean(rec["jacc"]))
        lines.append(f"    {st:6s}  mean Jaccard={mj:.3f}  rounds={rec['n']}")
        summary[st] = {"mean_jaccard": mj, "n_rounds": rec["n"]}
    lines.append("  Low Jaccard = the two methods pick different conformational bins.")
    return lines, summary


def run_one(kind: str, horizon: int) -> str:
    arr, y = load_table(kind, horizon)
    taps, tr, va, _ = temporal_residual_score(kind, arr, y)
    log(f"{kind}  n={len(y)}  train={len(tr)}  val={len(va)}")
    lines = [
        f"HYBRID 03  {kind}  horizon={horizon}ps",
        "TAPS score here = temporal residual after subtracting static/LAST (not old S_p).",
        "",
    ]
    block, tab_sum = table_block(kind, arr, y, taps, va)
    lines.extend(block)
    lines.append("")
    sblock, _ = stage_table(kind, arr, y, taps)
    lines.extend(sblock)
    lines.append("")
    cblock, camp_sum = campaign_block(kind)
    lines.extend(cblock)
    lines.append("")
    lines.append("Hypothesis check (do not pre-write as a result):")
    lines.append("  LAST stronger early / TAPS increment late is supported only if")
    lines.append("  TAPS∩true rises from early→late while Jaccard stays clearly < 1.")
    text = "\n".join(lines) + "\n"
    out = hybrid_outdir()
    (out / f"{kind}_complement_report.txt").write_text(text, encoding="utf-8")
    np.savez_compressed(
        out / f"{kind}_complement.npz",
        y=y,
        last=arr["last_score"],
        taps_residual=taps,
        t_ps=arr["t_ps"],
        source=arr["source"],
        va=va,
    )
    meta = {"kind": kind, "horizon": horizon, "table": tab_sum, "campaign": camp_sum}
    (out / f"{kind}_complement_meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(text)
    return text


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--system", default="cln025", choices=("cln025", "ala2", "both"))
    p.add_argument("--horizon", type=int, default=200, choices=(200, 500, 1000))
    args = p.parse_args(argv)
    try:
        log(f"HYBRID 03  complementarity  system={args.system}")
        if args.system in ("cln025", "both"):
            run_one("cln", args.horizon)
        if args.system in ("ala2", "both"):
            run_one("ala2", args.horizon)
        return 0
    except TapsError as exc:
        log(str(exc), "ERROR")
        return 1


if __name__ == "__main__":
    sys.exit(main())
