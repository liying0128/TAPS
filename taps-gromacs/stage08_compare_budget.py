#!/usr/bin/env python3
"""
STAGE 08  |  大纲 §6.2  同预算对比：cMD vs TAPS vs Least-counts

用 stage01 的 100 ns cMD 截前 --budget-ns，对比各 campaign 的
覆盖曲线、C7ax / 各 basin FPT。不跑 MD。

输入:  analysis/<system>/dihedrals.npz
       analysis/<system>/campaigns/<tag>/history.json  （或 dihedrals.npz）
输出:  analysis/<system>/compare_<budget>ns/
         coverage_vs_time.csv
         compare_report.txt
         coverage.png

上一阶段: stage07（每个策略跑完一个 --tag）
下一阶段: 看报告；同时可跑 stage09 / stage10（不依赖本步）
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from taps_common import (  # noqa: E402
    ANALYSIS,
    BASINS,
    MAIN_KEYS,
    TapsError,
    basin_fpt_ps,
    get_spec,
    load_dihedrals,
    log,
    rama_coverage,
    to_bins,
)


def cmd_curve(phi, psi, t_ps, budget_ns: float, nbins: int, every_ps: float):
    cut = t_ps <= budget_ns * 1000.0 + 1e-6
    phi, psi, t_ps = phi[cut], psi[cut], t_ps[cut]
    i, j = to_bins(phi, psi, nbins)
    flat = i * nbins + j
    every = max(1, int(round(every_ps / max(1e-6, float(t_ps[1] - t_ps[0])))))
    seen = np.zeros(nbins * nbins, dtype=np.bool_)
    rows = []
    for end in range(every, len(flat) + 1, every):
        seen[flat[:end]] = True
        rows.append((float(t_ps[end - 1]) / 1000.0, float(seen.sum()) / seen.size))
    if not rows or rows[-1][0] < t_ps[-1] / 1000.0 - 1e-9:
        seen[flat] = True
        rows.append((float(t_ps[-1]) / 1000.0, float(seen.sum()) / seen.size))
    fpt = {name: basin_fpt_ps(phi, psi, t_ps, name) for name in BASINS}
    return rows, fpt, rama_coverage(phi, psi, nbins)


def campaign_curve(tag_dir: Path, nbins: int):
    hist_path = tag_dir / "history.json"
    dih_path = tag_dir / "dihedrals.npz"
    rows = []
    fpt = {name: None for name in BASINS}
    cov = None
    if hist_path.exists():
        history = json.loads(hist_path.read_text(encoding="utf-8"))
        for h in history:
            rows.append((float(h["sim_ns"]), float(h["coverage"])))
            if h.get("c7ax_fpt_ns") is not None and fpt["c7ax"] is None:
                fpt["c7ax"] = float(h["c7ax_fpt_ns"]) * 1000.0
        if history:
            cov = float(history[-1]["coverage"])
    if dih_path.exists():
        data = np.load(dih_path)
        phi, psi, t = data["phi"], data["psi"], data["t_ps"]
        cov = rama_coverage(phi, psi, nbins)
        for name in BASINS:
            hit = basin_fpt_ps(phi, psi, t, name)
            if hit is not None:
                fpt[name] = hit
    return rows, fpt, cov


def write_png(path: Path, series: dict) -> bool:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return False
    fig, ax = plt.subplots(figsize=(6.4, 4.2))
    for name, rows in series.items():
        if not rows:
            continue
        xs = [r[0] for r in rows]
        ys = [r[1] for r in rows]
        ax.plot(xs, ys, marker="o", ms=3, label=name)
    ax.set_xlabel("accumulated simulation time (ns)")
    ax.set_ylabel("Ramachandran coverage")
    ax.set_ylim(0, max(0.4, ax.get_ylim()[1]))
    ax.legend(frameon=False)
    ax.set_title("Matched-budget coverage")
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return True


def fmt_fpt(ps):
    if ps is None:
        return "NOT VISITED"
    return f"{ps/1000.0:.3f} ns"


def run(system: str, tags: list, budget_ns: float, nbins: int, every_ps: float) -> None:
    spec = get_spec(system)
    data = load_dihedrals(spec)
    out = ANALYSIS / system / f"compare_{budget_ns:g}ns"
    out.mkdir(parents=True, exist_ok=True)

    series = {}
    cmd_rows, cmd_fpt, cmd_cov = cmd_curve(data["phi"], data["psi"], data["t_ps"], budget_ns, nbins, every_ps)
    series["cMD"] = cmd_rows

    reports = [
        f"matched budget = {budget_ns:g} ns   bins = {nbins}x{nbins}",
        "",
        f"cMD  coverage={cmd_cov:.4f}",
    ]
    for name, ps in cmd_fpt.items():
        reports.append(f"  {name:<7s}  FPT={fmt_fpt(ps)}")

    for tag in tags:
        tag_dir = ANALYSIS / system / "campaigns" / tag
        if not tag_dir.exists():
            reports.append(f"\n{tag}: MISSING  ({tag_dir})")
            log(f"campaign {tag} not found", "WARN")
            continue
        rows, fpt, cov = campaign_curve(tag_dir, nbins)
        series[tag] = rows
        reports.append(f"\n{tag}  coverage={cov if cov is None else f'{cov:.4f}'}")
        for name, ps in fpt.items():
            reports.append(f"  {name:<7s}  FPT={fmt_fpt(ps)}")

    csv_path = out / "coverage_vs_time.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["method", "t_ns", "coverage"])
        for name, rows in series.items():
            for t_ns, cov in rows:
                w.writerow([name, f"{t_ns:.4f}", f"{cov:.6f}"])

    report = out / "compare_report.txt"
    report.write_text("\n".join(reports) + "\n", encoding="utf-8")
    log(f"wrote {report.relative_to(ROOT)}")
    for line in reports:
        log(line)
    png = out / "coverage.png"
    if write_png(png, series):
        log(f"wrote {png.relative_to(ROOT)}")
    else:
        log("matplotlib unavailable; skipped coverage.png", "WARN")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--system", default="ala2_vacuum", choices=MAIN_KEYS)
    p.add_argument("--campaign", action="append", dest="campaigns", default=None, help="repeatable tag")
    p.add_argument("--budget-ns", type=float, default=20.0)
    p.add_argument("--nbins", type=int, default=36)
    p.add_argument("--every-ps", type=float, default=500.0)
    p.add_argument("--check", action="store_true")
    args = p.parse_args(argv)
    tags = args.campaigns or ["taps_full", "least_counts"]
    try:
        spec = get_spec(args.system)
        log(f"STAGE 08  compare budget  system={args.system}  tags={tags}")
        try:
            load_dihedrals(spec)
        except TapsError as exc:
            log(str(exc), "ERROR")
            return 2
        if args.check:
            log("check passed")
            return 0
        run(args.system, tags, args.budget_ns, args.nbins, args.every_ps)
        return 0
    except TapsError as exc:
        log(str(exc), "ERROR")
        return 1


if __name__ == "__main__":
    sys.exit(main())
