#!/usr/bin/env bash
# On the 31.55 4090: wait until AdK seed=1/2 GPU replicates finish, then
# MBP seed=1 1 us (Random / LAST / LC / MOAS-static). Do not interrupt AdK.
set -euo pipefail
MBP="$(cd "$(dirname "$0")/.." && pwd)"
ADK="$(cd "$MBP/../moas-adk" && pwd)"
LOG="$MBP/logs/gpu_after_adk.log"
mkdir -p "$MBP/logs"
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
exec > >(tee -a "$LOG") 2>&1
echo "============================================================"
echo "[$(date '+%F %T')] MBP-after-AdK waiter start  pid=$$  nt=$NT"
echo "  wait: AdK run_gpu_replicates.sh / stage_adk_discover.py"
echo "  then: SEED=1  budget=1000 ns  methods=random,last,density,moas"
df -h / | tail -n 1
echo "============================================================"

adk_busy() {
  pgrep -f '[b]ash .*/run_gpu_replicates.sh' >/dev/null 2>&1 \
    || pgrep -f '[p]ython3 stage_adk_discover.py' >/dev/null 2>&1
}

echo "[$(date '+%F %T')] waiting for AdK GPU replicates to finish"
while adk_busy; do
  sleep 30
done
echo "[$(date '+%F %T')] AdK GPU replicates idle; starting MBP seed=1"
sleep 5

TPR="$MBP/systems/mbp/water_open/runs/md_20ns.tpr"
GRO="$MBP/systems/mbp/water_open/runs/md_20ns.gro"
MDP="$MBP/systems/mbp/water_open/mdp/md_prod_20ns.mdp"
TOP="$MBP/systems/mbp/water_open/topol.top"
if [[ ! -f "$GRO" ]]; then
  echo "missing $GRO" >&2
  exit 1
fi
need_grompp=1
if [[ -f "$TPR" ]] && gmx dump -s "$TPR" >/dev/null 2>&1; then
  need_grompp=0
fi
if [[ "$need_grompp" -eq 1 ]]; then
  echo "[$(date '+%F %T')] grompp MBP md_20ns.tpr with this GROMACS"
  gmx grompp -f "$MDP" -c "$GRO" -p "$TOP" -o "$TPR" -maxwarn 1
fi

cd "$MBP"
python3 stage_mbp_discover.py --check
SEED=1 bash "$MBP/scripts/run_discover.sh"
echo "[$(date '+%F %T')] MBP-after-AdK exit"
