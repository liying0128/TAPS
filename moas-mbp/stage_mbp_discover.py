#!/usr/bin/env python3
"""MBP open→closed adaptive sampling. Four methods only: Random, LAST, LC, MOAS-static.

CVs are N–C domain CA-COM distance (nm) and hinge angle (deg). Success is both
inside the closed window for ≥ 200 ps (not first-hit).

Requires equilibrated open box and an init cMD (20 ns prefix of a 200 ns campaign):

  python3 run_md.py --system mbp_open --length 20 --gpu --nt 16
  python3 stage_mbp_discover.py --check
  python3 stage_mbp_discover.py --gpu --nt 16 --methods random last density moas \
    --init-ns 20 --budget-ns 200 --n-seeds 6 --short-ps 2000 --max-rounds 15
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

import run_md  # noqa: E402
from mbp_cvs import cvs_from_ca, in_closed, load_refs  # noqa: E402
from mbp_common import (  # noqa: E402
    ANALYSIS,
    MbpError,
    dump_frame,
    find_gmx,
    gro_ca,
    log,
    parse_xvg,
    run_gmx,
    write_ca_ndx,
)

SHORT_MDP = "md_short_2ns.mdp"
METHOD_TAGS = {"last": "last", "density": "lc", "random": "random", "moas": "static"}
OPEN_DIR = ROOT / "systems/mbp/water_open"
OPEN_GRO = ROOT / "systems/mbp/gmx_common_open/protein.gro"
PROD_XTC = OPEN_DIR / "runs/md_20ns.xtc"
PROD_TPR = OPEN_DIR / "runs/md_20ns.tpr"


@dataclass(frozen=True)
class MbpSpec:
    tag: str = ""

    @property
    def workdir(self) -> Path:
        return OPEN_DIR

    @property
    def outdir(self) -> Path:
        return ANALYSIS / "mbp_open" / "campaigns" / self.tag

    @property
    def adaptive_root(self) -> Path:
        return self.workdir / "adaptive" / "campaigns" / self.tag


def mdrun_short(gmx: str, workdir: Path, deffnm: str, nt: int, gpu: bool) -> None:
    argv = [gmx, "mdrun", "-v", "-deffnm", deffnm, "-cpt", "1", "-nt", str(nt), "-pin", "on" if gpu else "off"]
    if gpu:
        argv += ["-ntmpi", "1", "-nb", "gpu", "-pme", "gpu", "-bonded", "gpu", "-pmefft", "gpu", "-update", "gpu"]
    progress = run_md.MdProgress(
        label=deffnm, nsteps=None, dt_ps=0.002, log_path=workdir / f"{deffnm}.log", gpu=gpu, is_em=False
    )
    run_md.run_mdrun_process(argv, cwd=workdir, progress=progress)
    logp = workdir / f"{deffnm}.log"
    if not logp.exists() or "Finished mdrun" not in logp.read_text(encoding="utf-8", errors="replace"):
        raise MbpError(f"short MD did not finish: {logp}")


def extract_cvs(tpr: Path, xtc: Path, dest_npz: Path, scratch: Path) -> dict:
    dest_npz.parent.mkdir(parents=True, exist_ok=True)
    scratch.mkdir(parents=True, exist_ok=True)
    gmx = find_gmx()
    prot = scratch / "prot.xtc"
    ca_ndx = scratch / "ca.ndx"
    ca_xvg = scratch / "ca.xvg"
    write_ca_ndx(ca_ndx, OPEN_GRO)
    run_gmx(
        [gmx, "trjconv", "-s", str(tpr), "-f", str(xtc), "-o", str(prot), "-pbc", "mol", "-center"],
        cwd=scratch,
        stdin_text="Protein\nSystem\n",
    )
    run_gmx(
        [gmx, "traj", "-s", str(tpr), "-f", str(prot), "-n", str(ca_ndx), "-ox", str(ca_xvg)],
        cwd=scratch,
        stdin_text="CA\n",
    )
    arr = parse_xvg(ca_xvg)
    t_ps = arr[:, 0]
    xyz = arr[:, 1:].reshape(len(arr), -1, 3)
    _, resids, _ = gro_ca(OPEN_GRO)
    if xyz.shape[1] != len(resids):
        raise MbpError(f"CA count {xyz.shape[1]} != gro {len(resids)}")
    dist, theta = cvs_from_ca(xyz, resids)
    refs = load_refs()
    closed = in_closed(dist, theta, refs)
    np.savez_compressed(dest_npz, t_ps=t_ps, dist=dist, theta=theta, closed=closed.astype(np.int8))
    return {"t_ps": t_ps, "dist": dist, "theta": theta, "closed": closed}


def to_bins(dist, theta, nbins, lo, hi):
    i = np.clip(((np.asarray(dist) - lo[0]) / (hi[0] - lo[0]) * nbins).astype(np.int64), 0, nbins - 1)
    j = np.clip(((np.asarray(theta) - lo[1]) / (hi[1] - lo[1]) * nbins).astype(np.int64), 0, nbins - 1)
    return i, j


def density_at(dist_all, theta_all, dist_q, theta_q, nbins, lo, hi):
    i, j = to_bins(dist_all, theta_all, nbins, lo, hi)
    hist = np.zeros((nbins, nbins), dtype=np.float64)
    np.add.at(hist, (i, j), 1)
    hist /= max(1.0, hist.sum())
    iq, jq = to_bins(dist_q, theta_q, nbins, lo, hi)
    return hist[iq, jq]


def last_frontier_scores(dist_all, theta_all, dist_q, theta_q, nbins: int = 24) -> np.ndarray:
    # Scale nm vs deg so LAST bins are not dominated by the angle axis.
    z = np.stack([np.asarray(dist_all) / 0.05, np.asarray(theta_all) / 4.0], axis=1)
    zq = np.stack([np.asarray(dist_q) / 0.05, np.asarray(theta_q) / 4.0], axis=1)
    lo = z.min(axis=0) - 2.0
    hi = z.max(axis=0) + 2.0
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


def greedy_diverse(dist, theta, score, n_seeds: int, min_sep: float) -> list:
    order = np.argsort(-np.asarray(score))
    picked = []
    for idx in order:
        i = int(idx)
        if all(float(np.hypot((dist[i] - dist[j]) / 0.05, (theta[i] - theta[j]) / 4.0)) >= min_sep for j in picked):
            picked.append(i)
        if len(picked) >= n_seeds:
            break
    return picked


def _percentile_rank(a: np.ndarray) -> np.ndarray:
    a = np.asarray(a, dtype=np.float64)
    order = np.argsort(a, kind="mergesort")
    ranks = np.empty(len(a), dtype=np.float64)
    ranks[order] = np.linspace(0.0, 1.0, len(a), dtype=np.float64)
    return ranks


def concat_pool(segments: list) -> dict:
    dist = np.concatenate([s["dist"] for s in segments])
    theta = np.concatenate([s["theta"] for s in segments])
    closed = np.concatenate([s["closed"] for s in segments])
    accum, clock = [], 0.0
    for s in segments:
        n = len(s["t_ps"])
        dt = float(s["t_ps"][1] - s["t_ps"][0]) if n > 1 else 2.0
        length = float(s["t_ps"][-1] - s["t_ps"][0]) + dt
        accum.append(clock + s["t_ps"] - float(s["t_ps"][0]))
        clock += length
    t_accum = np.concatenate(accum) if accum else np.zeros(0)
    return {"dist": dist, "theta": theta, "closed": closed, "t_accum_ps": t_accum, "sim_ns": clock / 1000.0}


def first_commit_ns(closed: np.ndarray, t_ps: np.ndarray, commit_ps: float) -> float | None:
    dt = float(t_ps[1] - t_ps[0]) if len(t_ps) > 1 else 2.0
    need = max(1, int(round(commit_ps / max(dt, 1e-9))))
    run = 0
    for i, v in enumerate(closed.astype(bool)):
        run = run + 1 if v else 0
        if run >= need:
            return float(t_ps[i - need + 1]) / 1000.0
    return None


def snapshot(segments, refs, nbins: int) -> dict:
    pool = concat_pool(segments)
    dist, theta = pool["dist"], pool["theta"]
    lo = np.array([min(dist.min(), refs["closed_dist"] - 0.2), min(theta.min(), refs["closed_theta"] - 5)])
    hi = np.array([max(dist.max(), refs["open_dist"] + 0.2), max(theta.max(), refs["open_theta"] + 5)])
    i, j = to_bins(dist, theta, nbins, lo, hi)
    cov = len(set(zip(i.tolist(), j.tolist()))) / float(nbins * nbins)
    hit = pool["closed"].any()
    first_hit = None
    if hit:
        idx = int(np.flatnonzero(pool["closed"])[0])
        first_hit = float(pool["t_accum_ps"][idx]) / 1000.0
    return {
        "sim_ns": pool["sim_ns"],
        "coverage": cov,
        "frac_closed": float(pool["closed"].mean()),
        "first_hit_ns": first_hit,
        "first_commit_ns": first_commit_ns(pool["closed"], pool["t_accum_ps"], refs["commit_ps"]),
        "mean_dist": float(dist.mean()),
        "mean_theta": float(theta.mean()),
        "min_dist": float(dist.min()),
        "min_theta": float(theta.min()),
    }


def load_segment_npz(npz: Path, name: str, xtc: Path, tpr: Path) -> dict:
    d = np.load(npz)
    return {
        "name": name,
        "t_ps": d["t_ps"],
        "dist": d["dist"],
        "theta": d["theta"],
        "closed": d["closed"].astype(bool),
        "xtc": str(xtc),
        "tpr": str(tpr),
    }


def ensure_cmd_cvs(force: bool = False) -> dict:
    dest = ANALYSIS / "mbp_open" / "cvs.npz"
    if dest.exists() and not force:
        log(f"reuse {dest.relative_to(ROOT)}")
        data = np.load(dest)
        return {k: data[k] for k in data.files}
    if not PROD_XTC.exists() or not PROD_TPR.exists():
        raise MbpError(f"missing init cMD {PROD_XTC}. Run: python3 run_md.py --system mbp_open --length 20 --gpu")
    log("extracting domain distance / hinge angle from open 20 ns cMD")
    return extract_cvs(PROD_TPR, PROD_XTC, dest, ANALYSIS / "mbp_open" / "scratch_cmd")


def slice_cmd_init(init_ns: float) -> dict:
    data = np.load(ANALYSIS / "mbp_open" / "cvs.npz")
    mask = data["t_ps"] <= init_ns * 1000.0 + 1e-6
    return {
        "name": "cmd_init",
        "t_ps": data["t_ps"][mask],
        "dist": data["dist"][mask],
        "theta": data["theta"][mask],
        "closed": data["closed"][mask].astype(bool),
        "xtc": str(PROD_XTC),
        "tpr": str(PROD_TPR),
    }


def rebuild_segments(spec: MbpSpec, init_ns: float) -> list:
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


def select_and_dump(spec, pack, method, n_seeds, min_sep, segments, seed_dir: Path, rng_seed: int, refs: dict) -> list:
    dist_e, theta_e = pack["dist_end"], pack["theta_end"]
    pool = concat_pool(segments)
    lo = np.array([pool["dist"].min() - 0.2, pool["theta"].min() - 5])
    hi = np.array([pool["dist"].max() + 0.2, pool["theta"].max() + 5])
    rho = density_at(pool["dist"], pool["theta"], dist_e, theta_e, 24, lo, hi)
    inv = 1.0 / (rho + 1e-6)
    inv = inv / (inv.max() + 1e-12)
    last_sc = last_frontier_scores(pool["dist"], pool["theta"], dist_e, theta_e)
    d_closed = np.hypot((dist_e - refs["closed_dist"]) / 0.05, (theta_e - refs["closed_theta"]) / 4.0)
    commit = 1.0 / (d_closed + 5.0)
    if method == "density":
        raw = inv
    elif method == "last":
        raw = last_sc
    elif method == "random":
        raw = np.random.default_rng(int(rng_seed)).random(len(dist_e))
    elif method == "moas":
        raw = (_percentile_rank(inv) + _percentile_rank(last_sc) + _percentile_rank(commit)) / 3.0
    else:
        raise MbpError(f"unknown method {method}")
    picked = greedy_diverse(dist_e, theta_e, raw, n_seeds, min_sep)
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
            "dist": float(dist_e[idx]),
            "theta": float(theta_e[idx]),
            "score": float(raw[idx]),
            "gro": str(gro.relative_to(ROOT)),
        }
        records.append(rec)
        log(f"  seed {rank:02d}  {seg['name']}  t={rec['t_ps']:.1f}  dist={rec['dist']:.3f} nm theta={rec['theta']:.1f}  score={rec['score']:.3f}")
    return records


def build_windows(segments, window, horizon, stride) -> dict:
    Xs, extra = [], []
    for si, seg in enumerate(segments):
        dist, theta, t_ps = seg["dist"], seg["theta"], seg["t_ps"]
        n = len(dist)
        last_start = n - window - horizon
        if last_start < 0:
            continue
        starts = np.arange(0, last_start + 1, stride, dtype=np.int64)
        end = starts + window - 1
        extra.append(
            {
                "seg_id": np.full(len(starts), si, dtype=np.int32),
                "t_end_ps": t_ps[end],
                "dist_end": dist[end],
                "theta_end": theta[end],
            }
        )
        Xs.append(starts)
    if not extra:
        raise MbpError("no windows; raise --init-ns or lower --window-ps")
    return {
        "seg_id": np.concatenate([e["seg_id"] for e in extra]),
        "t_end_ps": np.concatenate([e["t_end_ps"] for e in extra]),
        "dist_end": np.concatenate([e["dist_end"] for e in extra]),
        "theta_end": np.concatenate([e["theta_end"] for e in extra]),
    }


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
                mdrun_short(gmx, job, "md_short", nt=nt, gpu=gpu)
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
                "n_frames": int(len(s["dist"])),
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
        dist=pool["dist"],
        theta=pool["theta"],
        closed=pool["closed"].astype(np.int8),
    )


def run_one_method(args, method: str, tag: str, nt: int, gpu: bool) -> dict:
    spec = MbpSpec(tag=tag)
    spec.outdir.mkdir(parents=True, exist_ok=True)
    refs = load_refs()
    short_ns = args.n_seeds * args.short_ps / 1000.0
    remain = max(0.0, args.budget_ns - args.init_ns)
    auto_rounds = int(np.ceil(remain / short_ns)) if short_ns > 0 else 0
    n_rounds = args.max_rounds if args.max_rounds > 0 else auto_rounds
    window = int(round(args.window_ps / 2.0))
    horizon = int(round(args.horizon_ps / 2.0))
    stride = int(round(args.stride_ps / 2.0))
    log(
        f"==== method={method} tag={tag}  init={args.init_ns} ns  budget={args.budget_ns} ns  "
        f"short={args.short_ps} ps  seeds={args.n_seeds}  rounds={n_rounds}  nt={nt} gpu={gpu} ===="
    )
    segments = rebuild_segments(spec, args.init_ns)
    history = []
    hist_path = spec.outdir / "history.json"
    if hist_path.exists() and not args.force:
        try:
            history = json.loads(hist_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            history = []
    snap0 = snapshot(segments, refs, args.nbins)
    log(f"start  sim={snap0['sim_ns']:.3f} ns  cov={snap0['coverage']:.4f}  commit={snap0['first_commit_ns']}")
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
        pack = build_windows(segments, window, horizon, stride)
        log(f"  windows={len(pack['dist_end'])}")
        seeds_json = spec.outdir / f"seeds_round{rid:02d}.json"
        if seeds_json.exists() and not args.force:
            records = json.loads(seeds_json.read_text(encoding="utf-8")).get("seeds") or []
            log(f"  reuse {seeds_json.name} ({len(records)} seeds)")
        else:
            records = select_and_dump(
                spec, pack, method, args.n_seeds, args.min_sep, segments,
                spec.outdir / f"seeds_r{rid:02d}",
                rng_seed=int(args.seed) * 10007 + rid,
                refs=refs,
            )
            seeds_json.write_text(json.dumps({"method": method, "round": rid, "seeds": records}, indent=2) + "\n")
        new_segs = run_short_round(spec, records, rid, nt, gpu, args.force)
        segments.extend(new_segs)
        snap = snapshot(segments, refs, args.nbins)
        history.append({"round": rid, **snap})
        save_pool(spec, segments, history)
        log(
            f"round {rid:02d} done  sim={snap['sim_ns']:.3f} ns  cov={snap['coverage']:.4f}  "
            f"hit={snap['first_hit_ns']}  commit={snap['first_commit_ns']}"
        )
    final = snapshot(segments, refs, args.nbins)
    (spec.outdir / "discover_stats.json").write_text(json.dumps(final, indent=2) + "\n")
    return {"tag": tag, "method": method, **final}


def parse_args():
    p = argparse.ArgumentParser(description="MBP 4-method adaptive sampling")
    p.add_argument("--check", action="store_true")
    p.add_argument("--gpu", action="store_true")
    p.add_argument("--cpu", action="store_true")
    p.add_argument("--nt", type=int, default=16)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--methods", nargs="+", default=["random", "last", "density", "moas"])
    p.add_argument("--tag-prefix", default="mbp")
    p.add_argument("--init-ns", type=float, default=20.0)
    p.add_argument("--budget-ns", type=float, default=200.0)
    p.add_argument("--n-seeds", type=int, default=6)
    p.add_argument("--short-ps", type=float, default=2000.0)
    p.add_argument("--max-rounds", type=int, default=15)
    p.add_argument("--window-ps", type=float, default=50.0)
    p.add_argument("--horizon-ps", type=float, default=200.0)
    p.add_argument("--stride-ps", type=float, default=10.0)
    p.add_argument("--nbins", type=int, default=24)
    p.add_argument("--min-sep", type=float, default=1.0)
    p.add_argument("--force", action="store_true")
    return p.parse_args()


def method_tag(prefix: str, method: str, seed: int) -> str:
    stem = METHOD_TAGS[method]
    return f"{prefix}_{stem}"


def main() -> int:
    args = parse_args()
    os.environ.setdefault("GMX_MAXBACKUP", "-1")
    unknown = [m for m in args.methods if m not in METHOD_TAGS]
    if unknown:
        raise MbpError(f"unknown methods {unknown}; allowed: {list(METHOD_TAGS)}")
    if args.cpu and args.gpu:
        raise MbpError("use only one of --cpu / --gpu")
    gpu = bool(args.gpu) if (args.cpu or args.gpu) else run_md.detect_gpu()
    log("STAGE MBP  methods=" + ",".join(args.methods))
    if args.check:
        find_gmx()
        load_refs()
        for p in (OPEN_GRO, OPEN_DIR / "ions.gro", OPEN_DIR / "topol.top"):
            if not p.exists():
                raise MbpError(f"missing {p}; run bash scripts/prepare_mbp.sh")
        npt = OPEN_DIR / "npt.gro"
        log(f"open gro={'ok' if OPEN_GRO.exists() else 'MISSING'}  ions={'ok' if (OPEN_DIR/'ions.gro').exists() else 'MISSING'}  npt={'ok' if npt.exists() else 'not eq yet'}")
        log(f"init cMD={'ok' if PROD_XTC.exists() else 'MISSING (run --length 20)'}")
        log("check finished; no MD started")
        return 0
    ensure_cmd_cvs(force=args.force)
    prefix = args.tag_prefix
    for method in args.methods:
        tag = method_tag(prefix, method, args.seed)
        run_one_method(args, method, tag, args.nt, gpu)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except MbpError as exc:
        log(str(exc), "ERROR")
        sys.exit(1)
