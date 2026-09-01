#!/usr/bin/env bash
# Prepare GROMACS topologies, boxes, and (where needed) solvated/ionized systems.
# Usage:
#   bash scripts/prepare_gromacs.sh            # ala2 + tetrapeptide + chignolin
#   INCLUDE_ADK=1 bash scripts/prepare_gromacs.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MDP="$ROOT/shared/mdp"
GMX="${GMX:-gmx}"
FF="amber99sb-ildn"
WATER="tip3p"
INCLUDE_ADK="${INCLUDE_ADK:-0}"

export GMX_MAXBACKUP=-1
export GMX_SUPPRESS_DUMP=1

log() { printf "\n==== %s ====\n" "$*"; }

relativize_posre() {
  # pdb2gmx writes an absolute #include for posre.itp; that breaks after copying the folder.
  python3 - "$1" <<'PY'
import re, sys
from pathlib import Path
p = Path(sys.argv[1])
text = p.read_text()
fixed = re.sub(r'#include\s+"[^"]*posre\.itp"', '#include "posre.itp"', text)
if fixed != text:
    p.write_text(fixed)
PY
}

pdb2gmx_capped() {
  local pdb="$1" outdir="$2"
  mkdir -p "$outdir"
  "$GMX" pdb2gmx \
    -f "$pdb" \
    -o "$outdir/protein.gro" \
    -p "$outdir/topol.top" \
    -i "$outdir/posre.itp" \
    -ignh \
    -missing \
    -ff "$FF" \
    -water "$WATER"
  relativize_posre "$outdir/topol.top"
}

pdb2gmx_protein() {
  # Default amber termini: 0 = NH3+, 0 = COO-
  local pdb="$1" outdir="$2"
  mkdir -p "$outdir"
  printf "0\n0\n" | "$GMX" pdb2gmx \
    -f "$pdb" \
    -o "$outdir/protein.gro" \
    -p "$outdir/topol.top" \
    -i "$outdir/posre.itp" \
    -ignh \
    -missing \
    -ter \
    -ff "$FF" \
    -water "$WATER"
  relativize_posre "$outdir/topol.top"
}

make_vacuum_box() {
  local src="$1" outdir="$2" box="${3:-4.0}"
  mkdir -p "$outdir"
  cp "$src/topol.top" "$outdir/topol.top"
  cp "$src/posre.itp" "$outdir/posre.itp" 2>/dev/null || true
  "$GMX" editconf -f "$src/protein.gro" -o "$outdir/box.gro" -box "$box" "$box" "$box" -c -bt cubic
  relativize_posre "$outdir/topol.top"
}

make_water_box() {
  local src="$1" outdir="$2" dist="${3:-1.0}" conc="${4:-0.0}"
  mkdir -p "$outdir"
  cp "$src/topol.top" "$outdir/topol.top"
  cp "$src/posre.itp" "$outdir/posre.itp" 2>/dev/null || true
  "$GMX" editconf -f "$src/protein.gro" -o "$outdir/box.gro" -d "$dist" -c -bt cubic
  "$GMX" solvate -cp "$outdir/box.gro" -cs spc216.gro -o "$outdir/solv.gro" -p "$outdir/topol.top"
  "$GMX" grompp -f "$MDP/ions.mdp" -c "$outdir/solv.gro" -p "$outdir/topol.top" -o "$outdir/ions.tpr" -maxwarn 1
  if awk -v c="$conc" 'BEGIN{exit !(c>0)}'; then
    echo SOL | "$GMX" genion -s "$outdir/ions.tpr" -o "$outdir/ions.gro" -p "$outdir/topol.top" \
      -pname NA -nname CL -neutral -conc "$conc"
  else
    echo SOL | "$GMX" genion -s "$outdir/ions.tpr" -o "$outdir/ions.gro" -p "$outdir/topol.top" \
      -pname NA -nname CL -neutral
  fi
  relativize_posre "$outdir/topol.top"
}

copy_mdp() {
  local outdir="$1"
  shift
  mkdir -p "$outdir/mdp"
  for f in "$@"; do
    cp "$MDP/$f" "$outdir/mdp/"
  done
}

# ---------------------------------------------------------------------------
log "Alanine dipeptide (capped ACE-ALA-NME)"
ALA2="$ROOT/systems/alanine_dipeptide"
pdb2gmx_capped "$ALA2/structures/ala2_c7eq.pdb" "$ALA2/gmx_common"
# Convert other basins with the same topology (atom order must match)
for basin in c7eq c7ax c5 alphaR; do
  "$GMX" pdb2gmx \
    -f "$ALA2/structures/ala2_${basin}.pdb" \
    -o "$ALA2/structures/ala2_${basin}.gro" \
    -p "$ALA2/_tmp_${basin}.top" \
    -i "$ALA2/_tmp_${basin}_posre.itp" \
    -ignh -missing -ff "$FF" -water "$WATER" >/dev/null
  rm -f "$ALA2/_tmp_${basin}.top" "$ALA2/_tmp_${basin}_posre.itp"
done

make_vacuum_box "$ALA2/gmx_common" "$ALA2/vacuum" 4.0
# Place each basin into the vacuum box
mkdir -p "$ALA2/vacuum/seeds"
for basin in c7eq c7ax c5 alphaR; do
  "$GMX" editconf -f "$ALA2/structures/ala2_${basin}.gro" -o "$ALA2/vacuum/seeds/${basin}.gro" -box 4.0 4.0 4.0 -c -bt cubic
