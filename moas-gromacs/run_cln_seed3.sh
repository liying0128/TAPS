#!/usr/bin/env bash
# CLN025 extra seed=3 for methods that still only have seeds 0/1/2.
# LAST / Random / MOAS-static already have discover_s3_* / moas_s3_*.
# Official n=3 remains seeds 0,1,2; seed=3 is the matching extra replicate.
set -u
MOAS="$(cd "$(dirname "$0")" && pwd)"
TAPS="$(cd "$MOAS/../taps-gromacs" && pwd)"
LOG="$MOAS/logs/cln_seed3.log"
mkdir -p "$MOAS/logs"
unset CUDA_VISIBLE_DEVICES
unset OMP_NUM_THREADS
unset GOMP_CPU_AFFINITY
export PYTHONUNBUFFERED=1
export GMX_MAXBACKUP=-1
exec > >(tee -a "$LOG") 2>&1
echo "============================================================"
echo "[$(date '+%F %T')] CLN seed=3 start  pid=$$  GPU=$(nvidia-smi -L 2>/dev/null | head -1)"
echo "============================================================"

run() {
  echo
  echo "===== $* ====="
  echo "[$(date '+%F %T')] START"
  if "$@"; then
    echo "[$(date '+%F %T')] DONE"
    return 0
  fi
  echo "[$(date '+%F %T')] FAILED"
  return 1
}

cd "$TAPS"

# Four-method set: LC is the one still missing seed=3
run python3 stage13_cln025_discover.py --gpu --nt 16 --seed 3 \
  --methods density --tag-prefix discover_s3 \
  --init-ns 10 --budget-ns 82 --n-seeds 6 --short-ps 1000 --max-rounds 12

# CLN-only methods: bring TAPS / dynamic / Pareto to the same extra seed
run python3 stage13_cln025_discover.py --gpu --nt 16 --seed 3 \
  --methods taps --tag-prefix discover_s3 \
  --init-ns 10 --budget-ns 82 --n-seeds 6 --short-ps 1000 --max-rounds 12

run python3 stage13_cln025_discover.py --gpu --nt 16 --seed 3 \
  --methods dynamic --tag-prefix moas_s3 \
  --init-ns 10 --budget-ns 82 --n-seeds 6 --short-ps 1000 --max-rounds 12

run python3 stage13_cln025_discover.py --gpu --nt 16 --seed 3 \
  --methods pareto --tag-prefix moas_s3 \
  --init-ns 10 --budget-ns 82 --n-seeds 6 --short-ps 1000 --max-rounds 12

cd "$MOAS"
run python3 experiments/commit_all_cln.py

echo "============================================================"
echo "[$(date '+%F %T')] CLN seed=3 exit"
echo "============================================================"
