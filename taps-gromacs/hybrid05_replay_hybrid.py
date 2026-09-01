#!/usr/bin/env python3
"""
HYBRID 05  |  Workflow §7  固定 LAST→TAPS 切换的离线回放（不跑新 MD）

把已有 LAST / TAPS 短轨迹按轮次拼接：
  Hybrid-1  前 25% 轮 LAST，其余 TAPS
  Hybrid-2  前 50% 轮 LAST，其余 TAPS
  Hybrid-3  前 75% 轮 LAST，其余 TAPS

和同预算 cMD / LC / LAST / TAPS 比 productive exploration。
这不是真正的在线 hybrid（后半段 TAPS 短轨迹仍来自纯 TAPS campaign），
只回答：若早期用 LAST 的探索、后期用 TAPS 的开采，指标会不会更好。

  python3 hybrid05_replay_hybrid.py --system cln025
  python3 hybrid05_replay_hybrid.py --system both

输出: analysis/hybrid/<kind>_replay_hybrid_report.txt
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

import hybrid01_build_candidates as h01  # noqa: E402
from hybrid_common import hybrid_outdir  # noqa: E402
from hybrid_metrics import fmt_productive, productive_metrics  # noqa: E402
from taps_common import ANALYSIS, TapsError, log, parse_xvg, wrap_deg  # noqa: E402


def parse_round_name(name: str):
    if name.startswith("r") and "_s" in name:
        try:
            return int(name.split("_")[0][1:])
        except ValueError:
            return None
    return None


def filter_cln(segs, rounds):
    keep = []
    for s in segs:
        if s["name"] in ("cmd_init", "cmd"):
            keep.append(s)
            continue
        rid = parse_round_name(s["name"])
        if rid is not None and rid in rounds:
            keep.append(s)
    return keep


def load_ala2_init(max_ps: float = 2000.0):
    path = ANALYSIS / "ala2_vacuum" / "dihedrals.npz"
    d = np.load(path)
    t = d["t_ps"]
    m = t <= max_ps + 1e-6
    return [{"name": "cmd_init", "t_ps": t[m], "x": wrap_deg(d["phi"][m]), "y": wrap_deg(d["psi"][m])}]


def load_ala2_rounds(tag: str, rounds):
    root = ANALYSIS / "ala2_vacuum" / "campaigns" / tag / "adaptive"
    segs = []
    for rid in sorted(rounds):
        rnd = root / f"round{rid:02d}"
        if not rnd.is_dir():
            continue
        for phi_xvg in sorted(rnd.glob("seed_*_dihedrals_phi.xvg")):
            rank = phi_xvg.name.split("_")[1]
            psi_xvg = rnd / f"seed_{rank}_dihedrals_psi.xvg"
            if not psi_xvg.exists():
                continue
            phi = parse_xvg(phi_xvg)
            psi = parse_xvg(psi_xvg)
            n = min(len(phi), len(psi))
            segs.append(
                {
                    "name": f"r{rid:02d}_s{rank}",
                    "t_ps": phi[:n, 0],
                    "x": wrap_deg(phi[:n, 1]),
                    "y": wrap_deg(psi[:n, 1]),
                }
            )
    return segs


def pack_metrics(kind: str, segs: list, label: str) -> dict:
    if not segs:
        raise TapsError(f"no segments for {label}")
    pack = h01.concat_resample(segs, kind)
    m = productive_metrics(kind, pack["t_ps"], pack["x"], pack["y"], pack["seg"])
    m["label"] = label
    return m


def n_rounds_available(kind: str) -> int:
    if kind == "cln":
        hist = ANALYSIS / "cln025_unfolded" / "campaigns" / "discover_last" / "history.json"
    else:
        hist = ANALYSIS / "ala2_vacuum" / "campaigns" / "discover_last" / "history.json"
    if not hist.exists():
        return 0
    rows = json.loads(hist.read_text(encoding="utf-8"))
    return max(int(h["round"]) for h in rows)


def method_segs(kind: str, tag: str):
    if kind == "cln":
        return h01.load_cln_source(tag if tag != "cmd" else "cmd")
    if tag == "cmd":
        path = ANALYSIS / "ala2_vacuum" / "dihedrals.npz"
        d = np.load(path)
        # match adaptive budget later; load full cMD and trim by frame count in run_one
        return [{"name": "cmd", "t_ps": d["t_ps"], "x": wrap_deg(d["phi"]), "y": wrap_deg(d["psi"])}]
    return load_ala2_init() + load_ala2_rounds(f"discover_{tag}" if not tag.startswith("discover") else tag, range(1, 99))


def stitch(kind: str, last_rounds, taps_rounds):
    if kind == "cln":
        last = filter_cln(h01.load_cln_source("discover_last"), last_rounds)
        taps = [s for s in h01.load_cln_source("discover_taps") if parse_round_name(s["name"]) in taps_rounds]
        # keep LAST's cmd_init only once
        taps = [s for s in taps if s["name"] not in ("cmd_init", "cmd")]
        return last + taps
    segs = load_ala2_init() + load_ala2_rounds("discover_last", last_rounds) + load_ala2_rounds("discover_taps", taps_rounds)
    return segs


def trim_cmd(kind: str, segs, target_ns: float):
    pack = h01.concat_resample(segs, kind)
    t = pack["t_ps"]
    dt = float(t[1] - t[0]) if len(t) > 1 else 2.0
    need = t <= (t[0] + target_ns * 1000.0 - dt + 1e-6)
    return productive_metrics(kind, t[need], pack["x"][need], pack["y"][need], pack["seg"][need])


def run_one(kind: str) -> str:
    n_rounds = n_rounds_available(kind)
    if n_rounds < 2:
        raise TapsError(f"{kind}: need campaign history with ≥2 rounds")
    schedules = {
        "hybrid1_25": max(1, int(round(0.25 * n_rounds))),
        "hybrid2_50": max(1, int(round(0.50 * n_rounds))),
        "hybrid3_75": max(1, int(round(0.75 * n_rounds))),
    }
    rows = []
    if kind == "cln":
        last_full = pack_metrics(kind, h01.load_cln_source("discover_last"), "last")
        taps_full = pack_metrics(kind, h01.load_cln_source("discover_taps"), "taps")
        lc_full = pack_metrics(kind, h01.load_cln_source("discover_lc"), "lc")
        budget = last_full["sim_ns"]
        cmd = trim_cmd(kind, h01.load_cln_source("cmd"), budget)
        cmd["label"] = "cmd"
    else:
        last_full = pack_metrics(kind, load_ala2_init() + load_ala2_rounds("discover_last", range(1, n_rounds + 1)), "last")
        taps_full = pack_metrics(kind, load_ala2_init() + load_ala2_rounds("discover_taps", range(1, n_rounds + 1)), "taps")
        lc_full = pack_metrics(kind, load_ala2_init() + load_ala2_rounds("discover_lc", range(1, n_rounds + 1)), "lc")
        budget = last_full["sim_ns"]
        cmd = trim_cmd(kind, method_segs(kind, "cmd"), budget)
        cmd["label"] = "cmd"
    rows.extend([cmd, lc_full, last_full, taps_full])

    for name, n_last in schedules.items():
        last_r = set(range(1, n_last + 1))
        taps_r = set(range(n_last + 1, n_rounds + 1))
        segs = stitch(kind, last_r, taps_r)
        m = pack_metrics(kind, segs, name)
        m["n_last_rounds"] = n_last
        rows.append(m)
        log(f"{kind} {name}: LAST rounds 1-{n_last}, TAPS {n_last + 1}-{n_rounds}")

    lines = [
        f"HYBRID 05  {kind}  offline LAST→TAPS stitch  adaptive_rounds={n_rounds}",
        "first_hit is reported but first_commit / residence / novel_per_ns are the targets.",
        "",
    ]
    for m in rows:
        extra = f"  (LAST rounds=1-{m['n_last_rounds']})" if "n_last_rounds" in m else ""
        lines.append(fmt_productive(m["label"], m) + extra)

    last = next(m for m in rows if m["label"] == "last")
    lines.append("")
    lines.append("vs LAST (positive = hybrid better):")
    for m in rows:
        if not m["label"].startswith("hybrid"):
            continue
        dcov = m["coverage"] - last["coverage"]
        dnov = m["novel_per_ns"] - last["novel_per_ns"]
        dfrac = m["frac_target"] - last["frac_target"]
        lines.append(
            f"  {m['label']:16s}  Δcov={dcov:+.4f}  Δnovel/ns={dnov:+.2f}  "
            f"Δfrac_target={dfrac:+.4f}  commit {m['first_commit_ns']} vs LAST {last['first_commit_ns']}"
        )
    lines.append("")
    lines.append("Caveat: late TAPS shorts were not trained/selected under a LAST-first history.")
    lines.append("Use this as a cheap screen. A true Hybrid campaign is Hybrid 05b (new MD).")
    text = "\n".join(lines) + "\n"
    out = hybrid_outdir()
    (out / f"{kind}_replay_hybrid_report.txt").write_text(text, encoding="utf-8")
    (out / f"{kind}_replay_hybrid_meta.json").write_text(
        json.dumps({"kind": kind, "n_rounds": n_rounds, "rows": rows}, indent=2, default=str) + "\n"
    )
    print(text)
    return text


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--system", default="cln025", choices=("cln025", "ala2", "both"))
    args = p.parse_args(argv)
    try:
        log(f"HYBRID 05  replay hybrid  system={args.system}")
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
