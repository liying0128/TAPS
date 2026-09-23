#!/usr/bin/env bash
# kNN-AS only, CLN025 protocol (10 ns init + 12×6×1 ns = 82 ns).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONUNBUFFERED=1
export GMX_MAXBACKUP=-1
unset CUDA_VISIBLE_DEVICES OMP_NUM_THREADS GOMP_CPU_AFFINITY
NT="${NT:-16}"
SEED="${SEED:-0}"
PREFIX="discover"
[[ "$SEED" != 0 ]] && PREFIX="discover_s${SEED}"
LOG="$ROOT/logs/knn_seed${SEED}.log"
mkdir -p "$ROOT/logs"
exec > >(tee -a "$LOG") 2>&1
echo "[$(date '+%F %T')] CLN kNN-AS start  seed=$SEED  budget=82 ns  nt=$NT"
python3 stage13_cln025_discover.py --gpu --nt "$NT" --seed "$SEED" --tag-prefix "$PREFIX" \
  --methods knn --init-ns 10 --budget-ns 82 --n-seeds 6 --short-ps 1000 --max-rounds 12
echo "[$(date '+%F %T')] CLN kNN-AS exit"
