#!/usr/bin/env python3
"""
STAGE 09  |  大纲 §6.1 / §9.2(b)  S_p 是否学到动力学信号

把潜力分数铺在 Ramachandran 上，标出被选 seed，并看：
  - 高 S_p 是在转移走廊还是阱底 / 纯 outlier
  - seed 前一段是即将跨越还是原地振荡
  - S_p 与局部扩散、滞留时间的相关

默认读第一次闭环（analysis/<system>/sp_scores.npz）。
加 --tag 则读某个 campaign 的分数。

输入:  dihedrals.npz  windows.npz  labels.npz  sp_scores.npz  seeds_*.json
输出:  analysis/<system>/figures_sp/   或  campaigns/<tag>/figures_sp/

上一阶段: stage04 + stage05（已有即可跑；不依赖 stage07）
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
    BASIN_RADIUS,
    BASINS,
    MAIN_KEYS,
    TapsError,
    cv_dist,
    get_spec,
    in_basin,
    load_dihedrals,
    log,
    spearman,
    to_bins,
    wrap_deg,
)


def load_seeds(outdir: Path) -> list:
    files = sorted(outdir.glob("seeds_round*.json"))
    if not files and (outdir / "seeds_round00.json").exists():
        files = [outdir / "seeds_round00.json"]
    seeds = []
    for path in files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        seeds.extend(payload.get("seeds") or [])
    return seeds


def basin_or_corridor(phi, psi) -> str:
    for name, center in BASINS.items():
        if float(cv_dist(phi, psi, center[0], center[1])) <= BASIN_RADIUS:
            return name
    # C7eq ↔ C7ax barrier region (rough, for a readable map)
    if abs(phi) < 50 and abs(psi) < 80:
        return "corridor"
    return "other"


def dwell_frames(phi, psi, idx: int, radius: float = 20.0) -> int:
    """How long the trajectory stayed near frame idx, looking backward."""
    n = 1
    for k in range(idx - 1, -1, -1):
        if float(cv_dist(phi[k], psi[k], phi[idx], psi[idx])) > radius:
            break
        n += 1
    return n


def try_mpl():
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        return plt
    except Exception:
        return None


def plot_sp_map(plt, path, phi, psi, scores, seeds, nbins):
    i, j = to_bins(phi, psi, nbins)
    acc = np.zeros((nbins, nbins), dtype=np.float64)
    cnt = np.zeros((nbins, nbins), dtype=np.float64)
    np.add.at(acc, (i, j), scores)
    np.add.at(cnt, (i, j), 1)
    mean = np.full_like(acc, np.nan)
    ok = cnt > 0
    mean[ok] = acc[ok] / cnt[ok]
    fig, ax = plt.subplots(figsize=(6.4, 5.4))
    extent = [-180, 180, -180, 180]
    im = ax.imshow(mean.T, origin="lower", extent=extent, cmap="viridis", aspect="equal")
    fig.colorbar(im, ax=ax, label=r"$S_p$")
    for name, (x, y) in BASINS.items():
        ax.scatter([x], [y], s=36, c="white", edgecolors="black", zorder=3)
        ax.annotate(name, (x, y), xytext=(4, 4), textcoords="offset points", color="white", fontsize=8)
    if seeds:
        ax.scatter(
            [s["phi"] for s in seeds],
            [s["psi"] for s in seeds],
            s=50,
            c="red",
            marker="x",
            linewidths=1.4,
            label="seeds",
            zorder=4,
        )
        ax.legend(loc="upper right", frameon=False)
    ax.set_xlabel(r"$\phi$ (deg)")
    ax.set_ylabel(r"$\psi$ (deg)")
    ax.set_title(r"$S_p$ on Ramachandran")
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


def plot_seed_windows(plt, path, phi, psi, t_ps, seeds, half=50):
    n = max(1, len(seeds))
    cols = 4
    rows = int(np.ceil(n / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(3.2 * cols, 3.0 * rows), squeeze=False)
    for ax in axes.ravel():
        ax.set_xlim(-180, 180)
        ax.set_ylim(-180, 180)
        ax.set_aspect("equal")
        ax.grid(True, alpha=0.2)
    for k, seed in enumerate(seeds):
        ax = axes[k // cols][k % cols]
        frame = int(seed.get("frame", -1))
        if frame < 0:
            # fall back: nearest CV
            d = cv_dist(phi, psi, seed["phi"], seed["psi"])
            frame = int(np.argmin(d))
        a = max(0, frame - half)
        b = min(len(phi), frame + 1)
        ax.plot(phi[a:b], psi[a:b], color="0.6", lw=0.8)
        ax.scatter(phi[a:b], psi[a:b], c=np.linspace(0.2, 1, b - a), s=8, cmap="cividis")
        ax.scatter([seed["phi"]], [seed["psi"]], c="red", marker="x", s=40, zorder=3)
        tag = basin_or_corridor(seed["phi"], seed["psi"])
        ax.set_title(f"seed {seed.get('rank', k)}  {tag}", fontsize=9)
    fig.suptitle("Seed local path (backward 50 frames)", y=1.01)
    fig.tight_layout()
    fig.savefig(path, dpi=140, bbox_inches="tight")
    plt.close(fig)


def plot_corr(plt, path, x, y, xlabel, ylabel, title):
    fig, ax = plt.subplots(figsize=(4.6, 4.2))
    ax.scatter(x, y, s=6, alpha=0.25, c="#1f4e79")
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


def run(system: str, tag: str, nbins: int) -> None:
    spec = get_spec(system, tag=tag)
    src = get_spec(system)
    outdir = spec.outdir
    if not (outdir / "sp_scores.npz").exists():
        outdir = src.outdir
    dih = load_dihedrals(src)
    win_path = outdir / "windows.npz"
    lab_path = outdir / "labels.npz"
    sc_path = outdir / "sp_scores.npz"
    if not sc_path.exists() or not win_path.exists():
        raise TapsError(f"missing {sc_path} or windows.npz. Run stage04 first.")

    windows = np.load(win_path)
    scores = np.load(sc_path)["S_p"].astype(np.float64)
    labels = np.load(lab_path) if lab_path.exists() else None
    phi_e = wrap_deg(windows["phi_end"])
    psi_e = wrap_deg(windows["psi_end"])
    n = min(len(scores), len(phi_e))
    scores, phi_e, psi_e = scores[:n], phi_e[:n], psi_e[:n]
    seeds = load_seeds(outdir)

    figdir = outdir / "figures_sp"
    figdir.mkdir(parents=True, exist_ok=True)

    where = np.array([basin_or_corridor(p, q) for p, q in zip(phi_e, psi_e)])
    top = scores >= np.quantile(scores, 0.9)
    lines = [
        f"system={spec.key}  tag={tag or '(first loop)'}",
        f"windows={n}  S_p mean={scores.mean():.3f} std={scores.std():.3f}",
        "region counts (all windows / top-decile S_p):",
    ]
    for name in list(BASINS) + ["corridor", "other"]:
        all_n = int((where == name).sum())
        top_n = int(((where == name) & top).sum())
        lines.append(f"  {name:<9s}  all={all_n:5d}  top10%={top_n:5d}")
    if labels is not None and "y_diff_deg" in labels.files:
        y_diff = labels["y_diff_deg"][:n]
        rho_s = spearman(scores, y_diff)
        lines.append(f"Spearman(S_p, future CV jump) = {rho_s:.3f}")
    else:
        y_diff = None
        rho_s = float("nan")

    # dwell from the parent dihedral series at window end frames
    if "end_idx" in windows.files:
        dwell = np.array([dwell_frames(dih["phi"], dih["psi"], int(i)) for i in windows["end_idx"][:n]])
        rho_d = spearman(scores, 1.0 / dwell)
        lines.append(f"Spearman(S_p, 1/dwell)        = {rho_d:.3f}")
    else:
        dwell = None
        rho_d = float("nan")

    if seeds:
        lines.append("selected seeds:")
        for s in seeds:
            tag_s = basin_or_corridor(s["phi"], s["psi"])
            lines.append(
                f"  rank {s.get('rank', '?')}  φ={s['phi']:.1f} ψ={s['psi']:.1f}  "
                f"S_p={s.get('S_p', float('nan')):.3f}  region={tag_s}"
            )

    report = figdir / "sp_mechanistics.txt"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log(f"wrote {report.relative_to(ROOT)}")
    for line in lines:
        log(line)

    plt = try_mpl()
    if plt is None:
        log("matplotlib unavailable; skipped figures", "WARN")
        return
    plot_sp_map(plt, figdir / "sp_on_rama.png", phi_e, psi_e, scores, seeds, nbins)
    log(f"wrote {(figdir / 'sp_on_rama.png').relative_to(ROOT)}")
    if seeds:
        plot_seed_windows(plt, figdir / "seed_local_paths.png", dih["phi"], dih["psi"], dih["t_ps"], seeds)
        log(f"wrote {(figdir / 'seed_local_paths.png').relative_to(ROOT)}")
    if y_diff is not None:
        plot_corr(plt, figdir / "sp_vs_diffusion.png", scores, y_diff, r"$S_p$", "future CV jump (deg)", f"Spearman={rho_s:.3f}")
        log(f"wrote {(figdir / 'sp_vs_diffusion.png').relative_to(ROOT)}")
    if dwell is not None:
        plot_corr(plt, figdir / "sp_vs_dwell.png", scores, dwell, r"$S_p$", "dwell (frames)", f"Spearman(S_p, 1/dwell)={rho_d:.3f}")
        log(f"wrote {(figdir / 'sp_vs_dwell.png').relative_to(ROOT)}")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--system", default="ala2_vacuum", choices=MAIN_KEYS)
    p.add_argument("--tag", default="", help="optional campaign tag; default = first 01–06 loop")
    p.add_argument("--nbins", type=int, default=36)
    p.add_argument("--check", action="store_true")
    args = p.parse_args(argv)
    try:
        spec = get_spec(args.system, tag=args.tag)
        log(f"STAGE 09  S_p Ramachandran  system={args.system}  tag={args.tag or '(first loop)'}")
        sc = spec.outdir / "sp_scores.npz"
        if not sc.exists():
            sc = get_spec(args.system).outdir / "sp_scores.npz"
        if not sc.exists():
            log(f"missing {sc}. Run stage04 first.", "ERROR")
            return 2
        if args.check:
            log("check passed")
            return 0
        run(args.system, args.tag, args.nbins)
        return 0
    except TapsError as exc:
        log(str(exc), "ERROR")
        return 1


if __name__ == "__main__":
    sys.exit(main())
