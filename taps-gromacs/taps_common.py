#!/usr/bin/env python3
"""Shared helpers for the main-system TAPS stage scripts (not a runnable stage)."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

ROOT = Path(__file__).resolve().parent
ANALYSIS = ROOT / "analysis"

# Outline §2 / §5.6: main system only. Extension systems use other CVs later.
MAIN_KEYS = ("ala2_vacuum", "ala2_water")

# Outline §2 basins (degrees). Used for FPT / seed sanity checks.
BASINS: Dict[str, Tuple[float, float]] = {
    "c7eq": (-80.0, 70.0),
    "c7ax": (70.0, -70.0),
    "c5": (-150.0, 150.0),
    "alphaR": (-70.0, -30.0),
}
BASIN_RADIUS = 25.0

# ACE-ALA-NME backbone (1-based GROMACS ids) after pdb2gmx -ignh.
PHI_ATOMS = (5, 7, 9, 15)  # ACE-C, ALA-N, ALA-CA, ALA-C
PSI_ATOMS = (7, 9, 15, 17)  # ALA-N, ALA-CA, ALA-C, NME-N


@dataclass(frozen=True)
class MainSpec:
    key: str
    title: str
    rel_dir: str
    solvent: str
    short_mdp: str
    prod_xtc: str = "runs/md_100ns.xtc"
    prod_tpr: str = "runs/md_100ns.tpr"
    prod_edr: str = "runs/md_100ns.edr"
    tag: str = ""

    @property
    def workdir(self) -> Path:
        return ROOT / self.rel_dir

    @property
    def outdir(self) -> Path:
        if self.tag:
            return ANALYSIS / self.key / "campaigns" / self.tag
        return ANALYSIS / self.key

    @property
    def adaptive_root(self) -> Path:
        if self.tag:
            return self.workdir / "adaptive" / "campaigns" / self.tag
        return self.workdir / "adaptive"


SPECS: Dict[str, MainSpec] = {
    "ala2_vacuum": MainSpec(
        key="ala2_vacuum",
        title="Alanine dipeptide vacuum (main system)",
        rel_dir="systems/alanine_dipeptide/vacuum",
        solvent="vacuum",
        short_mdp="md_short_vacuum.mdp",
    ),
    "ala2_water": MainSpec(
        key="ala2_water",
        title="Alanine dipeptide water (main system, explicit solvent)",
        rel_dir="systems/alanine_dipeptide/water",
        solvent="water",
        short_mdp="md_short.mdp",
    ),
}


class TapsError(RuntimeError):
    pass


def log(msg: str, level: str = "INFO") -> None:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {level:<7s} {msg}", flush=True)


def get_spec(key: str, tag: str = "") -> MainSpec:
    if key not in SPECS:
        raise TapsError(
            f"unknown system {key!r}. Main-system scripts accept: {', '.join(MAIN_KEYS)}"
        )
    spec = SPECS[key]
    return replace(spec, tag=tag) if tag else spec


def find_gmx() -> str:
    explicit = os.environ.get("GMX") or os.environ.get("GMX_BIN")
    if explicit:
        path = Path(explicit)
        if path.exists():
            return str(path)
        found = shutil.which(explicit)
        if found:
            return found
        raise TapsError(f"GMX={explicit} not found")
    for name in ("gmx", "gmx_mpi", "gmx_d"):
        found = shutil.which(name)
        if found:
            return found
    raise TapsError("gmx not in PATH. Load the GROMACS module or set GMX=/path/to/gmx")


def run_gmx(
    argv: Sequence[str],
    cwd: Path,
    stdin_text: str = "",
) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.setdefault("GMX_MAXBACKUP", "-1")
    env.setdefault("GMX_SUPPRESS_DUMP", "1")
    log("$ " + " ".join(argv) + f"   (cwd={cwd})")
    proc = subprocess.run(
        list(argv),
        cwd=str(cwd),
        env=env,
        input=stdin_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if proc.returncode != 0:
        tail = "\n".join((proc.stdout or "").splitlines()[-20:])
        raise TapsError(f"command failed ({proc.returncode}): {' '.join(argv)}\n{tail}")
    return proc


def parse_xvg(path: Path) -> np.ndarray:
    rows: List[List[float]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped or stripped[0] in "#@&":
            continue
        rows.append([float(x) for x in stripped.split()])
    if not rows:
        raise TapsError(f"no data in {path}")
    return np.asarray(rows, dtype=np.float64)


def wrap_deg(angle: np.ndarray) -> np.ndarray:
    return (np.asarray(angle, dtype=np.float64) + 180.0) % 360.0 - 180.0


def circ_diff(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return wrap_deg(np.asarray(a, dtype=np.float64) - np.asarray(b, dtype=np.float64))


def cv_dist(phi1, psi1, phi2, psi2) -> np.ndarray:
    return np.hypot(circ_diff(phi1, phi2), circ_diff(psi1, psi2))


def to_bins(phi: np.ndarray, psi: np.ndarray, nbins: int) -> Tuple[np.ndarray, np.ndarray]:
    i = np.floor((wrap_deg(phi) + 180.0) / 360.0 * nbins).astype(np.int64) % nbins
    j = np.floor((wrap_deg(psi) + 180.0) / 360.0 * nbins).astype(np.int64) % nbins
    return i, j


def in_basin(phi: np.ndarray, psi: np.ndarray, center: Tuple[float, float], radius: float = BASIN_RADIUS) -> np.ndarray:
    return cv_dist(phi, psi, center[0], center[1]) <= radius


def nearest_basin(phi: float, psi: float, radius: float = BASIN_RADIUS) -> Optional[str]:
    best = None
    best_d = radius
    for name, center in BASINS.items():
        d = float(cv_dist(phi, psi, center[0], center[1]))
        if d <= best_d:
            best_d = d
            best = name
    return best


def resample_1ps(t_ps: np.ndarray, phi: np.ndarray, psi: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Interpolate a segment onto a 1 ps grid so mixed xtc strides can share one window length."""
    t_ps = np.asarray(t_ps, dtype=np.float64)
    if len(t_ps) < 2:
        return t_ps, wrap_deg(phi), wrap_deg(psi)
    t0, t1 = float(t_ps[0]), float(t_ps[-1])
    t_new = np.arange(t0, t1 + 0.5, 1.0)
    phi_u = np.unwrap(np.deg2rad(wrap_deg(phi)))
    psi_u = np.unwrap(np.deg2rad(wrap_deg(psi)))
    phi_i = wrap_deg(np.rad2deg(np.interp(t_new, t_ps, phi_u)))
    psi_i = wrap_deg(np.rad2deg(np.interp(t_new, t_ps, psi_u)))
    return t_new, phi_i, psi_i


