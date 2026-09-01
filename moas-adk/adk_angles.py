#!/usr/bin/env python3
"""LID–CORE and NMP–CORE angles for E. coli AdK (Beckstein / Snow CA-COM definition).

Groups (PDB residue numbers, chain A, 1–214):
  LID angle vertex 115–125 (CORE), arms 179–185 (CORE) and 125–153 (LID)
  NMP angle vertex 115–125 (CORE), arms  90–100 (CORE) and  35–55  (NMP)

  python3 adk_angles.py --refs
  python3 adk_angles.py --gro systems/adk/gmx_common_open/protein.gro
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from adk_common import ROOT, AdkError, gro_ca, log

# vertex, arm1, arm2
LID_GROUPS = ((115, 125), (179, 185), (125, 153))
NMP_GROUPS = ((115, 125), (90, 100), (35, 55))


def angle_deg(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> np.ndarray:
    u = a - b
    v = c - b
    nu = np.linalg.norm(u, axis=-1)
    nv = np.linalg.norm(v, axis=-1)
    cos = np.clip(np.sum(u * v, axis=-1) / (nu * nv + 1e-12), -1.0, 1.0)
    return np.degrees(np.arccos(cos))


def com_range(xyz: np.ndarray, resids: np.ndarray, lo: int, hi: int) -> np.ndarray:
    mask = (resids >= lo) & (resids <= hi)
    if not np.any(mask):
        raise AdkError(f"no CA in residues {lo}-{hi}")
    return xyz[..., mask, :].mean(axis=-2)


def angles_from_ca(xyz: np.ndarray, resids: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """xyz: (n_ca, 3) or (n_frames, n_ca, 3)."""
    single = xyz.ndim == 2
    if single:
        xyz = xyz[None, ...]
    lid_b = com_range(xyz, resids, *LID_GROUPS[0])
    lid_a = com_range(xyz, resids, *LID_GROUPS[1])
    lid_c = com_range(xyz, resids, *LID_GROUPS[2])
    nmp_b = com_range(xyz, resids, *NMP_GROUPS[0])
    nmp_a = com_range(xyz, resids, *NMP_GROUPS[1])
    nmp_c = com_range(xyz, resids, *NMP_GROUPS[2])
    lid = angle_deg(lid_a, lid_b, lid_c)
    nmp = angle_deg(nmp_a, nmp_b, nmp_c)
    if single:
        return lid[0], nmp[0]
    return lid, nmp


def angles_from_gro(gro: Path) -> tuple[float, float]:
    xyz, resids, _ = gro_ca(gro)
    lid, nmp = angles_from_ca(xyz, resids)
    return float(lid), float(nmp)


def write_refs() -> dict:
    open_gro = ROOT / "systems/adk/gmx_common_open/protein.gro"
    closed_gro = ROOT / "systems/adk/gmx_common_closed/protein.gro"
    if not open_gro.exists() or not closed_gro.exists():
        raise AdkError("run scripts/prepare_adk.sh first")
    o_lid, o_nmp = angles_from_gro(open_gro)
    c_lid, c_nmp = angles_from_gro(closed_gro)

    def closed_side(open_v: float, closed_v: float, margin: float = 8.0) -> tuple[str, float]:
        cut = 0.5 * (open_v + closed_v)
        if closed_v < open_v:
            return "lt", float(min(cut, closed_v + margin))
        return "gt", float(max(cut, closed_v - margin))

    lid_op, lid_thr = closed_side(o_lid, c_lid)
    nmp_op, nmp_thr = closed_side(o_nmp, c_nmp)
    refs = {
        "open_lid": o_lid,
        "open_nmp": o_nmp,
        "closed_lid": c_lid,
        "closed_nmp": c_nmp,
        "closed_lid_op": lid_op,
        "closed_lid_thr": lid_thr,
        "closed_nmp_op": nmp_op,
        "closed_nmp_thr": nmp_thr,
        "commit_ps": 200.0,
        "lid_groups": [list(g) for g in LID_GROUPS],
        "nmp_groups": [list(g) for g in NMP_GROUPS],
    }
    dest = ROOT / "systems/adk/angle_refs.json"
    dest.write_text(json.dumps(refs, indent=2) + "\n", encoding="utf-8")
    log(
        f"open   LID={o_lid:.1f}  NMP={o_nmp:.1f}   "
        f"closed LID={c_lid:.1f}  NMP={c_nmp:.1f}   "
        f"closed window LID {lid_op} {lid_thr:.1f}  NMP {nmp_op} {nmp_thr:.1f}  commit≥200 ps"
    )
    log(f"wrote {dest}")
    return refs


def load_refs() -> dict:
    path = ROOT / "systems/adk/angle_refs.json"
    if not path.exists():
        return write_refs()
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    p = argparse.ArgumentParser(description="AdK LID/NMP angles")
    p.add_argument("--refs", action="store_true")
    p.add_argument("--gro", type=Path, default=None)
    args = p.parse_args()
    if args.refs:
        write_refs()
        return 0
    if args.gro:
        lid, nmp = angles_from_gro(args.gro)
        print(f"{args.gro}  LID={lid:.2f}  NMP={nmp:.2f}")
        return 0
    write_refs()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
