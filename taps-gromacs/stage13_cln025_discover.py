#!/usr/bin/env python3
"""
STAGE 13  |  CLN025 展开态：发现设定 + LAST + 1 ns 短轨迹

cMD 对照用展开态 100 ns 前缀（不从 native 灌折叠结构）。
CV 是 CA-RMSD(to native) 和 Rg，不再用二肽 φ/ψ。
对照：TAPS / LAST / Least-counts / 同预算 cMD。

标签：未来 RMSD 是否下降（朝折叠推进）+ 是否走进 (RMSD, Rg) 空 bin。

输入:  systems/chignolin_cln025/water_unfolded/runs/md_100ns.{xtc,tpr,gro}
       systems/chignolin_cln025/gmx_common/protein.gro
输出:  analysis/cln025_unfolded/cvs.npz
       analysis/cln025_unfolded/campaigns/<prefix>_taps|last|lc/
       analysis/cln025_unfolded/discover_last/report.txt

  python3 stage13_cln025_discover.py --check
  python3 stage13_cln025_discover.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import stage06_adaptive_round as s06  # noqa: E402
import stage07_multi_round as s07  # noqa: E402
from taps_common import (  # noqa: E402
    ANALYSIS,
    TapsError,
    dump_frame,
    find_gmx,
    log,
    parse_xvg,
    run_gmx,
)

SHORT_MDP = "md_short_1ns.mdp"
METHOD_TAGS = {
    "taps": "taps",
    "last": "last",
    "density": "lc",
    "random": "random",
    "moas": "static",
    "dynamic": "dynamic",
    "pareto": "pareto",
}
NATIVE_GRO = ROOT / "systems/chignolin_cln025/gmx_common/protein.gro"
UNF_DIR = ROOT / "systems/chignolin_cln025/water_unfolded"
PROD_XTC = UNF_DIR / "runs/md_100ns.xtc"
PROD_TPR = UNF_DIR / "runs/md_100ns.tpr"
PROD_GRO = UNF_DIR / "runs/md_100ns.gro"
PROD_LOG = UNF_DIR / "runs/md_100ns.log"
RMSD_MAX = 1.60
RG_MIN, RG_MAX = 0.45, 1.70
FOLD_RMSD = 0.25


@dataclass(frozen=True)
class ClnSpec:
    key: str = "cln025_unfolded"
    tag: str = ""

    @property
    def workdir(self) -> Path:
        return UNF_DIR

    @property
    def outdir(self) -> Path:
        if self.tag:
            return ANALYSIS / self.key / "campaigns" / self.tag
        return ANALYSIS / self.key

    @property
    def adaptive_root(self) -> Path:
        if self.tag:
            return self.workdir / "adaptive" / "campaigns" / self.tag
        return self.workdir / "adaptive"


def ca_indices(gro: Path) -> list:
    ids = []
    lines = gro.read_text(encoding="utf-8", errors="replace").splitlines()
    natom = int(lines[1])
    for line in lines[2 : 2 + natom]:
        name = line[10:15].strip()
        idx = int(line[15:20])
        if name == "CA":
            ids.append(idx)
    if len(ids) < 8:
        raise TapsError(f"found {len(ids)} CA atoms in {gro}")
    return ids


def write_ca_ndx(path: Path, gro: Path) -> None:
    ids = ca_indices(gro)
    path.write_text("[ CA ]\n" + " ".join(str(i) for i in ids) + "\n", encoding="utf-8")


def extract_cvs(tpr: Path, xtc: Path, dest_npz: Path, scratch: Path) -> dict:
    dest_npz.parent.mkdir(parents=True, exist_ok=True)
    scratch.mkdir(parents=True, exist_ok=True)
    gmx = find_gmx()
    prot_xtc = scratch / "prot.xtc"
    rmsd_xvg = scratch / "rmsd.xvg"
    rg_xvg = scratch / "rg.xvg"
    ca_ndx = scratch / "ca.ndx"
    write_ca_ndx(ca_ndx, NATIVE_GRO)
    run_gmx(
        [gmx, "trjconv", "-s", str(tpr), "-f", str(xtc), "-o", str(prot_xtc), "-pbc", "mol", "-center"],
        cwd=scratch,
        stdin_text="Protein\nProtein\n",
    )
    run_gmx(
        [gmx, "rms", "-s", str(NATIVE_GRO), "-f", str(prot_xtc), "-n", str(ca_ndx), "-o", str(rmsd_xvg)],
        cwd=scratch,
        stdin_text="CA\nCA\n",
    )
    run_gmx(
        [gmx, "gyrate", "-s", str(NATIVE_GRO), "-f", str(prot_xtc), "-o", str(rg_xvg)],
        cwd=scratch,
        stdin_text="System\n",
    )
    rmsd = parse_xvg(rmsd_xvg)
    rg = parse_xvg(rg_xvg)
    n = min(len(rmsd), len(rg))
    pack = {
        "t_ps": rmsd[:n, 0].astype(np.float64),
        "rmsd": rmsd[:n, 1].astype(np.float64),
        "rg": rg[:n, 1].astype(np.float64),
    }
    np.savez_compressed(dest_npz, **pack)
    return pack


def resample_2ps(t_ps, rmsd, rg):
    t_ps = np.asarray(t_ps, dtype=np.float64)
    if len(t_ps) < 2:
        return t_ps, np.asarray(rmsd), np.asarray(rg)
    t0, t1 = float(t_ps[0]), float(t_ps[-1])
    t_new = np.arange(t0, t1 + 1e-9, 2.0)
    return (
        t_new,
        np.interp(t_new, t_ps, rmsd),
        np.interp(t_new, t_ps, rg),
    )


def to_bins_rect(rmsd, rg, nbins: int):
    i = np.floor(np.clip(rmsd, 0.0, RMSD_MAX) / RMSD_MAX * nbins).astype(np.int64)
    i = np.clip(i, 0, nbins - 1)
    j = np.floor(np.clip(rg - RG_MIN, 0.0, RG_MAX - RG_MIN) / (RG_MAX - RG_MIN) * nbins).astype(np.int64)
    j = np.clip(j, 0, nbins - 1)
    return i, j


def coverage_rect(rmsd, rg, nbins: int) -> float:
    i, j = to_bins_rect(rmsd, rg, nbins)
    return len(set(zip(i.tolist(), j.tolist()))) / float(nbins * nbins)


def density_at(rmsd_all, rg_all, rmsd_q, rg_q, nbins: int):
    i, j = to_bins_rect(rmsd_all, rg_all, nbins)
    hist = np.zeros((nbins, nbins), dtype=np.float64)
    np.add.at(hist, (i, j), 1)
    hist /= max(1.0, hist.sum())
    iq, jq = to_bins_rect(rmsd_q, rg_q, nbins)
    return hist[iq, jq]


def greedy_diverse(rmsd, rg, score, n_seeds: int, min_nm: float) -> list:
    order = np.argsort(-np.asarray(score))
    picked = []
    for idx in order:
        i = int(idx)
        if all(float(np.hypot(rmsd[i] - rmsd[j], rg[i] - rg[j])) >= min_nm for j in picked):
            picked.append(i)
        if len(picked) >= n_seeds:
            break
    return picked


def encode_cv(rmsd, rg) -> np.ndarray:
    return np.stack(
        [
            np.asarray(rmsd, dtype=np.float64) / 1.20,
            (np.asarray(rg, dtype=np.float64) - 0.70) / 0.60,
            np.exp(-np.asarray(rmsd, dtype=np.float64) / 0.30),
        ],
        axis=-1,
    ).astype(np.float32)


def fold_labels(rmsd, rg, starts, window, horizon, nbins: int) -> dict:
    i, j = to_bins_rect(rmsd, rg, nbins)
    flat = i * nbins + j
    hist = np.zeros(nbins * nbins, dtype=np.int64)
    y_fold = np.zeros(len(starts), dtype=np.float64)
    y_new = np.zeros(len(starts), dtype=np.float64)
    y_drop = np.zeros(len(starts), dtype=np.float64)
    cursor = 0
    for k, s in enumerate(starts):
        end = int(s + window - 1)
        while cursor <= end:
            hist[flat[cursor]] += 1
            cursor += 1
        fut = rmsd[end + 1 : end + 1 + horizon]
        fut_flat = flat[end + 1 : end + 1 + horizon]
        if fut.size:
            drop = float(rmsd[end] - fut.min())
            y_drop[k] = drop
            y_fold[k] = float(np.clip(drop / 0.30, 0.0, 1.0))
            if float(fut.min()) < FOLD_RMSD:
                y_fold[k] = max(y_fold[k], 1.0)
            y_new[k] = float((hist[fut_flat] == 0).mean())
    y = np.clip(0.65 * y_fold + 0.35 * y_new, 0.0, 1.0)
    return {"y": y, "y_fold": y_fold, "y_newbin": y_new, "y_drop": y_drop}


def last_frontier_scores(rmsd_all, rg_all, rmsd_q, rg_q, nbins: int = 24) -> np.ndarray:
    z = np.stack([rmsd_all, rg_all], axis=1)
    zq = np.stack([rmsd_q, rg_q], axis=1)
    lo = z.min(axis=0)
    hi = z.max(axis=0)
    span = np.maximum(hi - lo, 1e-6)
    lo = lo - 0.05 * span
    hi = hi + 0.05 * span
    hist, xedges, yedges = np.histogram2d(z[:, 0], z[:, 1], bins=nbins, range=[[lo[0], hi[0]], [lo[1], hi[1]]])
    occ = hist > 0
    pad = np.pad(occ, 1, constant_values=False)
    empty_n = (~pad[:-2, 1:-1]) | (~pad[2:, 1:-1]) | (~pad[1:-1, :-2]) | (~pad[1:-1, 2:])
    frontier = occ & empty_n
    iq = np.clip(np.digitize(zq[:, 0], xedges) - 1, 0, nbins - 1)
    jq = np.clip(np.digitize(zq[:, 1], yedges) - 1, 0, nbins - 1)
    radius = np.linalg.norm(zq - z.mean(axis=0), axis=1)
    radius = radius / (float(radius.max()) + 1e-12)
    lat_rho = hist[iq, jq]
    lat_rho = lat_rho / (float(lat_rho.max()) + 1e-12)
    on_rim = frontier[iq, jq].astype(np.float64)
    return 1.5 * on_rim + radius * (1.0 - 0.5 * lat_rho)


def concat_pool(segments: list) -> dict:
    rmsd = np.concatenate([s["rmsd"] for s in segments])
    rg = np.concatenate([s["rg"] for s in segments])
    t_local = np.concatenate([s["t_ps"] for s in segments])
    seg_id = np.concatenate([np.full(len(s["rmsd"]), i, dtype=np.int32) for i, s in enumerate(segments)])
    accum = []
    clock = 0.0
    for s in segments:
        n = len(s["t_ps"])
        if n == 0:
            continue
        dt = float(s["t_ps"][1] - s["t_ps"][0]) if n > 1 else 1.0
        length = float(s["t_ps"][-1] - s["t_ps"][0]) + dt
        accum.append(clock + s["t_ps"] - float(s["t_ps"][0]))
        clock += length
    t_accum = np.concatenate(accum) if accum else np.zeros(0)
    return {
        "rmsd": rmsd,
        "rg": rg,
        "t_local": t_local,
        "t_accum_ps": t_accum,
        "seg_id": seg_id,
        "sim_ns": clock / 1000.0,
    }


def slice_cmd_init(init_ns: float) -> dict:
    path = ANALYSIS / "cln025_unfolded" / "cvs.npz"
    data = np.load(path)
    t_ps = data["t_ps"]
    mask = t_ps <= init_ns * 1000.0 + 1e-6
    if int(mask.sum()) < 40:
        raise TapsError(f"init-ns={init_ns} only has {int(mask.sum())} CV frames")
    return {
        "name": "cmd_init",
        "t_ps": t_ps[mask],
        "rmsd": data["rmsd"][mask],
        "rg": data["rg"][mask],
        "xtc": str(PROD_XTC),
        "tpr": str(PROD_TPR),
    }


def load_segment_npz(path: Path, name: str, xtc: Path, tpr: Path) -> dict:
    data = np.load(path)
    return {
        "name": name,
        "t_ps": data["t_ps"],
        "rmsd": data["rmsd"],
        "rg": data["rg"],
        "xtc": str(xtc),
        "tpr": str(tpr),
    }


def first_time_ns(mask, t_ps):
    hit = np.flatnonzero(mask)
    if hit.size == 0:
        return None
    return float(t_ps[int(hit[0])]) / 1000.0


def discovery_stats(rmsd, rg, t_ps) -> dict:
    return {
        "n_frames": int(len(rmsd)),
        "sim_ns": float(t_ps[-1] / 1000.0) if len(t_ps) else 0.0,
        "coverage": float(coverage_rect(rmsd, rg, 24)),
        "min_rmsd": float(np.min(rmsd)) if len(rmsd) else None,
        "p10_rmsd": float(np.percentile(rmsd, 10)) if len(rmsd) else None,
        "mean_rg": float(np.mean(rg)) if len(rg) else None,
        "frac_fold": float((rmsd < FOLD_RMSD).mean()) if len(rmsd) else 0.0,
        "n_fold": int((rmsd < FOLD_RMSD).sum()),
        "first_fold_ns": first_time_ns(rmsd < FOLD_RMSD, t_ps),
        "first_rmsd40_ns": first_time_ns(rmsd < 0.40, t_ps),
    }


def snapshot(segments, nbins: int) -> dict:
    pool = concat_pool(segments)
    stats = discovery_stats(pool["rmsd"], pool["rg"], pool["t_accum_ps"])
    stats["n_segments"] = len(segments)
    stats["sim_ns"] = float(pool["sim_ns"])
    stats["coverage"] = float(coverage_rect(pool["rmsd"], pool["rg"], nbins))
    return stats


def fmt(v, nd=3):
    if v is None:
        return "none"
    return f"{v:.{nd}f}"


def build_windows(segments, window, horizon, stride, nbins: int):
    prior_r, prior_g = [], []
    Xs, ys, extra = [], [], []
    for si, seg in enumerate(segments):
        t_ps, rmsd, rg = resample_2ps(seg["t_ps"], seg["rmsd"], seg["rg"])
        n = len(rmsd)
        last_start = n - window - horizon
        if last_start < 0:
            prior_r.append(rmsd)
            prior_g.append(rg)
            continue
        starts = np.arange(0, last_start + 1, stride, dtype=np.int64)
        feats = encode_cv(rmsd, rg)
        X = np.stack([feats[s : s + window] for s in starts], axis=0)
        if prior_r:
            r_cat = np.concatenate(prior_r + [rmsd])
            g_cat = np.concatenate(prior_g + [rg])
            offset = sum(len(p) for p in prior_r)
            labels = fold_labels(r_cat, g_cat, starts + offset, window, horizon, nbins)
        else:
            labels = fold_labels(rmsd, rg, starts, window, horizon, nbins)
        Xs.append(X)
        ys.append(labels["y"])
        end = starts + window - 1
        extra.append(
            {
                "seg_id": np.full(len(starts), si, dtype=np.int32),
                "end_idx": end,
                "t_end_ps": t_ps[end],
                "rmsd_end": rmsd[end],
                "rg_end": rg[end],
                "y_fold": labels["y_fold"],
                "y_newbin": labels["y_newbin"],
            }
        )
        prior_r.append(rmsd)
        prior_g.append(rg)
    if not Xs:
        raise TapsError("no windows; lower --window-ps/--horizon-ps or raise --init-ns")
    pack = {
        "X": np.concatenate(Xs, axis=0).astype(np.float32),
        "y": np.concatenate(ys).astype(np.float32),
        "seg_id": np.concatenate([e["seg_id"] for e in extra]),
        "end_idx": np.concatenate([e["end_idx"] for e in extra]),
        "t_end_ps": np.concatenate([e["t_end_ps"] for e in extra]),
        "rmsd_end": np.concatenate([e["rmsd_end"] for e in extra]),
        "rg_end": np.concatenate([e["rg_end"] for e in extra]),
        "window": window,
        "horizon": horizon,
        "stride": stride,
    }
    log(
        f"  labels  y={pack['y'].mean():.3f}  fold={np.concatenate([e['y_fold'] for e in extra]).mean():.3f}  "
        f"newbin={np.concatenate([e['y_newbin'] for e in extra]).mean():.3f}"
    )
    return pack


def _percentile_rank(a: np.ndarray) -> np.ndarray:
    a = np.asarray(a, dtype=np.float64)
    order = np.argsort(a, kind="mergesort")
    ranks = np.empty(len(a), dtype=np.float64)
    ranks[order] = np.linspace(0.0, 1.0, len(a), dtype=np.float64)
    return ranks


def _pareto_mask(cols: np.ndarray) -> np.ndarray:
    x = np.asarray(cols, dtype=np.float64)
    n = len(x)
    keep = np.ones(n, dtype=bool)
    for i in range(n):
        if not keep[i]:
            continue
        dominated = np.all(x[i] >= x, axis=1) & np.any(x[i] > x, axis=1)
        keep[dominated] = False
        if np.any((np.all(x >= x[i], axis=1) & np.any(x > x[i], axis=1))):
            keep[i] = False
    return keep


def select_and_dump(spec, pack, scores, method, n_seeds, min_nm, segments, seed_dir: Path, rng_seed: int = 0, round_id: int = 1) -> list:
    rmsd_e = pack["rmsd_end"]
    rg_e = pack["rg_end"]
    pool = concat_pool(segments)
    rho = density_at(pool["rmsd"], pool["rg"], rmsd_e, rg_e, 24)
    inv = 1.0 / (rho + 1e-6)
    inv = inv / (inv.max() + 1e-12)
    last_sc = last_frontier_scores(pool["rmsd"], pool["rg"], rmsd_e, rg_e)
    commit = 1.0 / (np.maximum(rmsd_e - FOLD_RMSD, 0.0) + 0.05)
    if method == "density":
        raw = inv
    elif method == "last":
        raw = last_sc
    elif method == "random":
        raw = np.random.default_rng(int(rng_seed)).random(len(rmsd_e))
    elif method in ("moas", "moas_static"):
        raw = (_percentile_rank(inv) + _percentile_rank(last_sc) + _percentile_rank(commit)) / 3.0
    elif method in ("dynamic", "moas_dyn"):
        q = (int(round_id) - 1) / 11.0
        if q < 1.0 / 3.0:
            w = (2.0, 2.0, 0.25)
        elif q < 2.0 / 3.0:
            w = (1.0, 1.0, 1.0)
        else:
            w = (0.25, 0.5, 2.0)
        raw = (w[0] * _percentile_rank(inv) + w[1] * _percentile_rank(last_sc) + w[2] * _percentile_rank(commit)) / sum(w)
    elif method in ("pareto", "moas_pareto"):
        cols = np.column_stack([_percentile_rank(inv), _percentile_rank(last_sc), _percentile_rank(commit)])
        front = np.flatnonzero(_pareto_mask(cols))
        util = cols.mean(axis=1)
        raw = np.full(len(rmsd_e), -1.0)
        if len(front):
            raw[front] = util[front] + 1.0
        else:
            raw = util
    else:
        raw = np.asarray(scores, dtype=np.float64) * inv
    picked = greedy_diverse(rmsd_e, rg_e, raw, n_seeds, min_nm)
    seed_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for rank, idx in enumerate(picked):
        seg = segments[int(pack["seg_id"][idx])]
        gro = seed_dir / f"seed_{rank:02d}.gro"
        dump_frame(Path(seg["tpr"]), Path(seg["xtc"]), float(pack["t_end_ps"][idx]), gro, spec.outdir)
        rec = {
            "rank": rank,
            "window_index": int(idx),
            "seg": seg["name"],
            "t_ps": float(pack["t_end_ps"][idx]),
            "rmsd": float(rmsd_e[idx]),
            "rg": float(rg_e[idx]),
            "S_p": float(scores[idx]) if scores is not None else 0.0,
            "rho": float(rho[idx]),
            "score": float(raw[idx]),
            "gro": str(gro.relative_to(ROOT)),
        }
        records.append(rec)
        log(
            f"  seed {rank:02d}  {seg['name']}  t={rec['t_ps']:.1f}  "
            f"RMSD={rec['rmsd']:.3f} Rg={rec['rg']:.3f}  score={rec['score']:.3f}"
        )
    return records


def run_short_round(spec, records, round_id: int, nt: int, gpu: bool, force: bool) -> list:
    mdp = spec.workdir / "mdp" / SHORT_MDP
    top = spec.workdir / "topol.top"
    gmx = find_gmx()
    adaptive_root = spec.adaptive_root / f"round{round_id:02d}"
    analysis_round = spec.outdir / "adaptive" / f"round{round_id:02d}"
    adaptive_root.mkdir(parents=True, exist_ok=True)
    analysis_round.mkdir(parents=True, exist_ok=True)
    new_segments = []
    for rec in records:
        rank = int(rec["rank"])
        gro = ROOT / rec["gro"]
        job = adaptive_root / f"seed_{rank:02d}"
        job.mkdir(parents=True, exist_ok=True)
        xtc = job / "md_short.xtc"
        tpr = job / "md_short.tpr"
        dest = analysis_round / f"seed_{rank:02d}_cvs.npz"
        if xtc.exists() and (job / "md_short.gro").exists() and dest.exists() and not force:
            log(f"  seed {rank:02d}: short MD + CVs already complete")
        else:
            if not (xtc.exists() and (job / "md_short.gro").exists()) or force:
                run_gmx(
                    [gmx, "grompp", "-f", str(mdp), "-c", str(gro), "-p", str(top), "-o", "md_short.tpr", "-maxwarn", "1"],
                    cwd=job,
                )
                s06.mdrun_short(gmx, job, "md_short", nt=nt, gpu=gpu)
            if xtc.exists():
                extract_cvs(tpr, xtc, dest, analysis_round / f"seed_{rank:02d}_scratch")
        if dest.exists():
            new_segments.append(load_segment_npz(dest, f"r{round_id:02d}_s{rank:02d}", xtc, tpr))
    return new_segments


def save_pool(spec, segments, history) -> None:
    spec.outdir.mkdir(parents=True, exist_ok=True)
    catalog = []
    for s in segments:
        catalog.append(
            {
                "name": s["name"],
                "xtc": s["xtc"],
                "tpr": s["tpr"],
                "n_frames": int(len(s["rmsd"])),
                "t0": float(s["t_ps"][0]),
                "t1": float(s["t_ps"][-1]),
            }
        )
    (spec.outdir / "pool.json").write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
    (spec.outdir / "history.json").write_text(json.dumps(history, indent=2) + "\n", encoding="utf-8")
    pool = concat_pool(segments)
    np.savez_compressed(
        spec.outdir / "cvs.npz",
        t_ps=pool["t_accum_ps"],
        rmsd=pool["rmsd"],
        rg=pool["rg"],
        seg_id=pool["seg_id"],
    )


def rebuild_segments(spec, init_ns: float) -> list:
    segments = [slice_cmd_init(init_ns)]
    adaptive = spec.outdir / "adaptive"
    if not adaptive.exists():
        return segments
    for rnd in sorted(p for p in adaptive.glob("round*") if p.is_dir()):
        rid = rnd.name.replace("round", "")
        for npz in sorted(rnd.glob("seed_*_cvs.npz")):
            rank = npz.name.split("_")[1]
            job = spec.adaptive_root / rnd.name / f"seed_{rank}"
            xtc, tpr = job / "md_short.xtc", job / "md_short.tpr"
            if xtc.exists() and tpr.exists():
                segments.append(load_segment_npz(npz, f"r{rid}_s{rank}", xtc, tpr))
    return segments


def ensure_cmd_cvs(force: bool = False) -> dict:
    dest = ANALYSIS / "cln025_unfolded" / "cvs.npz"
    if dest.exists() and not force:
        log(f"reuse {dest.relative_to(ROOT)}")
        data = np.load(dest)
        return {k: data[k] for k in data.files}
    if not PROD_XTC.exists() or not PROD_TPR.exists():
        raise TapsError(f"missing production traj {PROD_XTC}")
    log("extracting CA-RMSD / Rg from unfolded 100 ns cMD")
    return extract_cvs(PROD_TPR, PROD_XTC, dest, ANALYSIS / "cln025_unfolded" / "scratch_cmd")


def run_one_method(args, method: str, tag: str, nt: int, gpu: bool) -> dict:
    spec = replace(ClnSpec(), tag=tag)
    spec.outdir.mkdir(parents=True, exist_ok=True)
    short_ns = args.n_seeds * args.short_ps / 1000.0
    remain = max(0.0, args.budget_ns - args.init_ns)
    auto_rounds = int(np.ceil(remain / short_ns)) if short_ns > 0 else 0
    n_rounds = args.max_rounds if args.max_rounds > 0 else auto_rounds
    window = int(round(args.window_ps / 2.0))
    horizon = int(round(args.horizon_ps / 2.0))
    stride = int(round(args.stride_ps / 2.0))
    log(
        f"==== method={method} tag={tag}  init={args.init_ns} ns  budget={args.budget_ns} ns  "
        f"short={args.short_ps} ps  seeds={args.n_seeds}  rounds={n_rounds}  "
        f"T={args.window_ps}ps M={args.horizon_ps}ps  nt={nt} gpu={gpu} ===="
    )
    segments = rebuild_segments(spec, args.init_ns)
    history = []
    hist_path = spec.outdir / "history.json"
    if hist_path.exists() and not args.force:
        try:
            history = json.loads(hist_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            history = []
    snap0 = snapshot(segments, args.nbins)
    log(
        f"start  sim={snap0['sim_ns']:.3f} ns  cov={snap0['coverage']:.4f}  "
        f"minRMSD={fmt(snap0['min_rmsd'])}  foldFPT={snap0['first_fold_ns']}"
    )
    if not history:
        history.append({"round": 0, **snap0})
        save_pool(spec, segments, history)
    done = {h["round"] for h in history if h["round"] > 0}
    for rid in range(1, n_rounds + 1):
        if rid in done and not args.force:
            log(f"round {rid:02d}: already in history -> skip")
            continue
        if concat_pool(segments)["sim_ns"] >= args.budget_ns - 1e-6:
            log(f"reached budget {args.budget_ns} ns; stop")
            break
        log(f"---- {tag} round {rid:02d} / {n_rounds} ----")
        pack = build_windows(segments, window, horizon, stride, args.nbins)
        log(f"  windows={len(pack['X'])}")
        np.savez_compressed(spec.outdir / "windows.npz", X=pack["X"], y=pack["y"], rmsd_end=pack["rmsd_end"], rg_end=pack["rg_end"])
        seeds_json = spec.outdir / f"seeds_round{rid:02d}.json"
        if seeds_json.exists() and not args.force:
            records = json.loads(seeds_json.read_text(encoding="utf-8")).get("seeds") or []
            log(f"  reuse {seeds_json.name} ({len(records)} seeds)")
        else:
            if method == "taps":
                scores = s07.train_sp(pack, spec.outdir, args.epochs, args.seed)
            else:
                scores = np.ones(len(pack["X"]), dtype=np.float64)
            records = select_and_dump(
                spec,
                pack,
                scores,
                method,
                args.n_seeds,
                args.min_nm,
                segments,
                spec.outdir / f"seeds_r{rid:02d}",
                rng_seed=int(args.seed) * 10007 + rid,
                round_id=rid,
            )
            seeds_json.write_text(json.dumps({"method": method, "round": rid, "seeds": records}, indent=2) + "\n")
        new_segs = run_short_round(spec, records, rid, nt, gpu, args.force)
        segments.extend(new_segs)
        snap = snapshot(segments, args.nbins)
        history.append({"round": rid, **snap})
        save_pool(spec, segments, history)
        log(
            f"round {rid:02d} done  sim={snap['sim_ns']:.3f} ns  cov={snap['coverage']:.4f}  "
            f"minRMSD={fmt(snap['min_rmsd'])}  foldFPT={snap['first_fold_ns']}"
        )
    final = snapshot(segments, args.nbins)
    (spec.outdir / "discover_stats.json").write_text(json.dumps(final, indent=2) + "\n")
    return {"tag": tag, "method": method, **final, "outdir": str(spec.outdir)}


def cmd_stats(budget_ns: float) -> dict:
    data = np.load(ANALYSIS / "cln025_unfolded" / "cvs.npz")
    mask = data["t_ps"] <= budget_ns * 1000.0 + 1e-6
    stats = discovery_stats(data["rmsd"][mask], data["rg"][mask], data["t_ps"][mask])
    stats["method"] = "cmd"
    stats["tag"] = "cmd"
    return stats


def write_report(args, results: list, cmd: dict, outdir: Path) -> None:
    outdir.mkdir(parents=True, exist_ok=True)

    def row(r):
        return (
            f"{r['method']:<10s} {r['sim_ns']:7.2f} {r['coverage']:7.4f} "
            f"{fmt(r.get('min_rmsd')):>8s} {fmt(r.get('p10_rmsd')):>8s} "
            f"{fmt(r.get('first_rmsd40_ns')):>8s} {fmt(r.get('first_fold_ns')):>8s} "
            f"{fmt(r.get('frac_fold')):>8s}"
        )

    lines = [
        "STAGE 13  CLN025 unfolded discovery + LAST + 1 ns shorts",
        f"init={args.init_ns} ns  budget={args.budget_ns} ns  short={args.short_ps} ps  n_seeds={args.n_seeds}",
        "CV = CA-RMSD to native + Rg. Folded if RMSD < 0.25 nm.",
        "",
        f"{'method':<10s} {'sim_ns':>7s} {'cov':>7s} {'minRMSD':>8s} {'p10RMSD':>8s} "
        f"{'<0.40 ns':>8s} {'fold ns':>8s} {'fold frac':>8s}",
        "-" * 80,
        row(cmd),
    ]
    for r in results:
        lines.append(row(r))
    lines += [
        "",
        "TAPS is only interesting if it reaches low RMSD / folded earlier than LAST, or gets closer.",
        "Coverage in (RMSD, Rg) alone is not enough.",
        "",
    ]
    adaptive = [r for r in results if r["method"] != "cmd"]
    if adaptive:
        best = min(adaptive, key=lambda r: 1e9 if r.get("min_rmsd") is None else r["min_rmsd"])
        folded = [r["method"] for r in adaptive if r.get("first_fold_ns") is not None]
        lines.append(f"lowest RMSD : {best['method']}  {fmt(best.get('min_rmsd'))} nm")
        lines.append(f"reached fold: {', '.join(folded) if folded else 'nobody'}")
        taps = next((r for r in adaptive if r["method"] == "taps"), None)
        last = next((r for r in adaptive if r["method"] == "last"), None)
        if taps and last and taps.get("min_rmsd") is not None and last.get("min_rmsd") is not None:
            if taps.get("first_fold_ns") is not None and last.get("first_fold_ns") is None:
                lines.append("verdict hint: TAPS folded and LAST did not.")
            elif last["min_rmsd"] - taps["min_rmsd"] > 0.08:
                lines.append("verdict hint: TAPS got clearly closer to native than LAST.")
            elif abs(taps["min_rmsd"] - last["min_rmsd"]) < 0.04:
                lines.append("verdict hint: TAPS ≈ LAST — not enough for the paper claim.")
            else:
                lines.append("verdict hint: mixed; inspect RMSD traces before deciding.")
    text = "\n".join(lines) + "\n"
    (outdir / "report.txt").write_text(text, encoding="utf-8")
    (outdir / "summary.json").write_text(json.dumps({"cmd": cmd, "methods": results, "args": vars(args)}, indent=2, default=str) + "\n")
    log(f"report -> {(outdir / 'report.txt').relative_to(ROOT)}")
    print(text)


def parse_methods(text: str) -> list:
    allowed = ("taps", "last", "density", "random", "moas", "dynamic", "pareto")
    out = []
    for raw in text.split(","):
        name = raw.strip().lower()
        if name in ("lc", "least", "least-counts", "least_counts"):
            name = "density"
        if name in ("moas_static", "moas-static", "weighted"):
            name = "moas"
        if name in ("moas_dyn", "moas-dynamic", "moas_dynamic"):
            name = "dynamic"
        if name in ("moas_pareto", "moas-pareto"):
            name = "pareto"
        if name and name not in allowed:
            raise TapsError(f"unknown method {raw!r}")
        if name and name not in out:
            out.append(name)
    if not out:
        raise TapsError("no methods")
    return out


def prod_finished() -> bool:
    if not PROD_LOG.exists() or not PROD_GRO.exists() or not PROD_XTC.exists():
        return False
    return "Finished mdrun" in PROD_LOG.read_text(encoding="utf-8", errors="replace")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--tag-prefix", default="discover")
    p.add_argument("--methods", default="taps,last,density")
    p.add_argument("--init-ns", type=float, default=10.0)
    p.add_argument("--budget-ns", type=float, default=82.0)
    p.add_argument("--max-rounds", type=int, default=12)
    p.add_argument("--n-seeds", type=int, default=6)
    p.add_argument("--short-ps", type=float, default=1000.0)
    p.add_argument("--window-ps", type=float, default=50.0)
    p.add_argument("--horizon-ps", type=float, default=200.0)
    p.add_argument("--stride-ps", type=float, default=10.0)
    p.add_argument("--nbins", type=int, default=24)
    p.add_argument("--min-nm", type=float, default=0.10)
    p.add_argument("--epochs", type=int, default=12)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--nt", type=int, default=int(os.environ.get("TAPS_NT", "0") or 0))
    p.add_argument("--cpu", action="store_true")
    p.add_argument("--gpu", action="store_true")
    p.add_argument("--force", action="store_true")
    p.add_argument("--check", action="store_true")
    args = p.parse_args(argv)
    try:
        methods = parse_methods(args.methods)
        log(f"STAGE 13  CLN025 unfolded discovery  methods={','.join(methods)}")
        if not NATIVE_GRO.exists():
            log(f"missing native ref {NATIVE_GRO}", "ERROR")
            return 2
        mdp = UNF_DIR / "mdp" / SHORT_MDP
        if not mdp.exists():
            log(f"missing {mdp}", "ERROR")
            return 2
        md_ns = len(methods) * args.n_seeds * args.max_rounds * (args.short_ps / 1000.0)
        log(f"planned new short MD ~{md_ns:.0f} ns  (~{md_ns / 1700.0 * 24:.1f} h at 1700 ns/day)")
        log("discovery: start from unfolded cMD prefix only; no native extra-init")
        if args.check:
            for method in methods:
                log(f"  would write analysis/cln025_unfolded/campaigns/{args.tag_prefix}_{METHOD_TAGS[method]}/")
            log(f"prod finished: {prod_finished()}")
            log("check passed")
            return 0
        if not prod_finished():
            raise TapsError("unfolded 100 ns cMD has not finished. Use run_cln025_followup.sh to wait.")
        ensure_cmd_cvs(force=args.force)
        import run_md

        nt = args.nt or run_md.default_thread_count()
        gpu = False if args.cpu else (True if args.gpu else run_md.detect_gpu())
        results = []
        for method in methods:
            tag = f"{args.tag_prefix}_{METHOD_TAGS[method]}"
            results.append(run_one_method(args, method, tag, nt, gpu))
        cmd = cmd_stats(args.budget_ns)
        write_report(args, results, cmd, ANALYSIS / "cln025_unfolded" / "discover_last")
        return 0
    except TapsError as exc:
        log(str(exc), "ERROR")
        return 1


if __name__ == "__main__":
    sys.exit(main())
