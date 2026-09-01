#!/usr/bin/env python3
"""
HYBRID 01  |  Workflow §2–§3  离线候选 seed + FEU（不跑新 MD）

从已有 cMD / TAPS / LAST / Least-counts 轨迹切候选点，写静态特征、
短窗口时序统计、以及 200/500/1000 ps 的 FEU 分量。

标签不再用 “未来 RMSD 下降”。FEU = novelty / diversity / discovery / commitment。
novelty 不再是 “扫过未见 bin 的帧比例”，而是 rare × info-gain × persist。

  python3 hybrid01_build_candidates.py --check
  python3 hybrid01_build_candidates.py --system cln025
  python3 hybrid01_build_candidates.py --system ala2
  python3 hybrid01_build_candidates.py --system both

输出: analysis/hybrid/<system>_candidates.npz
      analysis/hybrid/<system>_candidates_meta.json
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

from hybrid_common import (  # noqa: E402
    ALA_NBINS,
    COMMIT_PS,
    FEU_WEIGHTS,
    FOLD_RMSD,
    ala_bins,
    cln_bins,
    density_score,
    feu_from_future,
    feu_score,
    hybrid_outdir,
    in_c7ax,
    last_frontier_2d,
    resample_linear,
    window_stats,
)
from taps_common import ANALYSIS, TapsError, log, wrap_deg  # noqa: E402

DT = 2.0
HIST_PS = (50.0, 100.0, 200.0)
HORIZONS = (200.0, 500.0, 1000.0)
STRIDE_PS = 10.0
NBINS = 24


def load_cln_source(tag: str):
    """tag: cmd | discover_taps | discover_last | discover_lc"""
    if tag == "cmd":
        path = ANALYSIS / "cln025_unfolded" / "cvs.npz"
        if not path.exists():
            raise TapsError(f"missing {path}")
        d = np.load(path)
        return [{"name": "cmd", "t_ps": d["t_ps"], "x": d["rmsd"], "y": d["rg"]}]
    pool = ANALYSIS / "cln025_unfolded" / "campaigns" / tag / "pool.json"
    if not pool.exists():
        raise TapsError(f"missing {pool}")
    segs = []
    for rec in json.loads(pool.read_text(encoding="utf-8")):
        name = rec["name"]
        if name == "cmd_init":
            src = ANALYSIS / "cln025_unfolded" / "cvs.npz"
            d = np.load(src)
            mask = d["t_ps"] <= 10000.0 + 1e-6
            segs.append({"name": "cmd_init", "t_ps": d["t_ps"][mask], "x": d["rmsd"][mask], "y": d["rg"][mask]})
            continue
        # rXX_sYY  (r01_s00 or r1_s0)
        parts = name.split("_")
        rnd, rank = parts[0][1:], parts[1][1:]
        npz = (
            ANALYSIS
            / "cln025_unfolded"
            / "campaigns"
            / tag
            / "adaptive"
            / f"round{int(rnd):02d}"
            / f"seed_{int(rank):02d}_cvs.npz"
        )
        if not npz.exists():
            continue
        d = np.load(npz)
        segs.append({"name": name, "t_ps": d["t_ps"], "x": d["rmsd"], "y": d["rg"]})
    if not segs:
        raise TapsError(f"no CLN segments for {tag}")
    return segs


def load_ala2_source(tag: str):
    if tag == "cmd":
        path = ANALYSIS / "ala2_vacuum" / "dihedrals.npz"
        d = np.load(path)
        return [{"name": "cmd", "t_ps": d["t_ps"], "x": wrap_deg(d["phi"]), "y": wrap_deg(d["psi"])}]
    camp = ANALYSIS / "ala2_vacuum" / "campaigns" / tag
    dih = camp / "dihedrals.npz"
    if dih.exists():
        d = np.load(dih)
        phi = wrap_deg(d["phi"])
        psi = wrap_deg(d["psi"])
        t = d["t_ps"] if "t_ps" in d.files else np.arange(len(phi), dtype=np.float64)
        return [{"name": tag, "t_ps": t, "x": phi, "y": psi}]
    raise TapsError(f"missing ala2 campaign dihedrals: {dih}")


def concat_resample(segs, kind: str):
    """Resample each segment to 2 ps, then concatenate with a running clock."""
    xs, ys, clocks, names = [], [], [], []
    clock = 0.0
    for s in segs:
        t, x, y = resample_linear(s["t_ps"], s["x"], s["y"], dt=DT)
        if kind == "ala2":
            x, y = wrap_deg(x), wrap_deg(y)
        n = len(t)
        if n < 2:
            continue
        dt = float(t[1] - t[0])
        length = float(t[-1] - t[0]) + dt
        clocks.append(clock + (t - t[0]))
        xs.append(x)
        ys.append(y)
        names.append(np.full(n, s["name"]))
        clock += length
    return {
        "t_ps": np.concatenate(clocks),
        "x": np.concatenate(xs),
        "y": np.concatenate(ys),
        "seg": np.concatenate(names),
    }


def build_one(kind: str, source: str, segs) -> dict:
    pack = concat_resample(segs, kind)
    t, x, y = pack["t_ps"], pack["x"], pack["y"]
    n = len(t)
    if kind == "cln":
        bi, bj = cln_bins(x, y, NBINS)
        target = x < FOLD_RMSD
    else:
        bi, bj = ala_bins(x, y, ALA_NBINS)
        target = in_c7ax(x, y)
    nbin = (NBINS if kind == "cln" else ALA_NBINS) ** 2
    flat = bi * (NBINS if kind == "cln" else ALA_NBINS) + bj

    hist_need = int(max(HIST_PS) / DT)
    horz_need = {h: int(h / DT) for h in HORIZONS}
    stride = int(STRIDE_PS / DT)
    last_start = n - hist_need - horz_need[200.0]
    if last_start < 0:
        raise TapsError(f"{source}: trajectory too short ({n} frames @ {DT} ps)")
    ends = np.arange(hist_need - 1, n - horz_need[200.0], stride, dtype=np.int64)

    rows = []
    xy = np.stack([x, y], axis=1)
    for end in ends:
        past = slice(0, end + 1)
        hist50 = slice(end - int(50 / DT) + 1, end + 1)
        hist100 = slice(end - int(100 / DT) + 1, end + 1)
        hist200 = slice(end - int(200 / DT) + 1, end + 1)
        s50 = window_stats(x[hist50], DT)
        s100 = window_stats(x[hist100], DT) if end + 1 >= int(100 / DT) else s50
        s200 = window_stats(x[hist200], DT) if end + 1 >= int(200 / DT) else s100
        sy50 = window_stats(y[hist50], DT)
        past_flat = flat[past]
        rho = density_score(past_flat, flat[end : end + 1], nbin)[0]
        last_sc = last_frontier_2d(xy[past], xy[end : end + 1])[0]
        rec = {
            "source": source,
            "t_ps": float(t[end]),
            "x": float(x[end]),
            "y": float(y[end]),
            "rho": float(rho),
            "inv_rho": float(1.0 / (rho + 1e-6)),
            "last_score": float(last_sc),
            "in_target": bool(target[end]),
            "vel_x_50": s50["vel"],
            "acc_x_50": s50["acc"],
            "msd_x_50": s50["msd"],
            "var_x_50": s50["var"],
            "persist_x_50": s50["persist"],
            "vel_y_50": sy50["vel"],
            "msd_x_100": s100["msd"],
            "msd_x_200": s200["msd"],
            "persist_x_200": s200["persist"],
        }
        for H in HORIZONS:
            nH = horz_need[H]
            if end + nH >= n:
                continue
            fut = slice(end + 1, end + 1 + nH)
            comp = feu_from_future(
                past_flat,
                flat[fut],
                target[fut],
                bool(target[end]),
                DT,
                COMMIT_PS,
            )
            rec[f"nov_{int(H)}"] = comp["novelty"]
            rec[f"nov_unseen_{int(H)}"] = comp["novelty_unseen"]
            rec[f"nov_rare_{int(H)}"] = comp["novelty_rare"]
            rec[f"nov_info_{int(H)}"] = comp["novelty_info"]
            rec[f"nov_persist_{int(H)}"] = comp["novelty_persist"]
            rec[f"div_{int(H)}"] = comp["diversity"]
            rec[f"disc_{int(H)}"] = comp["discovery"]
            rec[f"disc_commit_{int(H)}"] = comp["discovery_commit"]
            rec[f"comm_{int(H)}"] = comp["commitment"]
            rec[f"feu_{int(H)}"] = feu_score(comp)
            rec[f"feu_eq_{int(H)}"] = feu_score(comp, FEU_WEIGHTS["equal"])
            rec[f"feu_commit_{int(H)}"] = feu_score(comp, FEU_WEIGHTS["commit"])
        if "feu_200" in rec:
            rows.append(rec)
    return {"rows": rows, "n_frames": n, "n_cand": len(rows)}


def stack_rows(all_rows: list) -> dict:
    if not all_rows:
        raise TapsError("no candidates")
    keys = sorted({k for r in all_rows for k in r})
    out = {}
    for k in keys:
        if k == "source":
            out[k] = np.array([r.get(k, "") for r in all_rows])
            continue
        if k == "in_target":
            out[k] = np.array([bool(r.get(k, False)) for r in all_rows])
            continue
        out[k] = np.array([r[k] if k in r else np.nan for r in all_rows], dtype=np.float64)
    return out


def summarize(kind: str, arr: dict) -> str:
    lines = [f"HYBRID 01  {kind}  candidates={len(arr['t_ps'])}"]
    src, cnt = np.unique(arr["source"], return_counts=True)
    for s, c in zip(src, cnt):
        lines.append(f"  {s}: {c}")
    for H in (200, 500, 1000):
        key = f"feu_{H}"
        if key not in arr:
            continue
        y = arr[key]
        ok = np.isfinite(y)
        if not ok.any():
            continue
        yy = y[ok]
        disc_c = arr[f"disc_commit_{H}"][ok].mean() if f"disc_commit_{H}" in arr else float("nan")
        nov_u = arr[f"nov_unseen_{H}"][ok].mean() if f"nov_unseen_{H}" in arr else float("nan")
        lines.append(
            f"  FEU@{H}ps  n={int(ok.sum())}  mean={yy.mean():.3f}  "
            f"p90={np.percentile(yy, 90):.3f}  disc={arr[f'disc_{H}'][ok].mean():.3f}  "
            f"disc_commit={disc_c:.3f}  comm={arr[f'comm_{H}'][ok].mean():.3f}  "
            f"nov={arr[f'nov_{H}'][ok].mean():.3f}  nov_unseen={nov_u:.3f}"
        )
    # shortcut check: corr(x, feu) on CLN is RMSD vs FEU
    if "feu_200" in arr and np.isfinite(arr["feu_200"]).sum() > 20:
        m = np.isfinite(arr["feu_200"])
        c = float(np.corrcoef(arr["x"][m], arr["feu_200"][m])[0, 1])
        lines.append(f"  corr(x, FEU_200)={c:.3f}  (CLN: x=RMSD; ala2: x=phi)")
        c2 = float(np.corrcoef(arr["msd_x_50"][m], arr["feu_200"][m])[0, 1])
        lines.append(f"  corr(msd_x_50, FEU_200)={c2:.3f}")
    return "\n".join(lines) + "\n"


def run_system(kind: str) -> Path:
    out = hybrid_outdir()
    rows = []
    meta = {"kind": kind, "dt_ps": DT, "horizons_ps": HORIZONS, "hist_ps": HIST_PS}
    if kind == "cln":
        sources = [
            ("cmd", load_cln_source("cmd")),
            ("taps", load_cln_source("discover_taps")),
            ("last", load_cln_source("discover_last")),
            ("lc", load_cln_source("discover_lc")),
        ]
    else:
        sources = [("cmd", load_ala2_source("cmd"))]
        for tag in ("discover_taps", "discover_last", "discover_lc"):
            try:
                sources.append((tag.replace("discover_", ""), load_ala2_source(tag)))
            except TapsError as exc:
                log(str(exc), "WARN")
    for name, segs in sources:
        log(f"{kind}/{name}: {len(segs)} segments")
        built = build_one(kind, name, segs)
        log(f"  frames={built['n_frames']}  candidates={built['n_cand']}")
        rows.extend(built["rows"])
        meta.setdefault("sources", {})[name] = {"segments": len(segs), "candidates": built["n_cand"]}
    arr = stack_rows(rows)
    dest = out / f"{kind}_candidates.npz"
    np.savez_compressed(dest, **arr)
    text = summarize(kind, arr)
    (out / f"{kind}_candidates_meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    (out / f"{kind}_candidates_report.txt").write_text(text, encoding="utf-8")
    log(f"wrote {dest.relative_to(ROOT)}")
    print(text)
    return dest


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--system", default="cln025", choices=("cln025", "ala2", "both"))
    p.add_argument("--check", action="store_true")
    args = p.parse_args(argv)
    try:
        log(f"HYBRID 01  offline candidates + FEU  system={args.system}")
        if args.check:
            if args.system in ("cln025", "both"):
                path = ANALYSIS / "cln025_unfolded" / "cvs.npz"
                log(f"  cln cMD cvs: {path.exists()}  {path}")
            if args.system in ("ala2", "both"):
                path = ANALYSIS / "ala2_vacuum" / "dihedrals.npz"
                log(f"  ala2 cMD: {path.exists()}  {path}")
            log("check passed")
            return 0
        if args.system in ("cln025", "both"):
            run_system("cln")
        if args.system in ("ala2", "both"):
            run_system("ala2")
        return 0
    except TapsError as exc:
        log(str(exc), "ERROR")
        return 1


if __name__ == "__main__":
    sys.exit(main())
