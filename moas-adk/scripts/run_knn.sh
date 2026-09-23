#!/usr/bin/env bash
# kNN-AS only, AdK protocol (20 ns init + 15×6×2 ns = 200 ns).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONUNBUFFERED=1
export GMX_MAXBACKUP=-1
unset CUDA_VISIBLE_DEVICES OMP_NUM_THREADS GOMP_CPU_AFFINITY
NT="${NT:-16}"
SEED="${SEED:-0}"
PREFIX="adk"
[[ "$SEED" != 0 ]] && PREFIX="adk_s${SEED}"
LOG="$ROOT/logs/knn_seed${SEED}.log"
mkdir -p "$ROOT/logs"
exec > >(tee -a "$LOG") 2>&1
echo "[$(date '+%F %T')] AdK kNN-AS start  seed=$SEED  budget=200 ns  nt=$NT"
python3 stage_adk_discover.py --gpu --nt "$NT" --seed "$SEED" --tag-prefix "$PREFIX" \
  --methods knn --init-ns 20 --budget-ns 200 --n-seeds 6 --short-ps 2000 --max-rounds 15
echo "[$(date '+%F %T')] AdK kNN-AS exit"
