#!/usr/bin/env bash
# Local queue: AdK (done) then MBP nov/bnd/tgt. novbnd/novtgt/bndtgt run on 55
# (see ablation_skip_local.txt). Resume-safe via history.json.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
TAPS="$(cd "$HERE/.." && pwd)"
if [[ -f /usr/local/gromacs/bin/GMXRC ]]; then
  set +u
  # shellcheck disable=SC1091
  source /usr/local/gromacs/bin/GMXRC
  set -u
fi
export PATH="/usr/local/gromacs/bin:${PATH}"
export GMX="/usr/local/gromacs/bin/gmx"
unset CUDA_VISIBLE_DEVICES OMP_NUM_THREADS GOMP_CPU_AFFINITY
export PYTHONUNBUFFERED=1
export GMX_MAXBACKUP=-1
NT="${NT:-16}"
LOG="$HERE/logs/ablation_local.log"
mkdir -p "$HERE/logs"
exec > >(tee -a "$LOG") 2>&1

# Novelty / Boundary / Target on-off. Do not re-run full MOAS (method=moas).
METHODS=(nov bnd tgt novbnd novtgt bndtgt)

drop_scratch() {
  local root="$1"
  if [[ -d "$root" && ! -L "$root" ]]; then
    echo "[$(date '+%F %T')] drop scratch $root"
    find "$root" -type d -name 'seed_*_scratch' -prune -print0 | xargs -0 -r rm -rf
  fi
}

echo "============================================================"
echo "[$(date '+%F %T')] ablation local queue  AdK then MBP  n=1  nt=$NT"
echo "============================================================"
df -h / /home/ly/data | tail -n +1

cd "$TAPS/moas-adk"
python3 stage_adk_discover.py --check --methods "${METHODS[@]}"
for m in "${METHODS[@]}"; do
  echo "[$(date '+%F %T')] ---- AdK ablation $m ----"
  python3 stage_adk_discover.py --gpu --nt "$NT" --seed 0 --tag-prefix adk \
    --methods "$m" --init-ns 20 --budget-ns 200 --n-seeds 6 --short-ps 2000 --max-rounds 15
  drop_scratch "$TAPS/moas-adk/analysis/adk_open/campaigns/adk_${m}"
  df -h / | tail -n 1
done

cd "$TAPS/moas-mbp"
python3 stage_mbp_discover.py --check --methods "${METHODS[@]}"
for m in "${METHODS[@]}"; do
  echo "[$(date '+%F %T')] ---- MBP ablation $m ----"
  python3 stage_mbp_discover.py --gpu --nt "$NT" --seed 0 --tag-prefix mbp \
    --methods "$m" --init-ns 20 --budget-ns 1000 --n-seeds 6 --short-ps 2000 --max-rounds 82
  drop_scratch "$TAPS/moas-mbp/analysis/mbp_open/campaigns/mbp_${m}"
  df -h / | tail -n 1
done

echo "[$(date '+%F %T')] ablation local queue exit"
df -h / /home/ly/data | tail -n +1
