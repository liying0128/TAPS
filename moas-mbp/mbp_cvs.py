#!/usr/bin/env python3
"""Domain COM distance and hinge angle for E. coli maltose-binding protein.

Open apo: PDB 1OMP. Closed holo: PDB 1ANF (maltose removed; apo reference only).

Domain CA groups (PDB numbering, ~1–370):
  N-lobe:  1–109 and 264–309
  C-lobe:  114–258 and 316–370
  hinge:   109–114, 258–264, 309–316

CVs:
  dist  = CA-COM(N) – CA-COM(C)  (nm)
  theta = angle N-COM — hinge-COM — C-COM  (deg)

  python3 mbp_cvs.py --refs
  python3 mbp_cvs.py --gro systems/mbp/gmx_common_open/protein.gro
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from mbp_common import ROOT, MbpError, gro_ca, log

N_DOM = ((1, 109), (264, 309))
C_DOM = ((114, 258), (316, 370))
HINGE = ((109, 114), (258, 264), (309, 316))


def angle_deg(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> np.ndarray:
    u = a - b
    v = c - b
    nu = np.linalg.norm(u, axis=-1)
    nv = np.linalg.norm(v, axis=-1)
    cos = np.clip(np.sum(u * v, axis=-1) / (nu * nv + 1e-12), -1.0, 1.0)
    return np.degrees(np.arccos(cos))


def com_ranges(xyz: np.ndarray, resids: np.ndarray, ranges) -> np.ndarray:
    mask = np.zeros(len(resids), dtype=bool)
    for lo, hi in ranges:
        mask |= (resids >= lo) & (resids <= hi)
    if not np.any(mask):
        raise MbpError(f"no CA in ranges {ranges}")
    return xyz[..., mask, :].mean(axis=-2)


def cvs_from_ca(xyz: np.ndarray, resids: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """xyz: (n_ca, 3) or (n_frames, n_ca, 3). dist in nm, theta in deg."""
    single = xyz.ndim == 2
    if single:
        xyz = xyz[None, ...]
    n_com = com_ranges(xyz, resids, N_DOM)
    c_com = com_ranges(xyz, resids, C_DOM)
    h_com = com_ranges(xyz, resids, HINGE)
    dist = np.linalg.norm(n_com - c_com, axis=-1)
    theta = angle_deg(n_com, h_com, c_com)
    if single:
        return dist[0], theta[0]
    return dist, theta


def cvs_from_gro(gro: Path) -> tuple[float, float]:
    xyz, resids, _ = gro_ca(gro)
    dist, theta = cvs_from_ca(xyz, resids)
    return float(dist), float(theta)


def in_closed(dist, theta, refs: dict) -> np.ndarray:
    dist = np.asarray(dist)
    theta = np.asarray(theta)
    d_ok = dist < refs["closed_dist_thr"] if refs["closed_dist_op"] == "lt" else dist > refs["closed_dist_thr"]
    t_ok = theta < refs["closed_theta_thr"] if refs["closed_theta_op"] == "lt" else theta > refs["closed_theta_thr"]
    return d_ok & t_ok


def write_refs() -> dict:
    open_gro = ROOT / "systems/mbp/gmx_common_open/protein.gro"
    closed_gro = ROOT / "systems/mbp/gmx_common_closed/protein.gro"
    if not open_gro.exists() or not closed_gro.exists():
        raise MbpError("run bash scripts/prepare_mbp.sh first")
    o_d, o_t = cvs_from_gro(open_gro)
    c_d, c_t = cvs_from_gro(closed_gro)

    def closed_side(open_v: float, closed_v: float, margin: float) -> tuple[str, float]:
        cut = 0.5 * (open_v + closed_v)
        if closed_v < open_v:
            return "lt", float(min(cut, closed_v + margin))
        return "gt", float(max(cut, closed_v - margin))

    # 0.08 nm ~ 0.8 Å; 8 deg — same idea as AdK's side-aware window
    d_op, d_thr = closed_side(o_d, c_d, margin=0.08)
    t_op, t_thr = closed_side(o_t, c_t, margin=8.0)
    refs = {
        "open_dist": o_d,
        "open_theta": o_t,
        "closed_dist": c_d,
        "closed_theta": c_t,
        "closed_dist_op": d_op,
        "closed_dist_thr": d_thr,
        "closed_theta_op": t_op,
        "closed_theta_thr": t_thr,
        "commit_ps": 200.0,
        "n_dom": [list(g) for g in N_DOM],
        "c_dom": [list(g) for g in C_DOM],
        "hinge": [list(g) for g in HINGE],
    }
    dest = ROOT / "systems/mbp/cv_refs.json"
    dest.write_text(json.dumps(refs, indent=2) + "\n", encoding="utf-8")
    log(
        f"open   dist={o_d:.3f} nm  theta={o_t:.1f} deg   "
        f"closed dist={c_d:.3f} nm  theta={c_t:.1f} deg   "
        f"window dist {d_op} {d_thr:.3f}  theta {t_op} {t_thr:.1f}  commit≥200 ps"
    )
    log(f"wrote {dest}")
    return refs


def load_refs() -> dict:
    path = ROOT / "systems/mbp/cv_refs.json"
    if not path.exists():
        return write_refs()
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    p = argparse.ArgumentParser(description="MBP domain distance / hinge angle")
    p.add_argument("--refs", action="store_true")
    p.add_argument("--gro", type=Path, default=None)
    args = p.parse_args()
    if args.refs:
        write_refs()
        return 0
    gro = args.gro or ROOT / "systems/mbp/gmx_common_open/protein.gro"
    dist, theta = cvs_from_gro(gro)
    print(f"{gro}  dist={dist:.3f} nm  theta={theta:.1f} deg")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except MbpError as exc:
        log(str(exc), "ERROR")
        raise SystemExit(1)
