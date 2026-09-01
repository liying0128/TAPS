#!/usr/bin/env python3
"""
STAGE 03  |  大纲 §5.1 / §5.2 轨迹切片 + §5.3 监督标签

把 φ/ψ 序列切成长度 T 的窗口，并用“未来 M 步是否走进当时的低密度区”
加上局部扩散，做成 S_p 的可计算代理标签（因果密度，不偷看窗口之后的历史）。

输入:  analysis/<system>/dihedrals.npz
输出:  analysis/<system>/windows.npz
       analysis/<system>/labels.npz

上一阶段: python3 stage02_cmd_coverage.py   （本步只依赖 stage01 的 npz）
下一阶段: python3 stage04_train_sp.py
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

from taps_common import (  # noqa: E402
    MAIN_KEYS,
    TapsError,
    circ_diff,
    get_spec,
    load_dihedrals,
    log,
    to_bins,
    wrap_deg,
)


def window_indices(n: int, window: int, horizon: int, stride: int) -> np.ndarray:
    last_start = n - window - horizon
    if last_start < 0:
        raise TapsError(
            f"trajectory too short ({n} frames) for window={window} horizon={horizon}"
        )
    return np.arange(0, last_start + 1, stride, dtype=np.int64)


def encode_trig(phi: np.ndarray, psi: np.ndarray) -> np.ndarray:
    phi = np.deg2rad(wrap_deg(phi))
    psi = np.deg2rad(wrap_deg(psi))
    return np.stack([np.sin(phi), np.cos(phi), np.sin(psi), np.cos(psi)], axis=-1)


def label_windows(
    phi: np.ndarray,
    psi: np.ndarray,
    starts: np.ndarray,
    window: int,
    horizon: int,
    nbins: int,
    rare_frac: float,
) -> dict:
    i, j = to_bins(phi, psi, nbins)
    flat = i * nbins + j
    nbin = nbins * nbins
    hist = np.zeros(nbin, dtype=np.int64)

    n_w = len(starts)
    y_reach = np.zeros(n_w, dtype=np.float64)
    y_diff = np.zeros(n_w, dtype=np.float64)
    rho_now = np.zeros(n_w, dtype=np.float64)
    cursor = 0

    for k, s in enumerate(starts):
        end = int(s + window - 1)
        while cursor <= end:
            hist[flat[cursor]] += 1
            cursor += 1
        total = max(1, int(hist.sum()))
        rare_cut = max(1.0, rare_frac * (total / nbin))
        future = flat[end + 1 : end + 1 + horizon]
        past_count = hist[future]
        y_reach[k] = float((past_count < rare_cut).mean())
        dphi = circ_diff(phi[end + 1 : end + 1 + horizon], phi[end])
        dpsi = circ_diff(psi[end + 1 : end + 1 + horizon], psi[end])
        y_diff[k] = float(np.hypot(dphi, dpsi).mean())
        rho_now[k] = float(hist[flat[end]]) / total

    y_diff_n = np.clip(y_diff / 90.0, 0.0, 1.0)
    y = 0.5 * y_reach + 0.5 * y_diff_n
    return {
        "y": y,
        "y_reach": y_reach,
        "y_diff_deg": y_diff,
        "rho_now": rho_now,
    }


def run(system: str, window: int, horizon: int, stride: int, nbins: int, rare_frac: float) -> None:
    spec = get_spec(system)
    data = load_dihedrals(spec)
    phi = data["phi"]
    psi = data["psi"]
    t_ps = data["t_ps"]
    starts = window_indices(len(phi), window, horizon, stride)
    log(f"{spec.key}: {len(phi)} frames -> {len(starts)} windows  T={window} M={horizon} stride={stride}")

    feats = encode_trig(phi, psi)
    X = np.stack([feats[s : s + window] for s in starts], axis=0)
    labels = label_windows(phi, psi, starts, window, horizon, nbins, rare_frac)
    end_idx = starts + window - 1

    out = spec.outdir
    np.savez_compressed(
        out / "windows.npz",
        X=X.astype(np.float32),
        starts=starts,
        end_idx=end_idx,
        t_end_ps=t_ps[end_idx],
        phi_end=phi[end_idx],
        psi_end=psi[end_idx],
        window=np.array(window),
        horizon=np.array(horizon),
        stride=np.array(stride),
    )
    np.savez_compressed(out / "labels.npz", **{k: np.asarray(v) for k, v in labels.items()})
    meta = {
        "system": spec.key,
        "n_windows": int(len(starts)),
        "window": window,
        "horizon": horizon,
        "stride": stride,
        "nbins": nbins,
        "rare_frac": rare_frac,
        "y_mean": float(labels["y"].mean()),
        "y_reach_mean": float(labels["y_reach"].mean()),
        "y_diff_mean_deg": float(labels["y_diff_deg"].mean()),
        "feature": "sin/cos of phi,psi  (T x 4)",
        "target": "0.5*P(future in currently-rare bin) + 0.5*clip(mean CV jump / 90 deg)",
    }
    (out / "windows_meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    log(f"wrote { (out / 'windows.npz').relative_to(ROOT) }  X={tuple(X.shape)}")
    log(
        f"label y: mean={meta['y_mean']:.3f}  "
        f"reach={meta['y_reach_mean']:.3f}  "
        f"diff={meta['y_diff_mean_deg']:.1f} deg"
    )


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--system", default="ala2_vacuum", choices=MAIN_KEYS)
    p.add_argument("--window", type=int, default=50, help="window length T in frames")
    p.add_argument("--horizon", type=int, default=50, help="future length M in frames")
    p.add_argument("--stride", type=int, default=10)
    p.add_argument("--nbins", type=int, default=36)
    p.add_argument("--rare-frac", type=float, default=0.25, help="bin is rare if count < this × mean count")
    p.add_argument("--check", action="store_true")
    args = p.parse_args(argv)
    try:
        spec = get_spec(args.system)
        log(f"STAGE 03  slice windows  system={args.system}")
        try:
            data = load_dihedrals(spec)
        except TapsError as exc:
            log(str(exc), "ERROR")
            return 2
        log(f"loaded {len(data['t_ps'])} frames from stage01")
        if args.check:
            log("check passed; no slicing started")
            return 0
        run(args.system, args.window, args.horizon, args.stride, args.nbins, args.rare_frac)
        return 0
    except TapsError as exc:
        log(str(exc), "ERROR")
        return 1


if __name__ == "__main__":
    sys.exit(main())
