#!/usr/bin/env python3
"""
HYBRID 02  |  Workflow §4  消融：谁能把 high-FEU seed 排到前面？

目标是 FEU，不是 future RMSD drop。本步只用 Hybrid 01 的表，不跑 MD。

  A  last-frame     只用当前坐标 x_t
  B  static         坐标 + density / LAST frontier
  C  traj-stats     B + 50/100/200 ps 窗口统计
  D  本步不做 GRU：表里没有整段窗口，等 Hybrid 02b 回灌序列

额外无训练基线：
  LAST     last_score
  LC       1 / density
  shortcut CLN 上用 -RMSD（旧 S_p shortcut）

划分：每个 source 按时间 70/30，避免同一条轨迹的未来泄漏到训练。

  python3 hybrid02_ablate_feu.py --system cln025
  python3 hybrid02_ablate_feu.py --system ala2
  python3 hybrid02_ablate_feu.py --system both

输出: analysis/hybrid/<kind>_ablate_feu_report.txt
      analysis/hybrid/<kind>_ablate_feu.npz
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
from taps_common import TapsError, log, spearman  # noqa: E402

STATIC = ("x", "y", "rho", "last_score")
TEMPORAL = (
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


def pearson(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    if a.size < 3 or a.std() < 1e-12 or b.std() < 1e-12:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def encode_xy(kind: str, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    if kind == "ala2":
        xr = np.deg2rad(x)
        yr = np.deg2rad(y)
        return np.stack([np.sin(xr), np.cos(xr), np.sin(yr), np.cos(yr)], axis=1)
    return np.stack([x, y], axis=1)


def feats(kind: str, arr: dict, names: tuple) -> np.ndarray:
    cols = []
    if "x" in names or "y" in names:
        cols.append(encode_xy(kind, arr["x"], arr["y"]))
    extra = [n for n in names if n not in ("x", "y")]
    if extra:
        cols.append(np.stack([arr[n] for n in extra], axis=1))
    return np.concatenate(cols, axis=1).astype(np.float64)


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
    w = np.linalg.solve(xtx, xty)
    return w


def ridge_pred(Xz: np.ndarray, w: np.ndarray) -> np.ndarray:
    return w[0] + Xz @ w[1:]


def ranking_metrics(pred: np.ndarray, y: np.ndarray, top_frac: float = 0.10, ks=(20, 50, 100)):
    pred = np.asarray(pred, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    n = len(y)
    out = {
        "n": n,
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
    parts = [
        f"{name:16s}  n={m['n']}",
        f"mse={m['mse']:.5f}",
        f"mae={m['mae']:.5f}",
        f"Sp={m['spearman']:+.3f}",
        f"Pe={m['pearson']:+.3f}",
        f"top10% P={m['top10_precision']:.3f}",
        f"enrich={m['top10_enrich']:.2f}",
        f"top10% FEU={m['top10_mean_feu']:.4f}",
    ]
    if "top50_precision" in m:
        parts.append(f"top50 P={m['top50_precision']:.3f}")
    if "top100_precision" in m:
        parts.append(f"top100 P={m['top100_precision']:.3f}")
    return "  ".join(parts)


def train_mlp(Xz, y, tr, va, epochs: int, seed: int):
    try:
        import torch
        import torch.nn as nn
        from torch.utils.data import DataLoader, TensorDataset
    except ImportError:
        return None
    torch.manual_seed(seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = nn.Sequential(
        nn.Linear(Xz.shape[1], 64),
        nn.ReLU(),
        nn.Linear(64, 64),
        nn.ReLU(),
        nn.Linear(64, 1),
        nn.Sigmoid(),
    ).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    loss_fn = nn.MSELoss()
    Xt = torch.from_numpy(Xz.astype(np.float32))
    yt = torch.from_numpy(y.astype(np.float32))
    loader = DataLoader(TensorDataset(Xt[tr], yt[tr]), batch_size=256, shuffle=True)
    val_X, val_y = Xt[va].to(device), yt[va].to(device)
    best, best_state = float("inf"), None
    for epoch in range(1, epochs + 1):
        model.train()
        for xb, yb in loader:
            pred = model(xb.to(device)).squeeze(-1)
            loss = loss_fn(pred, yb.to(device))
            opt.zero_grad()
            loss.backward()
            opt.step()
        model.eval()
        with torch.no_grad():
            val = float(loss_fn(model(val_X).squeeze(-1), val_y).item())
        if val < best:
            best = val
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
        if epoch == 1 or epoch == epochs or epoch % 10 == 0:
            log(f"  mlp epoch {epoch:03d}  val_mse={val:.5f}")
    model.load_state_dict(best_state)
    model.eval()
    with torch.no_grad():
        pred = model(Xt.to(device)).squeeze(-1).cpu().numpy()
    return pred


def run_one(kind: str, horizon: int, epochs: int, seed: int) -> str:
    path = hybrid_outdir() / f"{kind}_candidates.npz"
    if not path.exists():
        raise TapsError(f"missing {path}; run hybrid01 first")
    arr = dict(np.load(path, allow_pickle=True))
    ykey = f"feu_{horizon}"
    if ykey not in arr:
        raise TapsError(f"{path} has no {ykey}")
    y = arr[ykey]
    ok = np.isfinite(y)
    for k, v in list(arr.items()):
        arr[k] = v[ok]
    y = y[ok]
    tr, va = time_split_by_source(arr["source"], arr["t_ps"])
    log(f"{kind} horizon={horizon}ps  n={len(y)}  train={len(tr)}  val={len(va)}")

    groups = {
        "A_lastframe": ("x", "y"),
        "B_static": STATIC,
        "C_trajstats": STATIC + TEMPORAL,
    }
    report = [
        f"HYBRID 02  {kind}  target={ykey}  val_frac=0.3 by source time",
        f"n={len(y)}  train={len(tr)}  val={len(va)}  y_mean={y.mean():.4f}  y_p90={np.percentile(y, 90):.4f}",
        "",
        "=== validation ranking (higher FEU better) ===",
    ]
    preds = {"y": y, "t_ps": arr["t_ps"], "source": arr["source"], "tr": tr, "va": va}

    # no-train baselines on val
    baselines = {
        "LAST": arr["last_score"],
        "LC": arr["inv_rho"] if "inv_rho" in arr else 1.0 / (arr["rho"] + 1e-6),
    }
    if kind == "cln":
        baselines["shortcut_-RMSD"] = -arr["x"]
    for name, score in baselines.items():
        m = ranking_metrics(score[va], y[va])
        report.append(fmt_metrics(f"base {name}", m))
        preds[f"base_{name}"] = score

    for gname, cols in groups.items():
        X = feats(kind, arr, cols)
        mu, sd = zscore_fit(X, tr)
        Xz = apply_z(X, mu, sd)
        w = ridge_fit(Xz, y, tr)
        pred = ridge_pred(Xz, w)
        m = ranking_metrics(pred[va], y[va])
        report.append(fmt_metrics(f"ridge {gname}", m))
        preds[f"ridge_{gname}"] = pred
        log(fmt_metrics(f"ridge {gname}", m))

    Xc = feats(kind, arr, STATIC + TEMPORAL)
    mu, sd = zscore_fit(Xc, tr)
    Xz = apply_z(Xc, mu, sd)
    mlp = train_mlp(Xz, y, tr, va, epochs, seed)
    if mlp is not None:
        m = ranking_metrics(mlp[va], y[va])
        report.append(fmt_metrics("mlp C_trajstats", m))
        preds["mlp_C"] = mlp
        log(fmt_metrics("mlp C_trajstats", m))
    else:
        report.append("mlp C_trajstats  skipped (no torch)")

    report.append("")
    report.append("=== val by source (ridge C) ===")
    pred_c = preds["ridge_C_trajstats"]
    for src in np.unique(arr["source"]):
        mask = (arr["source"][va] == src)
        if mask.sum() < 20:
            continue
        m = ranking_metrics(pred_c[va][mask], y[va][mask])
        report.append(fmt_metrics(f"  {src}", m))

    report.append("")
    report.append("Model D (GRU on raw windows) is deferred to hybrid02b.")
    report.append("Decision: C must beat B and LAST on Spearman / top10% enrich,")
    report.append("not just MSE, before we spend compute on sequences or new MD.")
    text = "\n".join(report) + "\n"
    out = hybrid_outdir()
    stem = f"{kind}_ablate_feu_{horizon}"
    (out / f"{stem}_report.txt").write_text(text, encoding="utf-8")
    (out / f"{kind}_ablate_feu_report.txt").write_text(text, encoding="utf-8")
    save = {k: v for k, v in preds.items() if k not in ("source",)}
    save["source"] = np.asarray(arr["source"])
    np.savez_compressed(out / f"{stem}.npz", **save)
    meta = {
        "kind": kind,
        "horizon": horizon,
        "n": int(len(y)),
        "n_train": int(len(tr)),
        "n_val": int(len(va)),
        "y_mean": float(y.mean()),
    }
    (out / f"{stem}_meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(text)
    return text


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--system", default="cln025", choices=("cln025", "ala2", "both"))
    p.add_argument("--horizon", type=int, default=200, choices=(200, 500, 1000))
    p.add_argument("--epochs", type=int, default=30)
    p.add_argument("--seed", type=int, default=0)
    args = p.parse_args(argv)
    try:
        log(f"HYBRID 02  FEU ablation  system={args.system}  H={args.horizon}ps")
        if args.system in ("cln025", "both"):
            run_one("cln", args.horizon, args.epochs, args.seed)
        if args.system in ("ala2", "both"):
            run_one("ala2", args.horizon, args.epochs, args.seed)
        return 0
    except TapsError as exc:
        log(str(exc), "ERROR")
        return 1


if __name__ == "__main__":
    sys.exit(main())
