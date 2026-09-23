#!/usr/bin/env bash
# 55: remaining MBP ablation n=1 (novbnd, novtgt, bndtgt). Write to system disk (/).
# Do not use /home/ly/data (full). Resume-safe via history.json.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MBP="$ROOT/moas-mbp"
if [[ -f /usr/local/gromacs/bin/GMXRC ]]; then
  set +u
  # shellcheck disable=SC1091
  source /usr/local/gromacs/bin/GMXRC
  set -u
fi
export PATH="/usr/local/gromacs/bin:${PATH}"
export GMX="${GMX:-/usr/local/gromacs/bin/gmx}"
unset CUDA_VISIBLE_DEVICES OMP_NUM_THREADS GOMP_CPU_AFFINITY
export PYTHONUNBUFFERED=1
export GMX_MAXBACKUP=-1
NT="${NT:-16}"
LOG="$ROOT/moas-knn/logs/ablation_55.log"
mkdir -p "$ROOT/moas-knn/logs"
exec > >(tee -a "$LOG") 2>&1

METHODS=(novbnd novtgt bndtgt)

drop_scratch() {
  local root="$1"
  if [[ -d "$root" && ! -L "$root" ]]; then
    echo "[$(date '+%F %T')] drop scratch $root"
    find "$root" -type d -name 'seed_*_scratch' -prune -print0 | xargs -0 -r rm -rf
  fi
}

echo "============================================================"
echo "[$(date '+%F %T')] ablation 55 queue  MBP n=1  methods=${METHODS[*]}  nt=$NT"
echo "============================================================"
df -h / /home/ly/data | tail -n +1
avail=$(df -B1 --output=avail / | tail -1 | tr -d ' ')
need=$((280 * 1024 * 1024 * 1024))
if (( avail < need )); then
  echo "[$(date '+%F %T')] ABORT: / has $avail bytes free, need >= $need"
  exit 1
fi

cd "$MBP"
python3 stage_mbp_discover.py --check --methods "${METHODS[@]}"
for m in "${METHODS[@]}"; do
  echo "[$(date '+%F %T')] ---- MBP ablation $m ----"
  python3 stage_mbp_discover.py --gpu --nt "$NT" --seed 0 --tag-prefix mbp \
    --methods "$m" --init-ns 20 --budget-ns 1000 --n-seeds 6 --short-ps 2000 --max-rounds 82
  drop_scratch "$MBP/analysis/mbp_open/campaigns/mbp_${m}"
  df -h / | tail -n 1
done

echo "[$(date '+%F %T')] ablation 55 queue exit"
df -h / /home/ly/data | tail -n +1
