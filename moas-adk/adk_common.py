#!/usr/bin/env python3
"""Shared helpers for MOAS-AdK (no TAPS/CLN025 imports)."""

from __future__ import annotations

import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Sequence

import numpy as np

ROOT = Path(__file__).resolve().parent
ANALYSIS = ROOT / "analysis"
LOG_DIR = ROOT / "logs"
RUN_LOG = LOG_DIR / "adk.log"


class AdkError(RuntimeError):
    pass


def log(msg: str, level: str = "INFO") -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {level:<7s} {msg}"
    print(line, flush=True)
    with RUN_LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def find_gmx() -> str:
    explicit = os.environ.get("GMX") or os.environ.get("GMX_BIN")
    if explicit:
        path = Path(explicit)
        if path.exists():
            return str(path)
        found = shutil.which(explicit)
        if found:
            return found
        raise AdkError(f"GMX={explicit} not found")
    for name in ("gmx", "gmx_mpi", "gmx_d"):
        found = shutil.which(name)
        if found:
            return found
    raise AdkError("gmx not in PATH")


def run_gmx(argv: Sequence[str], cwd: Path, stdin_text: str = "") -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.setdefault("GMX_MAXBACKUP", "-1")
    env.setdefault("GMX_SUPPRESS_DUMP", "1")
    log("$ " + " ".join(str(x) for x in argv) + f"   (cwd={cwd})")
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
        raise AdkError(f"command failed ({proc.returncode}): {' '.join(str(x) for x in argv)}\n{tail}")
    return proc


def parse_xvg(path: Path) -> np.ndarray:
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped or stripped[0] in "#@&":
            continue
        rows.append([float(x) for x in stripped.split()])
    if not rows:
        raise AdkError(f"no data in {path}")
    return np.asarray(rows, dtype=np.float64)


def gro_ca(gro: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return CA xyz (n,3) in nm, residue ids, 1-based atom ids."""
    lines = gro.read_text(encoding="utf-8", errors="replace").splitlines()
    natom = int(lines[1])
    xyz, resids, ids = [], [], []
    for line in lines[2 : 2 + natom]:
        name = line[10:15].strip()
        if name != "CA":
            continue
        resids.append(int(line[0:5]))
        ids.append(int(line[15:20]))
        xyz.append((float(line[20:28]), float(line[28:36]), float(line[36:44])))
    if len(ids) < 50:
        raise AdkError(f"found {len(ids)} CA atoms in {gro}")
    return np.asarray(xyz, dtype=np.float64), np.asarray(resids, dtype=np.int32), np.asarray(ids, dtype=np.int32)


def write_ca_ndx(path: Path, gro: Path) -> list[int]:
    _, _, ids = gro_ca(gro)
    path.write_text("[ CA ]\n" + " ".join(str(i) for i in ids.tolist()) + "\n", encoding="utf-8")
    return ids.tolist()


def dump_frame(tpr: Path, xtc: Path, t_ps: float, dest: Path, cwd: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    gmx = find_gmx()
    run_gmx(
        [gmx, "trjconv", "-s", str(tpr), "-f", str(xtc), "-dump", f"{t_ps:.3f}", "-o", str(dest)],
        cwd=cwd,
        stdin_text="System\n",
    )
    if not dest.exists() or dest.stat().st_size == 0:
        raise AdkError(f"trjconv did not write {dest}")
