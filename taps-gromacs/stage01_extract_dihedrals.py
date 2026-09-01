#!/usr/bin/env python3
"""
STAGE 01  |  大纲 §5.2 轨迹表示（主体系：二面角 φ/ψ）

从 run_md.py 产出的无偏长轨迹抽取 Ramachandran 坐标。
这是主体系后续覆盖率、切片、S_p 训练的共同输入。

输入:  systems/alanine_dipeptide/<vac|water>/runs/md_100ns.xtc
输出:  analysis/<system>/dihedrals.npz   (t_ps, phi, psi)
       analysis/<system>/phi.xvg  psi.xvg

上一阶段: run_md.py --system ala2_vacuum --length 100
下一阶段: python3 stage02_cmd_coverage.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from taps_common import (  # noqa: E402
    ANALYSIS,
    MAIN_KEYS,
    PHI_ATOMS,
    PSI_ATOMS,
    TapsError,
    check_main_inputs,
    find_gmx,
    get_spec,
    log,
    parse_xvg,
    run_gmx,
    wrap_deg,
)


def write_single_ndx(path: Path, name: str, atoms: tuple) -> None:
    path.write_text(f"[ {name} ]\n" + " ".join(str(a) for a in atoms) + "\n", encoding="utf-8")


def extract_angle(gmx: str, xtc: Path, ndx: Path, xvg: Path, cwd: Path) -> None:
    run_gmx(
        [gmx, "angle", "-f", str(xtc), "-n", str(ndx), "-ov", str(xvg), "-type", "dihedral"],
        cwd=cwd,
    )


def run(system: str, traj_tag: str) -> Path:
    spec = get_spec(system)
    errors = check_main_inputs(spec)
    if errors:
        raise TapsError("\n".join(errors))

    xtc = spec.workdir / f"runs/{traj_tag}.xtc"
    if not xtc.exists():
        raise TapsError(f"missing trajectory {xtc}")

    out = spec.outdir
    out.mkdir(parents=True, exist_ok=True)
    phi_ndx = out / "phi.ndx"
    psi_ndx = out / "psi.ndx"
    phi_xvg = out / "phi.xvg"
    psi_xvg = out / "psi.xvg"
    write_single_ndx(phi_ndx, "phi", PHI_ATOMS)
    write_single_ndx(psi_ndx, "psi", PSI_ATOMS)

    gmx = find_gmx()
    log(f"{spec.key}: extracting φ/ψ from {xtc.relative_to(ROOT)}")
    extract_angle(gmx, xtc, phi_ndx, phi_xvg, cwd=out)
    extract_angle(gmx, xtc, psi_ndx, psi_xvg, cwd=out)

    phi_tab = parse_xvg(phi_xvg)
    psi_tab = parse_xvg(psi_xvg)
    n = min(len(phi_tab), len(psi_tab))
    t_ps = phi_tab[:n, 0]
    phi = wrap_deg(phi_tab[:n, 1])
    psi = wrap_deg(psi_tab[:n, 1])
    if len(t_ps) > 1:
        dt = float(t_ps[1] - t_ps[0])
    else:
        dt = 0.0

    dest = out / "dihedrals.npz"
    np.savez_compressed(
        dest,
        t_ps=t_ps,
        phi=phi,
        psi=psi,
        dt_ps=np.array(dt),
        n_frames=np.array(n),
        xtc=np.array(str(xtc)),
        traj_tag=np.array(traj_tag),
    )
    log(
        f"wrote {dest.relative_to(ROOT)}  frames={n}  "
        f"dt={dt:.3f} ps  t={t_ps[0]:.1f}→{t_ps[-1]:.1f} ps"
    )
    log(f"φ range [{phi.min():.1f}, {phi.max():.1f}]  ψ range [{psi.min():.1f}, {psi.max():.1f}]")
    return dest


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--system", default="ala2_vacuum", choices=MAIN_KEYS)
    p.add_argument("--traj-tag", default="md_100ns", help="runs/<tag>.xtc (default md_100ns)")
    p.add_argument("--check", action="store_true", help="verify inputs only")
    args = p.parse_args(argv)
    try:
        spec = get_spec(args.system)
        errors = check_main_inputs(spec)
        xtc = spec.workdir / f"runs/{args.traj_tag}.xtc"
        if not xtc.exists():
            errors.append(f"missing {xtc}")
        log(f"STAGE 01  extract dihedrals  system={args.system}")
        log(f"analysis dir: {ANALYSIS / args.system}")
        if errors:
            for e in errors:
                log(e, "ERROR")
            return 2
        if args.check:
            log("check passed; no extraction started")
            return 0
        run(args.system, args.traj_tag)
        return 0
    except TapsError as exc:
        log(str(exc), "ERROR")
        return 1


if __name__ == "__main__":
    sys.exit(main())
