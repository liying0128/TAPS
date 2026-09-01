#!/usr/bin/env bash
# CPU: commit≥40 ps reanalysis first, then extra LAST / MOAS-static / Random replicates (seed=3)
# while GPU runs dynamic+pareto. Uses -cpu, -nt 12, pin off; does not touch CUDA.
set -u
MOAS="$(cd "$(dirname "$0")" && pwd)"
TAPS="$(cd "$MOAS/../taps-gromacs" && pwd)"
LOG="$MOAS/logs/cpu_fill.log"
mkdir -p "$MOAS/logs"
export CUDA_VISIBLE_DEVICES=""
unset OMP_NUM_THREADS
unset GOMP_CPU_AFFINITY
export PYTHONUNBUFFERED=1
export GMX_MAXBACKUP=-1
exec > >(tee -a "$LOG") 2>&1
echo "============================================================"
echo "[$(date '+%F %T')] CPU fill start  pid=$$"
echo "============================================================"
run() {
  echo; echo "===== $* ====="; echo "[$(date '+%F %T')] START"
  if "$@"; then echo "[$(date '+%F %T')] DONE"; return 0; fi
  echo "[$(date '+%F %T')] FAILED"; return 1
}

cd "$MOAS"
run python3 experiments/commit_all_cln.py

cd "$TAPS"
# LAST seed=3 finished on CPU. Random + MOAS-static seed=3 moved to GPU
# (run_gpu_remaining.sh) after the 4090 became idle.
run python3 stage13_cln025_discover.py --cpu --nt 12 --seed 3 \
  --methods last --tag-prefix discover_s3 \
  --init-ns 10 --budget-ns 82 --n-seeds 6 --short-ps 1000 --max-rounds 12
echo "[$(date '+%F %T')] remaining Random/static seed=3 moved to GPU (run_gpu_remaining.sh)"

echo "[$(date '+%F %T')] CPU fill exit"
