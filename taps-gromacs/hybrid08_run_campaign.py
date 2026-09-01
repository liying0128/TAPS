#!/usr/bin/env python3
"""
HYBRID 08  |  Workflow §7  真正的 LAST→TAPS 固定切换 campaign（新 MD）

和 Hybrid 05 离线拼接不同：后半段 TAPS 是在「已经先跑过 LAST」的池子上
重新训练、重新选 seed、重新发短轨迹。

标签改成 FEU（novelty/diversity/discovery/commitment），不再用 RMSD drop。
成功标准看 first_commit / residence / re-exploit，不看 first-hit。

默认顺序 Hybrid-3 → Hybrid-2 → Hybrid-1（H3 离线筛选最好）。
同预算：10 ns init + 12 × 6 × 1 ns = 82 ns。

  python3 hybrid08_run_campaign.py --check
  python3 hybrid08_run_campaign.py --gpu
  python3 hybrid08_run_campaign.py --analyze-only

输出: analysis/cln025_unfolded/campaigns/hybrid{1_25,2_50,3_75}/
      analysis/hybrid/hybrid_campaign_report.txt
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import hybrid01_build_candidates as h01  # noqa: E402
import run_md  # noqa: E402
import stage07_multi_round as s07  # noqa: E402
import stage13_cln025_discover as s13  # noqa: E402
from hybrid_common import COMMIT_PS, FOLD_RMSD, feu_from_future, feu_score, hybrid_outdir  # noqa: E402
from hybrid_metrics import fmt_productive, productive_metrics  # noqa: E402
from taps_common import ANALYSIS, TapsError, log  # noqa: E402

SCHEDULES = {
    "hybrid3_75": 0.75,
    "hybrid2_50": 0.50,
    "hybrid1_25": 0.25,
    "hybrid_cov": -1.0,  # coverage-gain switch (Workflow §8)
}

COV_SWITCH_WINDOW = 3
COV_SWITCH_EPS = 0.003


def n_last_rounds(n_rounds: int, last_frac: float) -> int:
    if last_frac < 0:
        return -1
    return max(1, min(n_rounds - 1, int(round(last_frac * n_rounds))))


def method_for_round(rid: int, n_last: int, switched: bool = False) -> str:
    if n_last < 0:
        return "taps" if switched else "last"
    return "last" if rid <= n_last else "taps"


def build_feu_windows(segments, window: int, horizon: int, stride: int, nbins: int):
    """Online FEU labels. dt = 2 ps after resample. No future leak across the seed."""
    prepared = []
    for seg in segments:
        t_ps, rmsd, rg = s13.resample_2ps(seg["t_ps"], seg["rmsd"], seg["rg"])
        bi, bj = s13.to_bins_rect(rmsd, rg, nbins)
        prepared.append(
            {
                "name": seg["name"],
                "t_ps": t_ps,
                "rmsd": rmsd,
                "rg": rg,
                "flat": bi * nbins + bj,
                "target": rmsd < FOLD_RMSD,
                "feats": s13.encode_cv(rmsd, rg),
                "raw": seg,
            }
        )
    Xs, ys, extra = [], [], []
    prior_flat = []
    for si, seg in enumerate(prepared):
        n = len(seg["rmsd"])
        last_start = n - window - horizon
        if last_start < 0:
            prior_flat.append(seg["flat"])
            continue
        starts = np.arange(0, last_start + 1, stride, dtype=np.int64)
        X = np.stack([seg["feats"][s : s + window] for s in starts], axis=0)
        prior = np.concatenate(prior_flat) if prior_flat else np.zeros(0, dtype=np.int64)
        y = np.zeros(len(starts), dtype=np.float64)
        y_disc = np.zeros(len(starts), dtype=np.float64)
        y_comm = np.zeros(len(starts), dtype=np.float64)
        for k, st in enumerate(starts):
            end = int(st + window - 1)
            past = np.concatenate([prior, seg["flat"][: end + 1]]) if prior.size else seg["flat"][: end + 1]
            fut = slice(end + 1, end + 1 + horizon)
            comp = feu_from_future(
                past,
                seg["flat"][fut],
                seg["target"][fut],
                bool(seg["target"][end]),
                2.0,
                COMMIT_PS,
            )
            y[k] = feu_score(comp)
            y_disc[k] = comp["discovery"]
            y_comm[k] = comp["commitment"]
        Xs.append(X)
        ys.append(y)
        extra.append(
            {
                "seg_id": np.full(len(starts), si, dtype=np.int32),
                "end_idx": starts + window - 1,
                "t_end_ps": seg["t_ps"][starts + window - 1],
                "rmsd_end": seg["rmsd"][starts + window - 1],
                "rg_end": seg["rg"][starts + window - 1],
                "y_disc": y_disc,
                "y_comm": y_comm,
            }
        )
        prior_flat.append(seg["flat"])
    if not Xs:
        raise TapsError("no FEU windows; lower --window-ps/--horizon-ps or raise --init-ns")
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
        f"  FEU labels  y={pack['y'].mean():.3f}  disc={np.concatenate([e['y_disc'] for e in extra]).mean():.3f}  "
        f"comm={np.concatenate([e['y_comm'] for e in extra]).mean():.3f}  n={len(pack['y'])}"
    )
    return pack


def run_one_hybrid(args, tag: str, last_frac: float, nt: int, gpu: bool) -> dict:
    spec = replace(s13.ClnSpec(), tag=tag)
    spec.outdir.mkdir(parents=True, exist_ok=True)
    n_rounds = args.max_rounds
    n_last = n_last_rounds(n_rounds, last_frac)
    window = int(round(args.window_ps / 2.0))
    horizon = int(round(args.horizon_ps / 2.0))
    stride = int(round(args.stride_ps / 2.0))
    if n_last < 0:
        log(
            f"==== {tag}  LAST→TAPS by coverage gain  "
            f"init={args.init_ns} ns  budget={args.budget_ns} ns  nt={nt} gpu={gpu} ===="
        )
    else:
        log(
            f"==== {tag}  LAST rounds 1-{n_last}  TAPS {n_last + 1}-{n_rounds}  "
            f"init={args.init_ns} ns  budget={args.budget_ns} ns  nt={nt} gpu={gpu} ===="
        )
    (spec.outdir / "schedule.json").write_text(
        json.dumps({"tag": tag, "last_frac": last_frac, "n_last": n_last, "n_rounds": n_rounds}, indent=2) + "\n"
    )
    segments = s13.rebuild_segments(spec, args.init_ns)
    history = []
    hist_path = spec.outdir / "history.json"
    if hist_path.exists() and not args.force:
        try:
            history = json.loads(hist_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            history = []
    snap0 = s13.snapshot(segments, args.nbins)
    log(f"start  sim={snap0['sim_ns']:.3f} ns  cov={snap0['coverage']:.4f}  minRMSD={s13.fmt(snap0['min_rmsd'])}")
    if not history:
        history.append({"round": 0, "method": "init", **snap0})
        s13.save_pool(spec, segments, history)
    done = {h["round"] for h in history if h["round"] > 0}
    switched = any(h.get("method") == "taps" for h in history if h.get("round", 0) > 0)
    for rid in range(1, n_rounds + 1):
        if rid in done and not args.force:
            log(f"round {rid:02d}: already in history -> skip")
            continue
        if s13.concat_pool(segments)["sim_ns"] >= args.budget_ns - 1e-6:
            log(f"reached budget {args.budget_ns} ns; stop")
            break
        if n_last < 0 and not switched and rid > COV_SWITCH_WINDOW:
            covs = [float(h.get("coverage", 0.0)) for h in history]
            gains = [covs[i] - covs[i - 1] for i in range(1, len(covs))]
            tail = gains[-COV_SWITCH_WINDOW:]
            if len(tail) >= COV_SWITCH_WINDOW and all(g < COV_SWITCH_EPS for g in tail):
                switched = True
                log(f"  coverage saturated (last {COV_SWITCH_WINDOW} Δcov={tail}) -> switch to TAPS")
        method = method_for_round(rid, n_last, switched)
        log(f"---- {tag} round {rid:02d}/{n_rounds}  method={method} ----")
        pack = build_feu_windows(segments, window, horizon, stride, args.nbins)
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
            records = s13.select_and_dump(
                spec, pack, scores, method, args.n_seeds, args.min_nm, segments, spec.outdir / f"seeds_r{rid:02d}"
            )
            seeds_json.write_text(
                json.dumps({"method": method, "round": rid, "switch": "last_then_taps", "seeds": records}, indent=2) + "\n"
            )
        new_segs = s13.run_short_round(spec, records, rid, nt, gpu, args.force)
        segments.extend(new_segs)
        snap = s13.snapshot(segments, args.nbins)
        history.append({"round": rid, "method": method, **snap})
        s13.save_pool(spec, segments, history)
        log(
            f"round {rid:02d} done  method={method}  sim={snap['sim_ns']:.3f} ns  "
            f"cov={snap['coverage']:.4f}  minRMSD={s13.fmt(snap['min_rmsd'])}  "
            f"foldFPT={snap['first_fold_ns']}"
        )
    final = s13.snapshot(segments, args.nbins)
    (spec.outdir / "discover_stats.json").write_text(json.dumps({"tag": tag, **final}, indent=2) + "\n")
    return {"tag": tag, "n_last": n_last, **final}


def analyze_all(budget_ns: float) -> str:
    rows = []
    jobs = [
        ("cmd_matched", None),
        ("lc", "discover_lc"),
        ("last", "discover_last"),
        ("taps", "discover_taps"),
        ("hybrid1_25", "hybrid1_25"),
        ("hybrid2_50", "hybrid2_50"),
        ("hybrid3_75", "hybrid3_75"),
        ("hybrid_cov", "hybrid_cov"),
        ("hybrid3_75_s1", "hybrid3_75_s1"),
        ("hybrid2_50_s1", "hybrid2_50_s1"),
    ]
    cmd = h01.load_cln_source("cmd")
    pack = h01.concat_resample(cmd, "cln")
    t = pack["t_ps"]
    dt = float(t[1] - t[0])
    m = t <= t[0] + budget_ns * 1000.0 - dt + 1e-6
    rec = productive_metrics("cln", t[m], pack["x"][m], pack["y"][m], pack["seg"][m])
    rec["label"] = "cmd_matched"
    rows.append(rec)
    for label, tag in jobs[1:]:
        camp = ANALYSIS / "cln025_unfolded" / "campaigns" / tag
        if not (camp / "history.json").exists():
            continue
        try:
            segs = h01.load_cln_source(tag)
        except TapsError as exc:
            log(f"skip {tag}: {exc}", "WARN")
            continue
        p = h01.concat_resample(segs, "cln")
        rec = productive_metrics("cln", p["t_ps"], p["x"], p["y"], p["seg"])
        rec["label"] = label
        rows.append(rec)
    lines = [
        "HYBRID 08  CLN025 real LAST→TAPS campaigns",
        f"commit≥{COMMIT_PS:.0f} ps   first_hit is not the success metric",
        "",
    ]
    for rec in rows:
        lines.append(fmt_productive(rec["label"], rec))
    last = next((r for r in rows if r["label"] == "last"), None)
    lines.append("")
    if last:
        lines.append("vs LAST (positive = better):")
        for rec in rows:
            if not rec["label"].startswith("hybrid"):
                continue
            lines.append(
                f"  {rec['label']:16s}  Δcov={rec['coverage'] - last['coverage']:+.4f}  "
                f"Δfrac={rec['frac_target'] - last['frac_target']:+.4f}  "
                f"commit {rec['first_commit_ns']} vs LAST {last['first_commit_ns']}  "
                f"reexploit {rec['reexploit_segments']} vs {last['reexploit_segments']}"
            )
    last_c = next((r for r in rows if r["label"] == "last"), None)
    hybrids = [r for r in rows if r["label"].startswith("hybrid")]
    go = False
    if last_c and hybrids:
        go = any(
            (h["frac_target"] > last_c["frac_target"] + 1e-4 and not h["transient_only"])
            or (h["committed_visits"] > last_c["committed_visits"])
            for h in hybrids
        )
    lines.append("")
    lines.append("Go/No-Go for this campaign set:")
    if not hybrids:
        lines.append("  no hybrid campaign finished yet")
    elif go:
        lines.append("  at least one hybrid beat LAST on committed fold time or re-exploitation.")
    else:
        lines.append("  no hybrid beat LAST on committed discovery / residence. Do not claim Hybrid>LAST.")
    text = "\n".join(lines) + "\n"
    dest = hybrid_outdir() / "hybrid_campaign_report.txt"
    dest.write_text(text, encoding="utf-8")
    print(text)
    return text


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--schedules", default="hybrid3_75,hybrid2_50,hybrid1_25")
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
    p.add_argument("--analyze-only", action="store_true")
    p.add_argument("--tag-suffix", default="", help="append to campaign tag, e.g. _s1 for a replicate")
    args = p.parse_args(argv)
    try:
        names = [x.strip() for x in args.schedules.split(",") if x.strip()]
        for n in names:
            if n not in SCHEDULES:
                raise TapsError(f"unknown schedule {n}; choose from {list(SCHEDULES)}")
        if args.analyze_only:
            analyze_all(args.budget_ns)
            return 0
        if args.check:
            for n in names:
                n_last = n_last_rounds(args.max_rounds, SCHEDULES[n])
                tag = n + args.tag_suffix
                if n_last < 0:
                    log(f"  {tag}: LAST until coverage gain < {COV_SWITCH_EPS} for {COV_SWITCH_WINDOW} rounds")
                else:
                    log(f"  {tag}: LAST 1-{n_last} then TAPS {n_last + 1}-{args.max_rounds}")
            log(f"prod finished: {s13.prod_finished()}")
            return 0
        if not s13.prod_finished():
            raise TapsError("unfolded 100 ns cMD not finished")
        s13.ensure_cmd_cvs(force=args.force)
        nt = args.nt or run_md.default_thread_count()
        gpu = False if args.cpu else (True if args.gpu else run_md.detect_gpu())
        md_ns = len(names) * args.n_seeds * args.max_rounds * (args.short_ps / 1000.0)
        log(f"HYBRID 08  planned short MD ~{md_ns:.0f} ns  (~{md_ns / 1600.0 * 24:.1f} h at 1600 ns/day)")
        for name in names:
            run_one_hybrid(args, name + args.tag_suffix, SCHEDULES[name], nt, gpu)
            analyze_all(args.budget_ns)
        analyze_all(args.budget_ns)
        return 0
    except TapsError as exc:
        log(str(exc), "ERROR")
        return 1


if __name__ == "__main__":
    sys.exit(main())
