#!/usr/bin/env bash
# pdb2gmx + 1.2 nm dodecahedron + TIP3P + 0.15 M NaCl for apo MBP.
# Open (1OMP) is the production start. Closed (1ANF, maltose removed) is the
# domain-distance / hinge-angle reference.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MDP="$ROOT/shared/mdp"
GMX="${GMX:-gmx}"
FF="amber99sb-ildn"
WATER="tip3p"
export GMX_MAXBACKUP=-1
export GMX_SUPPRESS_DUMP=1

log() { printf "\n==== %s ====\n" "$*"; }

relativize_posre() {
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

pdb2gmx_protein() {
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

make_water_box() {
  local src="$1" outdir="$2" dist="${3:-1.2}" conc="${4:-0.15}"
  mkdir -p "$outdir"
  cp "$src/topol.top" "$outdir/topol.top"
  cp "$src/posre.itp" "$outdir/posre.itp"
  # Dodecahedron: MBP is larger than AdK; cubic 1.2 nm would waste water.
  "$GMX" editconf -f "$src/protein.gro" -o "$outdir/box.gro" -d "$dist" -c -bt dodecahedron
  "$GMX" solvate -cp "$outdir/box.gro" -cs spc216.gro -o "$outdir/solv.gro" -p "$outdir/topol.top"
  "$GMX" grompp -f "$MDP/ions.mdp" -c "$outdir/solv.gro" -p "$outdir/topol.top" -o "$outdir/ions.tpr" -maxwarn 2
  echo SOL | "$GMX" genion -s "$outdir/ions.tpr" -o "$outdir/ions.gro" -p "$outdir/topol.top" \
    -pname NA -nname CL -neutral -conc "$conc"
  relativize_posre "$outdir/topol.top"
}

copy_mdp() {
  local outdir="$1"
  mkdir -p "$outdir/mdp"
  for f in em.mdp ions.mdp nvt.mdp npt.mdp md_short.mdp md_short_500ps.mdp md_short_1ns.mdp md_short_2ns.mdp md_ref.mdp md_prod.mdp; do
    cp "$MDP/$f" "$outdir/mdp/"
  done
}

MBP="$ROOT/systems/mbp"

log "Download and clean 1OMP / 1ANF"
python3 "$ROOT/scripts/clean_mbp_pdb.py"

log "MBP open apo (1OMP chain A)"
pdb2gmx_protein "$MBP/structures/mbp_open.pdb" "$MBP/gmx_common_open"
make_water_box "$MBP/gmx_common_open" "$MBP/water_open" 1.2 0.15
copy_mdp "$MBP/water_open"

log "MBP closed apo (1ANF chain A, maltose removed)"
pdb2gmx_protein "$MBP/structures/mbp_closed.pdb" "$MBP/gmx_common_closed"
make_water_box "$MBP/gmx_common_closed" "$MBP/water_closed" 1.2 0.15
copy_mdp "$MBP/water_closed"

log "Reference domain distance / hinge angle from protein.gro"
python3 "$ROOT/mbp_cvs.py" --refs

echo
echo "Done. Next (GPU, after CLN seed=3 finishes):"
echo "  python3 run_md.py --system mbp_open --length 0 --gpu --nt 16"
echo "  python3 run_md.py --system mbp_closed --length 0 --gpu --nt 16"