def load_dihedrals(spec: MainSpec) -> dict:
    path = spec.outdir / "dihedrals.npz"
    if not path.exists():
        raise TapsError(
            f"missing {path}. Run: python3 stage01_extract_dihedrals.py --system {spec.key}"
        )
    data = np.load(path, allow_pickle=False)
    return {k: data[k] for k in data.files}


def require_numpy() -> None:
    # imported at module level; this exists so stage --check can stay explicit
    if np.__version__ is None:  # pragma: no cover
        raise TapsError("numpy is required")


def dump_frame(tpr: Path, xtc: Path, t_ps: float, dest: Path, cwd: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    gmx = find_gmx()
    run_gmx(
        [
            gmx,
            "trjconv",
            "-s",
            str(tpr),
            "-f",
            str(xtc),
            "-dump",
            f"{t_ps:.3f}",
            "-o",
            str(dest),
        ],
        cwd=cwd,
        stdin_text="System\n",
    )
    if not dest.exists() or dest.stat().st_size == 0:
        raise TapsError(f"trjconv did not write {dest}")


def rama_coverage(phi: np.ndarray, psi: np.ndarray, nbins: int = 36) -> float:
    i, j = to_bins(phi, psi, nbins)
    occupied = len(set(zip(i.tolist(), j.tolist())))
    return occupied / float(nbins * nbins)


def basin_fpt_ps(
    phi: np.ndarray,
    psi: np.ndarray,
    t_accum_ps: np.ndarray,
    name: str,
    radius: float = BASIN_RADIUS,
) -> Optional[float]:
    center = BASINS[name]
    hit = np.flatnonzero(in_basin(phi, psi, center, radius))
    if hit.size == 0:
        return None
    return float(t_accum_ps[int(hit[0])])


def spearman(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    if a.size < 3:
        return float("nan")
    ra = np.argsort(np.argsort(a))
    rb = np.argsort(np.argsort(b))
    if ra.std() < 1e-12 or rb.std() < 1e-12:
        return float("nan")
    return float(np.corrcoef(ra, rb)[0, 1])


def check_main_inputs(spec: MainSpec, need_prod: bool = True) -> List[str]:
    errors: List[str] = []
    if not spec.workdir.is_dir():
        errors.append(f"missing system directory {spec.workdir}")
        return errors
    if need_prod:
        for rel in (spec.prod_xtc, spec.prod_tpr):
            path = spec.workdir / rel
            if not path.exists():
                errors.append(f"missing {path}. Finish run_md.py --system {spec.key} --length 100 first")
    return errors
