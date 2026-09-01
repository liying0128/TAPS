#!/usr/bin/env python3
"""
STAGE 04  |  大纲 §5.3 时空模型与探索潜力分数 S_p

主体系：窗口已是 φ/ψ 的 sin/cos，空间侧用 Linear，时间侧用 TransformerEncoder。
监督目标来自 STAGE 03（未来走进低密度区 + 局部扩散）。输出标量 S_p ∈ (0,1)。

输入:  analysis/<system>/windows.npz
       analysis/<system>/labels.npz
输出:  analysis/<system>/sp_model.pt
       analysis/<system>/sp_model_meta.json
       analysis/<system>/sp_scores.npz
       analysis/<system>/train_log.txt

上一阶段: python3 stage03_slice_windows.py
下一阶段: python3 stage05_select_seeds.py
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

from taps_common import MAIN_KEYS, TapsError, get_spec, log  # noqa: E402


def require_torch():
    try:
        import torch
        import torch.nn as nn
        from torch.utils.data import DataLoader, TensorDataset
    except ImportError as exc:
        raise TapsError("stage04 needs torch. Install: python3 -m pip install torch") from exc
    return torch, nn, DataLoader, TensorDataset


def build_model(torch, nn, d_in: int, d_model: int, nhead: int, nlayers: int, dropout: float):
    class TemporalPotential(nn.Module):
        def __init__(self):
            super().__init__()
            self.in_proj = nn.Linear(d_in, d_model)
            layer = nn.TransformerEncoderLayer(
                d_model=d_model,
                nhead=nhead,
                dim_feedforward=d_model * 2,
                dropout=dropout,
                batch_first=True,
            )
            self.encoder = nn.TransformerEncoder(layer, num_layers=nlayers)
            self.head = nn.Sequential(
                nn.Linear(d_model, d_model),
                nn.ReLU(),
                nn.Linear(d_model, 1),
            )

        def forward(self, x):
            h = self.in_proj(x)
            h = self.encoder(h)
            logit = self.head(h[:, -1]).squeeze(-1)
            return torch.sigmoid(logit)

    return TemporalPotential()


def time_split(n: int, val_frac: float) -> tuple:
    n_val = max(1, int(round(n * val_frac)))
    n_train = n - n_val
    if n_train < 8:
        raise TapsError(f"not enough windows to train ({n})")
    return np.arange(0, n_train), np.arange(n_train, n)


def run(
    system: str,
    epochs: int,
    batch: int,
    lr: float,
    d_model: int,
    nhead: int,
    nlayers: int,
    val_frac: float,
    seed: int,
) -> None:
    torch, nn, DataLoader, TensorDataset = require_torch()
    spec = get_spec(system)
    win_path = spec.outdir / "windows.npz"
    lab_path = spec.outdir / "labels.npz"
    if not win_path.exists() or not lab_path.exists():
        raise TapsError(
            f"missing windows/labels. Run: python3 stage03_slice_windows.py --system {system}"
        )

    windows = np.load(win_path)
    labels = np.load(lab_path)
    X = windows["X"]
    y = labels["y"].astype(np.float32)
    if len(X) != len(y):
        raise TapsError(f"X/y length mismatch: {len(X)} vs {len(y)}")

    torch.manual_seed(seed)
    np.random.seed(seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    log(f"device={device}  windows={len(X)}  X={tuple(X.shape)}")

    tr_idx, va_idx = time_split(len(X), val_frac)
    X_t = torch.from_numpy(X)
    y_t = torch.from_numpy(y)
    train_loader = DataLoader(
        TensorDataset(X_t[tr_idx], y_t[tr_idx]),
        batch_size=batch,
        shuffle=True,
    )
    val_X = X_t[va_idx].to(device)
    val_y = y_t[va_idx].to(device)

    model = build_model(torch, nn, X.shape[-1], d_model, nhead, nlayers, dropout=0.1).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    loss_fn = nn.MSELoss()
    log_lines = []
    best_val = float("inf")
    best_state = None

    for epoch in range(1, epochs + 1):
        model.train()
        total = 0.0
        n_seen = 0
        for xb, yb in train_loader:
            xb = xb.to(device)
            yb = yb.to(device)
            pred = model(xb)
            loss = loss_fn(pred, yb)
            opt.zero_grad()
            loss.backward()
            opt.step()
            total += float(loss.item()) * len(xb)
            n_seen += len(xb)
        model.eval()
        with torch.no_grad():
            val_pred = model(val_X)
            val_loss = float(loss_fn(val_pred, val_y).item())
            val_mae = float((val_pred - val_y).abs().mean().item())
        train_loss = total / max(1, n_seen)
        line = f"epoch {epoch:03d}  train_mse={train_loss:.4f}  val_mse={val_loss:.4f}  val_mae={val_mae:.4f}"
        log(line)
        log_lines.append(line)
        if val_loss < best_val:
            best_val = val_loss
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}

    if best_state is not None:
        model.load_state_dict(best_state)
    model.eval()
    with torch.no_grad():
        scores = model(X_t.to(device)).cpu().numpy()

    out = spec.outdir
    ckpt = out / "sp_model.pt"
    torch.save(
        {
            "state_dict": model.state_dict(),
            "d_in": int(X.shape[-1]),
            "d_model": d_model,
            "nhead": nhead,
            "nlayers": nlayers,
        },
        ckpt,
    )
    meta = {
        "system": spec.key,
        "d_in": int(X.shape[-1]),
        "d_model": d_model,
        "nhead": nhead,
        "nlayers": nlayers,
        "window": int(windows["window"]),
        "epochs": epochs,
        "batch": batch,
        "lr": lr,
        "val_frac": val_frac,
        "best_val_mse": best_val,
        "device": str(device),
        "n_train": int(len(tr_idx)),
        "n_val": int(len(va_idx)),
        "score_mean": float(scores.mean()),
        "score_std": float(scores.std()),
    }
    (out / "sp_model_meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    np.savez_compressed(
        out / "sp_scores.npz",
        S_p=scores.astype(np.float32),
        y=y,
        end_idx=windows["end_idx"],
        t_end_ps=windows["t_end_ps"],
        phi_end=windows["phi_end"],
        psi_end=windows["psi_end"],
    )
    (out / "train_log.txt").write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    log(f"wrote {ckpt.relative_to(ROOT)}  best_val_mse={best_val:.4f}")
    log(f"S_p  mean={scores.mean():.3f}  std={scores.std():.3f}  min={scores.min():.3f}  max={scores.max():.3f}")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--system", default="ala2_vacuum", choices=MAIN_KEYS)
    p.add_argument("--epochs", type=int, default=20)
    p.add_argument("--batch", type=int, default=256)
    p.add_argument("--lr", type=float, default=1e-3)
    p.add_argument("--d-model", type=int, default=64)
    p.add_argument("--nhead", type=int, default=4)
    p.add_argument("--nlayers", type=int, default=2)
    p.add_argument("--val-frac", type=float, default=0.2)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--check", action="store_true")
    args = p.parse_args(argv)
    try:
        spec = get_spec(args.system)
        log(f"STAGE 04  train S_p  system={args.system}")
        win = spec.outdir / "windows.npz"
        lab = spec.outdir / "labels.npz"
        if not win.exists() or not lab.exists():
            log(f"missing {win} or {lab}. Run stage03 first.", "ERROR")
            return 2
        require_torch()
        if args.check:
            log("check passed; torch available, windows present")
            return 0
        run(
            args.system,
            args.epochs,
            args.batch,
            args.lr,
            args.d_model,
            args.nhead,
            args.nlayers,
            args.val_frac,
            args.seed,
        )
        return 0
    except TapsError as exc:
        log(str(exc), "ERROR")
        return 1


if __name__ == "__main__":
    sys.exit(main())
