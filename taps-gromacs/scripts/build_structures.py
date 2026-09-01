#!/usr/bin/env python3
"""Build TAPS initial structures: capped peptides + cleaned experimental PDBs."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from openmm import LocalEnergyMinimizer, LangevinMiddleIntegrator, CustomTorsionForce, unit
from openmm.app import ForceField, HBonds, Modeller, NoCutoff, PDBFile, Simulation
from pdbfixer import PDBFixer

ROOT = Path(__file__).resolve().parents[1]
SYS = ROOT / "systems"

AA3 = {
    "A": "ALA", "C": "CYS", "D": "ASP", "E": "GLU", "F": "PHE", "G": "GLY",
    "H": "HIS", "I": "ILE", "K": "LYS", "L": "LEU", "M": "MET", "N": "ASN",
    "P": "PRO", "Q": "GLN", "R": "ARG", "S": "SER", "T": "THR", "V": "VAL",
    "W": "TRP", "Y": "TYR",
}

# Bond lengths / angles (Engh & Huber-like, Angstrom / degree)
BL = {
    "CH3-C": 1.522,
    "C-O": 1.231,
    "C-N": 1.329,
    "N-CA": 1.458,
    "CA-C": 1.525,
    "CA-CB": 1.530,
    "N-CH3": 1.449,
}
ANG = {
    "CH3-C-N": 116.2,
    "CH3-C-O": 120.4,
    "C-N-CA": 121.7,
    "N-CA-C": 111.2,
    "CA-C-N": 116.2,
    "CA-C-O": 120.4,
    "C-N-CH3": 121.9,
    "N-CA-CB": 110.5,
}


def _norm(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v)
    if n < 1e-12:
        raise ValueError("zero vector")
    return v / n


def nerf(a, b, c, bond, angle_deg, torsion_deg) -> np.ndarray:
    """Place D given A-B-C, bond |C-D|, angle B-C-D, torsion A-B-C-D."""
    theta = math.radians(angle_deg)
    chi = math.radians(torsion_deg)
    bc = _norm(c - b)
    n = _norm(np.cross(b - a, bc))
    nc = np.cross(n, bc)
    m = np.column_stack((bc, nc, n))
    d_local = np.array(
        [
            -bond * math.cos(theta),
            bond * math.sin(theta) * math.cos(chi),
            bond * math.sin(theta) * math.sin(chi),
        ]
    )
    return c + m @ d_local


def format_atom(serial, name, resn, chain, resi, xyz, element) -> str:
    name = name.strip()
    name_field = name if len(name) == 4 else f" {name:<3s}"
    x, y, z = xyz
    return (
        f"ATOM  {serial:5d} {name_field} {resn:3s} {chain}{resi:4d}    "
        f"{x:8.3f}{y:8.3f}{z:8.3f}  1.00  0.00          {element:>2s}\n"
    )


def write_pdb(path: Path, atoms: list[dict], title: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"TITLE     {title}\n"]
    for i, atom in enumerate(atoms, 1):
        lines.append(
            format_atom(
                i,
                atom["name"],
                atom["resn"],
                atom["chain"],
                atom["resi"],
                atom["xyz"],
                atom["elem"],
            )
        )
    lines.append("TER\nEND\n")
    path.write_text("".join(lines))


def place_cb(n_xyz, ca_xyz, c_xyz) -> np.ndarray:
    v_n = _norm(n_xyz - ca_xyz)
    v_c = _norm(c_xyz - ca_xyz)
    bis = _norm(v_n + v_c)
    perp = _norm(np.cross(v_n, v_c))  # L-amino acid
    direction = _norm(-bis + perp)
    return ca_xyz + BL["CA-CB"] * direction


def build_capped_peptide(phi_list, psi_list, n_ala: int = 1) -> list[dict]:
    """ACE-(ALA)n-NME. phi_list/psi_list length = n_ala. omega = 180."""
    if len(phi_list) != n_ala or len(psi_list) != n_ala:
        raise ValueError("phi/psi length must equal n_ala")
    omega = 180.0
    atoms: list[dict] = []

    ace_ch3 = np.array([0.0, 0.0, 0.0])
    ace_c = np.array([BL["CH3-C"], 0.0, 0.0])
    dummy = np.array([0.0, 1.0, 0.0])
    ace_o = nerf(dummy, ace_ch3, ace_c, BL["C-O"], ANG["CH3-C-O"], 0.0)

    atoms.append({"name": "CH3", "resn": "ACE", "chain": "A", "resi": 1, "xyz": ace_ch3, "elem": "C"})
    atoms.append({"name": "C", "resn": "ACE", "chain": "A", "resi": 1, "xyz": ace_c, "elem": "C"})
    atoms.append({"name": "O", "resn": "ACE", "chain": "A", "resi": 1, "xyz": ace_o, "elem": "O"})

    prev_c = ace_c
    prev_ca_like = ace_ch3  # for first N placement torsion
    prev_n_xyz = None
    prev_ca_xyz = None

    for i in range(n_ala):
        resi = i + 2
        phi, psi = phi_list[i], psi_list[i]
        if i == 0:
            n_xyz = nerf(dummy, ace_ch3, ace_c, BL["C-N"], ANG["CH3-C-N"], 180.0)
        else:
            n_xyz = nerf(prev_n_xyz, prev_ca_xyz, prev_c, BL["C-N"], ANG["CA-C-N"], psi_list[i - 1])

        ca_xyz = nerf(prev_ca_like if i == 0 else prev_ca_xyz, prev_c, n_xyz, BL["N-CA"], ANG["C-N-CA"], omega)
        c_xyz = nerf(prev_c, n_xyz, ca_xyz, BL["CA-C"], ANG["N-CA-C"], phi)
        o_xyz = nerf(n_xyz, ca_xyz, c_xyz, BL["C-O"], ANG["CA-C-O"], psi + 180.0)
        cb_xyz = place_cb(n_xyz, ca_xyz, c_xyz)

        for name, xyz, elem in (
            ("N", n_xyz, "N"),
            ("CA", ca_xyz, "C"),
            ("C", c_xyz, "C"),
            ("O", o_xyz, "O"),
            ("CB", cb_xyz, "C"),
        ):
            atoms.append({"name": name, "resn": "ALA", "chain": "A", "resi": resi, "xyz": xyz, "elem": elem})

        prev_n_xyz, prev_ca_xyz, prev_c = n_xyz, ca_xyz, c_xyz
        prev_ca_like = ca_xyz

    nme_n = nerf(prev_n_xyz, prev_ca_xyz, prev_c, BL["C-N"], ANG["CA-C-N"], psi_list[-1])
    nme_ch3 = nerf(prev_ca_xyz, prev_c, nme_n, BL["N-CH3"], ANG["C-N-CH3"], omega)
    nme_resi = n_ala + 2
    atoms.append({"name": "N", "resn": "NME", "chain": "A", "resi": nme_resi, "xyz": nme_n, "elem": "N"})
    atoms.append({"name": "CH3", "resn": "NME", "chain": "A", "resi": nme_resi, "xyz": nme_ch3, "elem": "C"})
    return atoms


def build_uncapped_backbone(sequence: str, phi: float, psi: float) -> list[dict]:
    """Heavy-atom backbone + CB for an uncapped peptide (zwitterionic later via pdb2gmx)."""
    seq3 = [AA3[s] for s in sequence]
    omega = 180.0
    atoms: list[dict] = []
    n_xyz = np.array([0.0, 0.0, 0.0])
    ca_xyz = np.array([BL["N-CA"], 0.0, 0.0])
    dummy = np.array([0.0, 1.0, 0.0])
    c_xyz = nerf(dummy, n_xyz, ca_xyz, BL["CA-C"], ANG["N-CA-C"], phi)
    prev_n, prev_ca, prev_c = n_xyz, ca_xyz, c_xyz

    for i, resn in enumerate(seq3):
        resi = i + 1
        if i == 0:
            n_i, ca_i, c_i = n_xyz, ca_xyz, c_xyz
        else:
            n_i = nerf(prev_n, prev_ca, prev_c, BL["C-N"], ANG["CA-C-N"], psi)
            ca_i = nerf(prev_ca, prev_c, n_i, BL["N-CA"], ANG["C-N-CA"], omega)
            c_i = nerf(prev_c, n_i, ca_i, BL["CA-C"], ANG["N-CA-C"], phi)
        o_i = nerf(n_i, ca_i, c_i, BL["C-O"], ANG["CA-C-O"], psi + 180.0)
        atoms.append({"name": "N", "resn": resn, "chain": "A", "resi": resi, "xyz": n_i, "elem": "N"})
        atoms.append({"name": "CA", "resn": resn, "chain": "A", "resi": resi, "xyz": ca_i, "elem": "C"})
        atoms.append({"name": "C", "resn": resn, "chain": "A", "resi": resi, "xyz": c_i, "elem": "C"})
        atoms.append({"name": "O", "resn": resn, "chain": "A", "resi": resi, "xyz": o_i, "elem": "O"})
        if resn != "GLY":
            atoms.append({"name": "CB", "resn": resn, "chain": "A", "resi": resi, "xyz": place_cb(n_i, ca_i, c_i), "elem": "C"})
        prev_n, prev_ca, prev_c = n_i, ca_i, c_i
    return atoms


def minimize_capped_pdb(in_pdb: Path, out_pdb: Path, target_torsions: list[tuple] | None = None) -> None:
    """Add hydrogens with OpenMM, optionally restrain phi/psi, minimize, write heavy+H PDB."""
    pdb = PDBFile(str(in_pdb))
    ff = ForceField("amber99sbildn.xml")
    modeller = Modeller(pdb.topology, pdb.positions)
    modeller.addHydrogens(ff)
    system = ff.createSystem(modeller.topology, nonbondedMethod=NoCutoff, constraints=HBonds)

    if target_torsions:
        force = CustomTorsionForce("0.5*k*dtheta^2; dtheta=theta-theta0-floor((theta-theta0+pi)/(2*pi))*2*pi")
        force.addGlobalParameter("pi", math.pi)
        force.addPerTorsionParameter("k")
        force.addPerTorsionParameter("theta0")
        k = 2000.0  # kJ/mol/rad^2
        name_index = {(a.residue.index, a.name): a.index for a in modeller.topology.atoms()}
        for atoms4, theta0_deg in target_torsions:
            idxs = []
            for res_i, aname in atoms4:
                idxs.append(name_index[(res_i, aname)])
            force.addTorsion(*idxs, [k, math.radians(theta0_deg)])
        system.addForce(force)

    integrator = LangevinMiddleIntegrator(300 * unit.kelvin, 1.0 / unit.picosecond, 0.001 * unit.picoseconds)
    sim = Simulation(modeller.topology, system, integrator)
    sim.context.setPositions(modeller.positions)
    LocalEnergyMinimizer.minimize(sim.context, maxIterations=500)
    state = sim.context.getState(getPositions=True)
    PDBFile.writeFile(sim.topology, state.getPositions(), open(out_pdb, "w"))


def extract_chain(src: Path, dst: Path, chain_id: str = "A", model: int | None = 1) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    keep = []
    current_model = None
    with src.open() as f:
        for line in f:
            if line.startswith("MODEL"):
                try:
                    current_model = int(line.split()[1])
                except Exception:
                    current_model = 1
                continue
            if line.startswith("ENDMDL"):
                if model is not None and current_model == model:
                    break
                continue
            if line.startswith(("ATOM", "HETATM")):
                if model is not None and current_model not in (None, model) and current_model != model:
                    continue
                if line[21] != chain_id:
                    continue
                # drop crystal ligands / waters / hydrogens; pdbfixer will restore protein atoms
                resn = line[17:20].strip()
                if resn in {"HOH", "WAT", "SOL", "SO4", "PO4", "GOL", "EDO", "PEG", "AP5", "AP6"}:
                    continue
                keep.append("ATOM  " + line[6:] if line.startswith("HETATM") else line)
    with dst.open("w") as f:
        f.write(f"TITLE     {src.name} chain {chain_id}\n")
        f.writelines(keep)
        f.write("TER\nEND\n")


def pdbfixer_clean(src: Path, dst: Path, ph: float = 7.0) -> None:
    fixer = PDBFixer(filename=str(src))
    fixer.findMissingResidues()
    fixer.findNonstandardResidues()
    fixer.replaceNonstandardResidues()
    fixer.removeHeterogens(keepWater=False)
    fixer.findMissingAtoms()
    fixer.addMissingAtoms()
    fixer.addMissingHydrogens(ph)
    dst.parent.mkdir(parents=True, exist_ok=True)
    PDBFile.writeFile(fixer.topology, fixer.positions, open(dst, "w"))


def heavy_only(src: Path, dst: Path) -> None:
    """Keep heavy atoms as ATOM records so gmx pdb2gmx -ignh can rebuild hydrogens.

    OpenMM writes ACE/NME as HETATM and names the NME methyl carbon 'C';
    GROMACS amber99sb-ildn expects ATOM records and NME atom name CH3.
    HIS is renamed to HIE (epsilon tautomer) to avoid interactive pdb2gmx prompts.
    """
    out = []
    serial = 1
    with src.open() as f:
        for line in f:
            if line.startswith(("ATOM", "HETATM")):
                elem = line[76:78].strip() if len(line) >= 78 else ""
                name = line[12:16].strip()
                resn = line[17:20].strip()
                if elem == "H" or (not elem and name[:1] == "H"):
                    continue
                if resn == "NME" and name == "C":
                    name = "CH3"
                    name_field = name if len(name) == 4 else f" {name:<3s}"
                    line = line[:12] + name_field + line[16:]
                if resn == "HIS":
                    line = line[:17] + "HIE" + line[20:]
                # HETATM -> ATOM, renumber
                x = line[30:]
                name_field = line[12:16]
                resn_f = line[17:20]
                chain = line[21]
                resi = line[22:26]
                rest = line[26:]
                out.append(f"ATOM  {serial:5d} {name_field} {resn_f} {chain}{resi}{rest}")
                if not out[-1].endswith("\n"):
                    out[-1] += "\n"
                serial += 1
            elif line.startswith("TER"):
                out.append("TER\n")
            elif line.startswith("END"):
                out.append("END\n")
            elif line.startswith("TITLE"):
                out.append(line)
    if not out or not out[-1].startswith("END"):
        out.append("END\n")
    dst.write_text("".join(out))


def main() -> None:
    ala2_dir = SYS / "alanine_dipeptide" / "structures"
    ala4_dir = SYS / "alanine_tetrapeptide" / "structures"
    cln_dir = SYS / "chignolin_cln025" / "structures"
    adk_dir = SYS / "adk" / "structures"

    # --- Alanine dipeptide basins (vacuum-like canonical values) ---
    basins = {
        "c7eq": (-80.0, 70.0),
        "c7ax": (70.0, -70.0),
        "c5": (-150.0, 150.0),
        "alphaR": (-70.0, -30.0),
    }
    for name, (phi, psi) in basins.items():
        raw = ala2_dir / f"ala2_{name}_raw.pdb"
        mini = ala2_dir / f"ala2_{name}_minH.pdb"
        out = ala2_dir / f"ala2_{name}.pdb"
        write_pdb(raw, build_capped_peptide([phi], [psi], n_ala=1), f"ACE-ALA-NME {name} phi={phi} psi={psi}")
        target = [
            (((0, "C"), (1, "N"), (1, "CA"), (1, "C")), phi),   # phi
            (((1, "N"), (1, "CA"), (1, "C"), (2, "N")), psi),   # psi
        ]
        minimize_capped_pdb(raw, mini, target)
        heavy_only(mini, out)
        print(f"wrote {out}")

    # --- Alanine tetrapeptide ACE-(ALA)3-NME ---
    for name, phi, psi in (("extended", -135.0, 135.0), ("helix", -60.0, -45.0)):
        raw = ala4_dir / f"ala4_{name}_raw.pdb"
        mini = ala4_dir / f"ala4_{name}_minH.pdb"
        out = ala4_dir / f"ala4_{name}.pdb"
        write_pdb(raw, build_capped_peptide([phi] * 3, [psi] * 3, n_ala=3), f"ACE-(ALA)3-NME {name}")
        targets = []
        for i in range(3):
            # residues: 0 ACE, 1..3 ALA, 4 NME
            targets.append((((i, "C") if i == 0 else (i, "C"), (i + 1, "N"), (i + 1, "CA"), (i + 1, "C")), phi))
            nxt = "N"  # next residue N
            targets.append((((i + 1, "N"), (i + 1, "CA"), (i + 1, "C"), (i + 2, "N")), psi))
        minimize_capped_pdb(raw, mini, targets)
        heavy_only(mini, out)
        print(f"wrote {out}")

    # --- Chignolin CLN025 ---
    extract_chain(cln_dir / "5AWL_raw.pdb", cln_dir / "5AWL_chainA.pdb", "A", model=None)
    pdbfixer_clean(cln_dir / "5AWL_chainA.pdb", cln_dir / "cln025_native_H.pdb")
    heavy_only(cln_dir / "cln025_native_H.pdb", cln_dir / "cln025_native.pdb")
    print("wrote", cln_dir / "cln025_native.pdb")

    extract_chain(cln_dir / "2RVD_raw.pdb", cln_dir / "2RVD_model1_chainA.pdb", "A", model=1)
    pdbfixer_clean(cln_dir / "2RVD_model1_chainA.pdb", cln_dir / "cln025_nmr_H.pdb")
    heavy_only(cln_dir / "cln025_nmr_H.pdb", cln_dir / "cln025_nmr.pdb")
    print("wrote", cln_dir / "cln025_nmr.pdb")

    unfolded_raw = cln_dir / "cln025_unfolded_bb.pdb"
    write_pdb(
        unfolded_raw,
        build_uncapped_backbone("YYDPETGTWY", phi=-120.0, psi=140.0),
        "CLN025 extended unfolded backbone",
    )
    pdbfixer_clean(unfolded_raw, cln_dir / "cln025_unfolded_H.pdb")
    heavy_only(cln_dir / "cln025_unfolded_H.pdb", cln_dir / "cln025_unfolded.pdb")
    print("wrote", cln_dir / "cln025_unfolded.pdb")

    # --- AdK (optional large system): open 4AKE, closed 1AKE, chain A ---
    extract_chain(adk_dir / "4AKE_raw.pdb", adk_dir / "4AKE_chainA.pdb", "A", model=None)
    pdbfixer_clean(adk_dir / "4AKE_chainA.pdb", adk_dir / "adk_open_H.pdb")
    heavy_only(adk_dir / "adk_open_H.pdb", adk_dir / "adk_open.pdb")
    print("wrote", adk_dir / "adk_open.pdb")

    extract_chain(adk_dir / "1AKE_raw.pdb", adk_dir / "1AKE_chainA.pdb", "A", model=None)
    pdbfixer_clean(adk_dir / "1AKE_chainA.pdb", adk_dir / "adk_closed_H.pdb")
    heavy_only(adk_dir / "adk_closed_H.pdb", adk_dir / "adk_closed.pdb")
    print("wrote", adk_dir / "adk_closed.pdb")

    print("done")


if __name__ == "__main__":
    main()
