#!/usr/bin/env bash
# Energy-minimize (and optionally equilibrate) prepared TAPS systems.
# Usage:
#   bash scripts/run_em_eq.sh              # EM only
#   DO_EQ=1 bash scripts/run_em_eq.sh      # EM + NVT (+ NPT if water)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GMX="${GMX:-gmx}"
DO_EQ="${DO_EQ:-0}"
NT="${NT:-4}"
export GMX_MAXBACKUP=-1

run_em() {
  local dir="$1" mdp="$2" gro="$3"
  local here; here="$(pwd)"
  cd "$dir"
  "$GMX" grompp -f "mdp/$mdp" -c "$gro" -p topol.top -o em.tpr -maxwarn 1
  "$GMX" mdrun -deffnm em -nt "$NT"
  cd "$here"
}

run_eq_vacuum() {
  local dir="$1"
  local here; here="$(pwd)"
  cd "$dir"
  "$GMX" grompp -f mdp/nvt_vacuum.mdp -c em.gro -p topol.top -o nvt.tpr
  "$GMX" mdrun -deffnm nvt -nt "$NT"
  cd "$here"
}

run_eq_water() {
  local dir="$1"
  local here; here="$(pwd)"
  cd "$dir"
  "$GMX" grompp -f mdp/nvt.mdp -c em.gro -r em.gro -p topol.top -o nvt.tpr
  "$GMX" mdrun -deffnm nvt -nt "$NT"
  "$GMX" grompp -f mdp/npt.mdp -c nvt.gro -r nvt.gro -t nvt.cpt -p topol.top -o npt.tpr
  "$GMX" mdrun -deffnm npt -nt "$NT"
  cd "$here"
}

echo "EM: alanine dipeptide vacuum"
run_em "$ROOT/systems/alanine_dipeptide/vacuum" em_vacuum.mdp box.gro
echo "EM: alanine dipeptide water"
run_em "$ROOT/systems/alanine_dipeptide/water" em.mdp ions.gro
echo "EM: alanine tetrapeptide vacuum"
run_em "$ROOT/systems/alanine_tetrapeptide/vacuum" em_vacuum.mdp box.gro
echo "EM: alanine tetrapeptide water"
run_em "$ROOT/systems/alanine_tetrapeptide/water" em.mdp ions.gro
echo "EM: chignolin water"
run_em "$ROOT/systems/chignolin_cln025/water" em.mdp ions.gro

if [[ "$DO_EQ" == "1" ]]; then
  echo "EQ: alanine dipeptide vacuum (NVT 100 ps)"
  run_eq_vacuum "$ROOT/systems/alanine_dipeptide/vacuum"
  echo "EQ: alanine dipeptide water (NVT+NPT 100 ps each)"
  run_eq_water "$ROOT/systems/alanine_dipeptide/water"
  echo "EQ: alanine tetrapeptide water"
  run_eq_water "$ROOT/systems/alanine_tetrapeptide/water"
  echo "EQ: chignolin water"
  run_eq_water "$ROOT/systems/chignolin_cln025/water"
fi

echo "Done."
