#!/usr/bin/env bash
# Launch one unbiased short MD trajectory (one adaptive-sampling round).
# Usage:
#   bash scripts/run_short_md.sh systems/alanine_dipeptide/vacuum em.gro md_short_vacuum.mdp run01
#   bash scripts/run_short_md.sh systems/alanine_dipeptide/water npt.gro md_short.mdp run01
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GMX="${GMX:-gmx}"
NT="${NT:-4}"
export GMX_MAXBACKUP=-1

if [[ $# -lt 3 ]]; then
  echo "usage: $0 <system_dir> <input.gro> <mdp_name> [run_id]"
  exit 1
fi

SYS="$(cd "$1" && pwd)"
GRO="$2"
MDP="$3"
RUN="${4:-short}"

cd "$SYS"
mkdir -p runs
"$GMX" grompp -f "mdp/$MDP" -c "$GRO" -p topol.top -o "runs/${RUN}.tpr"
"$GMX" mdrun -deffnm "runs/${RUN}" -nt "$NT"
echo "wrote $SYS/runs/${RUN}.xtc"
