#!/usr/bin/env bash
# Remaining AdK n=3 replicates: seed=1 then seed=2.
# Shares the same 20 ns open init as seed=0. Four methods only.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ -f /usr/local/gromacs/bin/GMXRC ]]; then
  set +u
  # shellcheck disable=SC1091
  source /usr/local/gromacs/bin/GMXRC
  set -u
fi
export PATH="/usr/local/gromacs/bin:${PATH}"
if [[ -f /home/ly/miniconda3/etc/profile.d/conda.sh ]]; then
  set +u
  # shellcheck disable=SC1091
  source /home/ly/miniconda3/etc/profile.d/conda.sh
  conda activate base 2>/dev/null || true
  set -u
fi
unset CUDA_VISIBLE_DEVICES OMP_NUM_THREADS GOMP_CPU_AFFINITY
export PYTHONUNBUFFERED=1
export GMX_MAXBACKUP=-1
NT="${NT:-16}"
export NT
LOG="$ROOT/logs/gpu_replicates.log"
mkdir -p "$ROOT/logs" systems/adk/water_open/runs
exec > >(tee -a "$LOG") 2>&1
echo "============================================================"
echo "[$(date '+%F %T')] AdK GPU replicates start  pid=$$  nt=$NT"
echo "  seed=1 then seed=2   methods=random,last,density,moas   budget=200 ns"
echo "  gmx=$(command -v gmx)  python=$(command -v python3)"
gmx --version 2>/dev/null | head -n 3 || true
echo "============================================================"

TPR="$ROOT/systems/adk/water_open/runs/md_20ns.tpr"
GRO="$ROOT/systems/adk/water_open/runs/md_20ns.gro"
MDP="$ROOT/systems/adk/water_open/mdp/md_prod_20ns.mdp"
TOP="$ROOT/systems/adk/water_open/topol.top"
if [[ ! -f "$GRO" ]]; then
  echo "missing $GRO" >&2
  exit 1
fi
need_grompp=1
if [[ -f "$TPR" ]] && gmx dump -s "$TPR" >/dev/null 2>&1; then
  need_grompp=0
fi
if [[ "$need_grompp" -eq 1 ]]; then
  echo "[$(date '+%F %T')] grompp md_20ns.tpr with this GROMACS"
  gmx grompp -f "$MDP" -c "$GRO" -p "$TOP" -o "$TPR" -maxwarn 1
fi

python3 stage_adk_discover.py --check

SEED=1 bash "$ROOT/scripts/run_discover.sh"
SEED=2 bash "$ROOT/scripts/run_discover.sh"
echo "[$(date '+%F %T')] AdK GPU replicates exit"
