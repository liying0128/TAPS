#!/usr/bin/env python3
"""
STAGE 12  |  发现设定 + LAST + 1 ns 短轨迹（只跑真空主体系）

上一轮 C7ax 是 extra-init 灌进去的，FPT 不能当发现。本脚本改成：

  1) 发现设定：只用 cMD 前 --init-ns（默认 2 ns），禁止 c7ax.gro
  2) LAST：在 trig(φ,ψ) 的 2D PCA 隐空间里选已采样云的边界，不是 Least-counts 的 1/ρ
  3) 短轨迹 1 ns（T=50 ps + M=200 ps 窗口能落在短轨迹上）
  4) 同预算对照 TAPS / LAST / Least-counts / cMD

标签用 discover：未来是否朝 +φ 走、是否进空 bin、是否离开当前 basin。
这样即使全程还在 φ<0，也能学“朝势垒推进”，而不是 C7eq↔C5 闪烁。

输入:  analysis/ala2_vacuum/dihedrals.npz
       systems/alanine_dipeptide/vacuum/runs/md_100ns.xtc + .tpr
       systems/.../mdp/md_short_1ns_vacuum.mdp
输出:  analysis/ala2_vacuum/campaigns/<prefix>_taps|last|lc/
       analysis/ala2_vacuum/discover_last/report.txt

先检查再跑：
  python3 stage12_discover_last.py --check
正式跑（默认同跑三种方法，约 4 seeds × 1 ns × 5 轮 × 3 ≈ 60 ns MD）：
  python3 stage12_discover_last.py
只跑一种：
  python3 stage12_discover_last.py --methods taps
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
import stage05_select_seeds as s05  # noqa: E402
import stage07_multi_round as s07  # noqa: E402
import stage11_relabel_train as s11  # noqa: E402
from taps_common import (  # noqa: E402
    ANALYSIS,
    BASIN_RADIUS,
    BASINS,
    TapsError,
    basin_fpt_ps,
    cv_dist,
    dump_frame,
    get_spec,
    in_basin,
    load_dihedrals,
    log,
    nearest_basin,
    rama_coverage,
    to_bins,
    wrap_deg,
)

SHORT_MDP = "md_short_1ns_vacuum.mdp"
METHOD_TAGS = {"taps": "taps", "last": "last", "density": "lc"}


def discover_labels(phi, psi, starts, window, horizon, nbins: int) -> dict:
    """Toward +φ / empty bins / leave basin. Causal hist stops at window end."""
    i, j = to_bins(phi, psi, nbins)
    flat = i * nbins + j
    hist = np.zeros(nbins * nbins, dtype=np.int64)
    y_phi = np.zeros(len(starts), dtype=np.float64)
    y_new = np.zeros(len(starts), dtype=np.float64)
    y_esc = np.zeros(len(starts), dtype=np.float64)
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
        if fut_phi.size:
            dphi = wrap_deg(fut_phi - phi[end])
            max_up = float(np.max(dphi))
            crossed = float(np.any(fut_phi > 0.0))
            y_phi[k] = float(np.clip(0.7 * max_up / 90.0 + 0.3 * crossed, 0.0, 1.0))
            y_new[k] = float((hist[fut_flat] == 0).mean())
            y_jump[k] = float(cv_dist(fut_phi, fut_psi, phi[end], psi[end]).mean())
        name = nearest_basin(float(phi[end]), float(psi[end]), BASIN_RADIUS)
        if name is None:
            d = cv_dist(fut_phi, fut_psi, phi[end], psi[end]) if fut_phi.size else np.array([0.0])
            y_esc[k] = float(np.clip((float(d.max()) - 20.0) / 40.0, 0.0, 1.0))
        else:
            stayed = in_basin(fut_phi, fut_psi, BASINS[name], BASIN_RADIUS) if fut_phi.size else np.array([1.0])
            y_esc[k] = float(1.0 - stayed.mean())
    y = np.clip(0.45 * y_phi + 0.40 * y_new + 0.15 * y_esc, 0.0, 1.0)
    return {
        "y": y,
        "y_escape": y_esc,
        "y_newbin": y_new,
        "y_phi": y_phi,
        "y_jump_deg": y_jump,
    }


def build_windows(segments, window, horizon, stride, nbins, rare_frac, label: str):
    if label != "discover":
        return s07.build_windows(
            segments, window, horizon, stride, nbins, rare_frac, label=label, resample=True
        )
    prior_phi, prior_psi = [], []
    Xs, ys, extra = [], [], []
    for si, seg in enumerate(segments):
        t_ps, phi, psi = s07._seg_arrays(seg, resample=True)
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
            labels = discover_labels(phi_cat, psi_cat, starts + offset, window, horizon, nbins)
        else:
            labels = discover_labels(phi, psi, starts, window, horizon, nbins)
        Xs.append(X)
        ys.append(labels["y"])
        end = starts + window - 1
        extra.append(
            {
                "seg_id": np.full(len(starts), si, dtype=np.int32),
                "end_idx": end,
                "t_end_ps": t_ps[end],
                "phi_end": phi[end],
                "psi_end": psi[end],
                "y_diff": labels["y_jump_deg"],
                "y_reach": labels["y_escape"],
                "y_phi": labels["y_phi"],
                "y_newbin": labels["y_newbin"],
            }
        )
        prior_phi.append(phi)
        prior_psi.append(psi)
    if not Xs:
        raise TapsError("no windows; lower --window-ps/--horizon-ps or raise --init-ns")
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
    log(
        f"  labels  y={pack['y'].mean():.3f}  phi={np.concatenate([e['y_phi'] for e in extra]).mean():.3f}  "
        f"newbin={np.concatenate([e['y_newbin'] for e in extra]).mean():.3f}  "
        f"esc={pack['y_reach'].mean():.3f}"
    )
    return pack


def last_frontier_scores(phi_all, psi_all, phi_q, psi_q, nbins: int = 24) -> np.ndarray:
    """LAST-like: 2D PCA of trig(φ,ψ); high score on the rim of the sampled cloud."""
    feats_all = s03.encode_trig(phi_all, psi_all)
    feats_q = s03.encode_trig(phi_q, psi_q)
    mu = feats_all.mean(axis=0)
    xc = feats_all - mu
    _, _, vt = np.linalg.svd(xc, full_matrices=False)
    w = vt[:2].T
    z = xc @ w
    zq = (feats_q - mu) @ w
    lo = z.min(axis=0)
    hi = z.max(axis=0)
    span = np.maximum(hi - lo, 1e-6)
    lo = lo - 0.05 * span
    hi = hi + 0.05 * span
    hist, xedges, yedges = np.histogram2d(
        z[:, 0], z[:, 1], bins=nbins, range=[[lo[0], hi[0]], [lo[1], hi[1]]]
    )
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


def select_and_dump(spec, pack, scores, method, n_seeds, min_deg, segments, seed_dir: Path) -> list:
    phi_e = wrap_deg(pack["phi_end"])
    psi_e = wrap_deg(pack["psi_end"])
    pool = s07.concat_pool(segments)
    rho = s05.density_at(pool["phi"], pool["psi"], phi_e, psi_e, 36)
    inv = 1.0 / (rho + 1e-6)
    inv = inv / (inv.max() + 1e-12)
    if method == "density":
        raw = inv
    elif method == "last":
        raw = last_frontier_scores(pool["phi"], pool["psi"], phi_e, psi_e)
    else:
        raw = np.asarray(scores, dtype=np.float64) * inv
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
            "S_p": float(scores[idx]) if scores is not None else 0.0,
            "rho": float(rho[idx]),
            "score": float(raw[idx]),
            "gro": str(gro.relative_to(ROOT)),
        }
        records.append(rec)
        log(
            f"  seed {rank:02d}  {seg['name']}  t={rec['t_ps']:.1f}  "
            f"φ={rec['phi']:.1f} ψ={rec['psi']:.1f}  score={rec['score']:.3f}"
        )
    return records


def first_time_ns(mask: np.ndarray, t_ps: np.ndarray):
    hit = np.flatnonzero(mask)
    if hit.size == 0:
        return None
    return float(t_ps[int(hit[0])]) / 1000.0


def discovery_stats(phi, psi, t_ps) -> dict:
    phi = wrap_deg(phi)
    psi = wrap_deg(psi)
    d_c7ax = cv_dist(phi, psi, BASINS["c7ax"][0], BASINS["c7ax"][1])
    fpt = basin_fpt_ps(phi, psi, t_ps, "c7ax")
    return {
        "coverage": float(rama_coverage(phi, psi, 36)),
        "n_frames": int(len(phi)),
        "sim_ns": float(t_ps[-1] / 1000.0) if len(t_ps) else 0.0,
        "max_phi": float(np.max(phi)) if len(phi) else None,
        "min_dist_c7ax": float(np.min(d_c7ax)) if len(d_c7ax) else None,
        "frac_phi_pos": float((phi > 0.0).mean()) if len(phi) else 0.0,
        "n_near_c7ax": int((d_c7ax <= BASIN_RADIUS).sum()),
        "first_phi_pos_ns": first_time_ns(phi > 0.0, t_ps),
        "first_phi_30_ns": first_time_ns(phi > 30.0, t_ps),
        "c7ax_fpt_ns": None if fpt is None else fpt / 1000.0,
    }


def snapshot(segments, nbins: int) -> dict:
    pool = s07.concat_pool(segments)
    stats = discovery_stats(pool["phi"], pool["psi"], pool["t_accum_ps"])
    stats["n_segments"] = len(segments)
    stats["sim_ns"] = float(pool["sim_ns"])
    stats["coverage"] = float(rama_coverage(pool["phi"], pool["psi"], nbins))
    return stats


def fmt(v, nd=3):
    if v is None:
        return "none"
    return f"{v:.{nd}f}"


def run_one_method(args, method: str, tag: str, nt: int, gpu: bool) -> dict:
    spec = get_spec(args.system, tag=tag)
    spec.outdir.mkdir(parents=True, exist_ok=True)
    short_ns = args.n_seeds * args.short_ps / 1000.0
    remain = max(0.0, args.budget_ns - args.init_ns)
    auto_rounds = int(np.ceil(remain / short_ns)) if short_ns > 0 else 0
    n_rounds = args.max_rounds if args.max_rounds > 0 else auto_rounds
    window = int(args.window_ps)
    horizon = int(args.horizon_ps)
    stride = int(args.stride_ps)
    log(
        f"==== method={method} tag={tag}  init={args.init_ns} ns  budget={args.budget_ns} ns  "
        f"short={args.short_ps} ps  seeds={args.n_seeds}  rounds={n_rounds}  "
        f"T={window} M={horizon}  nt={nt} gpu={gpu} ===="
    )
    if args.short_ps + 1e-6 < window + horizon:
        raise TapsError(f"short-ps={args.short_ps} < T+M={window + horizon}; 1 ns shorts are required")

    segments = s07.rebuild_segments(spec, args.init_ns)
    if any(s["name"].startswith("init_extra") for s in segments):
        raise TapsError(
            f"{tag} already has init_extra segments. Discovery setting forbids C7ax injection. "
            f"Use a new --tag-prefix or delete {spec.outdir}"
        )
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
        f"maxφ={fmt(snap0['max_phi'], 1)}  minΔC7ax={fmt(snap0['min_dist_c7ax'], 1)}  "
        f"C7ax_FPT={snap0['c7ax_fpt_ns']}"
    )
    if not history:
        history.append({"round": 0, **snap0})
        s07.save_pool(spec, segments, history)

    done = {h["round"] for h in history if h["round"] > 0}
    for rid in range(1, n_rounds + 1):
        if rid in done and not args.force:
            log(f"round {rid:02d}: already in history -> skip")
            continue
        if s07.concat_pool(segments)["sim_ns"] >= args.budget_ns - 1e-6:
            log(f"reached budget {args.budget_ns} ns; stop")
            break
        log(f"---- {tag} round {rid:02d} / {n_rounds} ----")
        pack = build_windows(segments, window, horizon, stride, args.nbins, args.rare_frac, args.label)
        log(f"  windows={len(pack['X'])}")
        np.savez_compressed(
            spec.outdir / "windows.npz",
            X=pack["X"],
            end_idx=pack["end_idx"],
            t_end_ps=pack["t_end_ps"],
            phi_end=pack["phi_end"],
            psi_end=pack["psi_end"],
            seg_id=pack["seg_id"],
            y=pack["y"],
            window=np.array(pack["window"]),
            horizon=np.array(pack["horizon"]),
            stride=np.array(pack["stride"]),
        )
        seeds_json = spec.outdir / f"seeds_round{rid:02d}.json"
        if seeds_json.exists() and not args.force:
            records = json.loads(seeds_json.read_text(encoding="utf-8")).get("seeds") or []
            log(f"  reuse {seeds_json.name} ({len(records)} seeds)")
        else:
            if method == "taps":
                scores = s07.train_sp(pack, spec.outdir, args.epochs, args.seed)
            else:
                scores = np.ones(len(pack["X"]), dtype=np.float64)
            seed_dir = spec.outdir / f"seeds_r{rid:02d}"
            records = select_and_dump(
                spec, pack, scores, method, args.n_seeds, args.min_deg, segments, seed_dir
            )
            seeds_json.write_text(
                json.dumps({"method": method, "round": rid, "seeds": records}, indent=2) + "\n",
                encoding="utf-8",
            )
        new_segs = s07.run_short_round(spec, records, rid, nt, gpu, args.force, short_mdp=SHORT_MDP)
        segments.extend(new_segs)
        snap = snapshot(segments, args.nbins)
        history.append({"round": rid, **snap})
        s07.save_pool(spec, segments, history)
        log(
            f"round {rid:02d} done  sim={snap['sim_ns']:.3f} ns  cov={snap['coverage']:.4f}  "
            f"maxφ={fmt(snap['max_phi'], 1)}  minΔC7ax={fmt(snap['min_dist_c7ax'], 1)}  "
            f"φ>0={fmt(snap['first_phi_pos_ns'])}  C7ax_FPT={snap['c7ax_fpt_ns']}"
        )
    final = snapshot(segments, args.nbins)
    (spec.outdir / "discover_stats.json").write_text(json.dumps(final, indent=2) + "\n", encoding="utf-8")
    log(f"method {method} finished  {spec.outdir.relative_to(ROOT)}")
    return {"tag": tag, "method": method, **final, "outdir": str(spec.outdir)}


def cmd_stats(system: str, budget_ns: float) -> dict:
    src = get_spec(system)
    data = load_dihedrals(src)
    t_ps = np.asarray(data["t_ps"])
    mask = t_ps <= budget_ns * 1000.0 + 1e-6
    stats = discovery_stats(data["phi"][mask], data["psi"][mask], t_ps[mask])
    stats["method"] = "cmd"
    stats["tag"] = "cmd"
    return stats


def write_report(args, results: list, cmd: dict, outdir: Path) -> Path:
    outdir.mkdir(parents=True, exist_ok=True)
    lines = [
        "STAGE 12  discovery + LAST + 1 ns shorts",
        f"system={args.system}  prefix={args.tag_prefix}  init={args.init_ns} ns  "
        f"budget={args.budget_ns} ns  short={args.short_ps} ps  n_seeds={args.n_seeds}",
        "NO extra-init (C7ax must be discovered, not injected).",
        "",
        f"{'method':<10s} {'sim_ns':>7s} {'cov':>7s} {'maxφ':>8s} {'minΔC7ax':>9s} "
        f"{'φ>0 ns':>8s} {'φ>30 ns':>8s} {'C7ax FPT':>9s} {'φ>0 frac':>8s}",
        "-" * 88,
    ]

    def row(r):
        return (
            f"{r['method']:<10s} {r['sim_ns']:7.2f} {r['coverage']:7.4f} "
            f"{fmt(r.get('max_phi'), 1):>8s} {fmt(r.get('min_dist_c7ax'), 1):>9s} "
            f"{fmt(r.get('first_phi_pos_ns')):>8s} {fmt(r.get('first_phi_30_ns')):>8s} "
            f"{fmt(r.get('c7ax_fpt_ns')):>9s} {fmt(r.get('frac_phi_pos')):>8s}"
        )

    lines.append(row(cmd))
    for r in results:
        lines.append(row(r))
    lines += [
        "",
        "How to read this (discovery, not occupancy):",
        "  maxφ / minΔC7ax : did anyone leave the C7eq/C5 half-plane and approach C7ax?",
        "  φ>0 ns / C7ax FPT : first hitting time. 'none' = not discovered.",
        "  LAST is the latent-space rim; Least-counts (density) is 1/ρ on Ramachandran.",
        "  TAPS is only interesting if it reaches +φ or C7ax earlier than LAST, or gets closer.",
        "  Coverage alone is not enough — previous rounds already beat cMD without discovering C7ax.",
        "",
    ]
    adaptive = [r for r in results if r["method"] != "cmd"]
    if adaptive:
        best_phi = max(adaptive, key=lambda r: -1e9 if r.get("max_phi") is None else r["max_phi"])
        best_d = min(adaptive, key=lambda r: 1e9 if r.get("min_dist_c7ax") is None else r["min_dist_c7ax"])
        found = [r["method"] for r in adaptive if r.get("c7ax_fpt_ns") is not None]
        pos = [r["method"] for r in adaptive if r.get("first_phi_pos_ns") is not None]
        lines.append(f"closest to C7ax : {best_d['method']}  minΔ={fmt(best_d.get('min_dist_c7ax'), 1)}°")
        lines.append(f"largest φ       : {best_phi['method']}  maxφ={fmt(best_phi.get('max_phi'), 1)}°")
        lines.append(f"reached φ>0     : {', '.join(pos) if pos else 'nobody'}")
        lines.append(f"reached C7ax    : {', '.join(found) if found else 'nobody'}")
        taps = next((r for r in adaptive if r["method"] == "taps"), None)
        last = next((r for r in adaptive if r["method"] == "last"), None)
        if taps and last and taps.get("min_dist_c7ax") is not None and last.get("min_dist_c7ax") is not None:
            delta = last["min_dist_c7ax"] - taps["min_dist_c7ax"]
            if taps.get("c7ax_fpt_ns") is not None and last.get("c7ax_fpt_ns") is None:
                lines.append("verdict hint: TAPS discovered C7ax and LAST did not — this setting has paper value.")
            elif delta > 15.0 or (
                taps.get("first_phi_pos_ns") is not None and last.get("first_phi_pos_ns") is None
            ):
                lines.append("verdict hint: TAPS got clearly closer to +φ / C7ax than LAST — worth a second look.")
            elif abs(delta) < 8.0 and abs((taps.get("max_phi") or 0) - (last.get("max_phi") or 0)) < 10:
                lines.append("verdict hint: TAPS ≈ LAST on discovery metrics — still not enough for the paper claim.")
            else:
                lines.append("verdict hint: mixed; inspect seed φ/ψ and coverage curves before deciding.")
    text = "\n".join(lines) + "\n"
    report = outdir / "report.txt"
    report.write_text(text, encoding="utf-8")
    payload = {"cmd": cmd, "methods": results, "args": vars(args)}
    (outdir / "summary.json").write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    log(f"report -> {report.relative_to(ROOT)}")
    print(text)
    return report


def parse_methods(text: str) -> list:
    allowed = ("taps", "last", "density")
    out = []
    for raw in text.split(","):
        name = raw.strip().lower()
        if not name:
            continue
        if name in ("lc", "least", "least-counts", "least_counts"):
            name = "density"
        if name not in allowed:
            raise TapsError(f"unknown method {raw!r}; use taps, last, density")
        if name not in out:
            out.append(name)
    if not out:
        raise TapsError("no methods")
    return out


def plan_ns(args, n_methods: int) -> float:
    short_ns = args.n_seeds * args.short_ps / 1000.0
    remain = max(0.0, args.budget_ns - args.init_ns)
    n_rounds = args.max_rounds if args.max_rounds > 0 else (int(np.ceil(remain / short_ns)) if short_ns else 0)
    return n_methods * n_rounds * short_ns


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--system", default="ala2_vacuum", choices=("ala2_vacuum",))
    p.add_argument("--tag-prefix", default="discover", help="campaigns become <prefix>_taps / _last / _lc")
    p.add_argument("--methods", default="taps,last,density", help="comma list: taps,last,density")
    p.add_argument("--init-ns", type=float, default=2.0)
    p.add_argument("--budget-ns", type=float, default=22.0)
    p.add_argument("--max-rounds", type=int, default=0, help="0 = infer from budget")
    p.add_argument("--n-seeds", type=int, default=4)
    p.add_argument("--short-ps", type=float, default=1000.0)
    p.add_argument("--label", default="discover", choices=("discover", "escape", "mixed"))
    p.add_argument("--window-ps", type=float, default=50.0)
    p.add_argument("--horizon-ps", type=float, default=200.0)
    p.add_argument("--stride-ps", type=float, default=10.0)
    p.add_argument("--nbins", type=int, default=36)
    p.add_argument("--rare-frac", type=float, default=0.25)
    p.add_argument("--min-deg", type=float, default=30.0)
    p.add_argument("--epochs", type=int, default=15)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--nt", type=int, default=int(os.environ.get("TAPS_NT", "0") or 0))
    p.add_argument("--cpu", action="store_true")
    p.add_argument("--gpu", action="store_true")
    p.add_argument("--force", action="store_true")
    p.add_argument("--check", action="store_true")
    args = p.parse_args(argv)
    try:
        methods = parse_methods(args.methods)
        spec = get_spec(args.system)
        log(f"STAGE 12  discovery + LAST + 1 ns  system={args.system}  methods={','.join(methods)}")
        try:
            load_dihedrals(spec)
        except TapsError as exc:
            log(str(exc), "ERROR")
            return 2
        if not (spec.workdir / spec.prod_xtc).exists() or not (spec.workdir / spec.prod_tpr).exists():
            log(f"missing {spec.prod_xtc} or {spec.prod_tpr}", "ERROR")
            return 2
        mdp = spec.workdir / "mdp" / SHORT_MDP
        if not mdp.exists():
            log(f"missing {mdp}", "ERROR")
            return 2
        if abs(args.short_ps - 1000.0) > 1e-6:
            log(f"short-ps={args.short_ps} but MDP is 1 ns; keep --short-ps 1000 unless you changed the MDP", "WARN")
        md = load_dihedrals(spec)
        init_mask = md["t_ps"] <= args.init_ns * 1000.0 + 1e-6
        init_stats = discovery_stats(md["phi"][init_mask], md["psi"][init_mask], md["t_ps"][init_mask])
        if init_stats["c7ax_fpt_ns"] is not None or init_stats["first_phi_pos_ns"] is not None:
            log("init prefix already has φ>0 or C7ax; discovery contrast will be weak", "WARN")
        md_ns = plan_ns(args, len(methods))
        log(
            f"init  {args.init_ns:.1f} ns  cov={init_stats['coverage']:.4f}  "
            f"maxφ={fmt(init_stats['max_phi'], 1)}  minΔC7ax={fmt(init_stats['min_dist_c7ax'], 1)}°  "
            f"(must start from C7eq side)"
        )
        log(f"will run ~{md_ns:.1f} ns new short MD across {len(methods)} method(s)  (resumable)")
        log("discovery: extra-init / c7ax.gro is disabled")
        if args.check:
            for method in methods:
                tag = f"{args.tag_prefix}_{METHOD_TAGS[method]}"
                log(f"  would write analysis/{args.system}/campaigns/{tag}/")
            log("check passed")
            return 0

        import run_md

        nt = args.nt or run_md.default_thread_count()
        gpu = False if args.cpu else (True if args.gpu else run_md.detect_gpu())
        results = []
        for method in methods:
            tag = f"{args.tag_prefix}_{METHOD_TAGS[method]}"
            results.append(run_one_method(args, method, tag, nt, gpu))
        cmd = cmd_stats(args.system, args.budget_ns)
        report_dir = ANALYSIS / args.system / "discover_last"
        write_report(args, results, cmd, report_dir)
        return 0
    except TapsError as exc:
        log(str(exc), "ERROR")
        return 1


if __name__ == "__main__":
    sys.exit(main())
