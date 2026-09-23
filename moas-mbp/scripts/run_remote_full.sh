#!/usr/bin/env bash
# On a remote box: GROMACS + conda, remake init .tpr if this gmx cannot dump it,
# then 4-method MBP 1 us using all CPU threads and the GPU.
# Usage: SEED=2 bash scripts/run_remote_full.sh
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
  conda activate base
  set -u
fi
# conda may ship its own gmx; keep the CUDA 2024.3 build first.
export PATH="/usr/local/gromacs/bin:${PATH}"
export GMX="/usr/local/gromacs/bin/gmx"
unset CUDA_VISIBLE_DEVICES OMP_NUM_THREADS GOMP_CPU_AFFINITY
export PYTHONUNBUFFERED=1
export GMX_MAXBACKUP=-1
SEED="${SEED:-2}"
NT="${NT:-$(nproc)}"
export NT
LOG="$ROOT/logs/discover_seed${SEED}.log"
mkdir -p "$ROOT/logs"

TPR="$ROOT/systems/mbp/water_open/runs/md_20ns.tpr"
GRO="$ROOT/systems/mbp/water_open/runs/md_20ns.gro"
MDP="$ROOT/systems/mbp/water_open/mdp/md_prod_20ns.mdp"
TOP="$ROOT/systems/mbp/water_open/topol.top"
if [[ ! -f "$GRO" ]]; then
  echo "missing $GRO" >&2
  exit 1
fi
need_grompp=1
if [[ -f "$TPR" ]] && gmx dump -s "$TPR" >/dev/null 2>&1; then
  need_grompp=0
fi
if [[ "$need_grompp" -eq 1 ]]; then
  echo "[$(date '+%F %T')] grompp md_20ns.tpr with $(gmx --version 2>&1 | head -n 1)"
  gmx grompp -f "$MDP" -c "$GRO" -p "$TOP" -o "$TPR" -maxwarn 1
fi

python3 stage_mbp_discover.py --check
echo "[$(date '+%F %T')] MBP remote discover  seed=$SEED  nt=$NT  gpu=$(hostname)"
df -h / | tail -n 1
exec bash "$ROOT/scripts/run_discover.sh"
