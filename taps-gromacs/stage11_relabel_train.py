#!/usr/bin/env python3
"""
STAGE 11  |  方法修正：逃逸标签 + 200 ps 视野（先在 100 ns cMD 上验证）

上一轮失败原因（不要再重复那套默认超参）：
  1) 短轨迹 100 ps、窗口按帧算，horizon 实际只有 ~2 ps，标签几乎是局部晃动
  2) 时序和静态打平，因为静态也能预测“下一小步抖多远”
  3) 全部数据都在 φ<0，C7ax (φ≈+70) 从未靠近（最近 >109°）

本脚本只做便宜的验证，不跑新的 MD：
  把 100 ns cMD 按 1 ps 切 T=50 ps 窗口，预测未来 200 ps 是否离开当前 basin
  （或走出 >40°）。再训 Transformer，并和静态 MLP 对比。

输入:  analysis/<system>/dihedrals.npz
输出:  analysis/<system>/escape/
         escape_report.txt  windows.npz  labels.npz  sp_model.pt  sp_scores.npz
         ablate_report.txt  figures/

下一阶段: 若 escape 正例比例不是 0、且时序明显好于静态，再跑
  stage07 ... --label escape --short-ps 500 --extra-init .../c7ax.gro
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

import stage03_slice_windows as s03  # noqa: E402
import stage04_train_sp as s04  # noqa: E402
import stage10_ablate_static as s10  # noqa: E402
from taps_common import (  # noqa: E402
    BASINS,
    BASIN_RADIUS,
    MAIN_KEYS,
    TapsError,
    cv_dist,
    get_spec,
    in_basin,
    load_dihedrals,
    log,
    nearest_basin,
    spearman,
    to_bins,
    wrap_deg,
)


def escape_labels(phi, psi, starts, window, horizon, nbins: int) -> dict:
    i, j = to_bins(phi, psi, nbins)
    flat = i * nbins + j
    nbin = nbins * nbins
    hist = np.zeros(nbin, dtype=np.int64)
    y_esc = np.zeros(len(starts), dtype=np.float64)
    y_new = np.zeros(len(starts), dtype=np.float64)
    y_jump = np.zeros(len(starts), dtype=np.float64)
    cursor = 0
    for k, s in enumerate(starts):
        end = int(s + window - 1)
        while cursor <= end:
            hist[flat[cursor]] += 1
            cursor += 1
        fut_phi = phi[end + 1 : end + 1 + horizon]
        fut_psi = psi[end + 1 : end + 1 + horizon]
        fut_flat = flat[end + 1 : end + 1 + horizon]
        name = nearest_basin(float(phi[end]), float(psi[end]), BASIN_RADIUS)
        if name is None:
            d = cv_dist(fut_phi, fut_psi, phi[end], psi[end])
            y_esc[k] = float(np.clip((d.max() - 20.0) / 40.0, 0.0, 1.0))
        else:
            stayed = in_basin(fut_phi, fut_psi, BASINS[name], BASIN_RADIUS)
            y_esc[k] = float(1.0 - stayed.mean())
        y_new[k] = float((hist[fut_flat] == 0).mean())
        y_jump[k] = float(cv_dist(fut_phi, fut_psi, phi[end], psi[end]).mean())
    y = np.clip(0.7 * y_esc + 0.3 * y_new, 0.0, 1.0)
    return {"y": y, "y_escape": y_esc, "y_newbin": y_new, "y_jump_deg": y_jump}


def run(system: str, window: int, horizon: int, stride: int, nbins: int, epochs: int, seed: int) -> None:
    spec = get_spec(system)
    data = load_dihedrals(spec)
    phi = wrap_deg(data["phi"])
    psi = wrap_deg(data["psi"])
    t_ps = data["t_ps"]
    n = len(phi)
    last = n - window - horizon
    if last < 0:
        raise TapsError("trajectory too short for T + M")
    starts = np.arange(0, last + 1, stride, dtype=np.int64)
    X = np.stack([s03.encode_trig(phi, psi)[s : s + window] for s in starts], axis=0)
    labels = escape_labels(phi, psi, starts, window, horizon, nbins)
    y = labels["y"].astype(np.float32)
    log(
        f"windows={len(starts)}  T={window}ps  M={horizon}ps  "
        f"y_mean={y.mean():.3f}  escape={labels['y_escape'].mean():.3f}  "
        f"newbin={labels['y_newbin'].mean():.3f}  jump={labels['y_jump_deg'].mean():.1f}°"
    )
    pos = float((y > 0.5).mean())
    log(f"positive rate (y>0.5) = {pos:.3f}")

    out = spec.outdir / "escape"
    out.mkdir(parents=True, exist_ok=True)
    end = starts + window - 1
    np.savez_compressed(
        out / "windows.npz",
        X=X.astype(np.float32),
        starts=starts,
        end_idx=end,
        t_end_ps=t_ps[end],
        phi_end=phi[end],
        psi_end=psi[end],
        window=np.array(window),
        horizon=np.array(horizon),
        stride=np.array(stride),
    )
    np.savez_compressed(out / "labels.npz", **{k: np.asarray(v) for k, v in labels.items()})

    pack = {"X": X.astype(np.float32), "y": y}
    import stage07_multi_round as s07

    scores = s07.train_sp(pack, out, epochs, seed)
    np.savez_compressed(
        out / "sp_scores.npz",
        S_p=scores.astype(np.float32),
        y=y,
        end_idx=end,
        t_end_ps=t_ps[end],
        phi_end=phi[end],
        psi_end=psi[end],
    )

    static = s10.train_static(X[:, -1, :].astype(np.float32), y, epochs, seed)
    t_metrics = s10.temporal_metrics(scores.astype(np.float32), y, static["va_idx"])
    lines = [
        "STAGE 11 escape-label check on 100 ns cMD",
        f"T={window} ps   M={horizon} ps   stride={stride} ps   windows={len(starts)}",
        f"y_mean={y.mean():.3f}  escape={labels['y_escape'].mean():.3f}  "
        f"newbin={labels['y_newbin'].mean():.3f}  pos(y>0.5)={pos:.3f}",
        f"Spearman(S_p, y)         = {spearman(scores, y):.3f}",
        f"Spearman(S_p, escape)    = {spearman(scores, labels['y_escape']):.3f}",
        "",
        f"temporal  val_mse={t_metrics['val_mse']:.4f}  Spearman={t_metrics['val_spearman']:.3f}",
        f"static    val_mse={static['val_mse']:.4f}  Spearman={static['val_spearman']:.3f}",
        f"delta mse (static-temporal) = {static['val_mse'] - t_metrics['val_mse']:+.4f}",
    ]
    if t_metrics["val_mse"] < static["val_mse"] - 1e-4:
        lines.append("verdict: temporal now beats static — go to stage07 v2 campaigns.")
    else:
        lines.append("verdict: still tied/worse. Do not launch a 20 ns campaign until this flips.")
    (out / "escape_report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out / "ablate_report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out / "meta.json").write_text(json.dumps({"window": window, "horizon": horizon, "pos": pos}, indent=2) + "\n")
    for line in lines:
        log(line)

    # reuse stage09 map if matplotlib works
    try:
        import stage09_sp_ramachandran as s09

        plt = s09.try_mpl()
        if plt is not None:
            figdir = out / "figures"
            figdir.mkdir(exist_ok=True)
            s09.plot_sp_map(plt, figdir / "sp_on_rama.png", phi[end], psi[end], scores, [], nbins)
            log(f"wrote {(figdir / 'sp_on_rama.png').relative_to(ROOT)}")
    except Exception as exc:
        log(f"figure skipped: {exc}", "WARN")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--system", default="ala2_vacuum", choices=MAIN_KEYS)
    p.add_argument("--window", type=int, default=50, help="T in ps (1 ps/frame on cMD)")
    p.add_argument("--horizon", type=int, default=200, help="M in ps")
    p.add_argument("--stride", type=int, default=10)
    p.add_argument("--nbins", type=int, default=36)
    p.add_argument("--epochs", type=int, default=20)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--check", action="store_true")
    args = p.parse_args(argv)
    try:
        spec = get_spec(args.system)
        log(f"STAGE 11  escape relabel + train  system={args.system}")
        try:
            load_dihedrals(spec)
        except TapsError as exc:
            log(str(exc), "ERROR")
            return 2
        s04.require_torch()
        if args.check:
            log("check passed")
            return 0
        run(args.system, args.window, args.horizon, args.stride, args.nbins, args.epochs, args.seed)
        return 0
    except TapsError as exc:
        log(str(exc), "ERROR")
        return 1


if __name__ == "__main__":
    sys.exit(main())
