#!/usr/bin/env bash
# GPU: Word-doc methods still missing as online campaigns — MOAS-dynamic then MOAS-Pareto, 3 seeds each.
set -u
MOAS="$(cd "$(dirname "$0")" && pwd)"
TAPS="$(cd "$MOAS/../taps-gromacs" && pwd)"
LOG="$MOAS/logs/gpu_fill.log"
mkdir -p "$MOAS/logs"
unset CUDA_VISIBLE_DEVICES
unset OMP_NUM_THREADS
unset GOMP_CPU_AFFINITY
export PYTHONUNBUFFERED=1
export GMX_MAXBACKUP=-1
exec > >(tee -a "$LOG") 2>&1
echo "============================================================"
echo "[$(date '+%F %T')] GPU fill start  pid=$$"
echo "============================================================"
cd "$TAPS"
run() {
  echo; echo "===== $* ====="; echo "[$(date '+%F %T')] START"
  if "$@"; then echo "[$(date '+%F %T')] DONE"; return 0; fi
  echo "[$(date '+%F %T')] FAILED"; return 1
}
for seed in 0 1 2; do
  prefix="moas"
  [[ "$seed" != 0 ]] && prefix="moas_s${seed}"
  run python3 stage13_cln025_discover.py --gpu --nt 16 --seed "$seed" \
    --methods dynamic --tag-prefix "$prefix" \
    --init-ns 10 --budget-ns 82 --n-seeds 6 --short-ps 1000 --max-rounds 12
done
for seed in 0 1 2; do
  prefix="moas"
  [[ "$seed" != 0 ]] && prefix="moas_s${seed}"
  run python3 stage13_cln025_discover.py --gpu --nt 16 --seed "$seed" \
    --methods pareto --tag-prefix "$prefix" \
    --init-ns 10 --budget-ns 82 --n-seeds 6 --short-ps 1000 --max-rounds 12
done
echo "[$(date '+%F %T')] GPU fill exit"
