#!/usr/bin/env python3
"""MOAS Phase 1: offline dry-run on existing CLN025 candidates. No GROMACS, no DL.

Reads data/candidates/cln_candidates.npz, scores causal objectives, and compares
LAST / least-counts / random / MOAS-static / MOAS-dynamic / Pareto against
committed-exploration labels (residence ≥ 40 ps in the 200 ps horizon).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluation.ranking import fmt_rank, jaccard, ranking_metrics, topk_set  # noqa: E402
from moas_common import COMMIT_PS, DATA, FOLD_RMSD_NM, RESULTS  # noqa: E402
from objectives.boundary import boundary_score  # noqa: E402
from objectives.commitment import commitment_labels, commitment_proxy_rmsd  # noqa: E402
from objectives.information_gain import information_gain_score  # noqa: E402
from objectives.kinetic import kinetic_score  # noqa: E402
from objectives.novelty import novelty_score  # noqa: E402
from objectives.uncertainty import uncertainty_score  # noqa: E402
from policies.dynamic_rule import STAGE_WEIGHTS, stage_by_time_rank  # noqa: E402
from policies.fixed_weight import WEIGHT_MODES  # noqa: E402
from scoring.normalization import percentile_rank  # noqa: E402
from scoring.pareto import pareto_mask  # noqa: E402
from scoring.weighted_utility import weighted_utility  # noqa: E402
from selection.diversity import greedy_maxmin  # noqa: E402

HORIZON = 200
VAL_FRAC = 0.30
TOPK = 100
RNG = np.random.default_rng(0)


def time_split(source: np.ndarray, t_ps: np.ndarray, val_frac: float = VAL_FRAC):
    tr, va = [], []
    for src in np.unique(source):
        idx = np.flatnonzero(source == src)
        order = idx[np.argsort(t_ps[idx])]
        n_val = max(1, int(round(len(order) * val_frac)))
        n_tr = len(order) - n_val
        if n_tr < 8:
            tr.extend(order.tolist())
            continue
        tr.extend(order[:n_tr].tolist())
        va.extend(order[n_tr:].tolist())
    return np.asarray(tr, dtype=np.int64), np.asarray(va, dtype=np.int64)


def finite(arr: dict, *keys):
    m = np.ones(len(arr["t_ps"]), dtype=bool)
    for k in keys:
        m &= np.isfinite(np.asarray(arr[k], dtype=np.float64))
    return m


def pairwise_mean_dist(xy: np.ndarray) -> float:
    if len(xy) < 2:
        return 0.0
    d = np.sqrt(((xy[:, None, :] - xy[None, :, :]) ** 2).sum(axis=2))
    iu = np.triu_indices(len(xy), k=1)
    return float(d[iu].mean())


def dynamic_utility(norm: dict, stages: list) -> np.ndarray:
    n = len(stages)
    out = np.zeros(n, dtype=np.float64)
    for stage, w in STAGE_WEIGHTS.items():
        sel = np.array([s == stage for s in stages], dtype=bool)
        if not sel.any():
            continue
        sub = {k: v[sel] for k, v in norm.items()}
        out[sel] = weighted_utility(sub, w)
    return out


def main() -> int:
    cand_path = DATA / "candidates" / "cln_candidates.npz"
    outdir = RESULTS / "phase1_offline_cln025"
    outdir.mkdir(parents=True, exist_ok=True)
    log_path = outdir / "run.log"

    def log(msg: str):
        print(msg, flush=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(msg + "\n")

    log_path.write_text("", encoding="utf-8")
    log("MOAS Phase 1  CLN025 offline dry-run  (no MD, no DL)")
    log(f"candidates: {cand_path}")
    log(f"fold RMSD < {FOLD_RMSD_NM} nm   commit ≥ {COMMIT_PS} ps   horizon={HORIZON} ps")

    raw = np.load(cand_path, allow_pickle=True)
    arr = {k: raw[k] for k in raw.files}
    n = len(arr["t_ps"])
    src, cnt = np.unique(arr["source"], return_counts=True)
    log(f"n={n}  sources: " + ", ".join(f"{s}={c}" for s, c in zip(src, cnt)))

    y_commit = np.asarray(arr[f"comm_{HORIZON}"], dtype=np.float64)
    y_disc_c = np.asarray(arr[f"disc_commit_{HORIZON}"], dtype=np.float64)
    y_disc = np.asarray(arr[f"disc_{HORIZON}"], dtype=np.float64)
    ok = finite(arr, f"comm_{HORIZON}", f"disc_commit_{HORIZON}", "rho", "last_score", "msd_x_50")
    n_ok = int(ok.sum())
    trans_ratio = float(((y_disc > 0) & (y_disc_c <= 0) & ok).sum() / max(1, int(((y_disc > 0) & ok).sum())))
    log(
        f"valid={n_ok}  P(commit label>0)={float((y_commit[ok] > 0).mean()):.4f}  "
        f"P(disc_commit=1)={float((y_disc_c[ok] > 0).mean()):.4f}  "
        f"transient/hit={trans_ratio:.3f}"
    )

    causal = {
        "novelty": novelty_score(inv_rho=arr["inv_rho"]),
        "boundary": boundary_score(last_score=arr["last_score"]),
        "kinetic": kinetic_score(msd=arr["msd_x_50"], vel=arr["vel_x_50"], var=arr["var_x_50"]),
        "uncertainty": uncertainty_score(msd=arr["msd_x_50"], inv_rho=arr["inv_rho"]),
        "commitment": commitment_proxy_rmsd(arr["x"], fold_rmsd=FOLD_RMSD_NM),
        "information_gain": information_gain_score(inv_rho=arr["inv_rho"]),
    }
    labels = {
        "commitment_label": commitment_labels(comm=y_commit),
        "information_gain_label": information_gain_score(nov_info=arr[f"nov_info_{HORIZON}"]),
    }
    np.savez_compressed(
        outdir / "objectives_causal.npz",
        source=arr["source"],
        t_ps=arr["t_ps"],
        x=arr["x"],
        y=arr["y"],
        **causal,
        **labels,
        y_commit=y_commit,
        y_disc_commit=y_disc_c,
    )

    tr, va = time_split(arr["source"], arr["t_ps"])
    va = va[ok[va]]
    log(f"time split by source: train={len(tr)}  val={len(va)}  (val = last {VAL_FRAC:.0%} of each source)")

    norm_va = {k: percentile_rank(v[va]) for k, v in causal.items()}
    stages = stage_by_time_rank(arr["t_ps"][va])

    methods = {
        "LAST": arr["last_score"][va],
        "least_counts": arr["inv_rho"][va],
        "random": RNG.random(len(va)),
        "shortcut_-RMSD": -np.asarray(arr["x"][va], dtype=np.float64),
        "MOAS-equal": weighted_utility(norm_va, WEIGHT_MODES["equal"]),
        "MOAS-LAST-dominant": weighted_utility(norm_va, WEIGHT_MODES["last_dominant"]),
        "MOAS-kinetic-dominant": weighted_utility(norm_va, WEIGHT_MODES["kinetic_dominant"]),
        "MOAS-commit-proxy": weighted_utility(norm_va, WEIGHT_MODES["commitment_dominant"]),
        "MOAS-dynamic": dynamic_utility(norm_va, stages),
        "oracle_commit": y_commit[va],
        "oracle_disc_commit": y_disc_c[va],
        "oracle_IG": labels["information_gain_label"][va],
    }

    # Pareto on causal N/B/K/C, then diversity fill to TOPK
    pareto_cols = np.column_stack(
        [norm_va["novelty"], norm_va["boundary"], norm_va["kinetic"], norm_va["commitment"]]
    )
    pmask = pareto_mask(pareto_cols)
    pidx = np.flatnonzero(pmask)
    log(f"Pareto front (N/B/K/C on val): {len(pidx)} / {len(va)}")
    util_eq = methods["MOAS-equal"]
    pareto_score = np.full(len(va), -1.0)
    if len(pidx):
        chosen_local = greedy_maxmin(np.stack([arr["x"][va][pidx], arr["y"][va][pidx]], axis=1), util_eq[pidx], min(TOPK, len(pidx)))
        ranked = pidx[chosen_local]
        pareto_score[ranked] = np.linspace(float(len(ranked)), 1.0, len(ranked))
        # remaining front members still beat non-front
        rest = np.setdiff1d(pidx, ranked, assume_unique=False)
        pareto_score[rest] = 0.25
    methods["MOAS-Pareto"] = pareto_score

    targets = {
        "comm_200": y_commit[va],
        "disc_commit_200": y_disc_c[va],
        "feu_commit_200": np.asarray(arr[f"feu_commit_{HORIZON}"][va], dtype=np.float64),
    }

    report = []
    metrics_out = {}
    for tname, y in targets.items():
        report.append(f"\n=== validation ranking  target={tname}  (higher better) ===")
        metrics_out[tname] = {}
        for mname, pred in methods.items():
            m = ranking_metrics(pred, y)
            metrics_out[tname][mname] = m
            report.append(fmt_rank(mname, m))

    sets = {name: topk_set(pred, TOPK) for name, pred in methods.items() if not name.startswith("oracle")}
    report.append(f"\n=== top-{TOPK} Jaccard vs LAST ===")
    last_set = sets["LAST"]
    for name, s in sets.items():
        report.append(f"  {name:28s}  J={jaccard(s, last_set):.3f}  |set|={len(s)}")

    xy_va = np.stack([arr["x"][va], arr["y"][va]], axis=1)
    report.append(f"\n=== top-{TOPK} seed diversity (mean pairwise RMSD–Rg distance) ===")
    diversity = {}
    for name, pred in methods.items():
        if name.startswith("oracle"):
            continue
        idx = np.argsort(-pred)[:TOPK]
        d = pairwise_mean_dist(xy_va[idx])
        diversity[name] = d
        yhit = float((y_disc_c[va][idx] > 0).mean())
        ycomm = float(y_commit[va][idx].mean())
        report.append(f"  {name:28s}  dist={d:.4f}  disc_commit_rate={yhit:.3f}  mean_comm={ycomm:.4f}")

    last_enr = metrics_out["disc_commit_200"]["LAST"]["top10_enrich"]
    moas_enr = metrics_out["disc_commit_200"]["MOAS-equal"]["top10_enrich"]
    dyn_enr = metrics_out["disc_commit_200"]["MOAS-dynamic"]["top10_enrich"]
    proxy_enr = metrics_out["disc_commit_200"]["MOAS-commit-proxy"]["top10_enrich"]
    beat_last = []
    for name in ("MOAS-equal", "MOAS-dynamic", "MOAS-commit-proxy", "MOAS-Pareto", "MOAS-LAST-dominant"):
        e = metrics_out["disc_commit_200"][name]["top10_enrich"]
        if e > last_enr + 0.05:
            beat_last.append(f"{name} ({e:.2f} vs LAST {last_enr:.2f})")

    report.append("\n=== Go / No-Go for online GROMACS ===")
    report.append(f"LAST top10% disc_commit enrich={last_enr:.2f}")
    report.append(f"MOAS-equal enrich={moas_enr:.2f}  dynamic={dyn_enr:.2f}  commit-proxy={proxy_enr:.2f}")
    if beat_last:
        report.append("GAIN: " + "; ".join(beat_last))
        report.append("Next: start an online CLN025 adaptive campaign with the winning weight mode.")
        go = True
    else:
        report.append("NO-GO: no causal MOAS variant clearly beat LAST on committed-hit enrichment.")
        report.append("Do not launch new MD yet. Inspect objective redundancy (Novelty vs LC vs LAST).")
        go = False

    # legacy campaign snapshot
    snap = ROOT / "data" / "legacy" / "cln025_unfolded" / "firsthit_reps_report.txt"
    if snap.exists():
        report.append("\n=== existing 82 ns campaigns (copied; not re-run) ===")
        report.append(snap.read_text(encoding="utf-8").strip())

    text = "\n".join(report) + "\n"
    (outdir / "report.txt").write_text(
        f"MOAS Phase 1  CLN025  val_frac={VAL_FRAC}  horizon={HORIZON} ps\n" + text,
        encoding="utf-8",
    )
    (outdir / "metrics.json").write_text(
        json.dumps(
            {
                "n": n,
                "n_val": int(len(va)),
                "transient_over_hit": trans_ratio,
                "pareto_size": int(len(pidx)),
                "go_online_md": go,
                "diversity": diversity,
                "metrics": {
                    t: {m: {k: (None if isinstance(v, float) and not np.isfinite(v) else v) for k, v in mm.items()} for m, mm in block.items()}
                    for t, block in metrics_out.items()
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    log(text)
    log(f"wrote {outdir / 'report.txt'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
