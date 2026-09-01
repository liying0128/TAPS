#!/usr/bin/env python3
"""
STAGE 05  |  大纲 §5.4 复合 Seed 选择

Score(x) = S_p(x) * f(1/ρ(x)) - λ E_penalty(x)
再按 φ/ψ 距离做多样性，避免同一阱里连发。

--strategy 对应大纲消融：
  density     纯低密度（Least-counts 味道）
  potential   纯 S_p
  combo       密度 × 潜力
  full        密度 × 潜力 − 物理惩罚 + 多样性（默认）

输入:  analysis/<system>/windows.npz
       analysis/<system>/sp_scores.npz     （density 策略可不训练模型）
       analysis/<system>/dihedrals.npz
       runs/md_100ns.xtc + .tpr            （写出 seed.gro）
输出:  analysis/<system>/seeds_round00.json
       analysis/<system>/seeds/seed_XX.gro

上一阶段: python3 stage04_train_sp.py
下一阶段: python3 stage06_adaptive_round.py
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

from taps_common import (  # noqa: E402
    MAIN_KEYS,
    TapsError,
    cv_dist,
    find_gmx,
    get_spec,
    load_dihedrals,
    log,
    parse_xvg,
    run_gmx,
    to_bins,
    wrap_deg,
)


def load_energy(spec, t_query: np.ndarray) -> np.ndarray:
    edr = spec.workdir / spec.prod_edr
    if not edr.exists():
        log(f"no {edr.name}; E_penalty = 0", "WARN")
        return np.zeros_like(t_query)
    out = spec.outdir / "potential.xvg"
    gmx = find_gmx()
    try:
        run_gmx(
            [gmx, "energy", "-f", str(edr), "-o", str(out)],
            cwd=spec.outdir,
            stdin_text="Potential\n",
        )
        tab = parse_xvg(out)
        return np.interp(t_query, tab[:, 0], tab[:, 1])
    except TapsError as exc:
        log(f"could not read Potential from edr ({exc}); E_penalty = 0", "WARN")
        return np.zeros_like(t_query)


def density_at(phi: np.ndarray, psi: np.ndarray, phi_q: np.ndarray, psi_q: np.ndarray, nbins: int) -> np.ndarray:
    i, j = to_bins(phi, psi, nbins)
    hist = np.zeros((nbins, nbins), dtype=np.float64)
    np.add.at(hist, (i, j), 1)
    hist /= max(1.0, hist.sum())
    iq, jq = to_bins(phi_q, psi_q, nbins)
    return hist[iq, jq]


def greedy_diverse(phi, psi, score, n_seeds: int, min_deg: float) -> list:
    order = np.argsort(-score)
    picked = []
    for idx in order:
        i = int(idx)
        if all(float(cv_dist(phi[i], psi[i], phi[j], psi[j])) >= min_deg for j in picked):
            picked.append(i)
        if len(picked) >= n_seeds:
            break
    return picked


def dump_frame(spec, t_ps: float, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    gmx = find_gmx()
    run_gmx(
        [
            gmx,
            "trjconv",
            "-s",
            str(spec.workdir / spec.prod_tpr),
            "-f",
            str(spec.workdir / spec.prod_xtc),
            "-dump",
            f"{t_ps:.3f}",
            "-o",
            str(dest),
        ],
        cwd=spec.outdir,
        stdin_text="System\n",
    )
    if not dest.exists() or dest.stat().st_size == 0:
        raise TapsError(f"trjconv did not write {dest}")


def run(
    system: str,
    strategy: str,
    n_seeds: int,
    nbins: int,
    lam: float,
    min_deg: float,
    eps: float,
) -> None:
    spec = get_spec(system)
    dih = load_dihedrals(spec)
    win_path = spec.outdir / "windows.npz"
    if not win_path.exists():
        raise TapsError(f"missing {win_path}. Run stage03 first.")
    windows = np.load(win_path)
    phi_e = wrap_deg(windows["phi_end"])
    psi_e = wrap_deg(windows["psi_end"])
    t_e = windows["t_end_ps"]
    end_idx = windows["end_idx"]

    scores_path = spec.outdir / "sp_scores.npz"
    if strategy == "density":
        if scores_path.exists():
            S_p = np.load(scores_path)["S_p"].astype(np.float64)
        else:
            S_p = np.ones(len(phi_e), dtype=np.float64)
            log("no S_p file; density strategy uses S_p=1", "WARN")
    else:
        if not scores_path.exists():
            raise TapsError(f"missing {scores_path}. Run stage04, or use --strategy density")
        S_p = np.load(scores_path)["S_p"].astype(np.float64)
        if len(S_p) != len(phi_e):
            raise TapsError("sp_scores and windows length differ; rerun stage03→04")

    rho = density_at(dih["phi"], dih["psi"], phi_e, psi_e, nbins)
    inv = 1.0 / (rho + eps)
    inv = inv / (inv.max() + 1e-12)

    energy = load_energy(spec, t_e)
    med = float(np.median(energy))
    mad = float(np.median(np.abs(energy - med))) + 1e-6
    z = (energy - med) / (1.4826 * mad)
    penalty = np.clip(z - 2.0, 0.0, None)

    if strategy == "density":
        raw = inv
    elif strategy == "potential":
        raw = S_p
    elif strategy == "combo":
        raw = S_p * inv
    else:
        raw = S_p * inv - lam * penalty

    use_div = strategy in {"full", "combo", "potential", "density"}
    picked = greedy_diverse(phi_e, psi_e, raw, n_seeds, min_deg if use_div else 0.0)
    if len(picked) < n_seeds:
        log(f"only found {len(picked)} diverse seeds (asked {n_seeds})", "WARN")

    seed_dir = spec.outdir / "seeds"
    seed_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for rank, idx in enumerate(picked):
        gro = seed_dir / f"seed_{rank:02d}.gro"
        dump_frame(spec, float(t_e[idx]), gro)
        rec = {
            "rank": rank,
            "window_index": idx,
            "frame": int(end_idx[idx]),
            "t_ps": float(t_e[idx]),
            "phi": float(phi_e[idx]),
            "psi": float(psi_e[idx]),
            "S_p": float(S_p[idx]),
            "rho": float(rho[idx]),
            "inv_rho": float(inv[idx]),
            "E": float(energy[idx]),
            "E_penalty": float(penalty[idx]),
            "score": float(raw[idx]),
            "gro": str(gro.relative_to(ROOT)),
        }
        records.append(rec)
        log(
            f"seed {rank:02d}  t={rec['t_ps']:.1f} ps  "
            f"φ={rec['phi']:.1f} ψ={rec['psi']:.1f}  "
            f"S_p={rec['S_p']:.3f} ρ={rec['rho']:.2e} score={rec['score']:.3f}"
        )

    payload = {
        "system": spec.key,
        "strategy": strategy,
        "n_seeds": len(records),
        "lambda": lam,
        "min_deg": min_deg,
        "nbins": nbins,
        "formula": "Score = S_p * f(1/rho) - lambda * E_penalty",
        "seeds": records,
    }
    dest = spec.outdir / "seeds_round00.json"
    dest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    log(f"wrote {dest.relative_to(ROOT)}")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--system", default="ala2_vacuum", choices=MAIN_KEYS)
    p.add_argument(
        "--strategy",
        default="full",
        choices=("density", "potential", "combo", "full"),
        help="ablation mode from outline §5.4",
    )
    p.add_argument("--n-seeds", type=int, default=8)
    p.add_argument("--nbins", type=int, default=36)
    p.add_argument("--lambda", dest="lam", type=float, default=0.3)
    p.add_argument("--min-deg", type=float, default=30.0, help="diversity cutoff on (φ,ψ)")
    p.add_argument("--eps", type=float, default=1e-6)
    p.add_argument("--check", action="store_true")
    args = p.parse_args(argv)
    try:
        spec = get_spec(args.system)
        log(f"STAGE 05  select seeds  system={args.system}  strategy={args.strategy}")
        win = spec.outdir / "windows.npz"
        if not win.exists():
            log("missing windows.npz; run stage03 first", "ERROR")
            return 2
        if args.strategy != "density" and not (spec.outdir / "sp_scores.npz").exists():
            log("missing sp_scores.npz; run stage04, or pass --strategy density", "ERROR")
            return 2
        if args.check:
            log("check passed")
            return 0
        run(args.system, args.strategy, args.n_seeds, args.nbins, args.lam, args.min_deg, args.eps)
        return 0
    except TapsError as exc:
        log(str(exc), "ERROR")
        return 1


if __name__ == "__main__":
    sys.exit(main())
