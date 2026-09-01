#!/usr/bin/env python3
"""
HYBRID 04  |  Workflow §5  TAPS 不确定性是否校准（不跑 MD）

bootstrap ridge ensemble on C features → (μ, σ) per seed.
If low-σ seeds rank FEU better than high-σ seeds, uncertainty is usable
for the later controller. Otherwise fall back to stage-only switching.

  python3 hybrid04_uncertainty.py --system cln025
  python3 hybrid04_uncertainty.py --system both

输出: analysis/hybrid/<kind>_uncertainty_report.txt
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

from hybrid_common import hybrid_outdir  # noqa: E402
from hybrid_metrics import (  # noqa: E402
    STATIC_COLS,
    TEMPORAL_COLS,
    apply_z,
    feat_matrix,
    ranking_metrics,
    time_split_by_source,
    zscore_fit,
    ridge_fit,
    ridge_pred,
)
from taps_common import TapsError, log, spearman  # noqa: E402


def run_one(kind: str, horizon: int, n_boot: int, seed: int) -> str:
    path = hybrid_outdir() / f"{kind}_candidates.npz"
    if not path.exists():
        raise TapsError(f"missing {path}")
    arr = dict(np.load(path, allow_pickle=True))
    y = arr[f"feu_{horizon}"]
    ok = np.isfinite(y)
    for k, v in list(arr.items()):
        arr[k] = v[ok]
    y = y[ok]
    tr, va = time_split_by_source(arr["source"], arr["t_ps"])
    X = feat_matrix(kind, arr, STATIC_COLS + TEMPORAL_COLS)
    mu, sd = zscore_fit(X, tr)
    Xz = apply_z(X, mu, sd)
    rng = np.random.default_rng(seed)
    preds = []
    for b in range(n_boot):
        boot = rng.choice(tr, size=len(tr), replace=True)
        w = ridge_fit(Xz, y, boot)
        preds.append(ridge_pred(Xz, w))
    P = np.stack(preds, axis=0)
    mu_p = P.mean(axis=0)
    sig = P.std(axis=0)
    conf = mu_p / (sig + 1e-6)

    lines = [
        f"HYBRID 04  {kind}  target=feu_{horizon}  bootstrap={n_boot}",
        f"n={len(y)}  train={len(tr)}  val={len(va)}  mean σ={sig[va].mean():.4f}",
        "",
        "=== validation by uncertainty tertile (low σ should be more reliable) ===",
    ]
    order = np.argsort(sig[va])
    cuts = np.array_split(order, 3)
    names = ("low_σ", "mid_σ", "high_σ")
    bin_sp = []
    for name, idx in zip(names, cuts):
        sl = va[idx]
        m = ranking_metrics(mu_p[sl], y[sl])
        bin_sp.append(m["spearman"])
        lines.append(
            f"  {name:8s}  n={len(sl):5d}  meanσ={sig[sl].mean():.4f}  "
            f"Sp={m['spearman']:+.3f}  enrich={m['top10_enrich']:.2f}  "
            f"top10% FEU={m['top10_mean_feu']:.4f}"
        )
    usable = bool(np.isfinite(bin_sp[0]) and np.isfinite(bin_sp[2]) and bin_sp[0] > bin_sp[2] + 0.03)
    m_all = ranking_metrics(mu_p[va], y[va])
    m_conf = ranking_metrics(conf[va], y[va])
    lines.append("")
    lines.append(f"μ only     Sp={m_all['spearman']:+.3f}  enrich={m_all['top10_enrich']:.2f}")
    lines.append(f"μ/(σ+ε)    Sp={m_conf['spearman']:+.3f}  enrich={m_conf['top10_enrich']:.2f}")
    lines.append(f"Spearman(|err|, σ) on val = {spearman(np.abs(mu_p[va] - y[va]), sig[va]):+.3f}")
    lines.append("")
    if usable:
        lines.append("VERDICT: uncertainty has ranking calibration → keep for Hybrid 07 controller.")
    else:
        lines.append("VERDICT: uncertainty is NOT calibrated enough → use stage-based switch only.")
    text = "\n".join(lines) + "\n"
    out = hybrid_outdir()
    (out / f"{kind}_uncertainty_report.txt").write_text(text, encoding="utf-8")
    np.savez_compressed(
        out / f"{kind}_uncertainty.npz",
        mu=mu_p,
        sigma=sig,
        y=y,
        va=va,
        source=arr["source"],
        t_ps=arr["t_ps"],
    )
    meta = {"kind": kind, "usable": usable, "spearman_low": bin_sp[0], "spearman_high": bin_sp[2]}
    (out / f"{kind}_uncertainty_meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(text)
    return text


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--system", default="cln025", choices=("cln025", "ala2", "both"))
    p.add_argument("--horizon", type=int, default=200, choices=(200, 500, 1000))
    p.add_argument("--n-boot", type=int, default=20)
    p.add_argument("--seed", type=int, default=0)
    args = p.parse_args(argv)
    try:
        log(f"HYBRID 04  uncertainty  system={args.system}")
        if args.system in ("cln025", "both"):
            run_one("cln", args.horizon, args.n_boot, args.seed)
        if args.system in ("ala2", "both"):
            run_one("ala2", args.horizon, args.n_boot, args.seed)
        return 0
    except TapsError as exc:
        log(str(exc), "ERROR")
        return 1


if __name__ == "__main__":
    sys.exit(main())
