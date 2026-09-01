#!/usr/bin/env bash
# Move leftover fill work onto the RTX 4090.
# stage13 resumes finished rounds from history.json and restarts incomplete shorts.
set -u
MOAS="$(cd "$(dirname "$0")" && pwd)"
TAPS="$(cd "$MOAS/../taps-gromacs" && pwd)"
LOG="$MOAS/logs/gpu_remaining.log"
mkdir -p "$MOAS/logs"
unset CUDA_VISIBLE_DEVICES
unset OMP_NUM_THREADS
unset GOMP_CPU_AFFINITY
export PYTHONUNBUFFERED=1
export GMX_MAXBACKUP=-1
exec > >(tee -a "$LOG") 2>&1
echo "============================================================"
echo "[$(date '+%F %T')] GPU remaining start  pid=$$"
echo "============================================================"
cd "$TAPS"
run() {
  echo; echo "===== $* ====="; echo "[$(date '+%F %T')] START"
  if "$@"; then echo "[$(date '+%F %T')] DONE"; return 0; fi
  echo "[$(date '+%F %T')] FAILED"; return 1
}

# 1) last 6 ns of MOAS-dynamic seed=2 (GPU abort at round 12)
run python3 stage13_cln025_discover.py --gpu --nt 16 --seed 2 \
  --methods dynamic --tag-prefix moas_s2 \
  --init-ns 10 --budget-ns 82 --n-seeds 6 --short-ps 1000 --max-rounds 12

# 2) Random seed=3 (was on CPU; history through round 4, round 5 seed_00 incomplete)
run python3 stage13_cln025_discover.py --gpu --nt 16 --seed 3 \
  --methods random --tag-prefix moas_s3 \
  --init-ns 10 --budget-ns 82 --n-seeds 6 --short-ps 1000 --max-rounds 12

# 3) MOAS-static seed=3 (not started)
run python3 stage13_cln025_discover.py --gpu --nt 16 --seed 3 \
  --methods moas --tag-prefix moas_s3 \
  --init-ns 10 --budget-ns 82 --n-seeds 6 --short-ps 1000 --max-rounds 12

echo "[$(date '+%F %T')] GPU remaining exit"
