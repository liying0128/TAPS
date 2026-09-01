#!/usr/bin/env python3
"""
STAGE 06  |  大纲 §5.1 闭环：从选中的 seed 重启短 MD（无偏）

不改动力学，只换发枪位置。默认用 md_short*.mdp（真空 100 ps）。
跑完后把各条短轨迹的 φ/ψ 写到 analysis，供下一轮在线更新。

输入:  analysis/<system>/seeds_round00.json
       systems/.../mdp/md_short*.mdp
输出:  systems/.../adaptive/round01/seed_XX/md_short.xtc
       analysis/<system>/round01_status.json
       analysis/<system>/adaptive/round01/seed_XX_dihedrals.npz

上一阶段: python3 stage05_select_seeds.py
下一阶段: 把新短轨迹并入数据后，再跑 stage03→04 做在线更新
          （或先看 analysis/<system>/adaptive/ 里的新 φ/ψ）
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from taps_common import (  # noqa: E402
    MAIN_KEYS,
    PHI_ATOMS,
    PSI_ATOMS,
    TapsError,
    find_gmx,
    get_spec,
    log,
    parse_xvg,
    run_gmx,
    wrap_deg,
)


def write_ndx(path: Path, name: str, atoms: tuple) -> None:
    path.write_text(f"[ {name} ]\n" + " ".join(str(a) for a in atoms) + "\n", encoding="utf-8")


def extract_short_dihedrals(gmx: str, xtc: Path, dest_npz: Path) -> None:
    import numpy as np

    dest_npz.parent.mkdir(parents=True, exist_ok=True)
    phi_ndx = dest_npz.with_name(dest_npz.stem + "_phi.ndx")
    psi_ndx = dest_npz.with_name(dest_npz.stem + "_psi.ndx")
    phi_xvg = dest_npz.with_name(dest_npz.stem + "_phi.xvg")
    psi_xvg = dest_npz.with_name(dest_npz.stem + "_psi.xvg")
    write_ndx(phi_ndx, "phi", PHI_ATOMS)
    write_ndx(psi_ndx, "psi", PSI_ATOMS)
    run_gmx([gmx, "angle", "-f", str(xtc), "-n", str(phi_ndx), "-ov", str(phi_xvg), "-type", "dihedral"], cwd=dest_npz.parent)
    run_gmx([gmx, "angle", "-f", str(xtc), "-n", str(psi_ndx), "-ov", str(psi_xvg), "-type", "dihedral"], cwd=dest_npz.parent)
    phi_tab = parse_xvg(phi_xvg)
    psi_tab = parse_xvg(psi_xvg)
    n = min(len(phi_tab), len(psi_tab))
    np.savez_compressed(
        dest_npz,
        t_ps=phi_tab[:n, 0],
        phi=wrap_deg(phi_tab[:n, 1]),
        psi=wrap_deg(psi_tab[:n, 1]),
    )


def mdrun_short(gmx: str, workdir: Path, deffnm: str, nt: int, gpu: bool) -> None:
    import run_md

    argv = [
        gmx,
        "mdrun",
        "-v",
        "-deffnm",
        deffnm,
        "-cpt",
        "1",
        "-nt",
        str(nt),
        "-pin",
        "on" if gpu else "off",
    ]
    if gpu:
        argv += ["-ntmpi", "1", "-nb", "gpu", "-pme", "gpu", "-bonded", "gpu", "-pmefft", "gpu", "-update", "gpu"]
    progress = run_md.MdProgress(
        label=deffnm,
        nsteps=None,
        dt_ps=0.002,
        log_path=workdir / f"{deffnm}.log",
        gpu=gpu,
        is_em=False,
    )
    run_md.run_mdrun_process(argv, cwd=workdir, progress=progress)
    logp = workdir / f"{deffnm}.log"
    if not logp.exists() or "Finished mdrun" not in logp.read_text(encoding="utf-8", errors="replace"):
        raise TapsError(f"short MD did not finish: {logp}")


def run(system: str, seeds_json: Path, round_id: int, nt: int, gpu: bool, force: bool) -> None:
    spec = get_spec(system)
    payload = json.loads(seeds_json.read_text(encoding="utf-8"))
    seeds = payload.get("seeds") or []
    if not seeds:
        raise TapsError(f"no seeds in {seeds_json}")

    mdp = spec.workdir / "mdp" / spec.short_mdp
    if not mdp.exists():
        raise TapsError(f"missing {mdp}")
    top = spec.workdir / "topol.top"
    gmx = find_gmx()

    adaptive_root = spec.workdir / "adaptive" / f"round{round_id:02d}"
    adaptive_root.mkdir(parents=True, exist_ok=True)
    analysis_round = spec.outdir / "adaptive" / f"round{round_id:02d}"
    analysis_round.mkdir(parents=True, exist_ok=True)

    status = {
        "system": spec.key,
        "round": round_id,
        "nt": nt,
        "gpu": gpu,
        "seeds_json": str(seeds_json),
        "jobs": [],
    }

    for rec in seeds:
        rank = int(rec["rank"])
        gro = ROOT / rec["gro"]
        if not gro.exists():
            raise TapsError(f"missing seed gro {gro}")
        job = adaptive_root / f"seed_{rank:02d}"
        job.mkdir(parents=True, exist_ok=True)
        xtc = job / "md_short.xtc"
        entry = {"rank": rank, "dir": str(job.relative_to(ROOT)), "status": "pending"}
        if xtc.exists() and (job / "md_short.gro").exists() and not force:
            log(f"seed {rank:02d}: already complete -> skip")
            entry["status"] = "skipped"
        else:
            run_gmx(
                [
                    gmx,
                    "grompp",
                    "-f",
                    str(mdp),
                    "-c",
                    str(gro),
                    "-p",
                    str(top),
                    "-o",
                    "md_short.tpr",
                    "-maxwarn",
                    "1",
                ],
                cwd=job,
            )
            log(f"seed {rank:02d}: short MD from {gro.name}  φ={rec.get('phi')} ψ={rec.get('psi')}")
            mdrun_short(gmx, job, "md_short", nt=nt, gpu=gpu)
            entry["status"] = "ran"
        if xtc.exists():
            dest = analysis_round / f"seed_{rank:02d}_dihedrals.npz"
            extract_short_dihedrals(gmx, xtc, dest)
            entry["dihedrals"] = str(dest.relative_to(ROOT))
        status["jobs"].append(entry)

    dest = spec.outdir / f"round{round_id:02d}_status.json"
    dest.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    log(f"wrote {dest.relative_to(ROOT)}")
    log(f"round {round_id:02d}: {sum(j['status']=='ran' for j in status['jobs'])} ran, "
        f"{sum(j['status']=='skipped' for j in status['jobs'])} skipped")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--system", default="ala2_vacuum", choices=MAIN_KEYS)
    p.add_argument("--seeds", default=None, help="default: analysis/<sys>/seeds_round00.json")
    p.add_argument("--round", type=int, default=1)
    p.add_argument("--nt", type=int, default=int(os.environ.get("TAPS_NT", "0") or 0))
    p.add_argument("--cpu", action="store_true")
    p.add_argument("--gpu", action="store_true")
    p.add_argument("--force", action="store_true")
    p.add_argument("--check", action="store_true")
    args = p.parse_args(argv)
    try:
        import run_md

        spec = get_spec(args.system)
        seeds = Path(args.seeds) if args.seeds else spec.outdir / "seeds_round00.json"
        log(f"STAGE 06  adaptive short MD  system={args.system}  round={args.round}")
        if not seeds.exists():
            log(f"missing {seeds}. Run stage05 first.", "ERROR")
            return 2
        mdp = spec.workdir / "mdp" / spec.short_mdp
        if not mdp.exists():
            log(f"missing {mdp}", "ERROR")
            return 2
        if args.check:
            log(f"seeds file: {seeds}  short mdp: {mdp.name}")
            log("check passed")
            return 0
        nt = args.nt or run_md.default_thread_count()
        if args.cpu:
            gpu = False
        elif args.gpu:
            gpu = True
        else:
            gpu = run_md.detect_gpu()
        log(f"threads={nt}  gpu={gpu}  seeds={seeds}")
        run(args.system, seeds, args.round, nt, gpu, args.force)
        return 0
    except TapsError as exc:
        log(str(exc), "ERROR")
        return 1


if __name__ == "__main__":
    sys.exit(main())
