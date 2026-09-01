#!/usr/bin/env python3
"""Recompute CLN025 productive metrics (commit ≥ 40 ps).

Official n=3 is seeds 0/1/2 for every method. Seed=3 extras are listed separately
and are not mixed into the n=3 vs-LAST summary.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

MOAS = Path(__file__).resolve().parents[1]
TAPS = MOAS.parent / "taps-gromacs"
sys.path.insert(0, str(TAPS))

import hybrid01_build_candidates as h01  # noqa: E402
from hybrid_metrics import fmt_productive, productive_metrics  # noqa: E402
from taps_common import TapsError, log  # noqa: E402

OUT = MOAS / "results" / "commit_all_cln"
GROUPS = [
    ("LAST", ["discover_last", "discover_s1_last", "discover_s2_last"]),
    ("Least-counts", ["discover_lc", "discover_s1_lc", "discover_s2_lc"]),
    ("TAPS", ["discover_taps", "discover_s1_taps", "discover_s2_taps"]),
    ("Random", ["moas_random", "moas_s1_random", "moas_s2_random"]),
    ("MOAS-static", ["moas_static", "moas_s1_static", "moas_s2_static"]),
    ("MOAS-dynamic", ["moas_dynamic", "moas_s1_dynamic", "moas_s2_dynamic"]),
    ("MOAS-Pareto", ["moas_pareto", "moas_s1_pareto", "moas_s2_pareto"]),
]
EXTRAS = [
    ("LAST seed=3", ["discover_s3_last"]),
    ("Least-counts seed=3", ["discover_s3_lc"]),
    ("TAPS seed=3", ["discover_s3_taps"]),
    ("Random seed=3", ["moas_s3_random"]),
    ("MOAS-static seed=3", ["moas_s3_static"]),
    ("MOAS-dynamic seed=3", ["moas_s3_dynamic"]),
    ("MOAS-Pareto seed=3", ["moas_s3_pareto"]),
]
VS_LAST = ("Random", "MOAS-static", "MOAS-dynamic", "MOAS-Pareto", "TAPS", "Least-counts")


def one(tag: str) -> dict:
    segs = h01.load_cln_source(tag)
    p = h01.concat_resample(segs, "cln")
    rec = productive_metrics("cln", p["t_ps"], p["x"], p["y"], p["seg"])
    rec["tag"] = tag
    return rec


def emit_group(lines: list, all_rows: list, group: str, tags: list, extra: bool = False) -> None:
    lines.append(f"=== {group} ===")
    rows = []
    for tag in tags:
        try:
            rec = one(tag)
        except TapsError as exc:
            lines.append(f"  {tag:22s}  missing ({exc})")
            continue
        rec["group"] = group
        rec["extra_seed3"] = extra
        rows.append(rec)
        all_rows.append(rec)
        lines.append("  " + fmt_productive(tag, rec))
    if rows:
        commits = [r for r in rows if r["first_commit_ns"] is not None]
        trans = [r["tag"] for r in rows if r["transient_only"]]
        if commits:
            med = sorted(r["first_commit_ns"] for r in commits)[len(commits) // 2]
            lines.append(
                f"  committed {len(commits)}/{len(rows)}  "
                f"median commit={med:.3f} ns  "
                f"mean fold_frac={sum(r['frac_target'] for r in rows)/len(rows):.4f}  "
                f"mean reexploit={sum(r['reexploit_segments'] for r in rows)/len(rows):.1f}"
            )
        else:
            lines.append(f"  committed 0/{len(rows)}")
        if trans:
            lines.append("  TRANSIENT_ONLY: " + ", ".join(trans))
    lines.append("")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    lines = [
        "CLN025 commit≥40 ps  (first-hit is auxiliary)",
        "protocol: 10 ns init + 12 x 6 x 1 ns, RMSD<0.25 nm",
        "official n=3 = seeds 0/1/2; seed=3 extras are listed separately",
        "unique advantages vs LAST are allowed; LAST does not have to be beaten overall",
        "",
    ]
    all_rows = []
    for group, tags in GROUPS:
        emit_group(lines, all_rows, group, tags, extra=False)

    lines.append("--- seed=3 extras (not in n=3 vs-LAST) ---")
    lines.append("")
    extra_rows = []
    for group, tags in EXTRAS:
        emit_group(lines, extra_rows, group, tags, extra=True)

    n3 = [r for r in all_rows if not r.get("extra_seed3")]
    last_rows = [r for r in n3 if r.get("group") == "LAST"]
    lines.append("=== vs LAST (n=3, seeds 0/1/2; not required to win overall) ===")
    if last_rows:
        last_frac = sum(r["frac_target"] for r in last_rows) / len(last_rows)
        last_commit = [r["first_commit_ns"] for r in last_rows if r["first_commit_ns"] is not None]
        lines.append(
            f"LAST  n={len(last_rows)}  mean fold_frac={last_frac:.4f}  "
            f"commits={len(last_commit)}/{len(last_rows)}"
        )
        for group in VS_LAST:
            rows = [r for r in n3 if r.get("group") == group]
            if not rows:
                continue
            frac = sum(r["frac_target"] for r in rows) / len(rows)
            n_c = sum(r["first_commit_ns"] is not None for r in rows)
            n_hit = sum(r["first_hit_ns"] is not None for r in rows)
            notes = []
            if frac > last_frac * 1.05:
                notes.append(f"higher mean fold_frac ({frac:.4f} vs {last_frac:.4f})")
            if n_c == len(rows) and len(last_commit) < len(last_rows):
                notes.append("more consistent commit across seeds")
            if n_hit:
                notes.append(f"first-hit in {n_hit}/{len(rows)} seeds")
            extra = "; ".join(notes) if notes else "no standout vs LAST on these summary stats"
            lines.append(f"  {group:14s}  fold_frac={frac:.4f}  commit {n_c}/{len(rows)}  {extra}")

    text = "\n".join(lines) + "\n"
    (OUT / "report.txt").write_text(text, encoding="utf-8")
    slim = []
    for r in all_rows + extra_rows:
        slim.append({k: (None if isinstance(v, float) and v != v else v) for k, v in r.items() if k != "label"})
    (OUT / "metrics.json").write_text(json.dumps(slim, indent=2, default=str) + "\n", encoding="utf-8")
    print(text)
    log(f"wrote {OUT / 'report.txt'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
