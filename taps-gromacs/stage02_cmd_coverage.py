#!/usr/bin/env python3
"""
STAGE 02  |  大纲 §5.5 指标 / §6.2 cMD 基线（主体系）

用 STAGE 01 的 φ/ψ 算无偏长轨迹的 Ramachandran 覆盖与 basin 首次到达。
这是后面和 TAPS / Least-counts / LAST 对比时的 cMD 参照。

输入:  analysis/<system>/dihedrals.npz
输出:  analysis/<system>/cmd_report.txt
       analysis/<system>/coverage_vs_time.csv
       analysis/<system>/rama_hist.npz
       analysis/<system>/rama.png          (matplotlib 可用时)

上一阶段: python3 stage01_extract_dihedrals.py --system ala2_vacuum
下一阶段: python3 stage03_slice_windows.py
"""

from __future__ import annotations

import argparse
import csv
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
    get_spec,
    in_basin,
    load_dihedrals,
    log,
    to_bins,
)


def coverage_curve(phi: np.ndarray, psi: np.ndarray, nbins: int, every: int) -> tuple:
    i, j = to_bins(phi, psi, nbins)
    flat = i * nbins + j
    seen = np.zeros(nbins * nbins, dtype=np.bool_)
    times = []
    fracs = []
    nbin = nbins * nbins
    for end in range(every, len(flat) + 1, every):
        seen[flat[:end]] = True
        times.append(end)
        fracs.append(float(seen.sum()) / nbin)
    if times[-1] != len(flat):
        seen[flat] = True
        times.append(len(flat))
        fracs.append(float(seen.sum()) / nbin)
    return np.asarray(times), np.asarray(fracs)


def first_passage(phi: np.ndarray, psi: np.ndarray, t_ps: np.ndarray) -> dict:
    out = {}
    for name, center in BASINS.items():
        hit = np.flatnonzero(in_basin(phi, psi, center, BASIN_RADIUS))
        if hit.size:
            out[name] = {
                "hit": True,
                "frame": int(hit[0]),
                "t_ps": float(t_ps[hit[0]]),
                "n_frames": int(hit.size),
            }
        else:
            out[name] = {"hit": False, "frame": None, "t_ps": None, "n_frames": 0}
    return out


def write_rama_png(path: Path, phi: np.ndarray, psi: np.ndarray, nbins: int) -> bool:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return False
    fig, ax = plt.subplots(figsize=(6.2, 5.4))
    h = ax.hist2d(
        phi,
        psi,
        bins=nbins,
        range=[[-180, 180], [-180, 180]],
        cmap="magma",
        cmin=1,
    )
    fig.colorbar(h[3], ax=ax, label="frames")
    for name, (x, y) in BASINS.items():
        ax.scatter([x], [y], s=40, c="cyan", edgecolors="white", linewidths=0.6, zorder=3)
        ax.annotate(name, (x, y), textcoords="offset points", xytext=(4, 4), color="white", fontsize=8)
    ax.set_xlabel(r"$\phi$ (deg)")
    ax.set_ylabel(r"$\psi$ (deg)")
    ax.set_xlim(-180, 180)
    ax.set_ylim(-180, 180)
    ax.set_aspect("equal")
    ax.set_title("cMD Ramachandran")
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return True


def run(system: str, nbins: int, every_ps: float) -> None:
    spec = get_spec(system)
    data = load_dihedrals(spec)
    t_ps = data["t_ps"]
    phi = data["phi"]
    psi = data["psi"]
    dt = float(t_ps[1] - t_ps[0]) if len(t_ps) > 1 else 1.0
    every = max(1, int(round(every_ps / dt)))

    i, j = to_bins(phi, psi, nbins)
    hist = np.zeros((nbins, nbins), dtype=np.int64)
    np.add.at(hist, (i, j), 1)
    occupied = int((hist > 0).sum())
    total = nbins * nbins
    cov = occupied / total
    fpt = first_passage(phi, psi, t_ps)
    idx, frac = coverage_curve(phi, psi, nbins, every)

    out = spec.outdir
    np.savez_compressed(out / "rama_hist.npz", hist=hist, nbins=np.array(nbins), coverage=np.array(cov))

    csv_path = out / "coverage_vs_time.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["frame", "t_ps", "coverage"])
        for k, f in zip(idx, frac):
            w.writerow([int(k), float(t_ps[k - 1]), float(f)])

    lines = [
        f"system: {spec.key}",
        f"frames: {len(t_ps)}   dt: {dt:.3f} ps   length: {t_ps[-1]/1000:.3f} ns",
        f"Ramachandran bins: {nbins} x {nbins}  ({360/nbins:.1f} deg)",
        f"occupied bins: {occupied}/{total}  coverage={cov:.4f}",
        f"final coverage vs time written to {csv_path.name}",
        "",
        f"basin first-passage (radius {BASIN_RADIUS:.0f} deg):",
    ]
    for name, info in fpt.items():
        if info["hit"]:
            lines.append(
                f"  {name:<7s}  FPT={info['t_ps']/1000:.3f} ns  "
                f"frames_in_basin={info['n_frames']}"
            )
        else:
            lines.append(f"  {name:<7s}  NOT VISITED")
    report = out / "cmd_report.txt"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log(f"wrote {report.relative_to(ROOT)}")
    for line in lines:
        log(line)

    png = out / "rama.png"
    if write_rama_png(png, phi, psi, nbins):
        log(f"wrote {png.relative_to(ROOT)}")
    else:
        log("matplotlib not usable; skipped rama.png", "WARN")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--system", default="ala2_vacuum", choices=MAIN_KEYS)
    p.add_argument("--nbins", type=int, default=36, help="bins per φ/ψ axis (default 36 = 10 deg)")
    p.add_argument("--every-ps", type=float, default=1000.0, help="coverage curve stride in ps")
    p.add_argument("--check", action="store_true")
    args = p.parse_args(argv)
    try:
        spec = get_spec(args.system)
        log(f"STAGE 02  cMD coverage  system={args.system}")
        try:
            data = load_dihedrals(spec)
        except TapsError as exc:
            log(str(exc), "ERROR")
            return 2
        log(f"loaded {len(data['t_ps'])} frames from stage01")
        if args.check:
            log("check passed; no analysis started")
            return 0
        run(args.system, args.nbins, args.every_ps)
        return 0
    except TapsError as exc:
        log(str(exc), "ERROR")
        return 1


if __name__ == "__main__":
    sys.exit(main())
