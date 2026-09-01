#!/usr/bin/env python3
"""
STAGE 07  |  大纲 §9.1 / §6.2  多轮闭环（同预算、可对照基线）

从 cMD 的前 --init-ns 起步（不用后面那 98 ns，避免信息泄漏），然后反复：
  按轨迹段切片 →（TAPS 才训练 S_p）→ 选 seed → 短 MD → 并入数据。

--strategy full     = TAPS（密度 × 潜力 − 惩罚）
--strategy density  = Least-counts 味道（只追低密度）
每个策略必须用不同 --tag，否则会互相覆盖。

输入:  analysis/<system>/dihedrals.npz          （stage01 已有）
       systems/.../runs/md_100ns.xtc + .tpr
输出:  analysis/<system>/campaigns/<tag>/
       systems/.../adaptive/campaigns/<tag>/roundXX/

上一阶段: stage01（cMD φ/ψ）已齐即可
下一阶段: python3 stage08_compare_budget.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import stage03_slice_windows as s03  # noqa: E402
import stage04_train_sp as s04  # noqa: E402
import stage05_select_seeds as s05  # noqa: E402
import stage06_adaptive_round as s06  # noqa: E402
from taps_common import (  # noqa: E402
    MAIN_KEYS,
    TapsError,
    basin_fpt_ps,
    dump_frame,
    find_gmx,
    get_spec,
    load_dihedrals,
    log,
    rama_coverage,
    resample_1ps,
    run_gmx,
    wrap_deg,
)


def slice_cmd_init(spec, init_ns: float) -> dict:
    src = get_spec(spec.key)
    data = load_dihedrals(src)
    t_ps = data["t_ps"]
    cut = init_ns * 1000.0
    mask = t_ps <= cut + 1e-6
    if int(mask.sum()) < 80:
        raise TapsError(f"init-ns={init_ns} only has {int(mask.sum())} frames")
    return {
        "name": "cmd_init",
        "t_ps": t_ps[mask],
        "phi": wrap_deg(data["phi"][mask]),
        "psi": wrap_deg(data["psi"][mask]),
        "xtc": str(spec.workdir / spec.prod_xtc),
        "tpr": str(spec.workdir / spec.prod_tpr),
    }


def load_segment_npz(path: Path, name: str, xtc: Path, tpr: Path) -> dict:
    data = np.load(path)
    return {
        "name": name,
        "t_ps": data["t_ps"],
        "phi": wrap_deg(data["phi"]),
        "psi": wrap_deg(data["psi"]),
        "xtc": str(xtc),
        "tpr": str(tpr),
    }


def concat_pool(segments: list) -> dict:
    phi = np.concatenate([s["phi"] for s in segments])
    psi = np.concatenate([s["psi"] for s in segments])
    t_local = np.concatenate([s["t_ps"] for s in segments])
    seg_id = np.concatenate([np.full(len(s["phi"]), i, dtype=np.int32) for i, s in enumerate(segments)])
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
        "phi": phi,
        "psi": psi,
        "t_local": t_local,
        "t_accum_ps": t_accum,
        "seg_id": seg_id,
        "sim_ns": clock / 1000.0,
    }


def _seg_arrays(seg: dict, resample: bool):
    if resample:
        t, phi, psi = resample_1ps(seg["t_ps"], seg["phi"], seg["psi"])
        return t, phi, psi
    return seg["t_ps"], seg["phi"], seg["psi"]


def build_windows(segments: list, window: int, horizon: int, stride: int, nbins: int, rare_frac: float, label: str = "mixed", resample: bool = False):
    prior_phi = []
    prior_psi = []
    Xs, ys, extra = [], [], []
    import stage11_relabel_train as s11

    for si, seg in enumerate(segments):
        t_ps, phi, psi = _seg_arrays(seg, resample)
        n = len(phi)
        last_start = n - window - horizon
        if last_start < 0:
            prior_phi.append(phi)
            prior_psi.append(psi)
            continue
        starts = np.arange(0, last_start + 1, stride, dtype=np.int64)
        feats = s03.encode_trig(phi, psi)
        X = np.stack([feats[s : s + window] for s in starts], axis=0)
        if prior_phi:
            phi_cat = np.concatenate(prior_phi + [phi])
            psi_cat = np.concatenate(prior_psi + [psi])
            offset = sum(len(p) for p in prior_phi)
            starts_cat = starts + offset
            if label == "escape":
                labels = s11.escape_labels(phi_cat, psi_cat, starts_cat, window, horizon, nbins)
            else:
                labels = s03.label_windows(phi_cat, psi_cat, starts_cat, window, horizon, nbins, rare_frac)
        else:
            if label == "escape":
                labels = s11.escape_labels(phi, psi, starts, window, horizon, nbins)
            else:
                labels = s03.label_windows(phi, psi, starts, window, horizon, nbins, rare_frac)
        y_key = "y"
        Xs.append(X)
        ys.append(labels[y_key])
        end = starts + window - 1
        extra.append(
            {
                "seg_id": np.full(len(starts), si, dtype=np.int32),
                "end_idx": end,
                "t_end_ps": t_ps[end],
                "phi_end": phi[end],
                "psi_end": psi[end],
                "y_diff": np.asarray(labels["y_jump_deg"] if "y_jump_deg" in labels else labels["y_diff_deg"]),
                "y_reach": np.asarray(labels["y_escape"] if "y_escape" in labels else labels["y_reach"]),
            }
        )
        prior_phi.append(phi)
        prior_psi.append(psi)
    if not Xs:
        raise TapsError("no windows; lower --window/--horizon or raise --init-ns")
    pack = {
        "X": np.concatenate(Xs, axis=0).astype(np.float32),
        "y": np.concatenate(ys).astype(np.float32),
        "seg_id": np.concatenate([e["seg_id"] for e in extra]),
        "end_idx": np.concatenate([e["end_idx"] for e in extra]),
        "t_end_ps": np.concatenate([e["t_end_ps"] for e in extra]),
        "phi_end": np.concatenate([e["phi_end"] for e in extra]),
        "psi_end": np.concatenate([e["psi_end"] for e in extra]),
        "y_diff": np.concatenate([e["y_diff"] for e in extra]),
        "y_reach": np.concatenate([e["y_reach"] for e in extra]),
        "window": window,
        "horizon": horizon,
        "stride": stride,
    }
    return pack


def train_sp(pack: dict, outdir: Path, epochs: int, seed: int) -> np.ndarray:
    torch, nn, DataLoader, TensorDataset = s04.require_torch()
    X = pack["X"]
    y = pack["y"]
    torch.manual_seed(seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    tr_idx, va_idx = s04.time_split(len(X), 0.2)
    X_t = torch.from_numpy(X)
    y_t = torch.from_numpy(y)
    loader = DataLoader(TensorDataset(X_t[tr_idx], y_t[tr_idx]), batch_size=min(256, len(tr_idx)), shuffle=True)
    model = s04.build_model(torch, nn, X.shape[-1], 64, 4, 2, 0.1).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    loss_fn = nn.MSELoss()
    best, best_state = float("inf"), None
    val_X, val_y = X_t[va_idx].to(device), y_t[va_idx].to(device)
    for epoch in range(1, epochs + 1):
        model.train()
        for xb, yb in loader:
            pred = model(xb.to(device))
            loss = loss_fn(pred, yb.to(device))
            opt.zero_grad()
            loss.backward()
            opt.step()
        model.eval()
        with torch.no_grad():
            val = float(loss_fn(model(val_X), val_y).item())
        if val < best:
            best = val
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
        if epoch == 1 or epoch == epochs or epoch % 5 == 0:
            log(f"  train epoch {epoch:03d}  val_mse={val:.4f}")
    if best_state:
        model.load_state_dict(best_state)
    model.eval()
    with torch.no_grad():
        scores = model(X_t.to(device)).cpu().numpy()
    torch.save({"state_dict": model.state_dict(), "d_in": int(X.shape[-1])}, outdir / "sp_model.pt")
    np.savez_compressed(outdir / "sp_scores.npz", S_p=scores.astype(np.float32), y=y)
    log(f"  S_p mean={scores.mean():.3f} std={scores.std():.3f}  best_val={best:.4f}")
    return scores


def select_and_dump(spec, pack, scores, strategy, n_seeds, min_deg, lam, segments, seed_dir: Path) -> list:
    phi_e = wrap_deg(pack["phi_end"])
    psi_e = wrap_deg(pack["psi_end"])
    pool = concat_pool(segments)
    rho = s05.density_at(pool["phi"], pool["psi"], phi_e, psi_e, 36)
    inv = 1.0 / (rho + 1e-6)
    inv = inv / (inv.max() + 1e-12)
    if strategy == "density":
        raw = inv
    elif strategy == "last":
        from hybrid_common import last_frontier_2d

        xy_all = np.column_stack([wrap_deg(pool["phi"]), wrap_deg(pool["psi"])])
        xy_q = np.column_stack([phi_e, psi_e])
        raw = last_frontier_2d(xy_all, xy_q)
    elif strategy == "potential":
        raw = scores
    elif strategy == "combo":
        raw = scores * inv
    else:
        raw = scores * inv  # vacuum shorts have no reliable E; λ term stays 0 here
    picked = s05.greedy_diverse(phi_e, psi_e, raw, n_seeds, min_deg)
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
            "phi": float(phi_e[idx]),
            "psi": float(psi_e[idx]),
            "S_p": float(scores[idx]),
            "rho": float(rho[idx]),
            "score": float(raw[idx]),
            "gro": str(gro.relative_to(ROOT)),
        }
        records.append(rec)
        log(
            f"  seed {rank:02d}  {seg['name']}  t={rec['t_ps']:.1f}  "
            f"φ={rec['phi']:.1f} ψ={rec['psi']:.1f}  S_p={rec['S_p']:.3f} score={rec['score']:.3f}"
        )
    return records


def run_short_round(spec, records, round_id: int, nt: int, gpu: bool, force: bool, short_mdp: str | None = None) -> list:
    mdp = spec.workdir / "mdp" / (short_mdp or spec.short_mdp)
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
        if xtc.exists() and (job / "md_short.gro").exists() and not force:
            log(f"  seed {rank:02d}: short MD already complete")
        else:
            run_gmx(
                [gmx, "grompp", "-f", str(mdp), "-c", str(gro), "-p", str(top), "-o", "md_short.tpr", "-maxwarn", "1"],
                cwd=job,
            )
            s06.mdrun_short(gmx, job, "md_short", nt=nt, gpu=gpu)
        dest = analysis_round / f"seed_{rank:02d}_dihedrals.npz"
        if xtc.exists():
            s06.extract_short_dihedrals(gmx, xtc, dest)
            new_segments.append(
                load_segment_npz(dest, f"r{round_id:02d}_s{rank:02d}", xtc, tpr)
            )
    return new_segments


def snapshot(segments: list, nbins: int) -> dict:
    pool = concat_pool(segments)
    fpt = basin_fpt_ps(pool["phi"], pool["psi"], pool["t_accum_ps"], "c7ax")
    return {
        "n_segments": len(segments),
        "n_frames": int(len(pool["phi"])),
        "sim_ns": float(pool["sim_ns"]),
        "coverage": float(rama_coverage(pool["phi"], pool["psi"], nbins)),
        "c7ax_fpt_ns": None if fpt is None else fpt / 1000.0,
    }


def save_pool(spec, segments: list, history: list) -> None:
    spec.outdir.mkdir(parents=True, exist_ok=True)
    catalog = []
    for s in segments:
        catalog.append(
            {
                "name": s["name"],
                "xtc": s["xtc"],
                "tpr": s["tpr"],
                "n_frames": int(len(s["phi"])),
                "t0": float(s["t_ps"][0]),
                "t1": float(s["t_ps"][-1]),
            }
        )
    (spec.outdir / "pool.json").write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
    (spec.outdir / "history.json").write_text(json.dumps(history, indent=2) + "\n", encoding="utf-8")
    pool = concat_pool(segments)
    np.savez_compressed(
        spec.outdir / "dihedrals.npz",
        t_ps=pool["t_accum_ps"],
        phi=pool["phi"],
        psi=pool["psi"],
        seg_id=pool["seg_id"],
    )


def run_extra_init(spec, gro_paths: list, nt: int, gpu: bool, force: bool, short_mdp: str | None) -> list:
    if not gro_paths:
        return []
    dummy = [{"rank": i, "gro": str(Path(g) if Path(g).is_absolute() else ROOT / g), "phi": None, "psi": None} for i, g in enumerate(gro_paths)]
    # park extras under round00-style folder init_extra via a fake records list
    mdp = spec.workdir / "mdp" / (short_mdp or spec.short_mdp)
    top = spec.workdir / "topol.top"
    gmx = find_gmx()
    segs = []
    for rec in dummy:
        rank = int(rec["rank"])
        gro = Path(rec["gro"])
        if not gro.exists():
            raise TapsError(f"extra-init gro missing: {gro}")
        job = spec.adaptive_root / "init_extra" / f"seed_{rank:02d}"
        job.mkdir(parents=True, exist_ok=True)
        xtc = job / "md_short.xtc"
        tpr = job / "md_short.tpr"
        dest_dir = spec.outdir / "adaptive" / "init_extra"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"seed_{rank:02d}_dihedrals.npz"
        if not (xtc.exists() and (job / "md_short.gro").exists()) or force:
            run_gmx(
                [gmx, "grompp", "-f", str(mdp), "-c", str(gro), "-p", str(top), "-o", "md_short.tpr", "-maxwarn", "1"],
                cwd=job,
            )
            s06.mdrun_short(gmx, job, "md_short", nt=nt, gpu=gpu)
        if xtc.exists():
            s06.extract_short_dihedrals(gmx, xtc, dest)
            segs.append(load_segment_npz(dest, f"init_extra_{rank:02d}", xtc, tpr))
            log(f"extra-init {gro.name}: {len(segs[-1]['phi'])} frames")
    return segs


def rebuild_segments(spec, init_ns: float) -> list:
    segments = [slice_cmd_init(spec, init_ns)]
    adaptive = spec.outdir / "adaptive"
    extra_dir = adaptive / "init_extra"
    if extra_dir.exists():
        for npz in sorted(extra_dir.glob("seed_*_dihedrals.npz")):
            rank = npz.name.split("_")[1]
            job = spec.adaptive_root / "init_extra" / f"seed_{rank}"
            xtc, tpr = job / "md_short.xtc", job / "md_short.tpr"
            if xtc.exists() and tpr.exists():
                segments.append(load_segment_npz(npz, f"init_extra_{rank}", xtc, tpr))
    if not adaptive.exists():
        return segments
    for rnd in sorted(p for p in adaptive.glob("round*") if p.is_dir()):
        rid = rnd.name.replace("round", "")
        for npz in sorted(rnd.glob("seed_*_dihedrals.npz")):
            rank = npz.name.split("_")[1]
            job = spec.adaptive_root / rnd.name / f"seed_{rank}"
            xtc = job / "md_short.xtc"
            tpr = job / "md_short.tpr"
            if xtc.exists() and tpr.exists():
                segments.append(load_segment_npz(npz, f"r{rid}_s{rank}", xtc, tpr))
    return segments


def run_campaign(args) -> None:
    spec = get_spec(args.system, tag=args.tag)
    spec.outdir.mkdir(parents=True, exist_ok=True)
    import run_md

    nt = args.nt or run_md.default_thread_count()
    gpu = False if args.cpu else (True if args.gpu else run_md.detect_gpu())
    short_ns = args.n_seeds * args.short_ps / 1000.0
    extra_ns = 0.0 if not args.extra_init else len(args.extra_init) * args.short_ps / 1000.0
    remain = max(0.0, args.budget_ns - args.init_ns - extra_ns)
    auto_rounds = int(np.ceil(remain / short_ns)) if short_ns > 0 else 0
    n_rounds = args.max_rounds if args.max_rounds > 0 else auto_rounds
    resample = args.label == "escape" or args.window_ps > 0
    if resample:
        window = int(args.window_ps or 50)
        horizon = int(args.horizon_ps or 200)
        stride = int(args.stride_ps or 10)
    else:
        window, horizon, stride = args.window, args.horizon, args.stride
    if args.short_ps + 1e-6 < window + horizon:
        log(
            f"short-ps={args.short_ps} < T+M={window+horizon} ps; "
            "adaptive shorts will contribute few/no windows. Use --short-ps 500.",
            "WARN",
        )
    log(
        f"campaign tag={args.tag}  strategy={args.strategy}  label={args.label}  "
        f"init={args.init_ns} ns  extra={extra_ns:.2f} ns  budget={args.budget_ns} ns  "
        f"T={window} M={horizon} stride={stride}  short={args.short_ps} ps  "
        f"rounds={n_rounds}  (~{short_ns:.2f} ns/round)  nt={nt} gpu={gpu}"
    )

    segments = rebuild_segments(spec, args.init_ns)
    if args.extra_init and not any(s["name"].startswith("init_extra") for s in segments):
        segments.extend(run_extra_init(spec, args.extra_init, nt, gpu, args.force, args.short_mdp))
    history = []
    hist_path = spec.outdir / "history.json"
    if hist_path.exists() and not args.force:
        try:
            history = json.loads(hist_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            history = []
    snap0 = snapshot(segments, args.nbins)
    log(f"start  sim={snap0['sim_ns']:.3f} ns  cov={snap0['coverage']:.4f}  C7ax_FPT={snap0['c7ax_fpt_ns']}")
    if not history:
        history.append({"round": 0, **snap0})
        save_pool(spec, segments, history)

    done_rounds = {h["round"] for h in history if h["round"] > 0}
    for rid in range(1, n_rounds + 1):
        if rid in done_rounds and not args.force:
            log(f"round {rid:02d}: already in history -> skip")
            continue
        if concat_pool(segments)["sim_ns"] >= args.budget_ns - 1e-6:
            log(f"reached budget {args.budget_ns} ns; stop")
            break
        log(f"==== round {rid:02d} / {n_rounds} ====")
        pack = build_windows(
            segments, window, horizon, stride, args.nbins, args.rare_frac, label=args.label, resample=resample
        )
        log(f"  windows={len(pack['X'])}")
        np.savez_compressed(
            spec.outdir / "windows.npz",
            X=pack["X"],
            end_idx=pack["end_idx"],
            t_end_ps=pack["t_end_ps"],
            phi_end=pack["phi_end"],
            psi_end=pack["psi_end"],
            seg_id=pack["seg_id"],
            window=np.array(pack["window"]),
            horizon=np.array(pack["horizon"]),
            stride=np.array(pack["stride"]),
        )
        np.savez_compressed(
            spec.outdir / "labels.npz",
            y=pack["y"],
            y_diff_deg=pack["y_diff"],
            y_reach=pack["y_reach"],
        )
        seeds_json = spec.outdir / f"seeds_round{rid:02d}.json"
        if seeds_json.exists() and not args.force:
            records = json.loads(seeds_json.read_text(encoding="utf-8")).get("seeds") or []
            log(f"  reuse {seeds_json.name} ({len(records)} seeds)")
        else:
            if args.strategy in ("density", "last"):
                scores = np.ones(len(pack["X"]), dtype=np.float64)
            else:
                scores = train_sp(pack, spec.outdir, args.epochs, args.seed)
            seed_dir = spec.outdir / f"seeds_r{rid:02d}"
            records = select_and_dump(
                spec, pack, scores, args.strategy, args.n_seeds, args.min_deg, args.lam, segments, seed_dir
            )
            seeds_json.write_text(
                json.dumps({"strategy": args.strategy, "round": rid, "seeds": records}, indent=2) + "\n",
                encoding="utf-8",
            )
        new_segs = run_short_round(spec, records, rid, nt, gpu, args.force, short_mdp=args.short_mdp)
        segments.extend(new_segs)
        snap = snapshot(segments, args.nbins)
        history.append({"round": rid, **snap})
        save_pool(spec, segments, history)
        log(
            f"round {rid:02d} done  sim={snap['sim_ns']:.3f} ns  "
            f"cov={snap['coverage']:.4f}  C7ax_FPT={snap['c7ax_fpt_ns']}"
        )
    log(f"campaign finished  {spec.outdir.relative_to(ROOT)}")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--system", default="ala2_vacuum", choices=MAIN_KEYS)
    p.add_argument("--tag", required=True, help="campaign name, e.g. taps_full or least_counts")
    p.add_argument("--strategy", default="full", choices=("density", "potential", "combo", "full", "last"))
    p.add_argument("--init-ns", type=float, default=2.0, help="cMD prefix used as round 0 (default 2)")
    p.add_argument("--budget-ns", type=float, default=20.0, help="stop when total sim time reaches this")
    p.add_argument("--max-rounds", type=int, default=0, help="0 = infer from budget")
    p.add_argument("--n-seeds", type=int, default=8)
    p.add_argument("--short-ps", type=float, default=100.0, help="must match the short mdp")
    p.add_argument("--short-mdp", default=None, help="mdp filename in system mdp/, default spec.short_mdp")
    p.add_argument("--extra-init", action="append", default=[], help="extra starting gro (repeatable), e.g. seeds/c7ax.gro")
    p.add_argument("--label", default="mixed", choices=("mixed", "escape"))
    p.add_argument("--window", type=int, default=20)
    p.add_argument("--horizon", type=int, default=20)
    p.add_argument("--stride", type=int, default=5)
    p.add_argument("--window-ps", type=float, default=0.0, help="if >0 (or --label escape), resample to 1 ps and use this T")
    p.add_argument("--horizon-ps", type=float, default=0.0)
    p.add_argument("--stride-ps", type=float, default=0.0)
    p.add_argument("--nbins", type=int, default=36)
    p.add_argument("--rare-frac", type=float, default=0.25)
    p.add_argument("--min-deg", type=float, default=30.0)
    p.add_argument("--lambda", dest="lam", type=float, default=0.3)
    p.add_argument("--epochs", type=int, default=15)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--nt", type=int, default=int(os.environ.get("TAPS_NT", "0") or 0))
    p.add_argument("--cpu", action="store_true")
    p.add_argument("--gpu", action="store_true")
    p.add_argument("--force", action="store_true")
    p.add_argument("--check", action="store_true")
    args = p.parse_args(argv)
    try:
        spec = get_spec(args.system, tag=args.tag)
        log(f"STAGE 07  multi-round campaign  system={args.system}  tag={args.tag}")
        src = get_spec(args.system)
        try:
            load_dihedrals(src)
        except TapsError as exc:
            log(str(exc), "ERROR")
            return 2
        if not (src.workdir / src.prod_xtc).exists():
            log(f"missing {src.prod_xtc}", "ERROR")
            return 2
        if args.check:
            log(f"will write {spec.outdir}")
            log("check passed")
            return 0
        run_campaign(args)
        return 0
    except TapsError as exc:
        log(str(exc), "ERROR")
        return 1


if __name__ == "__main__":
    sys.exit(main())
