#!/usr/bin/env bash
# Four methods only: Random, LAST, Least-counts, MOAS-static.
# Default: one seed (seed=0). Repeat with SEED=1 bash scripts/run_discover.sh for a replicate.
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
LOG="$ROOT/logs/discover_seed${SEED}.log"
mkdir -p "$ROOT/logs"
exec > >(tee -a "$LOG") 2>&1
echo "[$(date '+%F %T')] AdK discover start  seed=$SEED  methods=random,last,density,moas  budget=200 ns"
python3 stage_adk_discover.py --gpu --nt "$NT" --seed "$SEED" --tag-prefix "$PREFIX" \
  --methods random last density moas \
  --init-ns 20 --budget-ns 200 --n-seeds 6 --short-ps 2000 --max-rounds 15
echo "[$(date '+%F %T')] AdK discover exit"
