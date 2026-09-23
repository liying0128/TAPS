#!/usr/bin/env bash
# kNN-AS only, MBP protocol (20 ns init + 82×6×2 ns = 1 μs).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONUNBUFFERED=1
export GMX_MAXBACKUP=-1
unset CUDA_VISIBLE_DEVICES OMP_NUM_THREADS GOMP_CPU_AFFINITY
NT="${NT:-16}"
SEED="${SEED:-0}"
PREFIX="mbp"
[[ "$SEED" != 0 ]] && PREFIX="mbp_s${SEED}"
LOG="$ROOT/logs/knn_seed${SEED}.log"
mkdir -p "$ROOT/logs"
exec > >(tee -a "$LOG") 2>&1
echo "[$(date '+%F %T')] MBP kNN-AS start  seed=$SEED  budget=1000 ns  nt=$NT"
python3 stage_mbp_discover.py --gpu --nt "$NT" --seed "$SEED" --tag-prefix "$PREFIX" \
  --methods knn --init-ns 20 --budget-ns 1000 --n-seeds 6 --short-ps 2000 --max-rounds 82
echo "[$(date '+%F %T')] MBP kNN-AS exit"
