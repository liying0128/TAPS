#!/usr/bin/env python3
"""Build phi/psi index groups from a GROMACS gro file."""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path


def parse_gro_atoms(path: Path):
    atoms = []
    lines = path.read_text().splitlines()
    natom = int(lines[1])
    for line in lines[2 : 2 + natom]:
        resi = int(line[0:5])
        resn = line[5:10].strip()
        name = line[10:15].strip()
        idx = int(line[15:20])
        atoms.append((idx, resi, resn, name))
    return atoms


def write_dihedral_ndx(gro: Path, ndx: Path) -> None:
    atoms = parse_gro_atoms(gro)
    by_res = defaultdict(dict)
    resn_of = {}
    for idx, resi, resn, name in atoms:
        by_res[resi][name] = idx
        resn_of[resi] = resn

    residues = sorted(by_res)
    lines = []
    count = 0
    for i, resi in enumerate(residues):
        if resn_of[resi] not in {"ALA", "GLY", "SER", "THR", "ASP", "GLU", "ASN", "GLN",
                                  "LYS", "ARG", "HIS", "HIE", "HID", "HIP", "CYS", "MET",
                                  "PHE", "TYR", "TRP", "LEU", "ILE", "VAL", "PRO"}:
            continue
        prev_i = i - 1
        next_i = i + 1
        if prev_i < 0 or next_i >= len(residues):
            continue
        prev, nxt = residues[prev_i], residues[next_i]
        try:
            phi = (by_res[prev]["C"], by_res[resi]["N"], by_res[resi]["CA"], by_res[resi]["C"])
            psi = (by_res[resi]["N"], by_res[resi]["CA"], by_res[resi]["C"], by_res[nxt]["N"])
        except KeyError:
            continue
        count += 1
        tag = f"{resn_of[resi]}{resi}"
        lines.append(f"[ phi_{tag} ]\n" + " ".join(map(str, phi)) + "\n")
        lines.append(f"[ psi_{tag} ]\n" + " ".join(map(str, psi)) + "\n")
    if count == 0:
        raise SystemExit(f"no phi/psi groups found in {gro}")
    ndx.write_text("".join(lines))
    print(f"wrote {ndx} ({count} residues)")


if __name__ == "__main__":
    gro = Path(sys.argv[1])
    ndx = Path(sys.argv[2]) if len(sys.argv) > 2 else gro.with_suffix(".dihe.ndx")
    write_dihedral_ndx(gro, ndx)
