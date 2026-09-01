#!/usr/bin/env python3
"""Compare CLN025 first-hit / commit across original + two seed replicates."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import hybrid01_build_candidates as h01  # noqa: E402
from hybrid_metrics import fmt_productive, productive_metrics  # noqa: E402
from taps_common import ANALYSIS, TapsError, log  # noqa: E402

REPLICATES = [
    ("original seed=0", "discover"),
    ("replicate s1 seed=1", "discover_s1"),
    ("replicate s2 seed=2", "discover_s2"),
]
METHODS = [("taps", "taps"), ("last", "last"), ("lc", "lc")]


def metrics_for(tag: str):
    segs = h01.load_cln_source(tag)
    p = h01.concat_resample(segs, "cln")
    rec = productive_metrics("cln", p["t_ps"], p["x"], p["y"], p["seg"])
    rec["label"] = tag
    return rec


def fmt_ns(v):
    return "none" if v is None else f"{v:.3f}"


def main() -> int:
    lines = [
        "CLN025 first-hit replicates",
        "same protocol as stage13: init 10 ns, 12 x 6 x 1 ns, RMSD<0.25 nm",
        "first_hit is reported; commit>=40 ps is the discovery criterion",
        "",
    ]
    by_rep = []
    for title, prefix in REPLICATES:
        lines.append(f"=== {title}  prefix={prefix} ===")
        rows = []
        for method, suffix in METHODS:
            tag = f"{prefix}_{suffix}"
            try:
                rec = metrics_for(tag)
            except TapsError as exc:
                lines.append(f"  {tag:20s}  not ready ({exc})")
                continue
            rec["method"] = method
            rows.append(rec)
            lines.append("  " + fmt_productive(method, rec))
        if rows:
            hits = [(r["method"], r["first_hit_ns"]) for r in rows if r["first_hit_ns"] is not None]
            hits.sort(key=lambda z: z[1])
            if hits:
                order = " < ".join(f"{m}({fmt_ns(t)})" for m, t in hits)
                lines.append(f"  first-hit order: {order}")
            else:
                lines.append("  first-hit order: nobody reached RMSD<0.25 nm")
            trans = [r["method"] for r in rows if r["transient_only"]]
            if trans:
                lines.append("  TRANSIENT_ONLY: " + ", ".join(trans))
        lines.append("")
        by_rep.append((title, rows))

    lines.append("=== across replicates: did TAPS hit earlier than LAST / LC? ===")
    for title, rows in by_rep:
        d = {r["method"]: r for r in rows}
        if "taps" not in d or "last" not in d:
            lines.append(f"  {title}: incomplete")
            continue
        th, lh = d["taps"]["first_hit_ns"], d["last"]["first_hit_ns"]
        lc = d["lc"]["first_hit_ns"] if "lc" in d else None
        if th is None and lh is None:
            rel = "neither TAPS nor LAST hit"
        elif th is None:
            rel = f"LAST hit ({fmt_ns(lh)}), TAPS did not"
        elif lh is None:
            rel = f"TAPS hit ({fmt_ns(th)}), LAST did not"
        elif th < lh:
            rel = f"TAPS earlier than LAST by {lh - th:.3f} ns"
        elif th > lh:
            rel = f"LAST earlier than TAPS by {th - lh:.3f} ns"
        else:
            rel = "TAPS and LAST tied"
        extra = ""
        if lc is not None:
            extra = f"  LC hit={fmt_ns(lc)}"
        lines.append(
            f"  {title}: {rel}{extra}  "
            f"TAPS commit={fmt_ns(d['taps']['first_commit_ns'])}  "
            f"LAST commit={fmt_ns(d['last']['first_commit_ns'])}"
        )

    dest = ANALYSIS / "cln025_unfolded" / "firsthit_reps_report.txt"
    dest.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(lines) + "\n"
    dest.write_text(text, encoding="utf-8")
    print(text)
    log(f"wrote {dest.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
