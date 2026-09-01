#!/usr/bin/env python3
"""
STAGE 10  |  大纲 §6.3 / §9.2(a)  时序 vs 静态消融

同一个窗口标签，对比：
  temporal  = 现有 Transformer（看整段 T）
  static    = 只看最后一帧的 MLP

若时序没有明显更低的 val MSE / 更高的与标签 Spearman，
§4.3「从单帧转向轨迹片段」这条贡献就站不住，需要改特征或标签。

输入:  analysis/<system>/windows.npz  labels.npz
       analysis/<system>/sp_scores.npz   （已有 temporal 分数则直接比）
输出:  analysis/<system>/ablate_static/
         ablate_report.txt
         static_model.pt
         pred_scatter.png

上一阶段: stage03 + stage04（第一次闭环已有即可跑）
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

import stage04_train_sp as s04  # noqa: E402
from taps_common import MAIN_KEYS, TapsError, get_spec, log, spearman  # noqa: E402


def build_static(nn, d_in: int, hidden: int = 64):
    return nn.Sequential(
        nn.Linear(d_in, hidden),
        nn.ReLU(),
        nn.Linear(hidden, hidden),
        nn.ReLU(),
        nn.Linear(hidden, 1),
        nn.Sigmoid(),
    )


def train_static(X_last, y, epochs, seed):
    torch, nn, DataLoader, TensorDataset = s04.require_torch()
    torch.manual_seed(seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    tr_idx, va_idx = s04.time_split(len(X_last), 0.2)
    X_t = torch.from_numpy(X_last)
    y_t = torch.from_numpy(y)
    loader = DataLoader(TensorDataset(X_t[tr_idx], y_t[tr_idx]), batch_size=256, shuffle=True)
    model = build_static(nn, X_last.shape[-1]).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    loss_fn = nn.MSELoss()
    best, best_state = float("inf"), None
    val_X, val_y = X_t[va_idx].to(device), y_t[va_idx].to(device)
    log_lines = []
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
            vp = model(val_X).squeeze(-1)
            val = float(loss_fn(vp, val_y).item())
            mae = float((vp - val_y).abs().mean().item())
        line = f"epoch {epoch:03d}  val_mse={val:.4f}  val_mae={mae:.4f}"
        log_lines.append(line)
        if epoch == 1 or epoch == epochs or epoch % 5 == 0:
            log("  static " + line)
        if val < best:
            best = val
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
    if best_state:
        model.load_state_dict(best_state)
    model.eval()
    with torch.no_grad():
        pred_all = model(X_t.to(device)).squeeze(-1).cpu().numpy()
        val_pred = model(val_X).squeeze(-1).cpu().numpy()
        val_true = val_y.cpu().numpy()
    return {
        "model": model,
        "pred_all": pred_all,
        "val_mse": float(np.mean((val_pred - val_true) ** 2)),
        "val_mae": float(np.mean(np.abs(val_pred - val_true))),
        "val_spearman": spearman(val_pred, val_true),
        "tr_idx": tr_idx,
        "va_idx": va_idx,
        "log_lines": log_lines,
        "best_val": best,
    }


def temporal_metrics(scores, y, va_idx):
    pred = scores[va_idx]
    true = y[va_idx]
    return {
        "val_mse": float(np.mean((pred - true) ** 2)),
        "val_mae": float(np.mean(np.abs(pred - true))),
        "val_spearman": spearman(pred, true),
    }


def write_scatter(path, y, pred_t, pred_s):
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return False
    fig, axes = plt.subplots(1, 2, figsize=(8.2, 3.8), sharex=True, sharey=True)
    for ax, pred, title in (
        (axes[0], pred_t, "temporal Transformer"),
        (axes[1], pred_s, "static last-frame MLP"),
    ):
        ax.scatter(y, pred, s=5, alpha=0.25)
        lim = [0, max(1.0, float(np.max(y)), float(np.max(pred)))]
        ax.plot(lim, lim, color="0.5", lw=0.8)
        ax.set_title(title)
        ax.set_xlabel("label y")
        ax.set_ylabel("predicted S_p")
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return True


def run(system: str, tag: str, epochs: int, seed: int) -> None:
    spec = get_spec(system, tag=tag)
    src = spec if (spec.outdir / "windows.npz").exists() else get_spec(system)
    win = np.load(src.outdir / "windows.npz")
    lab = np.load(src.outdir / "labels.npz")
    X = win["X"]
    y = lab["y"].astype(np.float32)
    X_last = X[:, -1, :].astype(np.float32)
    log(f"windows={len(X)}  feature last-frame={X_last.shape}")

    static = train_static(X_last, y, epochs, seed)
    scores_path = src.outdir / "sp_scores.npz"
    if scores_path.exists():
        temporal = np.load(scores_path)["S_p"].astype(np.float32)
        if len(temporal) != len(y):
            raise TapsError("sp_scores length != labels; rerun stage04 on the same windows")
        t_metrics = temporal_metrics(temporal, y, static["va_idx"])
    else:
        temporal = None
        t_metrics = None
        log("no sp_scores.npz; only static model will be reported", "WARN")

    out = src.outdir / "ablate_static"
    out.mkdir(parents=True, exist_ok=True)
    s04.require_torch()
    import torch

    torch.save({"state_dict": static["model"].state_dict(), "kind": "static_mlp"}, out / "static_model.pt")
    np.savez_compressed(out / "static_scores.npz", S_p=static["pred_all"], y=y)

    lines = [
        "ablation: temporal Transformer vs static last-frame MLP",
        f"system={src.key}  n={len(y)}  val_frac=0.2 (time split)",
        "",
        "static MLP",
        f"  val_mse={static['val_mse']:.4f}  val_mae={static['val_mae']:.4f}  "
        f"Spearman={static['val_spearman']:.3f}",
    ]
    if t_metrics:
        lines += [
            "temporal Transformer (existing stage04 scores)",
            f"  val_mse={t_metrics['val_mse']:.4f}  val_mae={t_metrics['val_mae']:.4f}  "
            f"Spearman={t_metrics['val_spearman']:.3f}",
            "",
            f"delta val_mse (static - temporal) = {static['val_mse'] - t_metrics['val_mse']:+.4f}",
            f"delta Spearman (temporal - static) = {t_metrics['val_spearman'] - static['val_spearman']:+.3f}",
        ]
        if t_metrics["val_mse"] < static["val_mse"] - 1e-4:
            lines.append("verdict: temporal is better on held-out windows.")
        elif static["val_mse"] < t_metrics["val_mse"] - 1e-4:
            lines.append("verdict: static is better or equal — time module is not helping yet.")
        else:
            lines.append("verdict: essentially tied. Need a stronger temporal signal / label.")
    (out / "ablate_report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out / "ablate_meta.json").write_text(
        json.dumps(
            {
                "static": {k: static[k] for k in ("val_mse", "val_mae", "val_spearman", "best_val")},
                "temporal": t_metrics,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    log(f"wrote {(out / 'ablate_report.txt').relative_to(ROOT)}")
    for line in lines:
        log(line)
    if temporal is not None:
        if write_scatter(out / "pred_scatter.png", y, temporal, static["pred_all"]):
            log(f"wrote {(out / 'pred_scatter.png').relative_to(ROOT)}")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--system", default="ala2_vacuum", choices=MAIN_KEYS)
    p.add_argument("--tag", default="", help="optional campaign tag")
    p.add_argument("--epochs", type=int, default=20)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--check", action="store_true")
    args = p.parse_args(argv)
    try:
        spec = get_spec(args.system, tag=args.tag)
        src = spec if (spec.outdir / "windows.npz").exists() else get_spec(args.system)
        log(f"STAGE 10  temporal vs static  system={args.system}")
        if not (src.outdir / "windows.npz").exists():
            log("missing windows.npz; run stage03 first", "ERROR")
            return 2
        s04.require_torch()
        if args.check:
            log("check passed")
            return 0
        run(args.system, args.tag, args.epochs, args.seed)
        return 0
    except TapsError as exc:
        log(str(exc), "ERROR")
        return 1


if __name__ == "__main__":
    sys.exit(main())