done
cp "$ALA2/vacuum/seeds/c7eq.gro" "$ALA2/vacuum/box.gro"
copy_mdp "$ALA2/vacuum" em_vacuum.mdp nvt_vacuum.mdp md_short_vacuum.mdp md_short_500ps_vacuum.mdp md_ref_vacuum.mdp md_prod_vacuum.mdp

make_water_box "$ALA2/gmx_common" "$ALA2/water" 1.0 0.0
mkdir -p "$ALA2/water/seeds"
# Water seeds: keep the solvated box from c7eq as the main start;
# additional peptide-only gro files are stored for adaptive restarts after first solvation.
for basin in c7eq c7ax c5 alphaR; do
  "$GMX" editconf -f "$ALA2/structures/ala2_${basin}.gro" -o "$ALA2/water/seeds/${basin}_peptide.gro" -c
done
copy_mdp "$ALA2/water" em.mdp ions.mdp nvt.mdp npt.mdp md_short.mdp md_short_500ps.mdp md_ref.mdp md_prod.mdp

# ---------------------------------------------------------------------------
log "Alanine tetrapeptide ACE-(ALA)3-NME"
ALA4="$ROOT/systems/alanine_tetrapeptide"
pdb2gmx_capped "$ALA4/structures/ala4_extended.pdb" "$ALA4/gmx_common"
"$GMX" pdb2gmx -f "$ALA4/structures/ala4_helix.pdb" -o "$ALA4/structures/ala4_helix.gro" \
  -p "$ALA4/_tmp.top" -i "$ALA4/_tmp_posre.itp" -ignh -missing -ff "$FF" -water "$WATER" >/dev/null
rm -f "$ALA4/_tmp.top" "$ALA4/_tmp_posre.itp"
make_vacuum_box "$ALA4/gmx_common" "$ALA4/vacuum" 5.0
copy_mdp "$ALA4/vacuum" em_vacuum.mdp nvt_vacuum.mdp md_short_vacuum.mdp md_short_500ps_vacuum.mdp md_ref_vacuum.mdp md_prod_vacuum.mdp
make_water_box "$ALA4/gmx_common" "$ALA4/water" 1.0 0.0
copy_mdp "$ALA4/water" em.mdp ions.mdp nvt.mdp npt.mdp md_short.mdp md_short_500ps.mdp md_ref.mdp md_prod.mdp

# ---------------------------------------------------------------------------
log "Chignolin CLN025 (native folded start; unfolded PDB kept for adaptive seeds)"
CLN="$ROOT/systems/chignolin_cln025"
pdb2gmx_protein "$CLN/structures/cln025_native.pdb" "$CLN/gmx_common"
printf "0\n0\n" | "$GMX" pdb2gmx \
  -f "$CLN/structures/cln025_unfolded.pdb" \
  -o "$CLN/structures/cln025_unfolded.gro" \
  -p "$CLN/_tmp.top" \
  -i "$CLN/_tmp_posre.itp" \
  -ignh -missing -ter -ff "$FF" -water "$WATER"
rm -f "$CLN/_tmp.top" "$CLN/_tmp_posre.itp"
printf "0\n0\n" | "$GMX" pdb2gmx \
  -f "$CLN/structures/cln025_nmr.pdb" \
  -o "$CLN/structures/cln025_nmr.gro" \
  -p "$CLN/_tmp.top" \
  -i "$CLN/_tmp_posre.itp" \
  -ignh -missing -ter -ff "$FF" -water "$WATER"
rm -f "$CLN/_tmp.top" "$CLN/_tmp_posre.itp"

make_water_box "$CLN/gmx_common" "$CLN/water" 1.0 0.15
copy_mdp "$CLN/water" em.mdp ions.mdp nvt.mdp npt.mdp md_short.mdp md_short_500ps.mdp md_ref.mdp md_prod.mdp

log "Chignolin CLN025 unfolded start (separate water box; do not overwrite native 100 ns)"
pdb2gmx_protein "$CLN/structures/cln025_unfolded.pdb" "$CLN/gmx_common_unfolded"
make_water_box "$CLN/gmx_common_unfolded" "$CLN/water_unfolded" 1.0 0.15
copy_mdp "$CLN/water_unfolded" em.mdp ions.mdp nvt.mdp npt.mdp md_short.mdp md_short_500ps.mdp md_ref.mdp md_prod.mdp

# ---------------------------------------------------------------------------
if [[ "$INCLUDE_ADK" == "1" ]]; then
  log "AdK open (4AKE chain A) — optional large system"
  ADK="$ROOT/systems/adk"
  pdb2gmx_protein "$ADK/structures/adk_open.pdb" "$ADK/gmx_common_open"
  make_water_box "$ADK/gmx_common_open" "$ADK/water_open" 1.2 0.15
  copy_mdp "$ADK/water_open" em.mdp ions.mdp nvt.mdp npt.mdp md_short.mdp md_ref.mdp md_prod.mdp

  log "AdK closed (1AKE chain A)"
  pdb2gmx_protein "$ADK/structures/adk_closed.pdb" "$ADK/gmx_common_closed"
  make_water_box "$ADK/gmx_common_closed" "$ADK/water_closed" 1.2 0.15
  copy_mdp "$ADK/water_closed" em.mdp ions.mdp nvt.mdp npt.mdp md_short.mdp md_ref.mdp md_prod.mdp
else
  log "Skip AdK solvation (set INCLUDE_ADK=1 to enable). Cleaned PDBs are already in systems/adk/structures."
fi

log "Done. Next: bash scripts/run_em_eq.sh"
