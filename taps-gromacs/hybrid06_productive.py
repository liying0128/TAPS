#!/usr/bin/env python3
"""
HYBRID 06  |  Workflow §10–§12  productive exploration 重分析（不跑 MD）

不再把 first RMSD<0.25 / first φ>0 当成成功。
对每条已有 campaign 报告：
  coverage, novel bins / ns, first hit vs first commit,
  residence, committed visits, re-exploitation, entropy.

CLN025：TAPS 30.54 ns 单帧 crossing 应显示为 TRANSIENT_ONLY（若从未连续停留 ≥40 ps）。
ala2：discovery 与 C7ax exploitation 分开；现有轨迹若从未进入 C7ax，commit 全是 none。

  python3 hybrid06_productive.py --system both

输出: analysis/hybrid/<kind>_productive_report.txt
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import hybrid01_build_candidates as h01  # noqa: E402
import hybrid05_replay_hybrid as h05  # noqa: E402
from hybrid_common import COMMIT_PS, hybrid_outdir  # noqa: E402
from hybrid_metrics import fmt_productive, productive_metrics  # noqa: E402
from taps_common import TapsError, log  # noqa: E402


def run_one(kind: str) -> str:
    rows = []
    if kind == "cln":
        jobs = [
            ("cmd", h01.load_cln_source("cmd")),
            ("taps", h01.load_cln_source("discover_taps")),
            ("last", h01.load_cln_source("discover_last")),
            ("lc", h01.load_cln_source("discover_lc")),
        ]
        # matched budget: first 82 ns of cMD
        cmd = jobs[0][1]
        pack = h01.concat_resample(cmd, kind)
        t = pack["t_ps"]
        dt = float(t[1] - t[0])
        last_pack = h01.concat_resample(jobs[2][1], kind)
        budget_ps = float(last_pack["t_ps"][-1] - last_pack["t_ps"][0] + dt)
        m = t <= t[0] + budget_ps + 1e-6
        cmd_m = productive_metrics(kind, t[m], pack["x"][m], pack["y"][m], pack["seg"][m])
        cmd_m["label"] = "cmd_matched"
        rows.append(cmd_m)
        for name, segs in jobs[1:]:
            p = h01.concat_resample(segs, kind)
            rec = productive_metrics(kind, p["t_ps"], p["x"], p["y"], p["seg"])
            rec["label"] = name
            rows.append(rec)
    else:
        n_rounds = h05.n_rounds_available(kind)
        jobs = [
            ("cmd", h05.method_segs(kind, "cmd")),
            ("taps", h05.load_ala2_init() + h05.load_ala2_rounds("discover_taps", range(1, n_rounds + 1))),
            ("last", h05.load_ala2_init() + h05.load_ala2_rounds("discover_last", range(1, n_rounds + 1))),
            ("lc", h05.load_ala2_init() + h05.load_ala2_rounds("discover_lc", range(1, n_rounds + 1))),
        ]
        last_p = h01.concat_resample(jobs[2][1], kind)
        budget_ns = productive_metrics(kind, last_p["t_ps"], last_p["x"], last_p["y"])["sim_ns"]
        cmd_m = h05.trim_cmd(kind, jobs[0][1], budget_ns)
        cmd_m["label"] = "cmd_matched"
        rows.append(cmd_m)
        for name, segs in jobs[1:]:
            p = h01.concat_resample(segs, kind)
            rec = productive_metrics(kind, p["t_ps"], p["x"], p["y"], p["seg"])
            rec["label"] = name
            rows.append(rec)

    lines = [
        f"HYBRID 06  {kind}  productive exploration   commit≥{COMMIT_PS:.0f} ps",
        "Do not treat first_hit as discovery. TRANSIENT_ONLY = hit but never stayed.",
        "",
    ]
    for m in rows:
        lines.append(fmt_productive(m["label"], m))
    lines.append("")
    taps = next((m for m in rows if m["label"] == "taps"), None)
    last = next((m for m in rows if m["label"] == "last"), None)
    if taps and last:
        if taps["transient_only"] and not last["transient_only"]:
            lines.append("CLN/ala2 note: TAPS has a first-hit without commitment; LAST committed.")
        if taps["first_hit_ns"] is not None and last["first_hit_ns"] is not None:
            lines.append(
                f"first_hit  TAPS {taps['first_hit_ns']:.3f} vs LAST {last['first_hit_ns']:.3f} ns  "
                "(not a superiority claim by itself)"
            )
        lines.append(
            f"frac_target TAPS {taps['frac_target']:.4f} vs LAST {last['frac_target']:.4f}  "
            f"reexploit TAPS {taps['reexploit_segments']} vs LAST {last['reexploit_segments']}"
        )
    text = "\n".join(lines) + "\n"
    out = hybrid_outdir()
    (out / f"{kind}_productive_report.txt").write_text(text, encoding="utf-8")
    print(text)
    return text


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--system", default="both", choices=("cln025", "ala2", "both"))
    args = p.parse_args(argv)
    try:
        log(f"HYBRID 06  productive  system={args.system}")
        if args.system in ("cln025", "both"):
            run_one("cln")
        if args.system in ("ala2", "both"):
            run_one("ala2")
        return 0
    except TapsError as exc:
        log(str(exc), "ERROR")
        return 1


if __name__ == "__main__":
    sys.exit(main())
